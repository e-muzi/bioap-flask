"""Image and upload directory utilities."""
import os
from datetime import datetime

from PIL import Image
import numpy as np


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


def sample_five_pixel_mean_rgb(image: Image.Image, x: int, y: int):
    """Sample center + 4-neighbors; return (r, g, b) as ints 0-255 (no background subtraction)."""
    img = image.convert('RGB')
    width, height = img.size
    coords = [(x, y), (x+1, y), (x-1, y), (x, y+1), (x, y-1)]
    pixels = []
    for px, py in coords:
        if 0 <= px < width and 0 <= py < height:
            pixels.append(img.getpixel((px, py)))
    if not pixels:
        return (0, 0, 0)
    arr = np.array(pixels, dtype=np.float32)
    mean_rgb = arr.mean(axis=0)
    return (int(round(mean_rgb[0])), int(round(mean_rgb[1])), int(round(mean_rgb[2])))
