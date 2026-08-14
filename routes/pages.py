from flask import Blueprint, render_template
from googletrans import LANGUAGES

pages_bp = Blueprint("pages", __name__)

@pages_bp.get("/")
def index():
    return render_template("index.html", languages=LANGUAGES)

@pages_bp.get("/health")
def health():
    return {"status": "ok"}
