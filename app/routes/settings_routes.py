"""Settings page and data clear."""
import os
import secrets

from flask import Blueprint, request, redirect, url_for, flash, render_template, send_from_directory, current_app

from app.extensions import db
from app.models import Run
from app.services import get_app_mode, get_app_setting, set_app_setting

bp = Blueprint('settings', __name__)

# Override with env TESTIMG_DOWNLOAD_PASSWORD in deployment if needed.
_TESTIMG_PASSWORD = os.environ.get('TESTIMG_DOWNLOAD_PASSWORD', 'Cpu26650078')
_TESTIMG_FILENAME = 'testIMG.png'


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
    if mode not in ('default', 'customize', 'scientific', 'haas'):
        flash('Invalid mode selected.', 'danger')
        return redirect(url_for('settings.settings'))
    set_app_setting('mode', mode)
    theme = request.form.get('theme', 'light').strip().lower()
    set_app_setting('ui_theme', theme if theme in ('light', 'dark') else 'light')
    flash('Settings saved.', 'success')
    return redirect(url_for('settings.settings'))


@bp.route('/settings/download-testimg', methods=['POST'])
def download_testimg():
    """Password-gated download for the reference assay image (public/testIMG.png)."""
    password = (request.form.get('password') or '').strip()
    expected = _TESTIMG_PASSWORD
    if len(password) != len(expected) or not secrets.compare_digest(password, expected):
        flash('Invalid password.', 'danger')
        return redirect(url_for('settings.settings'))
    root = current_app.config.get('PROJECT_ROOT', '.')
    return send_from_directory(
        os.path.join(root, 'public'),
        _TESTIMG_FILENAME,
        as_attachment=True,
        download_name=_TESTIMG_FILENAME,
    )


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
