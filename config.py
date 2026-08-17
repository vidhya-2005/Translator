import os


class Config:
    # Keep the secret in Render's environment; never hard-code it.
    API_KEY = os.environ.get("GEMINI_API_KEY")
    # Gemini 3.6 Flash is the current stable multimodal model used by the app.
    # Deliberately do not allow an old Render GEMINI_MODEL environment variable
    # to silently switch the application back to a retired model.
    GEMINI_MODEL = "gemini-3.6-flash"
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    GEMINI_TIMEOUT = 120
