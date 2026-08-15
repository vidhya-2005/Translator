import base64
import os
import requests
import fitz

IMAGE_MODEL = "gemini-3.1-flash-image"


def _image_request(image_bytes, mime_type, target_language, api_key):
    prompt = (
        f"Translate all human-readable text in this image into {target_language}. "
        "Preserve the original image as closely as possible: keep the same composition, "
        "background, images, colors, objects, spacing, and overall layout. Change only the text. "
        "Do not add explanations or new content."
    )
    response = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        json={
            "model": IMAGE_MODEL,
            "input": [
                {"type": "image", "mime_type": mime_type, "data": base64.b64encode(image_bytes).decode("utf-8")},
                {"type": "text", "text": prompt},
            ],
            "response_format": {"type": "image", "image_size": "1K"},
        },
        timeout=180,
    )
    if response.status_code not in (200, 201):
        try:
            message = response.json().get("error", {}).get("message", response.text)
        except ValueError:
            message = response.text
        raise ValueError(f"Gemini visual translation error: {message}")
    data = response.json()
    image = data.get("output_image")
    encoded = image.get("data") if image else None
    if not encoded:
        for step in data.get("steps", []):
            for item in step.get("content", []):
                if item.get("type") == "image" and item.get("data"):
                    encoded = item["data"]
                    break
            if encoded:
                break
    if not encoded:
        raise ValueError("Gemini returned no translated image.")
    return base64.b64decode(encoded)


def translate_image(input_path, output_path, target_language, api_key):
    with open(input_path, "rb") as f:
        data = f.read()
    mime = "image/png" if input_path.lower().endswith(".png") else "image/jpeg"
    translated = _image_request(data, mime, target_language, api_key)
    with open(output_path, "wb") as f:
        f.write(translated)


def translate_pdf(input_path, output_path, target_language, api_key):
    source = fitz.open(input_path)
    output = fitz.open()
    try:
        for page in source:
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            translated = _image_request(pix.tobytes("png"), "image/png", target_language, api_key)
            page_image = fitz.Pixmap(translated)
            new_page = output.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(new_page.rect, pixmap=page_image)
        output.save(output_path)
    finally:
        output.close()
        source.close()
