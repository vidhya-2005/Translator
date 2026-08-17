from services.document_service import translate_image_file, translate_pdf_file


def translate_image(input_path, output_path, target_language, api_key, source_language="auto"):
    """Compatibility wrapper for the active image translation implementation."""
    mime_type = "image/png" if input_path.lower().endswith(".png") else "image/jpeg"
    return translate_image_file(input_path, output_path, target_language, source_language, mime_type)


def translate_pdf(input_path, output_path, target_language, api_key, source_language="auto"):
    """Compatibility wrapper for the active PDF translation implementation."""
    return translate_pdf_file(input_path, output_path, target_language, source_language)
