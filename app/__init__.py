import os
import secrets

from dotenv import load_dotenv
from flask import Flask, abort, request, session
from flask_login import LoginManager

from .models import Usuario, db

load_dotenv()


def _url_do_banco():
    """Usa o DATABASE_URL (Neon) se existir; senão, um arquivo SQLite local."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        return "sqlite:///sic.db"
    # O Neon entrega "postgres://" ou "postgresql://"; o SQLAlchemy precisa saber que o driver é o psycopg 3
    for prefixo in ("postgres://", "postgresql://"):
        if url.startswith(prefixo):
            return "postgresql+psycopg://" + url[len(prefixo):]
    return url


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.config["SQLALCHEMY_DATABASE_URI"] = _url_do_banco()
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}

    db.init_app(app)

    login = LoginManager(app)
    login.login_view = "rotas.entrar"
    login.login_message = "Entre para continuar."
    login.login_message_category = "info"

    @login.user_loader
    def carregar_usuario(usuario_id):
        return db.session.get(Usuario, int(usuario_id))

    # Proteção simples contra envio de formulários por outros sites (CSRF)
    def token_csrf():
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(16)
        return session["csrf"]

    @app.before_request
    def conferir_csrf():
        if request.method == "POST" and request.form.get("csrf") != session.get("csrf"):
            abort(400, "Formulário expirado. Volte e tente de novo.")

    app.jinja_env.globals["csrf"] = token_csrf
    app.jinja_env.filters["data"] = lambda d: d.strftime("%d/%m/%Y") if d else ""
    app.jinja_env.filters["dia_mes"] = lambda d: d.strftime("%d/%m") if d else ""

    from .rotas import rotas

    app.register_blueprint(rotas)

    @app.cli.command("seed")
    def seed():
        """Apaga o banco e recria os dados de teste."""
        from .seed import popular

        popular()
        print("Banco recriado com dados de teste.")

    with app.app_context():
        db.create_all()

    return app
