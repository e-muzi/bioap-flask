"""Run and RunResult models."""
from datetime import datetime

from app.extensions import db


class Run(db.Model):
    __tablename__ = 'run'
    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.Integer, db.ForeignKey('calibration_profile.id'), nullable=False)
    mode = db.Column(db.String(20), nullable=False)  # 'default' | 'customize' | 'scientific'
    name = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    image_path = db.Column(db.String(500), nullable=False)
    used_normalization = db.Column(db.Boolean, default=False, nullable=False)
    background_point_x = db.Column(db.Integer, default=0, nullable=False)
    background_point_y = db.Column(db.Integer, default=0, nullable=False)
    sampling_scheme = db.Column(db.String(50), default='5-pixel', nullable=False)
    profile = db.relationship('CalibrationProfile')


class RunResult(db.Model):
    __tablename__ = 'run_result'
    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey('run.id'), nullable=False)
    pesticide_key = db.Column(db.String(50), nullable=False)
    pixel_x = db.Column(db.Integer, nullable=False)
    pixel_y = db.Column(db.Integer, nullable=False)
    rgb_sum = db.Column(db.Integer, nullable=False)
    concentration = db.Column(db.Float, nullable=False)
    level = db.Column(db.String(20), nullable=False)  # 'Low' | 'Medium' | 'High' | 'Out of range'
    scientific_data = db.Column(db.Text, nullable=True)  # JSON: {rgb, hex, hsv, hsl} for scientific mode
    run = db.relationship('Run', backref=db.backref('results', lazy=True, cascade="all, delete-orphan"))
