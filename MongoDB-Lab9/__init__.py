from flask import Flask
from .routes import lab9_bp

def create_app():
    app = Flask(__name__)
    app.register_blueprint(lab9_bp)
    return app
