"""
Development entry point.

For production, use a WSGI server such as gunicorn, e.g.:
    gunicorn -w 4 -b 0.0.0.0:8000 "run:app"
"""
import os
from app import create_app

app = create_app(os.environ.get("FLASK_ENV", "development"))

if __name__ == "__main__":
    debug = app.config.get("DEBUG", False)
    app.run(host="127.0.0.1", port=5000, debug=debug)
