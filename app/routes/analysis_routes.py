"""Analysis page, camera, upload/preview/compute."""
import base64
import json
import os
import uuid
from datetime import datetime

from flask import Blueprint, request, redirect, url_for, flash, render_template
from PIL import Image

from app.extensions import db
from app.models import Run, RunResult
from app.services import (
    get_active_profile,
    get_app_mode,
    get_active_pesticides,
    ensure_upload_dir,
    compute_background_offsets,
    sample_five_pixel_total,
    sample_five_pixel_mean_rgb,
    scientific_color_data,
    interpolate_concentration,
    classify_concentration,
)

bp = Blueprint('analysis', __name__)


@bp.route('/analysis')
def analysis():
    """Renders the analysis page."""
    return render_template('analysis.html', title="Analysis", scientific_mode=(get_app_mode() == 'scientific'))


@bp.route('/camera')
def camera():
    """Dedicated camera capture page."""
    return render_template('camera.html', title="Camera")


def _save_uploaded_image(request):
    """Save file or captured_data from request; return (full_path, image_path_for_db, subdir, filename, error_msg)."""
    file = request.files.get('image')
    captured_data = request.form.get('captured_data', '').strip()
    if not file and not captured_data:
        return None, None, None, None, None
    upload_dir, subdir = ensure_upload_dir()
    if file:
        ext = os.path.splitext(file.filename or '')[1].lower()
        if ext not in ('.jpg', '.jpeg', '.png'):
            ext = '.jpg'
        filename = f"{uuid.uuid4().hex}{ext}"
        full_path = os.path.join(upload_dir, filename)
        file.save(full_path)
        image_path = os.path.join('static', 'uploads', subdir, filename)
        return full_path, image_path, subdir, filename, None
    try:
        header, b64 = captured_data.split(',', 1)
        binary = base64.b64decode(b64)
        filename = f"{uuid.uuid4().hex}.png"
        full_path = os.path.join(upload_dir, filename)
        with open(full_path, 'wb') as f:
            f.write(binary)
    except Exception:
        return None, None, None, None, 'Failed to read captured image.'
    image_path = os.path.join('static', 'uploads', subdir, filename)
    return full_path, image_path, subdir, filename, None


@bp.route('/analysis', methods=['POST'])
def analysis_run():
    """Handle image upload and compute results with auto-placed points."""
    profile = get_active_profile()
    if not profile:
        flash('No active profile found.', 'danger')
        return redirect(url_for('analysis.analysis'))
    full_path, image_path, subdir, filename, err = _save_uploaded_image(request)
    if full_path is None:
        flash(err or 'Please select or capture an image.', 'danger' if err else 'warning')
        return redirect(url_for('analysis.analysis'))
    try:
        img = Image.open(full_path).convert('RGB')
    except Exception:
        flash('Failed to read image.', 'danger')
        return redirect(url_for('analysis.analysis'))
    width, height = img.size
    mode = get_app_mode()
    if mode == 'scientific':
        n = 5
        y = height // 2
        xs = [int(round((i+1) * (width / (n + 1)))) for i in range(n)]
        results = []
        points = []
        for i in range(n):
            x = xs[i]
            r, g, b = sample_five_pixel_mean_rgb(img, x, y)
            total = r + g + b
            data = scientific_color_data(r, g, b)
            points.append({"x": x, "y": y, "name": f"Point {i+1}"})
            results.append({
                "pesticide_key": f"point_{i+1}",
                "pesticide_name": f"Point {i+1}",
                "x": x, "y": y,
                "rgb_sum": total,
                "concentration": 0,
                "level": "—",
                "scientific_data": data
            })
        run = Run(
            profile_id=profile.id,
            mode='scientific',
            name=f"Run {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}",
            image_path=image_path,
            used_normalization=False,
            background_point_x=0,
            background_point_y=0,
            sampling_scheme='5-pixel'
        )
        db.session.add(run)
        db.session.flush()
        for r in results:
            db.session.add(RunResult(
                run_id=run.id,
                pesticide_key=r["pesticide_key"],
                pixel_x=r["x"], pixel_y=r["y"],
                rgb_sum=r["rgb_sum"],
                concentration=0.0,
                level="—",
                scientific_data=json.dumps(r["scientific_data"])
            ))
        db.session.commit()
        return render_template('analysis.html', title="Analysis", image_path=run.image_path, results=results, width=width, height=height, points=points, scientific_mode=True, run_id=run.id)
    pests = get_active_pesticides(profile.id)
    n = max(1, min(10, len(pests)))
    y = height // 2
    xs = [int(round((i+1) * (width / (n + 1)))) for i in range(n)]
    use_norm = (request.form.get('normalize') == 'on')
    bg_offsets = None
    norm_used_flag = False
    bg_point = (0, 0)
    if use_norm:
        bg_offsets, norm_used_flag = compute_background_offsets(img)
        if not norm_used_flag:
            bg_offsets = None
    results = []
    points = []
    for i, pest in enumerate(pests[:n]):
        x = xs[i]
        total = sample_five_pixel_total(img, x, y, bg_offsets)
        curve = [{"concentration": cp.concentration, "rgb_sum": cp.rgb_sum} for cp in sorted(pest.calibration_points, key=lambda c: c.seq_index)]
        conc = interpolate_concentration(curve, total)
        bands = {b.band: {"min": b.min_value, "max": b.max_value} for b in pest.threshold_bands}
        level = classify_concentration(bands, conc)
        points.append({"x": x, "y": y, "name": pest.display_name})
        results.append({
            "pesticide_key": pest.key,
            "pesticide_name": pest.display_name,
            "x": x, "y": y,
            "rgb_sum": total,
            "concentration": round(conc, 2),
            "level": level
        })
    run = Run(
        profile_id=profile.id,
        mode=mode,
        name=f"Run {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}",
        image_path=image_path,
        used_normalization=bool(norm_used_flag),
        background_point_x=bg_point[0],
        background_point_y=bg_point[1],
        sampling_scheme='5-pixel'
    )
    db.session.add(run)
    db.session.flush()
    for r in results:
        db.session.add(RunResult(
            run_id=run.id,
            pesticide_key=r["pesticide_key"],
            pixel_x=r["x"], pixel_y=r["y"],
            rgb_sum=r["rgb_sum"],
            concentration=float(r["concentration"]),
            level=r["level"]
        ))
    db.session.commit()
    return render_template('analysis.html', title="Analysis", image_path=run.image_path, results=results, width=width, height=height, points=points, run_id=run.id)


@bp.route('/analysis/preview', methods=['POST'])
def analysis_preview():
    """Upload/capture image and return preview with draggable points (no compute yet)."""
    profile = get_active_profile()
    if not profile:
        flash('No active profile found.', 'danger')
        return redirect(url_for('analysis.analysis'))
    full_path, image_path, subdir, filename, err = _save_uploaded_image(request)
    if full_path is None:
        flash(err or 'Please select or capture an image.', 'danger' if err else 'warning')
        return redirect(url_for('analysis.analysis'))
    try:
        img = Image.open(full_path).convert('RGB')
    except Exception:
        flash('Failed to read image.', 'danger')
        return redirect(url_for('analysis.analysis'))
    width, height = img.size
    scientific_mode = (get_app_mode() == 'scientific')
    if scientific_mode:
        n = 5
        y = height // 2
        xs = [int(round((i+1) * (width / (n + 1)))) for i in range(n)]
        points = [{"x": xs[i], "y": y, "name": f"Point {i+1}"} for i in range(n)]
    else:
        pests = get_active_pesticides(profile.id)
        n = max(1, min(10, len(pests)))
        y = height // 2
        xs = [int(round((i+1) * (width / (n + 1)))) for i in range(n)]
        points = [{"x": xs[i], "y": y, "name": pests[i].display_name} for i in range(n)]
    return render_template(
        'analysis.html',
        title="Analysis",
        image_path=image_path,
        width=width,
        height=height,
        points=points,
        results=None,
        scientific_mode=scientific_mode
    )


@bp.route('/analysis/compute', methods=['POST'])
def analysis_compute():
    """Compute from provided points and image path; persist run and show results."""
    profile = get_active_profile()
    if not profile:
        flash('No active profile found.', 'danger')
        return redirect(url_for('analysis.analysis'))
    image_path = request.form.get('image_path', '').strip().lstrip('/')
    points_json = request.form.get('points_json', '').strip()
    if not image_path or not points_json:
        flash('Missing image or points.', 'danger')
        return redirect(url_for('analysis.analysis'))
    try:
        points = json.loads(points_json)
    except Exception:
        flash('Invalid points data.', 'danger')
        return redirect(url_for('analysis.analysis'))
    full_path = image_path
    if not os.path.exists(full_path):
        full_path = os.path.join('.', image_path)
    if not os.path.exists(full_path):
        flash('Image file not found.', 'danger')
        return redirect(url_for('analysis.analysis'))
    img = Image.open(full_path).convert('RGB')
    width, height = img.size
    scientific_mode = (get_app_mode() == 'scientific')
    if scientific_mode:
        pts_sorted = sorted(points[:5], key=lambda p: p.get('x', 0))
        n = len(pts_sorted)
        if n == 0:
            flash('At least one point is required.', 'danger')
            return redirect(url_for('analysis.analysis'))
        results = []
        for i in range(n):
            x = int(pts_sorted[i].get('x', 0))
            y = int(pts_sorted[i].get('y', 0))
            r, g, b = sample_five_pixel_mean_rgb(img, x, y)
            total = r + g + b
            data = scientific_color_data(r, g, b)
            results.append({
                "pesticide_key": f"point_{i+1}",
                "pesticide_name": f"Point {i+1}",
                "x": x, "y": y,
                "rgb_sum": total,
                "concentration": 0,
                "level": "—",
                "scientific_data": data
            })
        run = Run(
            profile_id=profile.id,
            mode='scientific',
            name=f"Run {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}",
            image_path=image_path,
            used_normalization=False,
            background_point_x=0,
            background_point_y=0,
            sampling_scheme='5-pixel'
        )
        db.session.add(run)
        db.session.flush()
        for r in results:
            db.session.add(RunResult(
                run_id=run.id,
                pesticide_key=r["pesticide_key"],
                pixel_x=r["x"], pixel_y=r["y"],
                rgb_sum=r["rgb_sum"],
                concentration=0.0,
                level="—",
                scientific_data=json.dumps(r["scientific_data"])
            ))
        db.session.commit()
        return render_template('analysis.html', title="Analysis", image_path=image_path, results=results, width=width, height=height, points=[{"x": r["x"], "y": r["y"]} for r in results], scientific_mode=True, run_id=run.id)
    use_norm = (request.form.get('normalize') == 'on')
    bg_offsets = None
    norm_used_flag = False
    bg_point = (0, 0)
    if use_norm:
        bg_offsets, norm_used_flag = compute_background_offsets(img)
        if not norm_used_flag:
            bg_offsets = None
    pests = get_active_pesticides(profile.id)
    n = min(len(points), len(pests))
    pts_sorted = sorted(points[:n], key=lambda p: p.get('x', 0))
    results = []
    for i in range(n):
        pest = pests[i]
        x = int(pts_sorted[i].get('x', 0))
        y = int(pts_sorted[i].get('y', 0))
        total = sample_five_pixel_total(img, x, y, bg_offsets)
        curve = [{"concentration": cp.concentration, "rgb_sum": cp.rgb_sum} for cp in sorted(pest.calibration_points, key=lambda c: c.seq_index)]
        conc = interpolate_concentration(curve, total)
        bands = {b.band: {"min": b.min_value, "max": b.max_value} for b in pest.threshold_bands}
        level = classify_concentration(bands, conc)
        results.append({
            "pesticide_key": pest.key,
            "pesticide_name": pest.display_name,
            "x": x, "y": y,
            "rgb_sum": total,
            "concentration": round(conc, 2),
            "level": level
        })
    run = Run(
        profile_id=profile.id,
        mode=get_app_mode(),
        name=f"Run {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}",
        image_path=image_path,
        used_normalization=bool(norm_used_flag),
        background_point_x=bg_point[0],
        background_point_y=bg_point[1],
        sampling_scheme='5-pixel'
    )
    db.session.add(run)
    db.session.flush()
    for r in results:
        db.session.add(RunResult(
            run_id=run.id,
            pesticide_key=r["pesticide_key"],
            pixel_x=r["x"], pixel_y=r["y"],
            rgb_sum=r["rgb_sum"],
            concentration=float(r["concentration"]),
            level=r["level"]
        ))
    db.session.commit()
    return render_template('analysis.html', title="Analysis", image_path=image_path, results=results, width=width, height=height, points=[{"x": r["x"], "y": r["y"]} for r in results])
