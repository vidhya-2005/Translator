import base64
import json
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
    """Translate Word segments in bounded batches, with a per-batch fallback."""
    if not segments:
        return []
    translated_all = []
    batch_size = 20
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
                raise ValueError(f"Word translation failed for batch {start // batch_size + 1}: {batch_error}; fallback failed: {fallback_error}") from fallback_error
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
    payload = {
        "model": model,
        "input": [
            {"type": "video", "uri": url, "mime_type": "video/mp4"},
            {"type": "text", "text": prompt},
        ],
    }
    try:
        response = requests.post(endpoint, json=payload, headers={"Content-Type": "application/json", "x-goog-api-key": key}, timeout=max(current_app.config["GEMINI_TIMEOUT"], 180))
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


def process_audio(audio_path, target_language_name, source_language="auto"):
    with open(audio_path, "rb") as audio:
        encoded = base64.b64encode(audio.read()).decode()
    if source_language == "auto":
        prompt = "Transcribe this audio and identify its language. Return ONLY JSON with keys: language_code and transcription."
    else:
        prompt = f"The audio is in {LANGUAGES.get(source_language, source_language)}. Transcribe it. Return ONLY JSON with language_code='{source_language}' and transcription."
    result = _parse_json(_call({"contents": [{"parts": [{"text": prompt}, {"inlineData": {"mimeType": "audio/wav", "data": encoded}}]}]}, {"responseMimeType": "application/json"}))
    code = result.get("language_code", "en")
    transcription = result.get("transcription", "")
    language_name = LANGUAGES.get(code, "Unknown").capitalize()
    if not transcription:
        return {"detected_language_name": language_name, "detected_language_code": code, "transcription": "(No speech detected)", "translation": ""}
    translated = _call({"contents": [{"parts": [{"text": f"Translate the following text from {language_name} to {target_language_name}: {transcription}"}]}]}).strip()
    return {"detected_language_name": language_name, "detected_language_code": code, "transcription": transcription, "translation": translated}
