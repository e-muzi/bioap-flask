"""Color conversion utilities for RGB, hex, HSV, HSL."""
import colorsys


def rgb_to_hex(r, g, b):
    return "#{:02x}{:02x}{:02x}".format(
        max(0, min(255, int(r))),
        max(0, min(255, int(g))),
        max(0, min(255, int(b)))
    )


def rgb_to_hsv_str(r, g, b):
    r, g, b = r/255.0, g/255.0, b/255.0
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return "{:.0f}°, {:.0f}%, {:.0f}%".format(h * 360, s * 100, v * 100)


def rgb_to_hsl_str(r, g, b):
    r, g, b = r/255.0, g/255.0, b/255.0
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return "{:.0f}°, {:.0f}%, {:.0f}%".format(h * 360, s * 100, l * 100)


def scientific_color_data(r, g, b):
    """Return dict with rgb, hex, hsv, hsl for scientific mode display."""
    return {
        "rgb": [r, g, b],
        "hex": rgb_to_hex(r, g, b),
        "hsv": rgb_to_hsv_str(r, g, b),
        "hsl": rgb_to_hsl_str(r, g, b),
    }
