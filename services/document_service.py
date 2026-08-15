import base64
import json
import os
from io import BytesIO
from docx import Document
from pypdf import PdfReader
from googletrans import LANGUAGES
from PIL import Image, ImageDraw, ImageFont
from flask import current_app
from services.gemini_service import _call, _parse_json

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


def translate_docx_preserving_format(path, output_path, translate_text_func, target_language, source_language="auto"):
    document = Document(path)

    def translate_runs(paragraphs):
        for paragraph in paragraphs:
            for run in paragraph.runs:
                original = run.text
                if not original or not original.strip():
                    continue
                translated = translate_text_func(original, target_language, source_language).get("translation", "")
                if translated:
                    run.text = translated

    translate_runs(document.paragraphs)
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                translate_runs(cell.paragraphs)
                for nested_table in cell.tables:
                    for nested_row in nested_table.rows:
                        for nested_cell in nested_row.cells:
                            translate_runs(nested_cell.paragraphs)
    for section in document.sections:
        translate_runs(section.header.paragraphs)
        translate_runs(section.footer.paragraphs)
    document.save(output_path)


def _visual_prompt(target_language, source_language="auto"):
    source = "Detect the source language automatically." if source_language == "auto" else f"The source language is {LANGUAGES.get(source_language, source_language)}."
    return (
        "Read every visible human-readable text region in this image. "
        f"{source} Translate every region to {target_language}. "
        "Return ONLY JSON: {\"detected_language_name\":string,\"detected_language_code\":string,\"regions\":[{\"text\":string,\"translation\":string,\"x\":number,\"y\":number,\"width\":number,\"height\":number}]}. "
        "Coordinates must be normalized from 0 to 1000 relative to the image width and height. "
        "Do not omit visible text regions."
    )


def _analyze_visual(path, mime_type, target_language, source_language):
    result = _parse_json(_call({
        "contents": [{"parts": [
            {"text": _visual_prompt(target_language, source_language)},
            {"inlineData": {"mimeType": mime_type, "data": encode_file(path)}}
        ]}]
    }))
    return result


def _font(size):
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, max(10, size))
    return ImageFont.load_default()


def _render_translated_image(image, analysis):
    image = image.convert("RGB")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    regions = analysis.get("regions", [])
    for region in regions:
        translation = str(region.get("translation", "")).strip()
        if not translation:
            continue
        x = int(float(region.get("x", 0)) / 1000 * width)
        y = int(float(region.get("y", 0)) / 1000 * height)
        w = max(10, int(float(region.get("width", 100)) / 1000 * width))
        h = max(10, int(float(region.get("height", 40)) / 1000 * height))
        draw.rectangle((x, y, x + w, y + h), fill="white")
        size = max(12, min(64, int(h * 0.65)))
        font = _font(size)
        draw.multiline_text((x + 4, y + 2), translation, fill="black", font=font, spacing=2)
    return image


def translate_image_file(path, output_path, target_language, source_language, mime_type):
    analysis = _analyze_visual(path, mime_type, target_language, source_language)
    image = Image.open(path)
    translated = _render_translated_image(image, analysis)
    translated.save(output_path, format="PNG" if mime_type == "image/png" else "JPEG", quality=95)
    return {
        "detected_language_name": analysis.get("detected_language_name", "Unknown"),
        "detected_language_code": analysis.get("detected_language_code", ""),
        "transcription": "\n".join(str(r.get("text", "")) for r in analysis.get("regions", []) if r.get("text")),
        "translation": "\n".join(str(r.get("translation", "")) for r in analysis.get("regions", []) if r.get("translation")),
    }


def translate_pdf_file(path, output_path, target_language, source_language):
    import fitz
    source = fitz.open(path)
    output = fitz.open()
    all_transcription = []
    all_translation = []
    detected_name = "Unknown"
    detected_code = ""
    for page in source:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        image = Image.open(BytesIO(pix.tobytes("png")))
        temp = BytesIO()
        image.save(temp, format="PNG")
        temp_path = path + ".page.png"
        with open(temp_path, "wb") as handle:
            handle.write(temp.getvalue())
        try:
            analysis = _analyze_visual(temp_path, "image/png", target_language, source_language)
            translated = _render_translated_image(image, analysis)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        image_bytes = BytesIO()
        translated.save(image_bytes, format="PNG")
        page_out = output.new_page(width=page.rect.width, height=page.rect.height)
        page_out.insert_image(page_out.rect, stream=image_bytes.getvalue())
        detected_name = analysis.get("detected_language_name", detected_name)
        detected_code = analysis.get("detected_language_code", detected_code)
        all_transcription.extend(str(r.get("text", "")) for r in analysis.get("regions", []) if r.get("text"))
        all_translation.extend(str(r.get("translation", "")) for r in analysis.get("regions", []) if r.get("translation"))
    output.save(output_path)
    output.close()
    source.close()
    return {"detected_language_name": detected_name, "detected_language_code": detected_code, "transcription": "\n".join(all_transcription), "translation": "\n".join(all_translation)}
