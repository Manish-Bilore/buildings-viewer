#!/usr/bin/env python3
"""GPKG (2D polygons, EPSG:4326) -> newline-delimited GeoJSON.

Zero dependencies: sqlite3 + struct. Streams, so memory stays flat.
CLI: gpkg2ndjson.py in.gpkg out.ndjson [--layer L] [--fields a,b] [--precision 6]
"""
import argparse, json, sqlite3, struct, sys

ENV_LEN = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}


def geom(blob, nd):
    """Decode a GPKG geometry blob -> (geojson_type, coordinates) or None if empty."""
    flags = blob[3]
    if (flags >> 4) & 1:
        return None
    pos = 8 + ENV_LEN[(flags >> 1) & 7]          # skip header + envelope

    def ring(p, e):
        (n,) = struct.unpack_from(e + "I", blob, p)
        pts = struct.unpack_from(f"{e}{2 * n}d", blob, p + 4)
        return ([[round(pts[i], nd), round(pts[i + 1], nd)] for i in range(0, 2 * n, 2)],
                p + 4 + 16 * n)

    def polygon(p):
        e = "<" if blob[p] == 1 else ">"
        (nr,) = struct.unpack_from(e + "I", blob, p + 5)
        p, rings = p + 9, []
        for _ in range(nr):
            r, p = ring(p, e)
            rings.append(r)
        return rings, p

    e = "<" if blob[pos] == 1 else ">"
    (typ,) = struct.unpack_from(e + "I", blob, pos + 1)
    if typ & 0xFF == 3:
        return "Polygon", polygon(pos)[0]
    if typ & 0xFF == 6:
        (n,) = struct.unpack_from(e + "I", blob, pos + 5)
        p, polys = pos + 9, []
        for _ in range(n):
            rings, p = polygon(p)
            polys.append(rings)
        return "MultiPolygon", polys
    raise ValueError(f"unsupported WKB type {typ}")


def layer_info(db, layer=None):
    """-> (layer, geometry_column, [(col, decltype), ...])"""
    layer = layer or db.execute(
        "select table_name from gpkg_contents where data_type='features' limit 1").fetchone()[0]
    gcol = db.execute("select column_name from gpkg_geometry_columns where table_name=?",
                      (layer,)).fetchone()[0]
    cols = [(r[1], (r[2] or "").upper()) for r in db.execute(f'PRAGMA table_info("{layer}")')]
    return layer, gcol, cols


def convert(src, dst, fields=None, layer=None, precision=6, log=lambda s: None):
    db = sqlite3.connect(src)
    layer, gcol, cols = layer_info(db, layer)
    names = [c for c, _ in cols]
    keep = [c for c in (fields or names) if c in names and c != gcol]
    sel = ", ".join(f'"{c}"' for c in [gcol] + keep)

    n = 0
    with open(dst, "w") as out:
        for row in db.execute(f'select {sel} from "{layer}"'):
            g = geom(row[0], precision)
            if not g:
                continue
            props = {k: (round(v, 2) if isinstance(v, float) else v)
                     for k, v in zip(keep, row[1:]) if v is not None}
            out.write(json.dumps({"type": "Feature",
                                  "geometry": {"type": g[0], "coordinates": g[1]},
                                  "properties": props}, separators=(",", ":")) + "\n")
            n += 1
            if n % 100_000 == 0:
                log(f"  {n:,}")
    return n


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("src"); p.add_argument("dst")
    p.add_argument("--layer"); p.add_argument("--fields")
    p.add_argument("--precision", type=int, default=6)
    a = p.parse_args()
    log = lambda s: print(s, file=sys.stderr)
    n = convert(a.src, a.dst, a.fields.split(",") if a.fields else None, a.layer, a.precision, log)
    log(f"{n:,} features -> {a.dst}")
