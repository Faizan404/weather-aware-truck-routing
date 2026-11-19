"""Build core/data/us_states.geojson from the US Census cartographic boundary file.

Source (public domain): https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_500k.zip

    python scripts/build_us_borders.py path/to/cb_2023_us_state_500k.zip [--tolerance 0.002]

Keeps the 50 states and DC (no territories), simplifies the outlines with
Douglas-Peucker and rounds coordinates to 4 decimals (~10 m).

Borders are simplified per *arc*, not per ring: a border two states share is
simplified once and used by both, so neighbouring states still meet exactly
(no gaps or overlaps along state lines that could misclassify a point).
Standard library only.
"""

from __future__ import annotations

import argparse
import io
import json
import struct
import zipfile
from pathlib import Path
from typing import Any

TERRITORIES = {"PR", "VI", "GU", "AS", "MP"}
OUT = Path(__file__).resolve().parent.parent / "core" / "data" / "us_states.geojson"

Pt = tuple[float, float]  # (lon, lat)


def read_dbf(data: bytes) -> list[dict[str, str]]:
    count = struct.unpack("<I", data[4:8])[0]
    header_len, record_len = struct.unpack("<HH", data[8:12])
    fields, pos = [], 32
    while data[pos] != 0x0D:
        name = data[pos : pos + 11].split(b"\0")[0].decode()
        fields.append((name, data[pos + 16]))
        pos += 32
    rows = []
    for i in range(count):
        rec = data[header_len + i * record_len : header_len + (i + 1) * record_len]
        row, off = {}, 1  # first byte is the deletion flag
        for name, length in fields:
            row[name] = rec[off : off + length].decode("utf-8", "replace").strip()
            off += length
        rows.append(row)
    return rows


def read_shp(data: bytes) -> list[list[list[Pt]]]:
    """Polygon records as lists of closed rings."""
    shapes: list[list[list[Pt]]] = []
    pos = 100
    while pos < len(data):
        length = struct.unpack(">i", data[pos + 4 : pos + 8])[0] * 2
        content = data[pos + 8 : pos + 8 + length]
        pos += 8 + length
        if struct.unpack("<i", content[:4])[0] != 5:
            shapes.append([])
            continue
        n_parts, n_points = struct.unpack("<ii", content[36:44])
        parts = list(struct.unpack(f"<{n_parts}i", content[44 : 44 + 4 * n_parts]))
        start = 44 + 4 * n_parts
        pts = [struct.unpack("<dd", content[start + 16 * k : start + 16 * k + 16]) for k in range(n_points)]
        bounds = parts + [n_points]
        shapes.append([[(round(x, 7), round(y, 7)) for x, y in pts[a:b]] for a, b in zip(bounds, bounds[1:])])
    return shapes


def _perp(p: Pt, a: Pt, b: Pt) -> float:
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    if dx == dy == 0:
        return ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
    return abs(dy * x - dx * y + x2 * y1 - y2 * x1) / (dx * dx + dy * dy) ** 0.5


def douglas_peucker(pts: list[Pt], tol: float) -> list[Pt]:
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        best, idx = 0.0, -1
        for i in range(a + 1, b):
            d = _perp(pts[i], pts[a], pts[b])
            if d > best:
                best, idx = d, i
        if best > tol:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(pts, keep) if k]


def simplify_arc(arc: list[Pt], tol: float) -> list[Pt]:
    """Same result whichever direction the arc is walked in."""
    if arc[-1] < arc[0]:
        return douglas_peucker(arc[::-1], tol)[::-1]
    return douglas_peucker(arc, tol)


def simplify_rings(rings: list[list[Pt]], tol: float) -> list[list[Pt] | None]:
    owners: dict[Pt, set[int]] = {}
    for rid, ring in enumerate(rings):
        for p in ring[:-1]:
            owners.setdefault(p, set()).add(rid)
    out: list[list[Pt] | None] = []
    for ring in rings:
        pts = ring[:-1]
        n = len(pts)
        # Fixed vertices: where the set of states sharing the border changes.
        fixed = [
            i for i in range(n)
            if len(owners[pts[i]]) > 1
            and (owners[pts[i]] != owners[pts[i - 1]] or owners[pts[i]] != owners[pts[(i + 1) % n]])
        ]
        if not fixed:  # island or unshared ring: pin the first and farthest points
            far = max(range(n), key=lambda i: (pts[i][0] - pts[0][0]) ** 2 + (pts[i][1] - pts[0][1]) ** 2)
            fixed = sorted({0, far})
        result: list[Pt] = []
        for k, a in enumerate(fixed):
            b = fixed[(k + 1) % len(fixed)]
            arc = pts[a : b + 1] if b > a else pts[a:] + pts[: b + 1]
            result += simplify_arc(arc, tol)[:-1]
        result.append(result[0])
        out.append(result if len(result) >= 4 else None)
    return out


def signed_area(ring: list[Pt]) -> float:
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:])) / 2


def inside(p: Pt, ring: list[Pt]) -> bool:
    x, y, hit = p[0], p[1], False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("zip_path")
    ap.add_argument("--tolerance", type=float, default=0.002, help="degrees (0.002 ~ 200 m)")
    args = ap.parse_args()

    with zipfile.ZipFile(args.zip_path) as z:
        shp_name = next(n for n in z.namelist() if n.endswith(".shp"))
        shp = z.read(shp_name)
        dbf = z.read(shp_name[:-4] + ".dbf")
    rows, shapes = read_dbf(dbf), read_shp(io.BytesIO(shp).getvalue())

    states = [(row, rings) for row, rings in zip(rows, shapes) if row["STUSPS"] not in TERRITORIES]
    all_rings = [ring for _, rings in states for ring in rings]
    simplified = iter(simplify_rings(all_rings, args.tolerance))

    features: list[dict[str, Any]] = []
    for row, rings in states:
        kept = [r for r in (next(simplified) for _ in rings) if r]
        kept = [[(round(x, 4), round(y, 4)) for x, y in r] for r in kept]
        # Shapefile outer rings are clockwise; GeoJSON wants outer rings
        # counter-clockwise and holes clockwise, holes inside their polygon.
        outers = [r[::-1] for r in kept if signed_area(r) < 0]
        holes = [r[::-1] for r in kept if signed_area(r) > 0]
        polygons = [[o] for o in outers]
        for h in holes:
            owner = next((p for p in polygons if inside(h[0], p[0])), None)
            if owner:
                owner.append(h)
        features.append({
            "type": "Feature",
            "properties": {"code": row["STUSPS"], "name": row["NAME"]},
            "geometry": {"type": "MultiPolygon", "coordinates": [[[list(pt) for pt in r] for r in p] for p in polygons]},
        })
    features.sort(key=lambda f: f["properties"]["code"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")))
    points = sum(len(r) for f in features for p in f["geometry"]["coordinates"] for r in p)
    print(f"{len(features)} states, {points} points, {OUT.stat().st_size / 1024:.0f} KB -> {OUT}")


if __name__ == "__main__":
    main()
