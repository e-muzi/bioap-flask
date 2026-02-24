"""Calibration page and save."""
from flask import Blueprint, redirect, url_for, flash, render_template, request

from app.extensions import db
from app.models import CalibrationProfile, Pesticide, CalibrationPoint, ThresholdBand
from app.services import get_active_profile, get_app_mode, validate_calibration_points

bp = Blueprint('calibration', __name__)


@bp.route('/calibration')
def calibration():
    """Renders the calibration page."""
    profile = get_active_profile()
    pesticides = []
    all_profiles = CalibrationProfile.query.order_by(CalibrationProfile.created_at.asc()).all()
    profile_case_counts = {p.id: Pesticide.query.filter_by(profile_id=p.id).count() for p in all_profiles}
    if profile:
        q = Pesticide.query.filter_by(profile_id=profile.id, active=True).order_by(Pesticide.order_index.asc()).all()
        for p in q:
            pts = sorted(p.calibration_points, key=lambda cp: cp.seq_index)
            bands = {b.band: {"min": b.min_value, "max": b.max_value} for b in p.threshold_bands}
            pesticides.append({
                "id": p.id,
                "key": p.key,
                "display_name": p.display_name,
                "points": [{"concentration": cp.concentration, "rgb_sum": cp.rgb_sum, "seq_index": cp.seq_index, "id": cp.id} for cp in pts],
                "thresholds": bands
            })
    is_customize = (get_app_mode() == 'customize')
    return render_template('calibration.html', title="Calibration", profile=profile, pesticides=pesticides, is_customize=is_customize, all_profiles=all_profiles, profile_case_counts=profile_case_counts)


@bp.route('/calibration/save', methods=['POST'])
def calibration_save():
    """Save edited calibration points for current active profile."""
    profile = get_active_profile()
    if not profile:
        flash("No active profile found.", "danger")
        return redirect(url_for('calibration.calibration'))
    grouped = {}
    for key, val in request.form.items():
        try:
            if key.startswith('concentration-'):
                _, pest_id, row = key.split('-')
                grouped.setdefault(pest_id, {}).setdefault(int(row), {})['concentration'] = float(val)
            elif key.startswith('rgb-'):
                _, pest_id, row = key.split('-')
                grouped.setdefault(pest_id, {}).setdefault(int(row), {})['rgb_sum'] = int(val)
        except Exception:
            continue
    for pest_id, rows in grouped.items():
        row_list = [rows[idx] for idx in sorted(rows.keys()) if 'concentration' in rows[idx] and 'rgb_sum' in rows[idx]]
        ok, msg = validate_calibration_points(row_list)
        if not ok:
            flash(f"Pesticide {pest_id}: {msg}", "danger")
            return redirect(url_for('calibration.calibration'))
    for pest_id, rows in grouped.items():
        pest = Pesticide.query.filter_by(id=int(pest_id), profile_id=profile.id).first()
        if not pest:
            continue
        CalibrationPoint.query.filter_by(pesticide_id=pest.id).delete()
        for seq_idx, row in enumerate([rows[i] for i in sorted(rows.keys())]):
            db.session.add(CalibrationPoint(
                pesticide_id=pest.id,
                seq_index=seq_idx,
                concentration=float(row['concentration']),
                rgb_sum=int(row['rgb_sum'])
            ))
    if get_app_mode() == 'customize':
        for key, val in request.form.items():
            if not key.startswith('thresh-'):
                continue
            try:
                _, band, bound, pest_id = key.split('-')
                pest = Pesticide.query.filter_by(id=int(pest_id), profile_id=profile.id).first()
                if not pest:
                    continue
                tb = ThresholdBand.query.filter_by(pesticide_id=pest.id, band=band).first()
                if not tb:
                    tb = ThresholdBand(pesticide_id=pest.id, band=band, min_value=0.0, max_value=0.0)
                    db.session.add(tb)
                if bound == 'min':
                    tb.min_value = float(val)
                elif bound == 'max':
                    tb.max_value = float(val)
            except Exception:
                continue
    db.session.commit()
    flash("Calibration saved.", "success")
    return redirect(url_for('calibration.calibration'))
