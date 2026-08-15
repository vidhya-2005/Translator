import os
import uuid
from flask import Blueprint, jsonify, request
from services.gemini_service import translate_text, translate_document, process_audio, translate_youtube
from services.audio_service import convert_to_wav
from services.document_service import get_file_type, extract_docx_text
from utils.validation import validate_source_target

translation_bp = Blueprint("translation", __name__)


def _error_response(exc):
    return jsonify(error=str(exc) or "An unexpected error occurred."), 500


@translation_bp.post("/translate-text")
def text_translation():
    try:
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
        source = data.get("source_language", "auto")
        target = data.get("target_language_name", "English")
        if not text:
            return jsonify(error="No text provided for translation"), 400
        validate_source_target(source, target)
        return jsonify(translate_text(text, target, source))
    except Exception as exc:
        return _error_response(exc)


@translation_bp.post("/translate")
def file_translation():
    try:
        if "file" not in request.files:
            return jsonify(error="No file part in the request"), 400

        file = request.files["file"]
        if not file.filename:
            return jsonify(error="No file selected"), 400

        source = request.form.get("source_language", "auto")
        target = request.form.get("target_language_name", "English")
        validate_source_target(source, target)

        mime_type, extension = get_file_type(file.filename)
        audio_video = file.mimetype.startswith(("audio/", "video/"))

        if not mime_type and not audio_video:
            return jsonify(error="Unsupported file. Use PNG, JPG/JPEG, PDF, DOCX, audio or video."), 400

        token = str(uuid.uuid4())
        os.makedirs("tmp", exist_ok=True)
        safe_extension = extension or os.path.splitext(file.filename)[1].lower()
        input_path = os.path.join("tmp", f"{token}{safe_extension}")
        wav_path = os.path.join("tmp", f"{token}.wav")
        file.save(input_path)

        try:
            if audio_video:
                convert_to_wav(input_path, wav_path)
                return jsonify(process_audio(wav_path, target, source))

            if extension == ".docx":
                text = extract_docx_text(input_path)
                if not text:
                    return jsonify(error="No readable text found in the Word document."), 400
                return jsonify(translate_text(text, target, source))

            if extension == ".doc":
                return jsonify(error="Legacy .doc files are not supported. Please save the file as .docx and upload again."), 400

            return jsonify(translate_document(input_path, mime_type, target, source))
        finally:
            for path in (input_path, wav_path):
                if os.path.exists(path):
                    os.remove(path)
    except Exception as exc:
        return _error_response(exc)


@translation_bp.post("/translate-youtube")
def youtube_translation():
    try:
        data = request.get_json(silent=True) or {}
        url = (data.get("url") or "").strip()
        source = data.get("source_language", "auto")
        target = data.get("target_language_name", "English")

        if not url:
            return jsonify(error="No YouTube URL provided"), 400
        validate_source_target(source, target)

        # Gemini receives the public YouTube URL directly. The Render server
        # does not download the video and therefore does not need YouTube access.
        return jsonify(translate_youtube(url, target, source))
    except Exception as exc:
        return _error_response(exc)
