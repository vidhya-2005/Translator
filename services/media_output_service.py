import base64
import subprocess
import uuid
import wave

import imageio_ffmpeg
import requests

TTS_MODEL = "gemini-3.1-flash-tts-preview"


def _ffmpeg():
    return imageio_ffmpeg.get_ffmpeg_exe()


def _run(args):
    completed = subprocess.run([_ffmpeg(), *args], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if completed.returncode != 0:
        raise ValueError(completed.stderr.decode("utf-8", errors="ignore")[-1500:])


def convert_to_wav(input_path, output_path):
    _run(["-y", "-i", input_path, "-vn", "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", output_path])


def generate_tts(text, api_key, output_path, language_name="English"):
    if not text.strip():
        raise ValueError("There is no translated text to generate audio from.")
    prompt = (
        f"Speak the following text naturally and clearly in {language_name}. "
        "Do not translate, summarize, or change the words. Use correct pronunciation "
        "for the requested language.\n\n" + text
    )
    response = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
            "Api-Revision": "2026-05-20",
        },
        json={
            "model": TTS_MODEL,
            "input": prompt,
            "response_format": {"type": "audio"},
            "generation_config": {
                "speech_config": [
                    {"voice": "Kore", "language": _language_code(language_name)}
                ]
            },
        },
        timeout=180,
    )
    if response.status_code not in (200, 201):
        try:
            message = response.json().get("error", {}).get("message", response.text)
        except ValueError:
            message = response.text
        raise ValueError(f"Gemini TTS error ({response.status_code}): {message}")
    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError("Gemini TTS returned a non-JSON response.") from exc

    audio = data.get("output_audio")
    encoded = audio.get("data") if audio else None
    if not encoded:
        for step in data.get("steps", []):
            for item in step.get("content", []):
                if item.get("type") == "audio" and item.get("data"):
                    encoded = item["data"]
                    break
            if encoded:
                break
    if not encoded:
        raise ValueError("Gemini TTS returned no audio data.")

    raw = base64.b64decode(encoded)
    with wave.open(output_path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(raw)


def _language_code(language_name):
    codes = {
        "English": "en-US",
        "Tamil": "ta-IN",
        "Hindi": "hi-IN",
        "Telugu": "te-IN",
        "Kannada": "kn-IN",
        "Malayalam": "ml-IN",
        "Bengali": "bn-IN",
        "Marathi": "mr-IN",
        "Gujarati": "gu-IN",
        "Punjabi": "pa-IN",
        "Urdu": "ur-IN",
        "Spanish": "es-ES",
        "French": "fr-FR",
        "German": "de-DE",
        "Italian": "it-IT",
        "Portuguese": "pt-BR",
        "Japanese": "ja-JP",
        "Korean": "ko-KR",
        "Chinese": "zh-CN",
        "Arabic": "ar-SA",
    }
    return codes.get(language_name, "en-US")


def video_with_translated_audio(video_path, translated_audio_path, output_path):
    # Keep the complete original video duration. If translated speech is
    # shorter, apad fills the audio track until the video ends.
    _run([
        "-y", "-i", video_path, "-i", translated_audio_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac",
        "-af", "apad", "-shortest", output_path,
    ])


def audio_as_mp3(wav_path, output_path):
    _run(["-y", "-i", wav_path, "-codec:a", "libmp3lame", "-q:a", "2", output_path])


def output_token():
    return uuid.uuid4().hex
