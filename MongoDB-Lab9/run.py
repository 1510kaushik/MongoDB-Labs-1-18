from flask import Flask
from routes import lab9_bp

app = Flask(__name__)
app.register_blueprint(lab9_bp)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)
