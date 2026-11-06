import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    # Desenvolvimento: python wsgi.py  (em produção o Render usa o gunicorn)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=True)
