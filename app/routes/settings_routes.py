"""Settings page and data clear."""
import os

from flask import Blueprint, request, redirect, url_for, flash, render_template

from app.extensions import db
from app.models import Run
from app.services import get_app_mode, get_app_setting, set_app_setting

bp = Blueprint('settings', __name__)


@bp.route('/settings')
def settings():
    """Renders the settings page."""
    app_settings = {
        'mode': get_app_mode(),
        'theme': get_app_setting('ui_theme', 'light')
    }
    return render_template('settings.html', title="Settings", settings=app_settings)


@bp.route('/settings', methods=['POST'])
def settings_save():
    """Saves mode and theme settings."""
    mode = request.form.get('mode', 'default').strip().lower()
    if mode not in ('default', 'customize', 'scientific'):
        flash('Invalid mode selected.', 'danger')
        return redirect(url_for('settings.settings'))
    set_app_setting('mode', mode)
    theme = request.form.get('theme', 'light').strip().lower()
    set_app_setting('ui_theme', theme if theme in ('light', 'dark') else 'light')
    flash('Settings saved.', 'success')
    return redirect(url_for('settings.settings'))


@bp.route('/data/clear', methods=['POST'])
def data_clear():
    """Clear analysis runs (and images)."""
    runs = Run.query.all()
    deleted = 0
    for r in runs:
        try:
            if r.image_path and os.path.exists(r.image_path):
                os.remove(r.image_path)
        except Exception:
            pass
        db.session.delete(r)
        deleted += 1
    db.session.commit()
    flash(f'Cleared {deleted} runs.', 'success')
    return redirect(url_for('settings.settings'))
