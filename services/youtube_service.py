import os
import re
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig


_VIDEO_ID_PATTERN = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)


def extract_video_id(url):
    match = _VIDEO_ID_PATTERN.search(url)
    if not match:
        raise ValueError("Invalid YouTube URL. Please provide a valid YouTube video link.")
    return match.group(1)


def _proxy_urls():
    http_proxy = os.environ.get("YOUTUBE_HTTP_PROXY")
    https_proxy = os.environ.get("YOUTUBE_HTTPS_PROXY") or http_proxy
    if not http_proxy and not https_proxy:
        return None
    return http_proxy, https_proxy or http_proxy


def get_youtube_transcript(url, source_language="auto"):
    video_id = extract_video_id(url)
    proxy_urls = _proxy_urls()

    if proxy_urls:
        http_url, https_url = proxy_urls
        api = YouTubeTranscriptApi(
            proxy_config=GenericProxyConfig(
                http_url=http_url,
                https_url=https_url,
            )
        )
    else:
        api = YouTubeTranscriptApi()

    try:
        transcripts = api.list(video_id)
    except Exception as exc:
        raise ValueError(
            "YouTube transcript access is blocked from this server. "
            "Configure YOUTUBE_HTTP_PROXY/YOUTUBE_HTTPS_PROXY with a rotating residential proxy, "
            "or upload the audio/video file directly."
        ) from exc

    selected = None
    if source_language != "auto":
        try:
            selected = transcripts.find_transcript([source_language])
        except Exception:
            selected = None

    if selected is None:
        try:
            selected = next(iter(transcripts))
        except StopIteration as exc:
            raise ValueError("No YouTube transcript or captions are available for this video.") from exc

    try:
        fetched = selected.fetch()
    except Exception as exc:
        raise ValueError(
            "YouTube transcript access is blocked from this server. "
            "Configure a rotating residential proxy or upload the audio/video file directly."
        ) from exc

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
    proxy_urls = _proxy_urls()

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

    if proxy_urls:
        options["proxy"] = proxy_urls[1]

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as exc:
        message = str(exc)
        if "Sign in to confirm" in message or "Failed to extract any player response" in message:
            raise ValueError(
                "YouTube blocked server-side extraction. Configure a rotating residential proxy, "
                "or upload the audio/video file directly."
            ) from exc
        raise ValueError(f"YouTube download failed: {message}") from exc

    generated = base + ".wav"
    if not os.path.exists(generated):
        raise FileNotFoundError("YouTube audio could not be converted to WAV.")

    return generated
