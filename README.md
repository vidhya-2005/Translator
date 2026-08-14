# AI Universal Translator

A Flask-based AI translation application that supports:

- Text translation
- Audio/video file translation
- Microphone recording
- YouTube audio translation
- Automatic language detection
- Text-to-speech playback

## Architecture

The project separates:

- `routes/` - HTTP/API endpoints
- `services/` - Gemini, audio and YouTube business logic
- `templates/` - HTML
- `static/css/` - styling
- `static/js/` - frontend behavior
- `utils/` - validation
- `config.py` - configuration

## Run locally

```bash
python -m venv venv
venv\\Scripts\\activate
pip install -r requirements.txt
```

Set `GEMINI_API_KEY` in the environment, then:

```bash
python app.py
```

For production:

```bash
gunicorn app:app
```

## Render deployment

Build command:

```text
pip install -r requirements.txt
```

Start command:

```text
gunicorn app:app
```

Add `GEMINI_API_KEY` as a Render environment variable.

FFmpeg must be available for audio/video conversion and YouTube extraction.
