"""Register all blueprints. Used by create_app."""
from app.routes.pages import bp as pages_bp
from app.routes.history import bp as history_bp
from app.routes.profiles import bp as profiles_bp
from app.routes.settings_routes import bp as settings_bp
from app.routes.analysis_routes import bp as analysis_bp
from app.routes.calibration_routes import bp as calibration_bp


def register_blueprints(app):
    app.register_blueprint(pages_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(profiles_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(calibration_bp)
