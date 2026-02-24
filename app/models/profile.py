"""Calibration profile, pesticide, calibration point, and threshold band models."""
from datetime import datetime

from app.extensions import db


class CalibrationProfile(db.Model):
    __tablename__ = 'calibration_profile'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_active = db.Column(db.Boolean, default=False, nullable=False)


class Pesticide(db.Model):
    __tablename__ = 'pesticide'
    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.Integer, db.ForeignKey('calibration_profile.id'), nullable=False)
    key = db.Column(db.String(50), nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    order_index = db.Column(db.Integer, default=0, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    profile = db.relationship('CalibrationProfile', backref=db.backref('pesticides', lazy=True, cascade="all, delete-orphan"))


class CalibrationPoint(db.Model):
    __tablename__ = 'calibration_point'
    id = db.Column(db.Integer, primary_key=True)
    pesticide_id = db.Column(db.Integer, db.ForeignKey('pesticide.id'), nullable=False)
    seq_index = db.Column(db.Integer, default=0, nullable=False)
    concentration = db.Column(db.Float, nullable=False)
    rgb_sum = db.Column(db.Integer, nullable=False)
    pesticide = db.relationship('Pesticide', backref=db.backref('calibration_points', lazy=True, cascade="all, delete-orphan"))


class ThresholdBand(db.Model):
    __tablename__ = 'threshold_band'
    id = db.Column(db.Integer, primary_key=True)
    pesticide_id = db.Column(db.Integer, db.ForeignKey('pesticide.id'), nullable=False)
    band = db.Column(db.String(20), nullable=False)  # 'low' | 'medium' | 'high'
    min_value = db.Column(db.Float, nullable=False)
    max_value = db.Column(db.Float, nullable=False)
    pesticide = db.relationship('Pesticide', backref=db.backref('threshold_bands', lazy=True, cascade="all, delete-orphan"))
