#!/usr/bin/env python3
"""Build browser tiles for one city.

    python3 build/make_tiles.py mumbai data/mumbai_typology.gpkg

Converts the GPKG to PMTiles with tippecanoe, profiles the attributes, and
registers the city in public/cities.json. Re-run per city; the viewer picks
up whatever is in the registry.
"""
import argparse, json, os, shutil, struct, sqlite3, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gpkg2ndjson import convert, layer_info

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_CATS = 60          # above this a text column is treated as free text, not a class
log = lambda s: print(s, file=sys.stderr, flush=True)


def profile(src, layer, keep):
    """Value counts for low-cardinality text columns, min/max for numeric ones."""
    db = sqlite3.connect(src)
    layer, gcol, cols = layer_info(db, layer)
    decl = dict(cols)
    total = db.execute(f'select count(*) from "{layer}"').fetchone()[0]
    cats, nums = {}, {}
    for c in keep:
        if c == gcol:
            continue
        if "CHAR" in decl.get(c, "") or "TEXT" in decl.get(c, ""):
            rows = db.execute(
                f'select "{c}", count(*) from "{layer}" where "{c}" is not null '
                f"group by 1 order by 2 desc limit {MAX_CATS + 1}").fetchall()
            if len(rows) <= MAX_CATS:
                cats[c] = dict(rows)
        else:
            lo, hi = db.execute(f'select min("{c}"), max("{c}") from "{layer}"').fetchone()
            if isinstance(lo, (int, float)):
                nums[c] = [round(lo, 2), round(hi, 2)]
    return total, cats, nums


def pmtiles_meta(path):
    """-> (bounds, [minzoom, maxzoom]) straight from the PMTiles v3 header."""
    h = open(path, "rb").read(127)
    return [v / 1e7 for v in struct.unpack_from("<iiii", h, 102)], [h[100], h[101]]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("city", help="slug, e.g. mumbai")
    p.add_argument("gpkg")
    p.add_argument("--label", help="display name (default: capitalised slug)")
    p.add_argument("--layer")
    p.add_argument("--fields", default="height,area_m2,typology_label,typo_src,source")
    p.add_argument("--minzoom", type=int, default=11)
    p.add_argument("--maxzoom", type=int, default=15)
    p.add_argument("--tiles-url", metavar="URL",
                   help="serve tiles from elsewhere, e.g. an R2/S3 bucket base URL")
    p.add_argument("--no-tiles", action="store_true",
                   help="only re-profile attributes and rewrite the registry")
    a = p.parse_args()

    if not shutil.which("tippecanoe"):
        sys.exit("tippecanoe not found - see README")

    keep = a.fields.split(",")
    out = os.path.join(ROOT, "public", "data", f"{a.city}.pmtiles")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    if not a.no_tiles:
        with tempfile.NamedTemporaryFile(suffix=".ndjson", delete=False) as tmp:
            nd = tmp.name
        try:
            log(f"[1/3] {a.gpkg} -> ndjson")
            n = convert(a.gpkg, nd, keep, a.layer, log=log)
            log(f"      {n:,} features")

            log(f"[2/3] tippecanoe z{a.minzoom}-{a.maxzoom}")
            subprocess.run(["tippecanoe", "-o", out, "-l", "buildings",
                            "-Z", str(a.minzoom), "-z", str(a.maxzoom),
                            "--drop-densest-as-needed", "--no-tile-size-limit",
                            "--force", "-q", nd], check=True)
        finally:
            os.unlink(nd)

    bounds, zoom = pmtiles_meta(out)
    log("[3/3] profiling attributes")
    total, cats, nums = profile(a.gpkg, a.layer, keep)

    reg_path = os.path.join(ROOT, "public", "cities.json")
    reg = json.load(open(reg_path)) if os.path.exists(reg_path) else {}
    reg[a.city] = {"label": a.label or a.city.title(),
                   "tiles": (f"{a.tiles_url.rstrip('/')}/{a.city}.pmtiles"
                             if a.tiles_url else f"data/{a.city}.pmtiles"),
                   "bounds": bounds, "zoom": zoom,
                   "count": total, "cats": cats, "nums": nums}
    json.dump(reg, open(reg_path, "w"), indent=1)

    log(f"done: {out} ({os.path.getsize(out) / 1e6:.0f} MB), registered as '{a.city}'")


if __name__ == "__main__":
    main()
