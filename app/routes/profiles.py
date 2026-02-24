"""Profile CRUD, activate, clone, setup, case edit, export, import."""
import json
from datetime import datetime

from flask import Blueprint, request, redirect, url_for, flash, render_template, jsonify

from app.extensions import db
from app.models import CalibrationProfile, Pesticide, CalibrationPoint, ThresholdBand
from app.services import get_active_profile, validate_calibration_points

bp = Blueprint('profiles', __name__, url_prefix='/profiles')


@bp.route('/create', methods=['POST'])
def profiles_create():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Profile name required.', 'warning')
        return redirect(url_for('calibration.calibration'))
    if CalibrationProfile.query.filter_by(name=name).first():
        flash('Profile name already exists.', 'danger')
        return redirect(url_for('calibration.calibration'))
    prof = CalibrationProfile(name=name, is_active=False)
    db.session.add(prof)
    db.session.commit()
    flash('Profile created. Set number of cases and concentrations below.', 'success')
    return redirect(url_for('profiles.profile_setup', profile_id=prof.id))


@bp.route('/activate/<int:profile_id>', methods=['POST'])
def profiles_activate(profile_id: int):
    prof = CalibrationProfile.query.get_or_404(profile_id)
    for p in CalibrationProfile.query.all():
        p.is_active = (p.id == prof.id)
    db.session.commit()
    flash(f'Activated profile: {prof.name}', 'success')
    return redirect(url_for('calibration.calibration'))


@bp.route('/clone/<int:profile_id>', methods=['POST'])
def profiles_clone(profile_id: int):
    src = CalibrationProfile.query.get_or_404(profile_id)
    new_name = request.form.get('name', '').strip() or f"{src.name} Copy"
    if CalibrationProfile.query.filter_by(name=new_name).first():
        flash('Target profile name already exists.', 'danger')
        return redirect(url_for('calibration.calibration'))
    dst = CalibrationProfile(name=new_name, is_active=False)
    db.session.add(dst)
    db.session.flush()
    for pest in Pesticide.query.filter_by(profile_id=src.id).all():
        new_p = Pesticide(profile_id=dst.id, key=pest.key, display_name=pest.display_name, order_index=pest.order_index, active=pest.active)
        db.session.add(new_p)
        db.session.flush()
        for cp in pest.calibration_points:
            db.session.add(CalibrationPoint(pesticide_id=new_p.id, seq_index=cp.seq_index, concentration=cp.concentration, rgb_sum=cp.rgb_sum))
        for tb in pest.threshold_bands:
            db.session.add(ThresholdBand(pesticide_id=new_p.id, band=tb.band, min_value=tb.min_value, max_value=tb.max_value))
    db.session.commit()
    flash(f'Cloned profile to: {new_name}', 'success')
    return redirect(url_for('calibration.calibration'))


@bp.route('/delete/<int:profile_id>', methods=['POST'])
def profiles_delete(profile_id: int):
    prof = CalibrationProfile.query.get_or_404(profile_id)
    if prof.name.lower() == 'default':
        flash('Cannot delete Default profile.', 'danger')
        return redirect(url_for('calibration.calibration'))
    if prof.is_active:
        flash('Deactivate profile before deleting.', 'danger')
        return redirect(url_for('calibration.calibration'))
    db.session.delete(prof)
    db.session.commit()
    flash('Profile deleted.', 'success')
    return redirect(url_for('calibration.calibration'))


@bp.route('/<int:profile_id>/setup', methods=['GET', 'POST'])
def profile_setup(profile_id: int):
    """Set number of cases and concentrations for a new profile (or empty profile)."""
    prof = CalibrationProfile.query.get_or_404(profile_id)
    existing_count = Pesticide.query.filter_by(profile_id=prof.id).count()
    if request.method == 'GET':
        return render_template(
            'calibration_setup.html',
            title="Profile setup",
            profile=prof,
            all_profiles=CalibrationProfile.query.order_by(CalibrationProfile.created_at.asc()).all(),
            existing_cases=existing_count,
        )
    try:
        num_cases = int(request.form.get('num_cases', 0))
        num_concentrations = int(request.form.get('num_concentrations', 0))
    except (TypeError, ValueError):
        num_cases = num_concentrations = 0
    if num_cases < 1 or num_concentrations < 2:
        flash('Number of cases must be at least 1; number of concentrations at least 2.', 'danger')
        return redirect(url_for('profiles.profile_setup', profile_id=prof.id))
    if existing_count > 0:
        flash('Profile already has cases. Delete them first if you want to reconfigure.', 'warning')
        return redirect(url_for('calibration.calibration'))
    for i in range(num_cases):
        key = f'case_{i + 1}'
        display_name = f'Case {i + 1}'
        pest = Pesticide(
            profile_id=prof.id,
            key=key,
            display_name=display_name,
            order_index=i,
            active=True,
        )
        db.session.add(pest)
        db.session.flush()
        for j in range(num_concentrations):
            conc = j / max(1, num_concentrations - 1)
            rgb = 400 - j * (300 // max(1, num_concentrations - 1))
            db.session.add(CalibrationPoint(
                pesticide_id=pest.id,
                seq_index=j,
                concentration=round(conc, 4),
                rgb_sum=max(100, rgb),
            ))
    db.session.commit()
    flash(f'Created {num_cases} case(s) with {num_concentrations} concentration point(s) each.', 'success')
    return redirect(url_for('calibration.calibration'))


@bp.route('/<int:profile_id>/cases/<int:pesticide_id>/edit', methods=['GET', 'POST'])
def calibration_case_edit(profile_id: int, pesticide_id: int):
    """Edit a single case (pesticide) and its calibration dataset."""
    prof = CalibrationProfile.query.get_or_404(profile_id)
    pest = Pesticide.query.filter_by(id=pesticide_id, profile_id=prof.id).first_or_404()
    if request.method == 'GET':
        pts = sorted(pest.calibration_points, key=lambda cp: cp.seq_index)
        return render_template(
            'calibration_case_edit.html',
            title="Edit case",
            profile=prof,
            case=pest,
            points=[{"concentration": cp.concentration, "rgb_sum": cp.rgb_sum, "id": cp.id} for cp in pts],
        )
    display_name = request.form.get('display_name', '').strip() or pest.display_name
    key = request.form.get('key', '').strip().lower().replace(' ', '_') or pest.key
    if not key:
        key = pest.key
    if Pesticide.query.filter_by(profile_id=prof.id).filter(Pesticide.id != pest.id).filter_by(key=key).first():
        flash(f'Key "{key}" is already used by another case in this profile.', 'danger')
        return redirect(url_for('profiles.calibration_case_edit', profile_id=prof.id, pesticide_id=pest.id))
    pest.display_name = display_name
    pest.key = key
    grouped = {}
    for k, v in request.form.items():
        if k.startswith('concentration-'):
            try:
                row = int(k.split('-')[1])
                grouped.setdefault(row, {})['concentration'] = float(v)
            except (IndexError, ValueError):
                continue
        elif k.startswith('rgb-'):
            try:
                row = int(k.split('-')[1])
                grouped.setdefault(row, {})['rgb_sum'] = int(v)
            except (IndexError, ValueError):
                continue
    row_list = [grouped[idx] for idx in sorted(grouped.keys()) if 'concentration' in grouped[idx] and 'rgb_sum' in grouped[idx]]
    ok, msg = validate_calibration_points(row_list)
    if not ok:
        flash(msg, 'danger')
        return redirect(url_for('profiles.calibration_case_edit', profile_id=prof.id, pesticide_id=pest.id))
    CalibrationPoint.query.filter_by(pesticide_id=pest.id).delete()
    for seq_idx, row in enumerate(row_list):
        db.session.add(CalibrationPoint(
            pesticide_id=pest.id,
            seq_index=seq_idx,
            concentration=float(row['concentration']),
            rgb_sum=int(row['rgb_sum']),
        ))
    db.session.commit()
    flash('Case and calibration data saved.', 'success')
    return redirect(url_for('calibration.calibration'))


@bp.route('/<int:profile_id>/export')
def profiles_export(profile_id: int):
    prof = CalibrationProfile.query.get_or_404(profile_id)
    payload = {
        "version": 1,
        "profile": {
            "name": prof.name,
            "pesticides": []
        }
    }
    for p in Pesticide.query.filter_by(profile_id=prof.id).order_by(Pesticide.order_index.asc()).all():
        payload["profile"]["pesticides"].append({
            "key": p.key,
            "display_name": p.display_name,
            "order_index": p.order_index,
            "active": p.active,
            "points": [{"concentration": cp.concentration, "rgb_sum": cp.rgb_sum} for cp in sorted(p.calibration_points, key=lambda c: c.seq_index)],
            "thresholds": {tb.band: {"min": tb.min_value, "max": tb.max_value} for tb in p.threshold_bands}
        })
    return jsonify(payload)


@bp.route('/import', methods=['POST'])
def profiles_import():
    file = request.files.get('file')
    if not file:
        flash('Please choose a profile JSON file.', 'warning')
        return redirect(url_for('calibration.calibration'))
    try:
        data = json.loads(file.read().decode('utf-8'))
        prof_name = data.get('profile', {}).get('name') or f"Imported {datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        if CalibrationProfile.query.filter_by(name=prof_name).first():
            flash('A profile with this name already exists.', 'danger')
            return redirect(url_for('calibration.calibration'))
        prof = CalibrationProfile(name=prof_name, is_active=False)
        db.session.add(prof)
        db.session.flush()
        for pest in data.get('profile', {}).get('pesticides', []):
            new_p = Pesticide(profile_id=prof.id, key=pest.get('key'), display_name=pest.get('display_name', pest.get('key')), order_index=int(pest.get('order_index', 0)), active=bool(pest.get('active', True)))
            db.session.add(new_p)
            db.session.flush()
            pts = pest.get('points', [])
            for idx, pt in enumerate(pts):
                db.session.add(CalibrationPoint(pesticide_id=new_p.id, seq_index=idx, concentration=float(pt['concentration']), rgb_sum=int(pt['rgb_sum'])))
            thr = pest.get('thresholds', {})
            for band in ['low', 'medium', 'high']:
                if band in thr:
                    db.session.add(ThresholdBand(pesticide_id=new_p.id, band=band, min_value=float(thr[band]['min']), max_value=float(thr[band]['max'])))
        db.session.commit()
        flash(f'Imported profile: {prof_name}', 'success')
    except Exception:
        db.session.rollback()
        flash('Failed to import profile JSON.', 'danger')
    return redirect(url_for('calibration.calibration'))
