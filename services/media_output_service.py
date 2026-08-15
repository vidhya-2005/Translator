import base64
import os
import subprocess
import uuid
import wave

import requests
import imageio_ffmpeg


TTS_MODEL = "gemini-3.1-flash-tts-preview"


def _ffmpeg():
    return imageio_ffmpeg.get_ffmpeg_exe()


def _run(args):
    subprocess.run([_ffmpeg(), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def generate_tts(text, api_key, output_path):
    if not text.strip():
        raise ValueError("There is no translated text to generate audio from.")
    response = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key, "Api-Revision": "2026-05-20"},
        json={
            "model": TTS_MODEL,
            "input": f"Read the following translated text naturally and clearly. Do not add or remove words.\n\n{text}",
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": "Kore"}]},
        },
        timeout=180,
    )
    if response.status_code not in (200, 201):
        try:
            message = response.json().get("error", {}).get("message", response.text)
        except ValueError:
            message = response.text
        raise ValueError(f"Gemini TTS error: {message}")
    data = response.json()
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
        raise ValueError("Gemini TTS returned no audio.")
    raw = base64.b64decode(encoded)
    # Gemini TTS returns PCM for the current REST interaction format in practice.
    with wave.open(output_path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(raw)


def video_with_translated_audio(video_path, translated_audio_path, output_path):
    _run([
        "-y", "-i", video_path, "-i", translated_audio_path,
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
        "-shortest", output_path,
    ])


def audio_as_mp3(wav_path, output_path):
    _run(["-y", "-i", wav_path, "-codec:a", "libmp3lame", "-q:a", "2", output_path])


def output_token():
    return uuid.uuid4().hex
