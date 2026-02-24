"""Root, about, and static public file routes."""
import os
from flask import Blueprint, redirect, url_for, render_template, send_from_directory, current_app

bp = Blueprint('pages', __name__)


@bp.route('/')
def index():
    """Redirect root to Analysis page (Dashboard removed)."""
    return redirect(url_for('analysis.analysis'))


@bp.route('/about')
def about():
    """Renders the about page."""
    return render_template('about.html', title="About")


@bp.route('/public/<path:filename>')
def public_files(filename: str):
    """Serve assets from the project 'public' directory (e.g., logo)."""
    root = current_app.config.get('PROJECT_ROOT', '.')
    return send_from_directory(os.path.join(root, 'public'), filename)
