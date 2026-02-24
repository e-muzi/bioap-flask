"""Concentration interpolation and classification (no Flask/db)."""


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
