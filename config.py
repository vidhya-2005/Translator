import os


class Config:
    API_KEY = os.environ.get("GEMINI_API_KEY")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    GEMINI_TIMEOUT = 60
