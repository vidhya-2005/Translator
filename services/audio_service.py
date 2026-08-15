import subprocess
from pydub import AudioSegment
from gtts import gTTS


def convert_to_wav(input_path, output_path):
    audio = AudioSegment.from_file(input_path)
    audio.export(output_path, format="wav")


def target_language_code(language_name):
    from googletrans import LANGUAGES
    wanted = language_name.strip().lower()
    for code, name in LANGUAGES.items():
        if name.lower() == wanted:
            return code
    return "en"


def generate_translated_audio(text, language_name, output_path):
    if not text.strip():
        raise ValueError("No translated speech was generated.")
    code = target_language_code(language_name).split("-")[0]
    try:
        gTTS(text=text, lang=code, slow=False).save(output_path)
    except Exception as exc:
        raise ValueError(f"Could not generate translated speech: {exc}")


def merge_translated_audio_into_video(video_path, audio_path, output_path):
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise ValueError(f"FFmpeg is unavailable for video processing: {exc}")

    command = [ffmpeg, "-y", "-i", video_path, "-i", audio_path,
               "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
               "-c:a", "aac", "-b:a", "192k", "-shortest", output_path]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise ValueError(f"Could not merge translated audio into the video: {completed.stderr[-500:]}")
