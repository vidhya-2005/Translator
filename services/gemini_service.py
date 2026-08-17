import base64
import json
import os
import time
import requests
from googletrans import LANGUAGES
from flask import current_app


def _url():
    key = current_app.config["API_KEY"]
    if not key:
        raise ValueError("GEMINI_API_KEY is not configured.")
    return f"https://generativelanguage.googleapis.com/v1beta/models/{current_app.config['GEMINI_MODEL']}:generateContent?key={key}"


def _call(payload, generation_config=None):
    if generation_config:
        payload = dict(payload)
        payload["generationConfig"] = generation_config
    response = requests.post(_url(), json=payload, headers={"Content-Type": "application/json"}, timeout=current_app.config["GEMINI_TIMEOUT"])
    if response.status_code != 200:
        try:
            message = response.json().get("error", {}).get("message", response.text)
        except ValueError:
            message = response.text
        raise ValueError(f"Gemini API error ({response.status_code}): {message}")
    try:
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Gemini returned an unexpected response.") from exc


def _parse_json(text):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "", 1).replace("```", "", 1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse Gemini JSON response: {exc}") from exc


def _translation_prompt(target_language_name, source_language="auto"):
    if source_language == "auto":
        return f"Detect the source language and translate the supplied content to {target_language_name}. Return ONLY JSON with keys: detected_language_name, transcription, translation."
    return f"The source language is {LANGUAGES.get(source_language, source_language)}. Translate the supplied content to {target_language_name}. Return ONLY JSON with keys: detected_language_name, transcription, translation."


def translate_text(text, target_language_name, source_language="auto"):
    return _parse_json(_call({"contents": [{"parts": [{"text": _translation_prompt(target_language_name, source_language)}, {"text": text}]}]}, {"responseMimeType": "application/json"}))


def _translate_segment_batch(segments, target_language_name, source_language):
    source = "Detect the source language automatically." if source_language == "auto" else f"The source language is {LANGUAGES.get(source_language, source_language)}."
    items = "\n".join(f"{i}: {json.dumps(text, ensure_ascii=False)}" for i, text in enumerate(segments))
    prompt = (
        "Translate each numbered text segment independently. "
        f"{source} Translate to {target_language_name}. "
        "Return ONLY a JSON array of strings in exactly the same order and count as the input. "
        "Do not merge, omit, explain, or renumber segments.\n\n" + items
    )
    result = _parse_json(_call({"contents": [{"parts": [{"text": prompt}]}]}, {"responseMimeType": "application/json"}))
    if not isinstance(result, list) or len(result) != len(segments):
        raise ValueError("Gemini returned an invalid number of translated Word segments.")
    return [str(item) for item in result]


def translate_segments(segments, target_language_name, source_language="auto"):
    if not segments:
        return []
    translated_all = []
    batch_size = 50
    for start in range(0, len(segments), batch_size):
        batch = segments[start:start + batch_size]
        try:
            translated_all.extend(_translate_segment_batch(batch, target_language_name, source_language))
        except Exception as batch_error:
            fallback = []
            try:
                for text in batch:
                    result = translate_text(text, target_language_name, source_language)
                    translated = str(result.get("translation", "")).strip()
                    if not translated:
                        raise ValueError("Gemini returned empty translated text.")
                    fallback.append(translated)
            except Exception as fallback_error:
                raise ValueError(f"Translation failed for batch {start // batch_size + 1}: {batch_error}; fallback failed: {fallback_error}") from fallback_error
            translated_all.extend(fallback)
    return translated_all


def translate_document(path, mime_type, target_language_name, source_language="auto"):
    with open(path, "rb") as file:
        encoded = base64.b64encode(file.read()).decode("utf-8")
    return _parse_json(_call({"contents": [{"parts": [{"text": _translation_prompt(target_language_name, source_language)}, {"inlineData": {"mimeType": mime_type, "data": encoded}}]}]}, {"responseMimeType": "application/json"}))


def translate_youtube(url, target_language_name, source_language="auto"):
    key = current_app.config["API_KEY"]
    if not key:
        raise ValueError("GEMINI_API_KEY is not configured.")
    model = current_app.config["GEMINI_MODEL"]
    endpoint = "https://generativelanguage.googleapis.com/v1beta/interactions"
    source_instruction = "Detect the spoken language automatically." if source_language == "auto" else f"The spoken language is {LANGUAGES.get(source_language, source_language)}."
    prompt = f"Analyze this public YouTube video. {source_instruction} Transcribe the spoken content and translate it into {target_language_name}. Do not summarize. Return ONLY valid JSON with no markdown using exactly these keys: detected_language_name, detected_language_code, transcription, translation."
    payload = {"model": model, "input": [{"type": "text", "text": prompt}, {"type": "video", "uri": url}]}
    try:
        response = requests.post(endpoint, json=payload, headers={"Content-Type": "application/json", "x-goog-api-key": key, "Api-Revision": "2026-05-20"}, timeout=max(current_app.config["GEMINI_TIMEOUT"], 180))
    except requests.RequestException as exc:
        raise ValueError(f"Gemini YouTube request failed: {exc}") from exc
    if response.status_code not in (200, 201):
        try:
            body = response.json()
            message = body.get("error", {}).get("message") or body.get("message") or response.text
        except ValueError:
            message = response.text
        raise ValueError(f"Gemini YouTube error ({response.status_code}): {message}")
    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError("Gemini returned a non-JSON YouTube response.") from exc
    output_text = data.get("output_text")
    if not output_text:
        for step in data.get("steps", []):
            for item in step.get("content", []):
                if item.get("type") == "text" and item.get("text"):
                    output_text = item["text"]
                    break
            if output_text:
                break
    if not output_text:
        raise ValueError("Gemini returned no YouTube translation output.")
    return _parse_json(output_text)


def _gemini_file_upload(path, mime_type, api_key):
    size = os.path.getsize(path)
    start = requests.post(
        "https://generativelanguage.googleapis.com/upload/v1beta/files",
        headers={
            "x-goog-api-key": api_key,
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(size),
            "X-Goog-Upload-Header-Content-Type": mime_type,
            "Content-Type": "application/json",
        },
        json={"file": {"display_name": os.path.basename(path)}},
        timeout=30,
    )
    if start.status_code not in (200, 201):
        raise ValueError(f"Gemini file upload initialization failed ({start.status_code}): {start.text}")
    upload_url = start.headers.get("x-goog-upload-url")
    if not upload_url:
        raise ValueError("Gemini did not return a file upload URL.")

    with open(path, "rb") as file:
        upload = requests.post(
            upload_url,
            headers={
                "Content-Length": str(size),
                "X-Goog-Upload-Offset": "0",
                "X-Goog-Upload-Command": "upload, finalize",
            },
            data=file,
            timeout=max(current_app.config["GEMINI_TIMEOUT"], 180),
        )
    if upload.status_code not in (200, 201):
        raise ValueError(f"Gemini file upload failed ({upload.status_code}): {upload.text}")
    try:
        file_info = upload.json().get("file", {})
    except ValueError as exc:
        raise ValueError("Gemini file upload returned an unexpected response.") from exc
    return file_info


def _wait_for_gemini_file(file_name, api_key):
    deadline = time.time() + max(current_app.config["GEMINI_TIMEOUT"], 180)
    while time.time() < deadline:
        response = requests.get(
            f"https://generativelanguage.googleapis.com/v1beta/{file_name}",
            headers={"x-goog-api-key": api_key},
            timeout=30,
        )
        if response.status_code != 200:
            raise ValueError(f"Gemini file status check failed ({response.status_code}): {response.text}")
        data = response.json()
        state = data.get("state") or data.get("file", {}).get("state")
        if state in ("ACTIVE", "active"):
            return data.get("file", data)
        if state in ("FAILED", "failed"):
            raise ValueError("Gemini failed to process the uploaded media file.")
        time.sleep(2)
    raise ValueError("Gemini media processing timed out. Please try a shorter file.")


def _delete_gemini_file(file_name, api_key):
    if not file_name:
        return
    try:
        requests.delete(
            f"https://generativelanguage.googleapis.com/v1beta/{file_name}",
            headers={"x-goog-api-key": api_key},
            timeout=20,
        )
    except requests.RequestException:
        pass


def process_media(media_path, mime_type, target_language_name, source_language="auto"):
    """Transcribe and translate uploaded audio/video without server-side extraction."""
    api_key = current_app.config["API_KEY"]
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    is_video = mime_type.startswith("video/")
    media_type = "video" if is_video else "audio"
    size = os.path.getsize(media_path)
    source_instruction = "Detect the spoken language automatically." if source_language == "auto" else f"The spoken language is {LANGUAGES.get(source_language, source_language)}."
    prompt = (
        f"{source_instruction} Transcribe ALL spoken content in this {media_type}. "
        f"Translate the complete transcription into {target_language_name}. "
        "Do not summarize, omit, or invent speech. Ignore music and non-speech sounds. "
        "Return ONLY valid JSON with exactly these keys: language_code, transcription, translation."
    )

    file_name = None
    try:
        if size < 20 * 1024 * 1024:
            with open(media_path, "rb") as media:
                encoded = base64.b64encode(media.read()).decode("utf-8")
            input_part = {"type": media_type, "data": encoded, "mime_type": mime_type}
        else:
            info = _gemini_file_upload(media_path, mime_type, api_key)
            file_name = info.get("name")
            info = _wait_for_gemini_file(file_name, api_key)
            input_part = {"type": media_type, "uri": info.get("uri"), "mime_type": mime_type}

        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/interactions",
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key, "Api-Revision": "2026-05-20"},
            json={
                "model": current_app.config["GEMINI_MODEL"],
                "input": [
                    {"type": "text", "text": prompt},
                    input_part,
                ],
            },
            timeout=max(current_app.config["GEMINI_TIMEOUT"], 180),
        )
        if response.status_code not in (200, 201):
            try:
                message = response.json().get("error", {}).get("message", response.text)
            except ValueError:
                message = response.text
            raise ValueError(f"Gemini media error ({response.status_code}): {message}")
        data = response.json()
        output_text = data.get("output_text")
        if not output_text:
            for step in data.get("steps", []):
                for item in step.get("content", []):
                    if item.get("type") == "text" and item.get("text"):
                        output_text = item["text"]
                        break
                if output_text:
                    break
        if not output_text:
            raise ValueError("Gemini returned no media translation output.")

        result = _parse_json(output_text)
        code = result.get("language_code", source_language if source_language != "auto" else "")
        language_name = LANGUAGES.get(code, "Unknown").capitalize() if code else "Auto-detected"
        transcription = str(result.get("transcription", "")).strip()
        translation = str(result.get("translation", "")).strip()
        if not transcription:
            return {"detected_language_name": language_name, "detected_language_code": code, "transcription": "(No speech detected)", "translation": ""}
        if not translation:
            raise ValueError("Gemini returned a transcription but no translated speech text.")
        return {"detected_language_name": language_name, "detected_language_code": code, "transcription": transcription, "translation": translation}
    finally:
        _delete_gemini_file(file_name, api_key)


def process_audio(audio_path, target_language_name, source_language="auto"):
    return process_media(audio_path, "audio/wav", target_language_name, source_language)
