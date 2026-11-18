#!/usr/bin/env python3
"""Fetch Natural Earth land polygons once, simplify them, and store tools/land.json.

The poster renderer never touches the network: it only reads the JSON this
script writes.  Run:

    python3 tools/prepare_land.py --fetch   # one time, downloads the source
    python3 tools/prepare_land.py           # re-simplify from the cached download

Output format:
    {"source": "...", "tolerance_deg": 0.12,
     "polygons": [[outer_ring, hole_ring, ...], ...]}

Holes are kept: inland water such as the Black Sea, the Caspian, the Persian
Gulf and the Bay of Bengal has to stay water, or the map prints as one tan blob.
"""

import argparse
import json
import math
import os
import sys
import urllib.request

SOURCE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_50m_land.geojson"
)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(HERE, "land.json")
RAW_CACHE = os.path.join(HERE, ".ne_50m_land.cache.geojson")

# A ring smaller than this (in square degrees) is a speck at page scale.
MIN_RING_AREA = 0.20


def point_segment_distance(pt, a, b):
    """Perpendicular distance from pt to the segment a-b."""
    x, y = pt
    x1, y1 = a
    x2, y2 = b
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0.0 and dy == 0.0:
        return math.hypot(x - x1, y - y1)
    t = ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


def douglas_peucker(points, tolerance):
    """Iterative Douglas-Peucker so deep coastlines cannot blow the stack."""
    n = len(points)
    if n < 3:
        return list(points)
    keep = [False] * n
    keep[0] = True
    keep[n - 1] = True
    stack = [(0, n - 1)]
    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue
        worst_d = -1.0
        worst_i = -1
        a = points[first]
        b = points[last]
        for i in range(first + 1, last):
            d = point_segment_distance(points[i], a, b)
            if d > worst_d:
                worst_d = d
                worst_i = i
        if worst_d > tolerance and worst_i > 0:
            keep[worst_i] = True
            stack.append((first, worst_i))
            stack.append((worst_i, last))
    return [p for p, k in zip(points, keep) if k]


def ring_area(points):
    """Shoelace area in square degrees (absolute)."""
    total = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return abs(total) * 0.5


def round_ring(points, ndigits=2):
    out = []
    last = None
    for lon, lat in points:
        p = (round(lon, ndigits), round(lat, ndigits))
        if p != last:
            out.append([p[0], p[1]])
            last = p
    # A ring needs at least three distinct vertices to enclose anything.
    if len(out) >= 4 and out[0] == out[-1]:
        out.pop()
    return out


def iter_polygons(geometry):
    """Yield each polygon as its list of rings (outer first, then holes)."""
    if not geometry:
        return
    gtype = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if gtype == "Polygon":
        if coords:
            yield coords
    elif gtype == "MultiPolygon":
        for poly in coords:
            if poly:
                yield poly


def load_source(do_fetch):
    if os.path.exists(RAW_CACHE):
        with open(RAW_CACHE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    if not do_fetch:
        sys.exit(
            "no cached download at %s -- run with --fetch once to get it"
            % RAW_CACHE
        )
    print("downloading %s" % SOURCE_URL)
    req = urllib.request.Request(
        SOURCE_URL, headers={"User-Agent": "makefun-news-image/1.0"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        blob = resp.read()
    with open(RAW_CACHE, "wb") as fh:
        fh.write(blob)
    print("cached %d bytes" % len(blob))
    return json.loads(blob.decode("utf-8"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fetch", action="store_true",
                    help="download the source geojson if it is not cached")
    ap.add_argument("--tolerance", type=float, default=0.12,
                    help="Douglas-Peucker tolerance in degrees (default 0.12)")
    ap.add_argument("--min-area", type=float, default=MIN_RING_AREA,
                    help="drop rings below this many square degrees")
    args = ap.parse_args(argv)

    data = load_source(args.fetch)
    features = data.get("features") or []

    polygons = []
    kept_pts = 0
    src_pts = 0
    for feat in features:
        for poly in iter_polygons(feat.get("geometry")):
            parts = []
            for idx, ring in enumerate(poly):
                pts = [(float(c[0]), float(c[1])) for c in ring if len(c) >= 2]
                src_pts += len(pts)
                if len(pts) < 4:
                    continue
                # Holes get a much lower bar: a small lake still reads as water.
                floor = args.min_area if idx == 0 else args.min_area * 0.06
                if ring_area(pts) < floor:
                    continue
                simple = douglas_peucker(pts, args.tolerance)
                simple = round_ring(simple)
                if len(simple) < 4 or ring_area(simple) < floor * 0.5:
                    continue
                parts.append(simple)
                kept_pts += len(simple)
            if parts:
                polygons.append(parts)

    # Deterministic order: biggest outer ring first, then by first coordinate.
    polygons.sort(key=lambda parts: (-ring_area([tuple(q) for q in parts[0]]),
                                     parts[0][0][0], parts[0][0][1]))

    payload = {
        "source": SOURCE_URL,
        "tolerance_deg": args.tolerance,
        "min_ring_area_deg2": args.min_area,
        "polygon_count": len(polygons),
        "ring_count": sum(len(p) for p in polygons),
        "point_count": kept_pts,
        "polygons": polygons,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"), sort_keys=True)

    size = os.path.getsize(OUT_JSON)
    print(json.dumps({
        "land_json": OUT_JSON,
        "bytes": size,
        "polygons": len(polygons),
        "rings": sum(len(p) for p in polygons),
        "points_in": src_pts,
        "points_out": kept_pts,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
