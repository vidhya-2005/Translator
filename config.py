import os

class Config:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    GEMINI_TIMEOUT = 60
