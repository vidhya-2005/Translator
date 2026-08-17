import os
import subprocess
import uuid

import imageio_ffmpeg
from gtts import gTTS


def _ffmpeg():
    return imageio_ffmpeg.get_ffmpeg_exe()


def _run(args):
    completed = subprocess.run([_ffmpeg(), *args], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if completed.returncode != 0:
        raise ValueError(completed.stderr.decode("utf-8", errors="ignore")[-1000:])


def convert_to_wav(input_path, output_path):
    _run(["-y", "-i", input_path, "-vn", "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", output_path])


def generate_tts(text, api_key, output_path, language_name=None):
    """Generate speech server-side so playback does not depend on browser voices."""
    if not text.strip():
        raise ValueError("There is no translated text to generate audio from.")
    if not language_name:
        try:
            from flask import request
            language_name = (request.form.get("target_language_name") or "").strip()
            if not language_name:
                data = request.get_json(silent=True) or {}
                language_name = (data.get("language_name") or "").strip()
        except RuntimeError:
            language_name = ""
    language_name = language_name or "English"
    from services.audio_service import target_language_code
    code = target_language_code(language_name).split("-")[0]
    temp_mp3 = output_path + ".source.mp3"
    try:
        gTTS(text=text, lang=code, slow=False).save(temp_mp3)
        _run(["-y", "-i", temp_mp3, "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", output_path])
    except Exception as exc:
        raise ValueError(f"Could not generate translated speech: {exc}") from exc
    finally:
        if os.path.exists(temp_mp3):
            os.remove(temp_mp3)


def video_with_translated_audio(video_path, translated_audio_path, output_path):
    _run(["-y", "-i", video_path, "-i", translated_audio_path, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-shortest", output_path])


def audio_as_mp3(wav_path, output_path):
    _run(["-y", "-i", wav_path, "-codec:a", "libmp3lame", "-q:a", "2", output_path])


def output_token():
    return uuid.uuid4().hex
