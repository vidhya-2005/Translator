import os

from flask import Flask
from config import Config


def create_app():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    app = Flask(
        __name__,
        template_folder=os.path.join(project_root, "templates"),
        static_folder=os.path.join(project_root, "static"),
    )
    app.config.from_object(Config)

    from routes.pages import pages_bp
    from routes.translation import translation_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(translation_bp)

    return app
