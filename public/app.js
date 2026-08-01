/* Building typology viewer.
   Everything the UI shows is derived from cities.json + the MODES table below,
   so adding a city (or an attribute) needs no changes here. */

const REPO = "";   // e.g. "https://github.com/you/buildings-viewer" - shown in the about panel
const BASEMAP = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";
const LAYER = "buildings";          // tippecanoe layer name, see build/make_tiles.py

/* Categorical colours, assigned in descending frequency order. */
const PALETTE = ["#4c78a8", "#f58518", "#54a24b", "#e45756", "#72b7b2", "#eeca3b",
                 "#b279a2", "#9d755d", "#ff9da6", "#88d27a", "#a0a7b4", "#d67195",
                 "#5b8ff9", "#c9a227"];

/* A mode with `stops` is continuous; otherwise it is categorical. */
const MODES = {
  typology:   { field: "typology_label", label: "typology" },
  provenance: { field: "typo_src",       label: "typology rule" },
  source:     { field: "source",         label: "data source" },
  height:     { field: "height",  label: "height",
                stops: [[0, "#20204a"], [5, "#6a2a7a"], [10, "#c6426e"], [20, "#f9834e"], [50, "#fbf2a8"]] },
  footprint:  { field: "area_m2", label: "footprint",
                stops: [[0, "#0d3b4a"], [100, "#1f7a8c"], [500, "#7fd1c6"], [2000, "#eef6f4"]] },
};

const $ = (id) => document.getElementById(id);
const fmt = (n) => n.toLocaleString("en-IN");
const el = (tag, attrs = {}, html = "") =>
  Object.assign(document.createElement(tag), { innerHTML: html, ...attrs });

const state = { city: null, mode: "typology", hmin: 0, hmax: 0, exag: 1, off: new Set() };
let registry, city, map, colours = {};

/* ---------- expressions ---------- */

const modesFor = (c) => Object.entries(MODES)
  .filter(([, m]) => (m.stops ? c.nums?.[m.field] : c.cats?.[m.field]));

const paint = () => {
  const m = MODES[state.mode];
  if (m.stops) return ["interpolate", ["linear"], ["get", m.field], ...m.stops.flat()];
  return ["match", ["get", m.field],
          ...Object.entries(colours[m.field]).flatMap(([k, v]) => [k, v]), "#555a61"];
};

const filter = () => {
  const f = ["all",
    [">=", ["coalesce", ["get", "height"], 0], state.hmin],
    ["<=", ["coalesce", ["get", "height"], 0], state.hmax]];
  const m = MODES[state.mode];
  if (!m.stops && state.off.size)
    f.push(["!", ["in", ["get", m.field], ["literal", [...state.off]]]]);
  return f;
};

/* ---------- rendering ---------- */

function apply() {
  if (!map.getLayer(LAYER)) return;
  map.setPaintProperty(LAYER, "fill-extrusion-color", paint());
  map.setPaintProperty(LAYER, "fill-extrusion-height",
    ["*", ["coalesce", ["get", "height"], 0], state.exag]);
  map.setFilter(LAYER, filter());
  drawLegend();
}

function drawLegend() {
  const m = MODES[state.mode], box = $("legend");
  box.replaceChildren();

  if (m.stops) {
    const [lo, hi] = [m.stops[0][0], m.stops.at(-1)[0]];
    const grad = m.stops.map(([v, c]) => `${c} ${((v - lo) / (hi - lo)) * 100}%`).join(",");
    box.append(el("div", { className: "ramp", style: `background:linear-gradient(90deg,${grad})` }));
    box.append(el("div", { className: "ticks" },
      m.stops.map(([v]) => `<span>${v}</span>`).join("")));
    box.append(el("div", { className: "ticks" },
      `<span>${m.label} ${m.field === "area_m2" ? "m²" : "m"}, clamped</span>`));
    return;
  }

  const counts = city.cats[m.field];
  for (const [k, n] of Object.entries(counts)) {
    const off = state.off.has(k);
    const b = el("button", { className: "key", type: "button", title: "click to toggle · shift-click to isolate" },
      `<i style="background:${colours[m.field][k]}"></i><b>${k}</b><span>${fmt(n)}</span>`);
    b.dataset.off = off;
    b.onclick = (e) => {
      if (e.shiftKey) {
        const rest = Object.keys(counts).filter((x) => x !== k);
        state.off = state.off.size === rest.length ? new Set() : new Set(rest);
      } else state.off.has(k) ? state.off.delete(k) : state.off.add(k);
      apply();
    };
    box.append(b);
  }
}

/* ---------- data ---------- */

function setCity(slug, fit = true) {
  state.city = slug;
  city = registry[slug];
  if (!modesFor(city).some(([k]) => k === state.mode)) state.mode = modesFor(city)[0][0];

  $("title").textContent = city.label;
  $("total").textContent = `${fmt(city.count)} bldgs`;

  /* share of buildings whose class came from a fallback rule rather than evidence */
  const rules = city.cats.typo_src;
  if (rules) {
    const guessed = Object.entries(rules)
      .filter(([k]) => k.startsWith("heuristic")).reduce((a, [, n]) => a + n, 0);
    $("fallback").textContent = `${Math.round((guessed / city.count) * 100)}%`;
  }
  $("mode").replaceChildren(...modesFor(city).map(([k, v]) =>
    el("option", { value: k, selected: k === state.mode }, v.label)));

  const [lo, hi] = city.nums.height || [0, 200];
  state.hmin = Math.floor(lo); state.hmax = Math.ceil(hi);
  $("hmin").value = state.hmin; $("hmax").value = state.hmax;
  $("hmin").max = $("hmax").max = state.hmax;
  state.off.clear();

  colours = Object.fromEntries(Object.entries(city.cats).map(([f, counts]) =>
    [f, Object.fromEntries(Object.keys(counts).map((k, i) => [k, PALETTE[i % PALETTE.length]]))]));

  /* the data only exists between these zooms, so don't let the view leave them */
  map.setMinZoom(city.zoom[0]);
  map.setMaxZoom(city.zoom[1] + 4);

  if (map.getLayer(LAYER)) map.removeLayer(LAYER);
  if (map.getSource("city")) map.removeSource("city");
  map.addSource("city", { type: "vector", url: `pmtiles://${city.tiles}` });

  const firstSymbol = map.getStyle().layers.find((l) => l.type === "symbol")?.id;
  map.addLayer({
    id: LAYER, type: "fill-extrusion", source: "city", "source-layer": LAYER,
    paint: {
      "fill-extrusion-color": paint(),
      "fill-extrusion-height": ["*", ["coalesce", ["get", "height"], 0], state.exag],
      "fill-extrusion-base": 0,
      "fill-extrusion-opacity": 0.92,
    },
  }, firstSymbol);

  if (fit)
    map.fitBounds(city.bounds, { padding: { top: 40, bottom: 40, left: 300, right: 40 }, duration: 0 });
  apply();
}

/* ---------- boot ---------- */

(async function init() {
  maplibregl.addProtocol("pmtiles", new pmtiles.Protocol().tile);
  registry = await (await fetch("cities.json")).json();

  const b0 = Object.values(registry)[0].bounds;
  map = new maplibregl.Map({
    container: "map", style: BASEMAP,
    center: [(b0[0] + b0[2]) / 2, (b0[1] + b0[3]) / 2], zoom: 11,
    pitch: 45, hash: true,
    attributionControl: { compact: true, customAttribution: "Buildings: Google Open Buildings, OpenStreetMap" },
  });
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
  map.addControl(new maplibregl.ScaleControl({ maxWidth: 90 }), "bottom-right");

  if (REPO) $("repo").innerHTML = `Pipeline and code: <a href="${REPO}">${REPO.replace(/^https?:\/\//, "")}</a>`;

  const many = Object.keys(registry).length > 1;
  $("city").hidden = !many;
  $("title").hidden = many;
  $("city").replaceChildren(...Object.entries(registry).map(([k, v]) =>
    el("option", { value: k }, v.label)));
  $("exag").replaceChildren(...[1, 2, 3].map((x) => {
    const b = el("button", { type: "button" }, `${x}×`);
    b.setAttribute("aria-pressed", x === state.exag);
    b.onclick = () => {
      state.exag = x;
      [...$("exag").children].forEach((c) => c.setAttribute("aria-pressed", c === b));
      apply();
    };
    return b;
  }));

  map.on("load", () => {
    map.setLight({ anchor: "viewport", color: "#ffffff", intensity: 0.35, position: [1.2, 200, 30] });
    setCity(Object.keys(registry)[0], !location.hash);
  });

  $("city").onchange = (e) => setCity(e.target.value);
  $("mode").onchange = (e) => { state.mode = e.target.value; state.off.clear(); apply(); };
  for (const k of ["hmin", "hmax"])
    $(k).oninput = (e) => { state[k] = Number(e.target.value || 0); apply(); };

  $("pitch").onclick = () => {
    const on = map.getPitch() < 10;
    $("pitch").setAttribute("aria-pressed", on);
    map.easeTo({ pitch: on ? 55 : 0, duration: 500 });
  };
  $("pitch").setAttribute("aria-pressed", true);

  $("reset").onclick = () => setCity(state.city);   // re-fits bounds and clears filters
  $("about-toggle").onclick = () => {
    const open = $("about").hidden;
    $("about").hidden = !open;
    $("about-toggle").setAttribute("aria-pressed", open);
  };

  /* rendered-feature readout: only meaningful once tiles are at full detail */
  map.on("idle", () => {
    $("view").textContent = map.getZoom() < 14 ? "zoom in for count"
      : `${fmt(map.queryRenderedFeatures({ layers: [LAYER] }).length)} in view`;
  });

  /* inspector */
  map.on("click", LAYER, (e) => {
    const p = e.features[0].properties;
    const rows = Object.entries(p)
      .map(([k, v]) => `<dt>${k}</dt><dd>${typeof v === "number" ? v.toLocaleString("en-IN") : v}</dd>`)
      .join("");
    new maplibregl.Popup({ closeButton: true, maxWidth: "260px" })
      .setLngLat(e.lngLat).setHTML(`<dl>${rows}</dl>`).addTo(map);
  });
  map.on("mouseenter", LAYER, () => (map.getCanvas().style.cursor = "pointer"));
  map.on("mouseleave", LAYER, () => (map.getCanvas().style.cursor = ""));
})();
