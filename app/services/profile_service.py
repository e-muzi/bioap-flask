"""Active profile, pesticides, and calibration validation."""
from app.models import CalibrationProfile, Pesticide


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


def get_active_pesticides(profile_id):
    q = Pesticide.query.filter_by(profile_id=profile_id, active=True).order_by(Pesticide.order_index.asc()).all()
    return q
