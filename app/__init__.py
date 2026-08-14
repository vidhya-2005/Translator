from flask import Flask
from config import Config

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    from routes.pages import pages_bp
    from routes.translation import translation_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(translation_bp)

    return app
