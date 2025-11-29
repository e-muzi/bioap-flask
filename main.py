from flask import Flask, redirect, url_for, session, render_template_string, render_template, request, flash,jsonify
from flask_session import Session
from flask_bootstrap import Bootstrap5
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import json
import uuid
from PIL import Image
import numpy as np
import base64
app = Flask(__name__)

bootstrap = Bootstrap5(app)
app.secret_key = os.urandom(24)  # For session encryption
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = '/tmp/flask_session'
app.jinja_env.auto_reload = True
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SESSION_COOKIE_NAME'] = "my_session"
Session(app)
os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)

os.makedirs(app.instance_path, exist_ok=True)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.instance_path, 'bioap.sqlite')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

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
    if mode not in ('default', 'customize'):
        mode = 'default'
    return mode

def get_active_profile():
    prof = CalibrationProfile.query.filter_by(is_active=True).first()
    if not prof:
        prof = CalibrationProfile.query.first()
    return prof

def validate_calibration_points(points):
    """
    points: list of dicts with keys 'concentration' (float), 'rgb_sum' (int)
    Enforce: at least 2 points; unique concentrations; strict monotonic rgb_sum vs concentration (decreasing).
    """
    if len(points) < 2:
        return False, "At least 2 points are required."
    concentrations = [p["concentration"] for p in points]
    if len(set(concentrations)) != len(concentrations):
        return False, "Duplicate concentrations are not allowed."
    pts = sorted(points, key=lambda p: p["concentration"])
    diffs = []
    for a, b in zip(pts, pts[1:]):
        diffs.append(b["rgb_sum"] - a["rgb_sum"])
    if not all(d < 0 for d in diffs):
        return False, "RGB totals must strictly decrease as concentration increases."
    return True, ""


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


class Run(db.Model):
    __tablename__ = 'run'
    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.Integer, db.ForeignKey('calibration_profile.id'), nullable=False)
    mode = db.Column(db.String(20), nullable=False)  # 'default' | 'customize'
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
    run = db.relationship('Run', backref=db.backref('results', lazy=True, cascade="all, delete-orphan"))


class AppSetting(db.Model):
    __tablename__ = 'app_setting'
    key = db.Column(db.String(100), primary_key=True)
    value_json = db.Column(db.Text, nullable=False, default='{}')

def ensure_upload_dir():
    now = datetime.utcnow()
    subdir = now.strftime("%Y%m")
    full = os.path.join('static', 'uploads', subdir)
    os.makedirs(full, exist_ok=True)
    return full, subdir

def compute_background_offsets(image: Image.Image, point_xy=None, patch_size=9, black_threshold=5):
    """Return per-channel mean of a corner patch; if 'black', return (0,0,0)."""
    img = image.convert('RGB')
    width, height = img.size
    half = patch_size // 2
    if point_xy is None:
        cx, cy = half, half  # top-left corner patch center
    else:
        cx, cy = int(point_xy[0]), int(point_xy[1])
    left = max(0, cx - half)
    top = max(0, cy - half)
    right = min(width, cx + half + 1)
    bottom = min(height, cy + half + 1)
    patch = img.crop((left, top, right, bottom))
    arr = np.asarray(patch, dtype=np.float32)
    mean_vals = arr.reshape(-1, 3).mean(axis=0)
    if (mean_vals <= black_threshold).all():
        return np.array([0.0, 0.0, 0.0], dtype=np.float32), False
    return mean_vals, True

def sample_five_pixel_total(image: Image.Image, x: int, y: int, bg_offsets=None):
    """Sample center + 4-neighbors; subtract bg per channel if provided; return rounded int total."""
    img = image.convert('RGB')
    width, height = img.size
    coords = [(x, y), (x+1, y), (x-1, y), (x, y+1), (x, y-1)]
    pixels = []
    for px, py in coords:
        if 0 <= px < width and 0 <= py < height:
            r, g, b = img.getpixel((px, py))
            if bg_offsets is not None:
                r = max(0.0, float(r) - float(bg_offsets[0]))
                g = max(0.0, float(g) - float(bg_offsets[1]))
                b = max(0.0, float(b) - float(bg_offsets[2]))
            pixels.append((r, g, b))
    if not pixels:
        return 0
    arr = np.array(pixels, dtype=np.float32)
    mean_rgb = arr.mean(axis=0)
    return int(round(float(mean_rgb.sum())))

def interpolate_concentration(points, rgb_sum_value):
    """points: list of {'concentration': float, 'rgb_sum': int}."""
    if not points:
        return 0.0
    pts = sorted(points, key=lambda p: p["rgb_sum"], reverse=True)
    if rgb_sum_value >= pts[0]["rgb_sum"]:
        return float(pts[0]["concentration"])
    if rgb_sum_value <= pts[-1]["rgb_sum"]:
        return float(pts[-1]["concentration"])
    for a, b in zip(pts, pts[1:]):
        if b["rgb_sum"] <= rgb_sum_value <= a["rgb_sum"]:
            denom = (a["rgb_sum"] - b["rgb_sum"])
            if denom == 0:
                return float(b["concentration"])
            t = (rgb_sum_value - b["rgb_sum"]) / denom
            return float(b["concentration"] + t * (a["concentration"] - b["concentration"]))
    return float(pts[-1]["concentration"])

def classify_concentration(bands_dict, conc_value):
    """bands_dict: {'low':{'min':..,'max':..}, 'medium':..., 'high':...}"""
    if not bands_dict:
        return 'Out of range'
    c = float(conc_value)
    low = bands_dict.get('low')
    med = bands_dict.get('medium')
    high = bands_dict.get('high')
    if low and (low.get('min') is not None) and (low.get('max') is not None):
        if low['min'] <= c < low['max']:
            return 'Low'
    if med and (med.get('min') is not None) and (med.get('max') is not None):
        if med['min'] <= c < med['max']:
            return 'Medium'
    if high and (high.get('min') is not None) and (high.get('max') is not None):
        if high['min'] <= c <= high['max']:
            return 'High'
    return 'Out of range'

def get_active_pesticides(profile_id):
    q = Pesticide.query.filter_by(profile_id=profile_id, active=True).order_by(Pesticide.order_index.asc()).all()
    return q


def seed_defaults():
    """Seed the Default profile, pesticides, calibration points, and default thresholds."""
    default_profile = CalibrationProfile.query.filter_by(name='Default').first()
    if not default_profile:
        default_profile = CalibrationProfile(name='Default', is_active=True)
        db.session.add(default_profile)
        db.session.commit()
    else:
        if not CalibrationProfile.query.filter_by(is_active=True).first():
            default_profile.is_active = True
            db.session.commit()

    existing_pesticides = Pesticide.query.filter_by(profile_id=default_profile.id).count()
    if existing_pesticides > 0:
        return

    default_curves = {
        "acephate": {
            "display_name": "Acephate",
            "points": [
                {"concentration": 0.0, "rgb_sum": 359},
                {"concentration": 0.3, "rgb_sum": 337},
                {"concentration": 1.0, "rgb_sum": 311},
            ],
            "thresholds": {"low": (0.01, 0.10), "medium": (0.10, 0.50), "high": (0.50, 1.00)},
        },
        "glyphosate": {
            "display_name": "Glyphosate",
            "points": [
                {"concentration": 0.0, "rgb_sum": 381},
                {"concentration": 0.3, "rgb_sum": 367},
                {"concentration": 1.0, "rgb_sum": 348},
            ],
            "thresholds": {"low": (0.10, 0.30), "medium": (0.30, 0.70), "high": (0.70, 1.00)},
        },
        "malathion": {
            "display_name": "Malathion",
            "points": [
                {"concentration": 0.0, "rgb_sum": 273},
                {"concentration": 0.3, "rgb_sum": 209},
                {"concentration": 1.0, "rgb_sum": 183},
            ],
            "thresholds": {"low": (0.10, 0.40), "medium": (0.40, 0.80), "high": (0.80, 1.00)},
        },
        "chlorpyrifos": {
            "display_name": "Chlorpyrifos",
            "points": [
                {"concentration": 0.0, "rgb_sum": 179},
                {"concentration": 0.3, "rgb_sum": 164},
                {"concentration": 1.0, "rgb_sum": 147},
            ],
            "thresholds": {"low": (0.01, 0.05), "medium": (0.05, 0.10), "high": (0.10, 1.00)},
        },
        "acetamiprid": {
            "display_name": "Acetamiprid",
            "points": [
                {"concentration": 0.0, "rgb_sum": 358},
                {"concentration": 0.3, "rgb_sum": 343},
                {"concentration": 1.0, "rgb_sum": 333},
            ],
            "thresholds": {"low": (0.01, 0.10), "medium": (0.10, 0.50), "high": (0.50, 1.00)},
        },
    }

    for idx, (key, conf) in enumerate(default_curves.items()):
        pest = Pesticide(
            profile_id=default_profile.id,
            key=key,
            display_name=conf["display_name"],
            order_index=idx,
            active=True
        )
        db.session.add(pest)
        db.session.flush()
        for sidx, pt in enumerate(conf["points"]):
            db.session.add(CalibrationPoint(
                pesticide_id=pest.id,
                seq_index=sidx,
                concentration=float(pt["concentration"]),
                rgb_sum=int(pt["rgb_sum"])
            ))
        for band, (min_v, max_v) in conf["thresholds"].items():
            db.session.add(ThresholdBand(
                pesticide_id=pest.id,
                band=band,
                min_value=float(min_v),
                max_value=float(max_v)
            ))
    db.session.commit()
@app.route('/')
def index():
    """Renders the main dashboard/index page."""
    # Sample data for the dashboard
    dashboard_data = {
        'active_analyses': 2,
        'recent_alerts': 0
    }
    return render_template('index.html', title="Dashboard", data=dashboard_data)

@app.route('/history')
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
    return render_template('history.html', title="Analysis History", history=items, q=q)

@app.route('/history/<int:run_id>')
def history_detail(run_id: int):
    """Show run detail."""
    run = Run.query.get_or_404(run_id)
    results = []
    for rr in run.results:
        results.append({
            "pesticide_key": rr.pesticide_key,
            "x": rr.pixel_x,
            "y": rr.pixel_y,
            "rgb_sum": rr.rgb_sum,
            "concentration": round(rr.concentration, 2),
            "level": rr.level
        })
    return render_template('history_detail.html', title=run.name, run=run, results=results)

@app.route('/history/<int:run_id>/rename', methods=['POST'])
def history_rename(run_id: int):
    new_name = request.form.get('name', '').strip()
    if not new_name:
        flash('Name cannot be empty.', 'warning')
        return redirect(url_for('history_detail', run_id=run_id))
    run = Run.query.get_or_404(run_id)
    run.name = new_name
    db.session.commit()
    flash('Run renamed.', 'success')
    return redirect(url_for('history_detail', run_id=run_id))

@app.route('/history/<int:run_id>/delete', methods=['POST'])
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
    return redirect(url_for('history'))

@app.route('/history/<int:run_id>/export')
def history_export(run_id: int):
    run = Run.query.get_or_404(run_id)
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
            "results": [{
                "pesticide_key": rr.pesticide_key,
                "pixel": {"x": rr.pixel_x, "y": rr.pixel_y},
                "rgb_sum": rr.rgb_sum,
                "concentration": float(rr.concentration),
                "level": rr.level
            } for rr in run.results]
        }
    }
    return jsonify(payload)

@app.route('/profiles/create', methods=['POST'])
def profiles_create():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Profile name required.', 'warning')
        return redirect(url_for('calibration'))
    if CalibrationProfile.query.filter_by(name=name).first():
        flash('Profile name already exists.', 'danger')
        return redirect(url_for('calibration'))
    prof = CalibrationProfile(name=name, is_active=False)
    db.session.add(prof)
    db.session.commit()
    flash('Profile created.', 'success')
    return redirect(url_for('calibration'))

@app.route('/profiles/activate/<int:profile_id>', methods=['POST'])
def profiles_activate(profile_id: int):
    prof = CalibrationProfile.query.get_or_404(profile_id)
    for p in CalibrationProfile.query.all():
        p.is_active = (p.id == prof.id)
    db.session.commit()
    flash(f'Activated profile: {prof.name}', 'success')
    return redirect(url_for('calibration'))

@app.route('/profiles/clone/<int:profile_id>', methods=['POST'])
def profiles_clone(profile_id: int):
    src = CalibrationProfile.query.get_or_404(profile_id)
    new_name = request.form.get('name', '').strip() or f"{src.name} Copy"
    if CalibrationProfile.query.filter_by(name=new_name).first():
        flash('Target profile name already exists.', 'danger')
        return redirect(url_for('calibration'))
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
    return redirect(url_for('calibration'))

@app.route('/profiles/delete/<int:profile_id>', methods=['POST'])
def profiles_delete(profile_id: int):
    prof = CalibrationProfile.query.get_or_404(profile_id)
    if prof.name.lower() == 'default':
        flash('Cannot delete Default profile.', 'danger')
        return redirect(url_for('calibration'))
    if prof.is_active:
        flash('Deactivate profile before deleting.', 'danger')
        return redirect(url_for('calibration'))
    db.session.delete(prof)
    db.session.commit()
    flash('Profile deleted.', 'success')
    return redirect(url_for('calibration'))

@app.route('/profiles/<int:profile_id>/export')
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

@app.route('/profiles/import', methods=['POST'])
def profiles_import():
    file = request.files.get('file')
    if not file:
        flash('Please choose a profile JSON file.', 'warning')
        return redirect(url_for('calibration'))
    try:
        data = json.loads(file.read().decode('utf-8'))
        prof_name = data.get('profile', {}).get('name') or f"Imported {datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        if CalibrationProfile.query.filter_by(name=prof_name).first():
            flash('A profile with this name already exists.', 'danger')
            return redirect(url_for('calibration'))
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
    except Exception as e:
        db.session.rollback()
        flash('Failed to import profile JSON.', 'danger')
    return redirect(url_for('calibration'))

@app.route('/settings')
def settings():
    """Renders the settings page."""
    app_settings = {
        'mode': get_app_mode(),
        'theme': get_app_setting('ui_theme', 'light')
    }
    return render_template('settings.html', title="Settings", settings=app_settings)

@app.route('/settings', methods=['POST'])
def settings_save():
    """Saves mode and theme settings."""
    mode = request.form.get('mode', 'default').strip().lower()
    if mode not in ('default', 'customize'):
        flash('Invalid mode selected.', 'danger')
        return redirect(url_for('settings'))
    set_app_setting('mode', mode)
    theme = request.form.get('theme', 'light').strip().lower()
    set_app_setting('ui_theme', theme if theme in ('light', 'dark') else 'light')
    flash('Settings saved.', 'success')
    return redirect(url_for('settings'))

@app.route('/data/clear', methods=['POST'])
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
    return redirect(url_for('settings'))

@app.route('/analysis')
def analysis():
    """Renders the analysis page."""
    return render_template('analysis.html', title="Analysis")

@app.route('/analysis', methods=['POST'])
def analysis_run():
    """Handle image upload and compute results with auto-placed points."""
    # Legacy direct compute path kept for compatibility; new flow uses /analysis/preview then /analysis/compute
    profile = get_active_profile()
    if not profile:
        flash('No active profile found.', 'danger')
        return redirect(url_for('analysis'))
    file = request.files.get('image')
    captured_data = request.form.get('captured_data', '').strip()
    if not file and not captured_data:
        flash('Please select or capture an image.', 'warning')
        return redirect(url_for('analysis'))
    # Save image (upload or captured)
    upload_dir, subdir = ensure_upload_dir()
    if file:
        ext = os.path.splitext(file.filename or '')[1].lower()
        if ext not in ('.jpg', '.jpeg', '.png'):
            ext = '.jpg'
        filename = f"{uuid.uuid4().hex}{ext}"
        full_path = os.path.join(upload_dir, filename)
        file.save(full_path)
    else:
        # Handle base64 data URL
        try:
            header, b64 = captured_data.split(',', 1)
            binary = base64.b64decode(b64)
            filename = f"{uuid.uuid4().hex}.png"
            full_path = os.path.join(upload_dir, filename)
            with open(full_path, 'wb') as f:
                f.write(binary)
        except Exception:
            flash('Failed to read captured image.', 'danger')
            return redirect(url_for('analysis'))
    img = Image.open(full_path).convert('RGB')
    width, height = img.size
    # Auto-pick points along horizontal midline
    pests = get_active_pesticides(profile.id)
    n = max(1, min(10, len(pests)))
    y = height // 2
    xs = [int(round((i+1) * (width / (n + 1)))) for i in range(n)]
    # Background normalization (optional)
    use_norm = (request.form.get('normalize') == 'on')
    bg_offsets = None
    norm_used_flag = False
    bg_point = (0, 0)
    if use_norm:
        bg_offsets, norm_used_flag = compute_background_offsets(img)
        if not norm_used_flag:
            bg_offsets = None
    # Compute results
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
            "x": x,
            "y": y,
            "rgb_sum": total,
            "concentration": round(conc, 2),
            "level": level
        })
    # Persist run
    run = Run(
        profile_id=profile.id,
        mode=get_app_mode(),
        name=f"Run {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}",
        image_path=os.path.join('static', 'uploads', subdir, filename),
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
            pixel_x=r["x"],
            pixel_y=r["y"],
            rgb_sum=r["rgb_sum"],
            concentration=float(r["concentration"]),
            level=r["level"]
        ))
    db.session.commit()
    return render_template('analysis.html', title="Analysis", image_path=run.image_path, results=results, width=width, height=height, points=points)

@app.route('/analysis/preview', methods=['POST'])
def analysis_preview():
    """Upload/capture image and return preview with draggable points (no compute yet)."""
    profile = get_active_profile()
    if not profile:
        flash('No active profile found.', 'danger')
        return redirect(url_for('analysis'))
    file = request.files.get('image')
    captured_data = request.form.get('captured_data', '').strip()
    if not file and not captured_data:
        flash('Please select or capture an image.', 'warning')
        return redirect(url_for('analysis'))
    upload_dir, subdir = ensure_upload_dir()
    if file:
        ext = os.path.splitext(file.filename or '')[1].lower()
        if ext not in ('.jpg', '.jpeg', '.png'):
            ext = '.jpg'
        filename = f"{uuid.uuid4().hex}{ext}"
        full_path = os.path.join(upload_dir, filename)
        file.save(full_path)
    else:
        try:
            header, b64 = captured_data.split(',', 1)
            binary = base64.b64decode(b64)
            filename = f"{uuid.uuid4().hex}.png"
            full_path = os.path.join(upload_dir, filename)
            with open(full_path, 'wb') as f:
                f.write(binary)
        except Exception:
            flash('Failed to read captured image.', 'danger')
            return redirect(url_for('analysis'))
    img = Image.open(full_path).convert('RGB')
    width, height = img.size
    pests = get_active_pesticides(profile.id)
    n = max(1, min(10, len(pests)))
    y = height // 2
    xs = [int(round((i+1) * (width / (n + 1)))) for i in range(n)]
    points = [{"x": xs[i], "y": y, "name": pests[i].display_name} for i in range(n)]
    return render_template(
        'analysis.html',
        title="Analysis",
        image_path=os.path.join('static', 'uploads', subdir, filename),
        width=width,
        height=height,
        points=points,
        results=None
    )

@app.route('/analysis/compute', methods=['POST'])
def analysis_compute():
    """Compute from provided points and image path; persist run and show results."""
    profile = get_active_profile()
    if not profile:
        flash('No active profile found.', 'danger')
        return redirect(url_for('analysis'))
    image_path = request.form.get('image_path', '').strip().lstrip('/')
    points_json = request.form.get('points_json', '').strip()
    if not image_path or not points_json:
        flash('Missing image or points.', 'danger')
        return redirect(url_for('analysis'))
    try:
        points = json.loads(points_json)
    except Exception:
        flash('Invalid points data.', 'danger')
        return redirect(url_for('analysis'))
    full_path = image_path
    if not os.path.exists(full_path):
        # try relative to project root
        full_path = os.path.join('.', image_path)
    if not os.path.exists(full_path):
        flash('Image file not found.', 'danger')
        return redirect(url_for('analysis'))
    img = Image.open(full_path).convert('RGB')
    width, height = img.size
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
    # Sort points left-to-right to map to pesticide order
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
            "x": x,
            "y": y,
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
            pixel_x=r["x"],
            pixel_y=r["y"],
            rgb_sum=r["rgb_sum"],
            concentration=float(r["concentration"]),
            level=r["level"]
        ))
    db.session.commit()
    return render_template('analysis.html', title="Analysis", image_path=image_path, results=results, width=width, height=height, points=[{"x": r["x"], "y": r["y"]} for r in results])

@app.route('/calibration')
def calibration():
    """Renders the calibration page."""
    profile = get_active_profile()
    pesticides = []
    all_profiles = CalibrationProfile.query.order_by(CalibrationProfile.created_at.asc()).all()
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
    return render_template('calibration.html', title="Calibration", profile=profile, pesticides=pesticides, is_customize=is_customize, all_profiles=all_profiles)

@app.route('/calibration/save', methods=['POST'])
def calibration_save():
    """Save edited calibration points for current active profile."""
    profile = get_active_profile()
    if not profile:
        flash("No active profile found.", "danger")
        return redirect(url_for('calibration'))
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
            return redirect(url_for('calibration'))
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
    # Save thresholds if in customize mode
    if get_app_mode() == 'customize':
        for key, val in request.form.items():
            if not key.startswith('thresh-'):
                continue
            try:
                _, band, bound, pest_id = key.split('-')  # thresh-low-min-<id>
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
    return redirect(url_for('calibration'))

@app.route('/about')
def about():
    """Renders the about page."""
    return render_template('about.html', title="About")


    
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        seed_defaults()
    app.run(port=3000, debug=False)
    # development
    #app.run(port=3001, debug=False)