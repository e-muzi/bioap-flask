### BioAP Architecture and Implementation Plan (Flask + HTML)

This document describes the full design for the PestiGuard Biosensor Analysis Platform (BioAP). It covers features, UX, data model, APIs, algorithms, validation, settings, profiles, import/export, testing, security, and delivery milestones.

## Purpose

Enable consumers to quantify pesticide residue from a captured/uploaded image of the biosensor. The software reads color intensity, compares against saved calibration curves, computes concentrations via linear interpolation, and classifies levels using configurable thresholds. It stores results, provides history, allows calibration editing, and supports multiple calibration profiles.

## Key Principles

- Inverse relationship: brighter (higher RGB total) → lower concentration.
- Analysis uses total RGB defined as R + G + B.
- Sampling uses exactly five pixels per test point: center + the four immediate 4‑neighbors (N, S, E, W).
- Background normalization: auto-pick a corner patch and detect if it is truly black; if not black, subtract background offsets per channel, clamp to ≥ 0, then compute totals.
- Default mode: fixed 5 pesticides (edit calibration points only).
- Customize mode: user can change pesticides and calibration points; maximum of 10 pesticides; user can define per‑pesticide thresholds.
- Results shown to 2 decimal places.
- Concentration bands can be Low/Medium/High or “Out of range” if outside defined bands.

## Tech Stack

- Backend: Flask (Jinja2 templating), SQLAlchemy (SQLite), Pillow (image I/O), NumPy (array math), Marshmallow (validation).
- Frontend: Server-rendered HTML templates + vanilla JS, Chart.js for calibration curves, simple responsive CSS (light/dark).
- Storage: SQLite database file under Flask instance path; user images under `static/uploads/`.

## Pages (Templates) and UX

- Analysis (`/analysis`)
  - Step 1: Upload/capture image (mobile-friendly `capture="environment"`).
  - Step 2: Preview on a canvas with N draggable sampling points; N is the number of active pesticides for the current mode/profile (Default N=5). Points are initially auto-placed horizontally at equal spacing across the image midline.
  - Background normalization controls:
    - Toggle “Use background normalization”.
    - Auto-picked background patch from an image corner is shown; user can optionally re-pick a background point.
  - Sampling scheme: fixed “5-pixel” (center + N,S,E,W).
  - Step 3: Analyze → compute RGB totals for each point, map to concentrations by interpolation, classify by thresholds; show results table. Store run by default.
  - Metadata saved per run: profile, mode, normalization on/off, background point, point coordinates, timestamp, and computed results.

- Calibration (`/calibration`)
  - Header: current Mode (Default/Customize), active Profile selector, buttons to Create/Clone/Rename/Delete profiles.
  - Pesticide list:
    - Default mode: 5 fixed pesticides; users can edit calibration points (concentration, total RGB). Cannot add/remove pesticides.
    - Customize mode: up to 10 pesticides; add/remove pesticides and calibration points; edit per-pesticide thresholds; toggle active.
  - Each pesticide card: editable table of calibration points, sparkline chart (Chart.js), validation hints (monotonicity, duplicates).
  - Actions: Save changes, Reset pesticide to defaults (available for default pesticides), Import/Export calibration profile JSON.
  - Banner: “Analysis uses saved calibration data; remember to Save after edits.”

- History (`/history`)
  - Search bar by name (and optional date range).
  - Results list with: name, date, mode, profile, quick danger summary; actions to view, rename inline, delete.
  - Detail view: thumbnail, per‑pesticide results (RGB total, concentration, band), thresholds used, sampling points and coordinates, normalization settings, export run JSON.

- Settings (`/settings`)
  - Mode selection: Default or Customize.
  - Theme: Light/Dark (toggle; saved to DB and localStorage).
  - Active calibration profile (same selector as Calibration header).
  - Data management: clear runs; optionally clear calibration profiles (with confirm).
  - Threshold defaults editor (Customize mode): edit per‑pesticide bands.
  - Import/Export: profiles, runs, or entire app data.

- About (`/about`)
  - Product overview, team, methodology, privacy note.

## Data Model (SQLite via SQLAlchemy)

- calibration_profile
  - id (pk), name (str, unique), created_at (datetime), is_active (bool)

- pesticide
  - id (pk), profile_id (fk → calibration_profile), key (slug), display_name (str), order_index (int), active (bool default true)
  - Constraints: profile_id + key unique; order_index defines UI ordering

- calibration_point
  - id (pk), pesticide_id (fk → pesticide), seq_index (int), concentration (float), rgb_sum (int)
  - Constraints: ≥2 points per pesticide; no duplicate concentrations for a pesticide; monotonic rgb_sum vs concentration enforced on save

- threshold_band
  - id (pk), pesticide_id (fk), band (enum: ‘low’|‘medium’|‘high’), min (float), max (float)
  - Interpretation: Low if min ≤ c < max; Medium if min ≤ c < max; High if min ≤ c ≤ max. Outside these, label “Out of range”.

- run
  - id (pk), profile_id (fk), mode (enum: ‘default’|‘customize’), name (str), created_at (datetime), image_path (str), used_normalization (bool), background_point_x (int), background_point_y (int), sampling_scheme (str: ‘5-pixel’)

- run_result
  - id (pk), run_id (fk), pesticide_key (str), pixel_x (int), pixel_y (int), rgb_sum (int), concentration (float), level (enum: ‘Low’|‘Medium’|‘High’|‘Out of range’)

- app_setting
  - key (pk), value_json (text)
  - Keys: ui_theme, mode, recent_profile_id, danger_thresholds_defaults (optional global fallbacks), etc.

## Default Calibration and Thresholds

- Seed the Default profile with 5 pesticides and curves:
  - Acephate: [(0, 359), (0.3, 337), (1, 311)]
  - Glyphosate: [(0, 381), (0.3, 367), (1, 348)]
  - Malathion: [(0, 273), (0.3, 209), (1, 183)]
  - Chlorpyrifos: [(0, 179), (0.3, 164), (1, 147)]
  - Acetamiprid: [(0, 358), (0.3, 343), (1, 333)]

- Default mode thresholds (display names as keys):
  - Acephate: Low [0.01–0.10), Medium [0.10–0.50), High [0.50–1.00]
  - Glyphosate: Low [0.10–0.30), Medium [0.30–0.70), High [0.70–1.00]
  - Malathion: Low [0.10–0.40), Medium [0.40–0.80), High [0.80–1.00]
  - Chlorpyrifos: Low [0.01–0.05), Medium [0.05–0.10), High [0.10–1.00]
  - Acetamiprid: Low [0.01–0.10), Medium [0.10–0.50), High [0.50–1.00]
  - If a computed concentration is outside all bands, label “Out of range”.
  - In Customize mode, thresholds are user-editable per pesticide and saved in the profile.

## Algorithms

### Sampling (5-pixel scheme)

For each test point center (x, y):
- Sample the center pixel and its 4-neighbors: (x, y), (x+1, y), (x-1, y), (x, y+1), (x, y-1).
- If any neighbor is outside the image bounds, skip that neighbor; keep collecting until up to 5 pixels (at least 1).
- Convert to RGB (Pillow) and get per-channel values.
- If background normalization is enabled, subtract per-channel background offsets (see below), clamp each channel to ≥ 0.
- Average per channel across the collected pixels, then total = round(R_avg + G_avg + B_avg) → integer rgb_sum.

### Background normalization

- Auto-pick background from a corner patch (default: top-left). Use a square window (e.g., 9×9 pixels) to average per-channel values.
- Decide “is black” by a per-channel threshold (default: mean ≤ 5 for each channel). If black, do not modify readings. If not black, compute background offset per channel as the patch mean values.
- For each sampled pixel channel value: value’ = max(0, value − background_offset_channel).
- Allow user to re-pick a background point on the canvas; show the chosen background average values for transparency.
- Store whether normalization was applied and the background point location in the run metadata.

### Interpolation (RGB total → concentration)

- For each pesticide:
  - Sort its calibration points by rgb_sum descending (higher sum → lower concentration).
  - If measured rgb_sum ≥ highest rgb_sum, clamp to the corresponding concentration (lowest concentration end).
  - If measured rgb_sum ≤ lowest rgb_sum, clamp to the corresponding concentration (highest concentration end).
  - Otherwise, find adjacent points [a, b] such that a.rgb_sum ≥ value ≥ b.rgb_sum and perform piecewise linear interpolation:
    - t = (value − b.rgb_sum) / (a.rgb_sum − b.rgb_sum)
    - c = b.concentration + t × (a.concentration − b.concentration)
  - Display c rounded to 2 decimal places.

### Classification (bands)

- Given per-pesticide thresholds (low/medium/high with [min,max] intervals):
  - If low.min ≤ c < low.max → “Low”
  - Else if medium.min ≤ c < medium.max → “Medium”
  - Else if high.min ≤ c ≤ high.max → “High”
  - Else → “Out of range”

## Validation Rules

- Calibration edits:
  - At least 2 points per pesticide.
  - Concentrations must be unique per pesticide.
  - Monotonicity: rgb_sum must change strictly in one direction as concentration increases (normally strictly decreasing). Reject flat or reversed segments.
  - seq_index normalized on save (sorted by concentration or explicit sort order).
- Analysis:
  - Points must lie within image bounds (with margin so neighbors exist when possible).
  - N equals the number of active pesticides for the active profile (capped at 10 in Customize).
  - Image files: size limit (e.g., 10 MB), supported types (JPEG/PNG), safe filenames (UUID).
  - Optional server-side downscale to max dimension (e.g., 2000 px).

## REST Endpoints

- Pages
  - GET `/` → index
  - GET `/analysis`
  - GET `/calibration`
  - GET `/history`
  - GET `/settings`
  - GET `/about`

- JSON APIs
  - Profiles
    - GET `/api/profiles` → list profiles
    - POST `/api/profiles` → create (name)
    - PATCH `/api/profiles/<id>` → rename/activate
    - DELETE `/api/profiles/<id>` → delete (with confirm; protect Default)
    - GET `/api/profiles/<id>/export` → export profile JSON
    - POST `/api/profiles/import` → import profile JSON
  - Pesticides & Calibrations
    - GET `/api/pesticides?profile_id=` → list pesticides for a profile
    - POST `/api/pesticides` → add/update (Customize only), reorder, toggle active
    - GET `/api/calibrations?pesticide_id=` → list points
    - POST `/api/calibrations` → upsert points array (validation enforced)
  - Thresholds
    - GET `/api/thresholds?pesticide_id=`
    - POST `/api/thresholds` → upsert low/medium/high bands
  - Analysis
    - POST `/api/analysis/upload` → upload image; returns temp id, image size, auto-placed N points, auto-picked background point
    - POST `/api/analysis/compute` → body: image/temp id, final points, normalization flag, background point → computes, stores run+results, returns results
  - History
    - GET `/api/history?q=&page=&page_size=` → list runs
    - GET `/api/history/<run_id>` → run detail
    - PATCH `/api/history/<run_id>/name` → rename
    - DELETE `/api/history/<run_id>` → delete (and image)
    - GET `/api/history/<run_id>/export` → export run JSON
  - Settings
    - GET `/api/settings`
    - PATCH `/api/settings` → mode, theme, active profile, data actions
    - POST `/api/data/clear` → clear runs; optional `include_profiles`

## Import/Export Formats

- Calibration Profile JSON
```json
{
  "version": 1,
  "profile": {
    "name": "Default",
    "pesticides": [
      {
        "key": "acephate",
        "display_name": "Acephate",
        "order_index": 0,
        "active": true,
        "points": [
          {"concentration": 0.0, "rgb_sum": 359},
          {"concentration": 0.3, "rgb_sum": 337},
          {"concentration": 1.0, "rgb_sum": 311}
        ],
        "thresholds": {
          "low": {"min": 0.01, "max": 0.10},
          "medium": {"min": 0.10, "max": 0.50},
          "high": {"min": 0.50, "max": 1.00}
        }
      }
    ]
  }
}
```

- Run Export JSON
```json
{
  "version": 1,
  "run": {
    "id": 123,
    "name": "Run 123",
    "created_at": "2025-01-01T12:00:00Z",
    "mode": "default",
    "profile": "Default",
    "image_path": "static/uploads/2025-01/uuid.jpg",
    "normalization": {"used": true, "background_point": {"x": 10, "y": 10}},
    "sampling_scheme": "5-pixel",
    "results": [
      {
        "pesticide_key": "acephate",
        "pixel": {"x": 100, "y": 240},
        "rgb_sum": 352,
        "concentration": 0.22,
        "band": "Low"
      }
    ]
  }
}
```

## File and Folder Layout

- `main.py` – Flask app (routes, blueprints, DB init, seed defaults)
- `templates/`
  - `base.html`, `index.html`, `analysis.html`, `calibration.html`, `history.html`, `settings.html`, `about.html`, `render_navbar.html`
- `static/`
  - `css/` theme styles
  - `js/` page scripts (`analysis.js`, `calibration.js`, `history.js`, `settings.js`, `charts.js`)
  - `uploads/` user images (date-partitioned folders)
- `instance/` – SQLite DB (`bioap.sqlite`)
- `pyproject.toml`, `README.md`, `uv.lock`
- `BIOAP_ARCHITECTURE.md` – this document

## Security and Safety

- Sanitize and randomize filenames (UUID); restrict MIME types to JPEG/PNG; max size e.g., 10 MB.
- CSRF protection on form posts (if WTForms/Flask-WTF used) or per-request tokens for JSON writes.
- Validate all calibration/threshold inputs (types, ranges, monotonicity).
- SQLite: safe for single-server usage; ensure atomic writes and exception handling.
- Privacy: store images locally; provide deletion tools; no third-party uploads.

## Performance and Reliability

- Downscale very large images server-side (preserve aspect) for speed.
- Avoid keeping large arrays in memory; compute per-point patches directly from Pillow images.
- Cache active profile and calibrations in memory; bust cache on save.
- Lazy-load thumbnails in history.

## Testing Strategy

- Unit tests:
  - Interpolation (clamping and interior segments)
  - Monotonicity validator and duplicate concentration detection
  - Sampling (5-pixel neighborhood) and bounds handling
  - Background normalization math
  - Threshold classification including “Out of range”
- Integration tests:
  - Upload → preview → compute → persist run
  - Calibration: edit → save → re-fetch → validate interpolation
  - History search, rename, delete, export
  - Profile create/clone/import/export flows
- Manual/visual:
  - Draggable/touch points across devices
  - Light/Dark theme rendering
  - Mobile capture behavior

## Milestones (Execution Order)

1) DB & Seed
   - Implement models and DB init; seed Default profile, pesticides, curves, and default thresholds.
2) Calibration
   - Build UI for Default & Customize; validation; save; profile CRUD; import/export.
3) Analysis
   - Upload/capture; canvas preview; auto-placed points; background auto-pick; draggable adjustments; compute and save.
4) History
   - List/search; detail view; rename; delete; export.
5) Settings
   - Mode toggle; theme; active profile; data management (clear runs/profiles).
6) Polish & Tests
   - Error handling, UX refinements, documentation, unit/integration/manual tests.

## Defaults and Configurables

- Max pesticides in Customize mode: 10.
- Background detection:
  - Corner: top-left by default; fallback to other corners if near-bounds cropping is needed.
  - Patch size: 9×9 (configurable).
  - Black threshold: per-channel mean ≤ 5 (configurable).
- Rounding: display 2 decimal places for concentrations.
- Sampling scheme: fixed 5-pixel (center + N,S,E,W).

## Rationale: SQLite vs TinyDB

SQLite with SQLAlchemy is selected for durability, relational integrity, query capability, and safer concurrency compared to TinyDB. Profiles, thresholds, calibrations, and runs benefit from relational joins and constraints; SQLite remains light and easy to ship, while offering better reliability for production use than a JSON store.

## Future Extensions

- Multiple sampling schemes (e.g., 3×3 or 5×5 averaging).
- White-balance or color card normalization.
- Multiple result images per run (replicates).
- Role-based access if deployed multi-user.
- Cloud export/import options.


