import os
import uuid
from flask import Blueprint, jsonify, request, send_file, after_this_request
from services.gemini_service import translate_text, translate_document, process_audio, translate_youtube
from services.audio_service import convert_to_wav
from services.media_output_service import convert_to_wav as convert_media_to_wav, generate_tts, video_with_translated_audio, audio_as_mp3
from services.document_service import get_file_type, extract_docx_text, translate_docx_preserving_format
from services.document_service import translate_image_file as translate_image, translate_pdf_file as translate_pdf
from utils.validation import validate_source_target

translation_bp = Blueprint("translation", __name__)


def _error_response(exc):
    return jsonify(error=str(exc) or "An unexpected error occurred."), 500


def _tmp_dir():
    path = os.path.join(os.getcwd(), "tmp")
    os.makedirs(path, exist_ok=True)
    return path


def _download_path(token):
    return os.path.join(_tmp_dir(), f"download_{token}")


def _media_download_response(path, download_name, mimetype):
    token = uuid.uuid4().hex
    stored = _download_path(token)
    os.replace(path, stored)
    return {"download_url": f"/download/{token}/{download_name}", "download_name": download_name, "mimetype": mimetype}


@translation_bp.get("/download/<token>/<path:download_name>")
def download_result(token, download_name):
    path = _download_path(token)
    if not os.path.exists(path):
        return jsonify(error="This download has expired. Please translate the file again."), 404
    response = send_file(path, as_attachment=True, download_name=os.path.basename(download_name))
    @after_this_request
    def cleanup(_response):
        try:
            if os.path.exists(path): os.remove(path)
        except OSError:
            pass
        return _response
    return response


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
        audio_video = (file.mimetype or "").startswith(("audio/", "video/"))
        if not mime_type and not audio_video:
            return jsonify(error="Unsupported file. Use PNG, JPG/JPEG, PDF, DOCX, audio or video."), 400
        token = str(uuid.uuid4())
        tmp = _tmp_dir()
        input_path = os.path.join(tmp, f"{token}{extension or os.path.splitext(file.filename)[1].lower()}")
        wav_path = os.path.join(tmp, f"{token}.wav")
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


@translation_bp.post("/translate-media")
def translate_media():
    input_path = wav_path = tts_path = output_path = None
    try:
        if "file" not in request.files:
            return jsonify(error="No media file provided."), 400
        file = request.files["file"]
        if not file.filename:
            return jsonify(error="No media file selected."), 400
        source = request.form.get("source_language", "auto")
        target = request.form.get("target_language_name", "English")
        validate_source_target(source, target)
        mimetype = file.mimetype or "application/octet-stream"
        is_video, is_audio = mimetype.startswith("video/"), mimetype.startswith("audio/")
        if not (is_video or is_audio):
            return jsonify(error="This endpoint accepts audio or video files."), 400
        token = uuid.uuid4().hex
        tmp = _tmp_dir()
        ext = os.path.splitext(file.filename)[1].lower() or (".mp4" if is_video else ".wav")
        input_path = os.path.join(tmp, f"{token}{ext}")
        wav_path = os.path.join(tmp, f"{token}_source.wav")
        tts_path = os.path.join(tmp, f"{token}_translated.wav")
        output_path = os.path.join(tmp, f"{token}_output.{ 'mp4' if is_video else 'mp3' }")
        file.save(input_path)
        convert_media_to_wav(input_path, wav_path)
        result = process_audio(wav_path, target, source)
        if not result.get("translation"):
            raise ValueError("No translatable speech was detected in the uploaded media.")
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not configured.")
        generate_tts(result["translation"], api_key, tts_path, target)
        if is_video:
            video_with_translated_audio(input_path, tts_path, output_path)
            media = _media_download_response(output_path, f"{os.path.splitext(file.filename)[0]}_translated.mp4", "video/mp4")
        else:
            audio_as_mp3(tts_path, output_path)
            media = _media_download_response(output_path, f"{os.path.splitext(file.filename)[0]}_translated.mp3", "audio/mpeg")
        return jsonify({**result, **media})
    except Exception as exc:
        return _error_response(exc)
    finally:
        for path in (input_path, wav_path, tts_path, output_path):
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass


@translation_bp.post("/translate-visual")
def translate_visual():
    input_path = output_path = None
    try:
        if "file" not in request.files:
            return jsonify(error="No image or PDF provided."), 400
        file = request.files["file"]
        if not file.filename:
            return jsonify(error="No file selected."), 400
        source = request.form.get("source_language", "auto")
        target = request.form.get("target_language_name", "English")
        validate_source_target(source, target)
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".pdf"):
            return jsonify(error="Use PNG, JPG/JPEG, or PDF here."), 400
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not configured.")
        token = uuid.uuid4().hex
        tmp = _tmp_dir()
        input_path = os.path.join(tmp, f"{token}{ext}")
        output_ext = ".pdf" if ext == ".pdf" else ".png"
        output_path = os.path.join(tmp, f"{token}_translated{output_ext}")
        file.save(input_path)
        if ext == ".pdf":
            result = translate_pdf(input_path, output_path, target, source)
            name, mime = f"{os.path.splitext(file.filename)[0]}_translated.pdf", "application/pdf"
        else:
            result = translate_image(input_path, output_path, target, api_key, source)
            name, mime = f"{os.path.splitext(file.filename)[0]}_translated.png", "image/png"
        media = _media_download_response(output_path, name, mime)
        return jsonify({**result, **media})
    except Exception as exc:
        return _error_response(exc)
    finally:
        for path in (input_path, output_path):
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass


@translation_bp.post("/translate-word")
def word_translation():
    input_path = output_path = None
    try:
        if "file" not in request.files:
            return jsonify(error="No Word document provided."), 400
        file = request.files["file"]
        if not file.filename:
            return jsonify(error="No Word document selected."), 400
        if not file.filename.lower().endswith(".docx"):
            return jsonify(error="Please upload a .docx Word document. Legacy .doc files are not supported."), 400
        source = request.form.get("source_language", "auto")
        target = request.form.get("target_language_name", "English")
        validate_source_target(source, target)
        tmp = _tmp_dir()
        token = str(uuid.uuid4())
        input_path = os.path.join(tmp, f"{token}.docx")
        output_path = os.path.join(tmp, f"{token}_translated.docx")
        file.save(input_path)
        translate_docx_preserving_format(input_path, output_path, translate_text, target, source)
        @after_this_request
        def cleanup(response):
            for path in (input_path, output_path):
                try:
                    if path and os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass
            return response
        download_name = f"{os.path.splitext(os.path.basename(file.filename))[0]}_translated.docx"
        return send_file(output_path, as_attachment=True, download_name=download_name, mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    except Exception as exc:
        for path in (input_path, output_path):
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
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
        return jsonify(translate_youtube(url, target, source))
    except Exception as exc:
        return _error_response(exc)


@translation_bp.post("/tts")
def text_to_speech():
    output_path = None
    try:
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
        language_name = (data.get("language_name") or "English").strip()
        if not text:
            return jsonify(error="No text provided for speech."), 400
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not configured.")
        output_path = os.path.join(_tmp_dir(), f"{uuid.uuid4().hex}.wav")
        generate_tts(text, api_key, output_path, language_name)
        response = send_file(output_path, mimetype="audio/wav", as_attachment=False)
        @after_this_request
        def cleanup(_response):
            try:
                if os.path.exists(output_path):
                    os.remove(output_path)
            except OSError:
                pass
            return _response
        return response
    except Exception as exc:
        if output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError:
                pass
        return _error_response(exc)
