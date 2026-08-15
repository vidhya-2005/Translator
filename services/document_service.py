import base64
import json
import os
from io import BytesIO
from docx import Document
from pypdf import PdfReader
from googletrans import LANGUAGES
from PIL import Image, ImageDraw, ImageFont
from services.gemini_service import _call, _parse_json

SUPPORTED_EXTENSIONS = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".doc": None,
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

def _translate_paragraph(paragraph, translate_text_func, target_language, source_language):
    text = paragraph.text
    if not text.strip():
        return
    result = translate_text_func(text, target_language, source_language)
    translated = result.get("translation", "").strip() if isinstance(result, dict) else ""
    if not translated:
        raise ValueError("Gemini returned no translated text for a Word paragraph.")
    runs = paragraph.runs
    if not runs:
        paragraph.add_run(translated)
        return
    runs[0].text = translated
    for run in runs[1:]:
        run.text = ""

def _translate_paragraphs(paragraphs, translate_text_func, target_language, source_language):
    for paragraph in paragraphs:
        _translate_paragraph(paragraph, translate_text_func, target_language, source_language)

def translate_docx_preserving_format(path, output_path, translate_text_func, target_language, source_language="auto"):
    document = Document(path)
    _translate_paragraphs(document.paragraphs, translate_text_func, target_language, source_language)
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                _translate_paragraphs(cell.paragraphs, translate_text_func, target_language, source_language)
                for nested_table in cell.tables:
                    for nested_row in nested_table.rows:
                        for nested_cell in nested_row.cells:
                            _translate_paragraphs(nested_cell.paragraphs, translate_text_func, target_language, source_language)
    for section in document.sections:
        _translate_paragraphs(section.header.paragraphs, translate_text_func, target_language, source_language)
        _translate_paragraphs(section.footer.paragraphs, translate_text_func, target_language, source_language)
    document.save(output_path)

def _visual_prompt(target_language, source_language="auto"):
    source = "Detect the source language automatically." if source_language == "auto" else f"The source language is {LANGUAGES.get(source_language, source_language)}."
    return ("Read every visible human-readable text region in this image. " + f"{source} Translate every region to {target_language}. " + "Return ONLY JSON: {\"detected_language_name\":string,\"detected_language_code\":string,\"regions\":[{\"text\":string,\"translation\":string,\"x\":number,\"y\":number,\"width\":number,\"height\":number}]}. Coordinates must be normalized from 0 to 1000 relative to the image width and height. Do not omit visible text regions.")

def _analyze_visual(path, mime_type, target_language, source_language):
    return _parse_json(_call({"contents": [{"parts": [{"text": _visual_prompt(target_language, source_language)}, {"inlineData": {"mimeType": mime_type, "data": encode_file(path)}}]}]}))

def _font(size):
    for path in ["/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", "/usr/share/fonts/opentype/noto/NotoSans-Regular.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
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
        draw.multiline_text((x + 4, y + 2), translation, fill="black", font=_font(max(12, min(64, int(h * 0.65)))), spacing=2)
    return image

def translate_image_file(path, output_path, target_language, source_language, mime_type):
    analysis = _analyze_visual(path, mime_type, target_language, source_language)
    image = Image.open(path)
    translated = _render_translated_image(image, analysis)
    translated.save(output_path, format="PNG" if mime_type == "image/png" else "JPEG", quality=95)
    return {"detected_language_name": analysis.get("detected_language_name", "Unknown"), "detected_language_code": analysis.get("detected_language_code", ""), "transcription": "\n".join(str(r.get("text", "")) for r in analysis.get("regions", []) if r.get("text")), "translation": "\n".join(str(r.get("translation", "")) for r in analysis.get("regions", []) if r.get("translation"))}

def translate_pdf_file(path, output_path, target_language, source_language):
    import pymupdf
    source = pymupdf.open(path)
    output = pymupdf.open()
    all_transcription, all_translation = [], []
    detected_name, detected_code = "Unknown", ""
    for page in source:
        pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
        image = Image.open(BytesIO(pix.tobytes("png")))
        temp_path = path + ".page.png"
        image.save(temp_path, format="PNG")
        try:
            analysis = _analyze_visual(temp_path, "image/png", target_language, source_language)
            translated = _render_translated_image(image, analysis)
        finally:
            if os.path.exists(temp_path): os.remove(temp_path)
        image_bytes = BytesIO()
        translated.save(image_bytes, format="PNG")
        page_out = output.new_page(width=page.rect.width, height=page.rect.height)
        page_out.insert_image(page_out.rect, stream=image_bytes.getvalue())
        detected_name = analysis.get("detected_language_name", detected_name)
        detected_code = analysis.get("detected_language_code", detected_code)
        all_transcription.extend(str(r.get("text", "")) for r in analysis.get("regions", []) if r.get("text"))
        all_translation.extend(str(r.get("translation", "")) for r in analysis.get("regions", []) if r.get("translation"))
    output.save(output_path)
    output.close(); source.close()
    return {"detected_language_name": detected_name, "detected_language_code": detected_code, "transcription": "\n".join(all_transcription), "translation": "\n".join(all_translation)}
