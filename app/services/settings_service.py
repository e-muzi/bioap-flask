"""App settings get/set and mode (uses db)."""
import json

from app.extensions import db
from app.models import AppSetting


def get_app_setting(key, default=None):
    rec = AppSetting.query.filter_by(key=key).first()
    if not rec:
        return default
    try:
        return json.loads(rec.value_json)
    except Exception:
        return default


def set_app_setting(key, value):
    rec = AppSetting.query.filter_by(key=key).first()
    if not rec:
        rec = AppSetting(key=key, value_json=json.dumps(value))
        db.session.add(rec)
    else:
        rec.value_json = json.dumps(value)
    db.session.commit()


def get_app_mode():
    mode = get_app_setting('mode', 'default')
    if mode not in ('default', 'customize', 'scientific'):
        mode = 'default'
    return mode
