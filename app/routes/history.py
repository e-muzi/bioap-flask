"""History list, detail, rename, delete, export, import-to-calibration."""
import json
import os

from flask import Blueprint, request, redirect, url_for, flash, render_template, jsonify
from PIL import Image

from app.extensions import db
from app.models import Run, Pesticide, CalibrationProfile, CalibrationPoint

bp = Blueprint('history', __name__, url_prefix='/history')


@bp.route('')
def history():
    """List analysis runs with optional search."""
    q = request.args.get('q', '').strip()
    query = Run.query.order_by(Run.created_at.desc())
    if q:
        query = query.filter(Run.name.contains(q))
    runs = query.all()
    items = []
    for r in runs:
        items.append({
            "id": r.id,
            "name": r.name,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M"),
            "mode": r.mode,
            "profile": r.profile.name if r.profile else "",
            "image_path": r.image_path
        })
    return render_template('history.html', title="History", history=items, q=q)


@bp.route('/<int:run_id>')
def history_detail(run_id: int):
    """Show run detail."""
    run = Run.query.get_or_404(run_id)
    results = []
    for rr in run.results:
        item = {
            "pesticide_key": rr.pesticide_key,
            "x": rr.pixel_x,
            "y": rr.pixel_y,
            "rgb_sum": rr.rgb_sum,
            "concentration": round(rr.concentration, 2),
            "level": rr.level
        }
        if rr.scientific_data:
            try:
                item["scientific_data"] = json.loads(rr.scientific_data)
            except Exception:
                item["scientific_data"] = None
        else:
            item["scientific_data"] = None
        results.append(item)
    scientific_mode = (run.mode == 'scientific')
    img_width = img_height = None
    if scientific_mode and results and run.image_path:
        try:
            path = run.image_path if os.path.isabs(run.image_path) else os.path.join('.', run.image_path)
            if os.path.exists(path):
                with Image.open(path) as im:
                    img_width, img_height = im.size
        except Exception:
            pass
    return render_template('history_detail.html', title=run.name, run=run, results=results, scientific_mode=scientific_mode, img_width=img_width, img_height=img_height)


@bp.route('/<int:run_id>/rename', methods=['POST'])
def history_rename(run_id: int):
    new_name = request.form.get('name', '').strip()
    if not new_name:
        flash('Name cannot be empty.', 'warning')
        return redirect(url_for('history.history_detail', run_id=run_id))
    run = Run.query.get_or_404(run_id)
    run.name = new_name
    db.session.commit()
    flash('Run renamed.', 'success')
    return redirect(url_for('history.history_detail', run_id=run_id))


@bp.route('/<int:run_id>/delete', methods=['POST'])
def history_delete(run_id: int):
    run = Run.query.get_or_404(run_id)
    try:
        if run.image_path and os.path.exists(run.image_path):
            os.remove(run.image_path)
    except Exception:
        pass
    db.session.delete(run)
    db.session.commit()
    flash('Run deleted.', 'success')
    return redirect(url_for('history.history'))


@bp.route('/<int:run_id>/export')
def history_export(run_id: int):
    run = Run.query.get_or_404(run_id)
    export_results = []
    for rr in run.results:
        r = {
            "pesticide_key": rr.pesticide_key,
            "pixel": {"x": rr.pixel_x, "y": rr.pixel_y},
            "rgb_sum": rr.rgb_sum,
            "concentration": float(rr.concentration),
            "level": rr.level
        }
        if rr.scientific_data:
            try:
                r["scientific_data"] = json.loads(rr.scientific_data)
            except Exception:
                pass
        export_results.append(r)
    payload = {
        "version": 1,
        "run": {
            "id": run.id,
            "name": run.name,
            "created_at": run.created_at.isoformat(),
            "mode": run.mode,
            "profile": run.profile.name if run.profile else None,
            "image_path": run.image_path,
            "normalization": {
                "used": run.used_normalization,
                "background_point": {"x": run.background_point_x, "y": run.background_point_y}
            },
            "sampling_scheme": run.sampling_scheme,
            "results": export_results
        }
    }
    return jsonify(payload)


@bp.route('/<int:run_id>/import-to-calibration', methods=['GET', 'POST'])
def import_to_calibration(run_id: int):
    """Import run's RGB totals into a calibration profile."""
    run = Run.query.get_or_404(run_id)
    results = []
    if run.mode == 'scientific':
        for rr in run.results:
            name = rr.pesticide_key.replace('point_', 'Point ') if rr.pesticide_key.startswith('point_') else rr.pesticide_key
            results.append({
                "index": len(results),
                "pesticide_key": rr.pesticide_key,
                "pesticide_name": name,
                "rgb_sum": rr.rgb_sum,
            })
    else:
        key_to_name = {}
        if run.profile_id:
            for p in Pesticide.query.filter_by(profile_id=run.profile_id).all():
                key_to_name[p.key] = p.display_name
        for rr in run.results:
            results.append({
                "index": len(results),
                "pesticide_key": rr.pesticide_key,
                "pesticide_name": key_to_name.get(rr.pesticide_key, rr.pesticide_key),
                "rgb_sum": rr.rgb_sum,
            })
    if not results:
        flash('This run has no results to import.', 'warning')
        return redirect(url_for('history.history_detail', run_id=run_id))
    all_profiles = CalibrationProfile.query.order_by(CalibrationProfile.created_at.asc()).all()
    profile_pesticides = {}
    for prof in all_profiles:
        profile_pesticides[prof.id] = [
            {"id": p.id, "key": p.key, "display_name": p.display_name}
            for p in Pesticide.query.filter_by(profile_id=prof.id).order_by(Pesticide.order_index.asc()).all()
        ]
    if request.method == 'POST':
        profile_id = request.form.get('profile_id', type=int)
        if not profile_id or not any(p.id == profile_id for p in all_profiles):
            flash('Please select a valid profile.', 'danger')
            return render_template('import_to_calibration.html', title="Import to calibration", run=run, results=results, all_profiles=all_profiles, profile_pesticides=profile_pesticides)
        added = 0
        for res in results:
            idx = res["index"]
            target_pesticide_id = request.form.get(f'target_pesticide_id-{idx}', type=int)
            concentration = request.form.get(f'concentration-{idx}', type=float)
            if target_pesticide_id is None or concentration is None:
                continue
            pest = Pesticide.query.filter_by(id=target_pesticide_id, profile_id=profile_id).first()
            if not pest:
                continue
            rgb_sum = res["rgb_sum"]
            max_seq = db.session.query(db.func.max(CalibrationPoint.seq_index)).filter_by(pesticide_id=pest.id).scalar()
            next_seq = (max_seq or 0) + 1
            db.session.add(CalibrationPoint(
                pesticide_id=pest.id,
                seq_index=next_seq,
                concentration=float(concentration),
                rgb_sum=int(rgb_sum),
            ))
            added += 1
        if added:
            db.session.commit()
            flash(f'Imported {added} point(s) into calibration. Review and save on the Calibration page.', 'success')
        else:
            flash('No valid entries to import. Select a profile and target case with concentration for each row.', 'warning')
        return redirect(url_for('calibration.calibration'))
    return render_template('import_to_calibration.html', title="Import to calibration", run=run, results=results, all_profiles=all_profiles, profile_pesticides=profile_pesticides)
