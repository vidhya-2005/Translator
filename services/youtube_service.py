import os
import yt_dlp


def download_youtube_audio(url, output_path):
    base = os.path.splitext(output_path)[0]

    options = {
        "format": "bestaudio/best",
        "outtmpl": base + ".%(ext)s",
        "quiet": True,
        "noplaylist": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "wav",
            "preferredquality": "192",
        }],
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as exc:
        message = str(exc)
        if "Sign in to confirm" in message or "Failed to extract any player response" in message:
            raise ValueError(
                "YouTube blocked audio extraction on the server. Please try again later or upload the audio/video file directly."
            ) from exc
        raise ValueError(f"YouTube download failed: {message}") from exc

    generated = base + ".wav"
    if not os.path.exists(generated):
        raise FileNotFoundError("YouTube audio could not be converted to WAV.")

    return generated
