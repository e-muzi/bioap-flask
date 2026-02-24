"""Application factory and package root."""
import os

from flask import Flask
from flask_session import Session
from flask_bootstrap import Bootstrap5

from app.extensions import db
from app import models  # noqa: F401 - register models with SQLAlchemy
from app.routes import register_blueprints


def create_app(config_overrides=None):
    # Templates and static live at project root (parent of app package)
    import os as _os
    _root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    app = Flask(
        __name__,
        instance_path=_os.path.join(_root, 'instance'),
        instance_relative_config=True,
        template_folder=_os.path.join(_root, 'templates'),
        static_folder=_os.path.join(_root, 'static'),
    )
    app.secret_key = os.urandom(24)
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['SESSION_FILE_DIR'] = '/tmp/flask_session'
    app.jinja_env.auto_reload = True
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.config['SESSION_COOKIE_NAME'] = "my_session"
    Session(app)
    os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)

    _os.makedirs(app.instance_path, exist_ok=True)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + _os.path.join(app.instance_path, 'bioap.sqlite')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    app.config['PROJECT_ROOT'] = _root
    if config_overrides:
        app.config.update(config_overrides)

    db.init_app(app)
    Bootstrap5(app)
    register_blueprints(app)

    return app
