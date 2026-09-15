import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    # Never hardcode debug=True — Werkzeug's debugger allows arbitrary
    # code execution from the browser if it's ever enabled outside of
    # active local development. This only matters if someone runs
    # `python wsgi.py` directly (the actual Docker/gunicorn deployment
    # never executes this block at all), but hardcoding it was still a
    # real risk if that ever happened by mistake on a real server.
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=5000, debug=debug_mode)
