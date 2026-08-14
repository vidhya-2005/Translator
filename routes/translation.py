import os
import uuid
from flask import Blueprint, jsonify, request
from services.gemini_service import translate_text, process_audio
from services.audio_service import convert_to_wav
from services.youtube_service import download_youtube_audio
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

        token = str(uuid.uuid4())
        os.makedirs("tmp", exist_ok=True)
        input_path = os.path.join("tmp", f"{token}_{file.filename}")
        wav_path = os.path.join("tmp", f"{token}.wav")

        file.save(input_path)
        try:
            convert_to_wav(input_path, wav_path)
            return jsonify(process_audio(wav_path, target, source))
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

        token = str(uuid.uuid4())
        os.makedirs("tmp", exist_ok=True)
        wav_path = os.path.join("tmp", f"{token}.wav")

        try:
            download_youtube_audio(url, wav_path)
            return jsonify(process_audio(wav_path, target, source))
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)
    except Exception as exc:
        return _error_response(exc)
