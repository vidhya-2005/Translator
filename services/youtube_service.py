import os
import re
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi


_VIDEO_ID_PATTERN = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)


def extract_video_id(url):
    match = _VIDEO_ID_PATTERN.search(url)
    if not match:
        raise ValueError("Invalid YouTube URL. Please provide a valid YouTube video link.")
    return match.group(1)


def get_youtube_transcript(url, source_language="auto"):
    video_id = extract_video_id(url)
    api = YouTubeTranscriptApi()
    transcripts = api.list(video_id)

    selected = None
    if source_language != "auto":
        try:
            selected = transcripts.find_transcript([source_language])
        except Exception:
            selected = None

    if selected is None:
        # Prefer manually created captions, then auto-generated captions.
        try:
            selected = next(iter(transcripts))
        except StopIteration as exc:
            raise ValueError("No YouTube transcript or captions are available for this video.") from exc

    fetched = selected.fetch()
    text = " ".join(snippet.text.strip() for snippet in fetched if snippet.text.strip()).strip()
    if not text:
        raise ValueError("The YouTube transcript is empty.")

    return {
        "video_id": video_id,
        "language_code": selected.language_code,
        "language_name": selected.language,
        "transcription": text,
        "is_generated": selected.is_generated,
    }


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
                "YouTube audio extraction was blocked. This video may still work if captions are available."
            ) from exc
        raise ValueError(f"YouTube download failed: {message}") from exc

    generated = base + ".wav"
    if not os.path.exists(generated):
        raise FileNotFoundError("YouTube audio could not be converted to WAV.")

    return generated
