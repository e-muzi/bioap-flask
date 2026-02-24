"""Seed default calibration profile and pesticides."""
from app.extensions import db
from app.models import CalibrationProfile, Pesticide, CalibrationPoint, ThresholdBand


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


def ensure_scientific_data_column():
    """Add scientific_data column to run_result if missing (for existing DBs)."""
    from sqlalchemy import text
    try:
        db.session.execute(text("ALTER TABLE run_result ADD COLUMN scientific_data TEXT"))
        db.session.commit()
    except Exception:
        db.session.rollback()
