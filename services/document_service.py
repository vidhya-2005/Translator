import base64
import os
from io import BytesIO
from docx import Document
from pypdf import PdfReader
from googletrans import LANGUAGES
from PIL import Image, ImageDraw, ImageFont
from services.gemini_service import _call, _parse_json, translate_segments

SUPPORTED_EXTENSIONS = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": None,
}


def get_file_type(filename):
    extension = os.path.splitext(filename.lower())[1]
    if extension not in SUPPORTED_EXTENSIONS:
        return None, extension
    return SUPPORTED_EXTENSIONS[extension], extension


def extract_docx_text(path):
    document = Document(path)
    parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text.strip() for cell in row.cells))
    return "\n".join(parts).strip()


def extract_pdf_text(path):
    reader = PdfReader(path)
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def encode_file(path):
    with open(path, "rb") as file:
        return base64.b64encode(file.read()).decode("utf-8")


def _paragraphs(document):
    paragraphs = list(document.paragraphs)
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                paragraphs.extend(cell.paragraphs)
                for nested in cell.tables:
                    for nested_row in nested.rows:
                        for nested_cell in nested_row.cells:
                            paragraphs.extend(nested_cell.paragraphs)
    for section in document.sections:
        paragraphs.extend(section.header.paragraphs)
        paragraphs.extend(section.footer.paragraphs)
    return paragraphs


def translate_docx_preserving_format(path, output_path, translate_text_func, target_language, source_language="auto"):
    """Translate Word runs in batches while keeping each run's formatting."""
    document = Document(path)
    candidates = []
    for paragraph in _paragraphs(document):
        for run in paragraph.runs:
            if run.text and run.text.strip():
                candidates.append((run, run.text))

    if not candidates:
        raise ValueError("No readable text found in the Word document.")

    translations = translate_segments(
        [text for _, text in candidates],
        target_language,
        source_language,
    )

    if len(translations) != len(candidates):
        raise ValueError("Word translation returned an incomplete result.")

    for (run, _), translated in zip(candidates, translations):
        run.text = translated

    document.save(output_path)


def _visual_prompt(target_language, source_language="auto"):
    source = "Detect the source language automatically." if source_language == "auto" else f"The source language is {LANGUAGES.get(source_language, source_language)}."
    return (
        "Read every visible human-readable text region in this image. "
        f"{source} Translate every region to {target_language}. "
        "Return ONLY JSON with keys detected_language_name, detected_language_code, and regions. "
        "Each region must contain text, translation, x, y, width, height. "
        "Coordinates are normalized 0-1000 relative to image width and height."
    )


def _analyze_visual(path, mime_type, target_language, source_language):
    return _parse_json(_call({"contents": [{"parts": [
        {"text": _visual_prompt(target_language, source_language)},
        {"inlineData": {"mimeType": mime_type, "data": encode_file(path)}}
    ]}]}, {"responseMimeType": "application/json"}))


def _font(size):
    for path in (
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if os.path.exists(path):
            return ImageFont.truetype(path, max(10, size))
    return ImageFont.load_default()


def _render_translated_image(image, analysis):
    image = image.convert("RGB")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    for region in analysis.get("regions", []):
        translation = str(region.get("translation", "")).strip()
        if not translation:
            continue
        x = int(float(region.get("x", 0)) / 1000 * width)
        y = int(float(region.get("y", 0)) / 1000 * height)
        w = max(10, int(float(region.get("width", 100)) / 1000 * width))
        h = max(10, int(float(region.get("height", 40)) / 1000 * height))
        draw.rectangle((x, y, x + w, y + h), fill="white")
        size = max(12, min(64, int(h * 0.65)))
        draw.multiline_text((x + 4, y + 2), translation, fill="black", font=_font(size), spacing=2)
    return image


def _result(analysis):
    regions = analysis.get("regions", [])
    return {
        "detected_language_name": analysis.get("detected_language_name", "Unknown"),
        "detected_language_code": analysis.get("detected_language_code", ""),
        "transcription": "\n".join(str(r.get("text", "")) for r in regions if r.get("text")),
        "translation": "\n".join(str(r.get("translation", "")) for r in regions if r.get("translation")),
    }


def translate_image_file(path, output_path, target_language, source_language, mime_type):
    analysis = _analyze_visual(path, mime_type, target_language, source_language)
    image = Image.open(path)
    translated = _render_translated_image(image, analysis)
    translated.save(output_path, format="PNG", optimize=True)
    return _result(analysis)


def translate_pdf_file(path, output_path, target_language, source_language):
    """Translate text-based PDFs in place, preserving the original page artwork.

    Scanned/image-only pages fall back to the existing visual translation path.
    Native PDF text is removed without touching images/vector graphics, then the
    translated text is inserted into the original text boxes.
    """
    import pymupdf

    doc = pymupdf.open(path)
    all_transcription = []
    all_translation = []
    detected_name = "Auto-detected" if source_language == "auto" else LANGUAGES.get(source_language, source_language).capitalize()
    detected_code = "" if source_language == "auto" else source_language

    try:
        for page in doc:
            text_blocks = []
            for block in page.get_text("dict", flags=11).get("blocks", []):
                if block.get("type") != 0:
                    continue
                lines = block.get("lines", [])
                text = "\n".join(
                    span.get("text", "")
                    for line in lines
                    for span in line.get("spans", [])
                    if span.get("text")
                ).strip()
                if not text:
                    continue
                first_span = next(
                    (span for line in lines for span in line.get("spans", []) if span.get("text")),
                    {},
                )
                text_blocks.append({
                    "rect": pymupdf.Rect(block["bbox"]),
                    "text": text,
                    "size": float(first_span.get("size", 11)),
                    "color": int(first_span.get("color", 0)),
                    "flags": int(first_span.get("flags", 0)),
                    "dir": tuple(lines[0].get("dir", (1, 0))) if lines else (1, 0),
                })

            if not text_blocks:
                # Scanned PDF page: preserve the page size and use the visual
                # translator only for this page.
                pix = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
                image = Image.open(BytesIO(pix.tobytes("png")))
                temp_path = f"{path}.page-{page.number}.png"
                image.save(temp_path, format="PNG")
                try:
                    analysis = _analyze_visual(temp_path, "image/png", target_language, source_language)
                finally:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                translated = _render_translated_image(image, analysis)
                image_bytes = BytesIO()
                translated.save(image_bytes, format="PNG")
                page.clean_contents()
                page.insert_image(page.rect, stream=image_bytes.getvalue())
                page_result = _result(analysis)
                detected_name = analysis.get("detected_language_name", detected_name)
                detected_code = analysis.get("detected_language_code", detected_code)
                if page_result["transcription"]:
                    all_transcription.append(page_result["transcription"])
                if page_result["translation"]:
                    all_translation.append(page_result["translation"])
                continue

            translations = translate_segments(
                [block["text"] for block in text_blocks],
                target_language,
                source_language,
            )
            if len(translations) != len(text_blocks):
                raise ValueError("PDF translation returned an incomplete result.")

            for block in text_blocks:
                rect = block["rect"]
                # Keep a tiny margin so glyph edges are removed cleanly while
                # not touching nearby images or vector artwork.
                page.add_redact_annot(rect + (-0.5, -0.5, 0.5, 0.5), fill=False, cross_out=False)
            page.apply_redactions(images=0, graphics=0)

            for block, translated in zip(text_blocks, translations):
                translated = str(translated).strip()
                if not translated:
                    continue
                color = block["color"]
                rgb = (
                    ((color >> 16) & 255) / 255,
                    ((color >> 8) & 255) / 255,
                    (color & 255) / 255,
                )
                flags = block["flags"]
                weight = "bold" if flags & (1 << 4) else "normal"
                style = "italic" if flags & (1 << 1) else "normal"
                angle = 0
                dx, dy = block["dir"]
                if abs(dx) < 0.01 and dy > 0:
                    angle = 90
                elif abs(dx) < 0.01 and dy < 0:
                    angle = 270
                elif dx < 0:
                    angle = 180

                # HTML boxes provide Unicode shaping and automatic font
                # fallback for scripts such as Tamil and Devanagari.
                html = (
                    f'<div style="font-family:sans-serif;font-size:{block["size"]:.2f}pt;'
                    f'font-weight:{weight};font-style:{style};color:rgb('
                    f'{int(rgb[0]*255)},{int(rgb[1]*255)},{int(rgb[2]*255)});">'
                    f'{_html_escape(translated).replace(chr(10), "<br>")}</div>'
                )
                rc = page.insert_htmlbox(rect, html, rotate=angle, overlay=True)
                if rc[0] < 0:
                    # If the translated text is longer than the original box,
                    # retry with a smaller size rather than silently dropping it.
                    for factor in (0.85, 0.7, 0.55):
                        html_small = html.replace(
                            f'font-size:{block["size"]:.2f}pt',
                            f'font-size:{max(6, block["size"] * factor):.2f}pt',
                        )
                        rc = page.insert_htmlbox(rect, html_small, rotate=angle, overlay=True)
                        if rc[0] >= 0:
                            break

                all_transcription.append(block["text"])
                all_translation.append(translated)

        doc.save(output_path, garbage=4, deflate=True)
    finally:
        doc.close()

    return {
        "detected_language_name": detected_name,
        "detected_language_code": detected_code,
        "transcription": "\n".join(all_transcription),
        "translation": "\n".join(all_translation),
    }


def _html_escape(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
