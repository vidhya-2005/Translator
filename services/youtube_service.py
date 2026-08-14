import os
import yt_dlp

def download_youtube_audio(url, output_path):
    base = os.path.splitext(output_path)[0]

    options = {
        "format": "bestaudio/best",
        "outtmpl": base + ".%(ext)s",
        "quiet": True,
        "noplaylist": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "wav",
            "preferredquality": "192",
        }],
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])

    generated = base + ".wav"
    if not os.path.exists(generated):
        raise FileNotFoundError("YouTube audio could not be converted to WAV.")

    return generated
