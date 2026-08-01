# Building typology viewer

Interactive 3D map of building footprints, heights and inferred use.
Mumbai (673,583 buildings) is tiled and bundled; the pipeline is city-agnostic.

Live: `https://<you>.github.io/buildings-viewer/`

## Run

```bash
python3 serve.py          # http://localhost:8000
```

No install step, no build step, no API keys. `serve.py` is a static server that
implements HTTP range requests, which PMTiles needs and the stdlib handler
doesn't. Internet is required for the CDN scripts and the CARTO basemap.

## Use

| Control | Effect |
|---|---|
| colour | which attribute drives the extrusion colour |
| height | min/max filter in metres |
| scale | vertical exaggeration — most of Mumbai is under 5 m, so ×2/×3 helps |
| 3D | toggle pitch |
| legend row | click to hide a class, shift-click to isolate it |
| building | click for the full attribute row |

Map position lives in the URL hash, so views are shareable.

## Add another city

```bash
python3 build/make_tiles.py pune data/pune_typology.gpkg --label Pune
```

That converts the GPKG, tiles it with [tippecanoe](https://github.com/felt/tippecanoe)
(`brew install tippecanoe` / `apt install tippecanoe`), reads the extent back out
of the PMTiles header, profiles the attributes, and registers the city in
`public/cities.json`. The viewer picks it up on reload — the city dropdown,
the colour modes, the legend classes and their counts are all read from that
file, so there is nothing to edit by hand.

Flags: `--fields` (default `height,area_m2,typology_label,typo_src,source`),
`--layer`, `--minzoom`/`--maxzoom` (default 11–15), `--no-tiles` to only
re-profile and rewrite the registry.

## Publish to GitHub Pages

Two hand-edits first, both one-liners:

1. `REPO` at the top of `public/app.js` — the repo URL, shown in the about
   panel. Leave it empty to hide that line.
2. `og:image` in `public/index.html` — link previews need an absolute URL, so
   change `card.png` to `https://<you>.github.io/buildings-viewer/card.png`
   once you know the address. `card.png` is generated from the class counts;
   re-make it when the data changes.

Then check the attribution wording in the about panel and in
`customAttribution` actually matches your sources and their licences. OSM data
is ODbL and requires attribution; make sure the Google dataset is named the way
its licence asks for.

```bash
git init && git add -A && git commit -m "Building typology viewer"
git remote add origin git@github.com:<you>/buildings-viewer.git
git push -u origin main
```

Then **Settings → Pages → Source: GitHub Actions**. The workflow in
`.github/workflows/pages.yml` publishes `public/` on every push that touches
it; the rest of the repo is build tooling and is not deployed. The site lives
at `https://<you>.github.io/buildings-viewer/` — all paths in the app are
relative, so the repo subpath is fine.

Nothing else changes: PMTiles works on Pages because Pages serves byte ranges,
which is the only thing the format needs from a host.

Three limits to keep in view:

- **50 MB / 100 MB per file.** `mumbai.pmtiles` is 62 MB, so `git push` prints
  a large-file warning. It still goes through; 100 MB is the hard block.
  Don't use Git LFS — Pages serves LFS pointer files, not the file.
- **1 GB repo, 1 GB published site.** At ~60 MB per city that is roughly ten
  cities, and every rebuild of a city leaves the old copy in git history
  forever. Fourteen cities will not fit.
- **100 GB/month bandwidth, soft.** A cold visit pulls a few MB of tiles, so
  this only matters if the map gets popular.

### When the repo gets too big

Move the tiles off GitHub and keep the code there. Put the `.pmtiles` files in
a bucket with public read and CORS enabled (Cloudflare R2 has no egress
charge, which suits this shape of traffic), then build with a base URL:

```bash
python3 build/make_tiles.py mumbai data/mumbai_typology.gpkg \
        --tiles-url https://tiles.example.com --no-tiles   # registry only
```

That writes an absolute URL into `cities.json`; the `pmtiles://` protocol
accepts one unchanged. Add `public/data/*.pmtiles` to `.gitignore` and the
repo drops to a few hundred KB.

### If tiles fail to load on Pages only

There is a [known intermittent failure](https://github.com/protomaps/PMTiles/issues/584)
on Pages where a range request comes back without a `content-length`, and the
client reports that the storage backend doesn't support byte serving. A hard
reload usually clears it; if it persists, the bucket route above is the fix.

## Layout

```
.github/workflows/      GitHub Pages deploy
serve.py                 static server with range support
build/gpkg2ndjson.py     GPKG -> ndjson, sqlite3 + struct only, streaming
build/make_tiles.py      one command per city: tile + profile + register
public/index.html        markup
public/app.css           styles
public/app.js            MODES table drives paint, filter and legend
public/cities.json       generated registry
public/data/*.pmtiles    generated tiles
```

To add a colour mode, add one entry to `MODES` in `app.js`. An entry with
`stops` is continuous, one without is categorical; modes whose field is absent
from a city are hidden automatically.

## Notes

- Tiles are z11–15 and overzoom to 19. Below z11 there is no data, so the map's
  minimum zoom is clamped to the tileset's.
- Attribute rounding is 2 dp and coordinates 6 dp, which is roughly 10 cm.
- `typo_src` records how each typology was assigned — `heuristic_default`
  covers 65% of buildings, so colour by *typology rule* before trusting the
  typology map.
- To run fully offline, save `maplibre-gl.js`, `maplibre-gl.css` and
  `pmtiles.js` next to `app.js`, point the tags in `index.html` at them, and
  swap `BASEMAP` for a blank style: `{"version":8,"sources":{},"layers":[]}`.
