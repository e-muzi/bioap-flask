"""App setting model."""
from app.extensions import db


class AppSetting(db.Model):
    __tablename__ = 'app_setting'
    key = db.Column(db.String(100), primary_key=True)
    value_json = db.Column(db.Text, nullable=False, default='{}')
