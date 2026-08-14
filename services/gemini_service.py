import base64
import json
import requests
from googletrans import LANGUAGES
from flask import current_app

def _url():
    key = current_app.config["GEMINI_API_KEY"]
    if not key:
        raise ValueError("GEMINI_API_KEY is not configured.")
    model = current_app.config["GEMINI_MODEL"]
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

def _call(payload):
    response = requests.post(
        _url(),
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=current_app.config["GEMINI_TIMEOUT"],
    )
    if response.status_code != 200:
        try:
            message = response.json().get("error", {}).get("message", response.text)
        except ValueError:
            message = response.text
        raise ValueError(f"Gemini API error: {message}")
    data = response.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise ValueError("Gemini returned an unexpected response.")

def _parse_json(text):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "", 1).replace("```", "", 1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse Gemini JSON response: {exc}")

def translate_text(text, target_language_name, source_language="auto"):
    if source_language == "auto":
        prompt = (
            f"Detect the language and translate the text to {target_language_name}. "
            "Return ONLY JSON with keys: detected_language_name, transcription, translation."
        )
    else:
        source_name = LANGUAGES.get(source_language, source_language)
        prompt = (
            f"The text is in {source_name}. Translate it to {target_language_name}. "
            "Return ONLY JSON with keys: detected_language_name, transcription, translation."
        )

    result = _parse_json(_call({
        "contents": [{"parts": [{"text": prompt}, {"text": text}]}]
    }))
    return result

def process_audio(audio_path, target_language_name, source_language="auto"):
    with open(audio_path, "rb") as audio:
        encoded = base64.b64encode(audio.read()).decode()

    if source_language == "auto":
        prompt = (
            "Transcribe this audio and identify its language. "
            "Return ONLY JSON with keys: language_code and transcription."
        )
    else:
        source_name = LANGUAGES.get(source_language, source_language)
        prompt = (
            f"The audio is in {source_name}. Transcribe it. "
            f"Return ONLY JSON with language_code='{source_language}' and transcription."
        )

    result = _parse_json(_call({
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inlineData": {"mimeType": "audio/wav", "data": encoded}}
            ]
        }]
    }))

    code = result.get("language_code", "en")
    transcription = result.get("transcription", "")
    language_name = LANGUAGES.get(code, "Unknown").capitalize()

    if not transcription:
        return {
            "detected_language_name": language_name,
            "detected_language_code": code,
            "transcription": "(No speech detected)",
            "translation": ""
        }

    translated = _call({
        "contents": [{
            "parts": [{
                "text": (
                    f"Translate the following text from {language_name} "
                    f"to {target_language_name}: {transcription}"
                )
            }]
        }]
    }).strip()

    return {
        "detected_language_name": language_name,
        "detected_language_code": code,
        "transcription": transcription,
        "translation": translated
    }
