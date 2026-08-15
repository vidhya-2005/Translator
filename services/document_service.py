import base64
import os
from docx import Document
from pypdf import PdfReader
from googletrans import LANGUAGES

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
    """Translate text in an existing DOCX while retaining its document structure and formatting.

    Text is replaced inside existing runs, so fonts, sizes, emphasis, tables and embedded
    images remain attached to the original document elements. Headers and footers are included.
    """
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
