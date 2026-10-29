// deck.gl + MapLibre. One point layer (the same layer factory in both renderers): a standalone
// Deck with an OrbitView for the embedding/custom views, and a MapboxOverlay on MapLibre for the
// map view. The overlay is not interleaved: @deck.gl/mapbox 9.4 reads map.transform, which
// maplibre-gl 6.x no longer has, so interleaved rendering throws (smt-fa2026 also uses false). Point moves between orbit layouts are animated on the CPU
// (lerp into one Float32Array) so they work with binary attributes.
import {
  Deck, OrbitView, COORDINATE_SYSTEM, LinearInterpolator,
  ScatterplotLayer, PathLayer, SolidPolygonLayer, LineLayer, TextLayer
} from 'deck.gl';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { Map as MapLibre, setWorkerUrl } from 'maplibre-gl';
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { INK } from './colors.js';

// From smt-fa2026 src/lib/sandboxes/_shared/maplibre.js: Vite moves maplibre-gl.mjs away from
// its worker, which then 404s silently (blank basemap). Hand MapLibre the worker Vite emitted.
setWorkerUrl(maplibreWorkerUrl);

export const TRANSITION_MS = 1500;      // placeholder
// placeholders: fewer points than `trigger` in view -> glyphs, at most `cap` of them
export const GLYPHS = { orbit: { trigger: 1500, cap: 1500 }, map: { trigger: 10000, cap: 6000 } };
const GLYPH_MAX_SHARDS = 150;           // fetch limit per update (shards follow BBL order, see README)
const GLYPH_NEIGHBORS = 50;             // orbit glyph size comes from the spread of this many lots around the target
const GLYPH_LOT_FT = 100;               // placeholder: a lot this wide fills half the local point spacing at size 1
const FLY_NEIGHBORS = 300;              // clicking a lot zooms until about this many lots are in view
const WAKE_IN_MS = 90;                  // hovered point grows to full size this fast
const WAKE_OUT_MS = 700;                // and shrinks back this slowly once the mouse leaves, leaving a wake
const WAKE_GROW = 2.2;                  // a fully hovered point is (1 + this) times its size
const ORIGIN = [-73.95, 40.7];
const POSITRON = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json';
const ORBIT0 = { target: [0, 0, 0], rotationX: 30, rotationOrbit: -30, zoom: 2.4, minZoom: -2, maxZoom: 16 };
const FT = 0.3048;

export class Viewer {
  constructor({ orbitEl, mapEl, store, onHover, onClick, onGlyphs = () => {} }) {
    this.store = store;
    this.N = store.N;
    this.orbitEl = orbitEl;
    this.mapEl = mapEl;
    this.pos = new Float32Array(this.N * 3);
    this.colors = new Uint8Array(this.N * 4);
    this.base = new Uint8Array(this.N * 4);
    this.mode = 'orbit';
    this.hidden = new Set();
    this.highlight = [];
    this.selected = -1;
    this.axes = null;
    this.pointSize = 1.6;     // pixels
    this.glyphSize = 1;       // multiplier on glyphUnit
    this.glyphUnit = null;    // orbit units per foot, set from local point spacing when glyphs turn on
    this.onGlyphs = onGlyphs;
    this.glyphData = { paths: [], polys: [], lots: [], pathsByLot: new Map() };
    this.hovered = -1;
    this.wake = new Map();    // lot -> 0..1, how far it has grown; see _hover
    this.orbitVS = ORBIT0;
    this._bump();

    // A point, or when glyphs are on, anywhere on the lot or its buildings.
    const pick = (info) => {
      const id = info?.layer?.id;
      if (id === 'points') return info.index;
      if (id?.startsWith('glyph-') && info.object) return info.object.i;
      return -1;
    };
    const hover = (info) => {
      const i = pick(info);
      this._hover(i);
      onHover(i, info);
    };
    this.deck = new Deck({
      parent: orbitEl,
      views: new OrbitView({ id: 'orbit', orbitAxis: 'Z', fovy: 50 }),
      initialViewState: ORBIT0,
      controller: true,
      onViewStateChange: ({ viewState }) => { this.orbitVS = viewState; this._scheduleGlyphs(); },
      onHover: hover,
      onClick: (info) => onClick(pick(info)),
      layers: []
    });

    // lon/lat offsets from ORIGIN, float32 keeps sub-meter precision this way
    this.mapPos = new Float32Array(this.N * 3);
    for (let i = 0; i < this.N; i++) {
      this.mapPos[i * 3] = store.lon[i] - ORIGIN[0];
      this.mapPos[i * 3 + 1] = store.lat[i] - ORIGIN[1];
    }
    // Top down only: no pitch, no rotation.
    this.map = new MapLibre({ container: mapEl, style: POSITRON, center: ORIGIN, zoom: 10, pitch: 0, maxPitch: 0,
      dragRotate: false, pitchWithRotate: false, touchPitch: false, attributionControl: { compact: true } });
    this.map.touchZoomRotate.disableRotation();
    this.map.keyboard.disableRotation();
    this.overlay = new MapboxOverlay({
      interleaved: false,
      layers: [],
      onHover: hover,
      onClick: (info) => onClick(pick(info))
    });
    this.map.addControl(this.overlay);
    this.map.on('moveend', () => this._scheduleGlyphs());
    // Never wait for `load`: redraw when it comes, and keep the size current (same source as above).
    this.map.on('load', () => { this.map.resize(); this.render(); });
    this.resizeObserver = new ResizeObserver(() => this.map.resize());
    this.resizeObserver.observe(mapEl);
  }

  destroy() {
    cancelAnimationFrame(this.wakeRaf);
    this.resizeObserver.disconnect();
    this.deck.finalize();
    this.map.remove();
  }

  _bump() {
    this.data = {
      length: this.N,
      attributes: {
        getPosition: { value: this.pos, size: 3 },
        getFillColor: { value: this.colors, size: 4, normalized: true }
      }
    };
  }

  // ---- positions -------------------------------------------------------------------------
  setPositions(target, mode) {
    cancelAnimationFrame(this.raf);
    const switching = mode !== this.mode;
    this.mode = mode;
    this.orbitEl.style.display = mode === 'orbit' ? '' : 'none';
    this.mapEl.style.display = mode === 'map' ? '' : 'none';
    if (mode === 'map') {
      this.pos.set(this.mapPos);
      this.map.resize();
    } else if (switching) {
      this.pos.set(target);
    }
    if (mode === 'map' || switching) {
      this._bump();
      this._clearGlyphs();
      this.render();
      this._scheduleGlyphs();
      return;
    }
    const from = this.pos.slice();
    const t0 = performance.now();
    this._clearGlyphs();
    const step = (now) => {
      const t = Math.min(1, (now - t0) / TRANSITION_MS);
      const e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      const pos = this.pos;
      for (let i = 0; i < pos.length; i++) pos[i] = from[i] + (target[i] - from[i]) * e;
      this._bump();
      this.render();
      if (t < 1) this.raf = requestAnimationFrame(step);
      else this._scheduleGlyphs();
    };
    this.raf = requestAnimationFrame(step);
  }

  setColors(base) {
    this.base.set(base);
    this._applyColors();
    if (this.hidden.size) this._scheduleGlyphs(0);   // rebuild glyphs in the new colors
  }

  _applyColors() {
    this.colors.set(this.base);
    for (const i of this.hidden) this.colors[i * 4 + 3] = 0;
    this._bump();
    this.render();
  }

  setAxes(axes) {
    this.axes = axes;
    this.render();
  }

  setHighlight(selected, near) {
    this.selected = selected;
    this.highlight = near;
    this.render();
  }

  setPointSize(px) {
    this.pointSize = px;
    this.render();
  }

  setGlyphSize(s) {
    this.glyphSize = s;
    this._scheduleGlyphs(0);
  }

  // ---- hover wake: the hovered lot grows quickly, and lots the mouse has left shrink back
  // slowly. Only the lots in the wake are redrawn each frame (a small layer of their own). ---
  _hover(i) {
    if (i === this.hovered) return;
    this.hovered = i;
    if (i >= 0 && !this.wake.has(i)) this.wake.set(i, 0);
    if (this.wakeRaf) return;
    let last = performance.now();
    const tick = (now) => {
      const dt = now - last;
      last = now;
      let moving = false;
      for (const [j, h] of this.wake) {
        if (j === this.hovered) {
          if (h < 1) { this.wake.set(j, Math.min(1, h + dt / WAKE_IN_MS)); moving = true; }
        } else if (h - dt / WAKE_OUT_MS <= 0) {
          this.wake.delete(j);
          moving = true;
        } else {
          this.wake.set(j, h - dt / WAKE_OUT_MS);
          moving = true;
        }
      }
      if (moving) this.render();
      this.wakeRaf = moving ? requestAnimationFrame(tick) : 0;
    };
    this.wakeRaf = requestAnimationFrame(tick);
  }

  // ---- camera ----------------------------------------------------------------------------
  // Zooms in on lot i close enough for its glyph to show, tilted so the extrusions read as 3D.
  flyTo(i) {
    if (this.mode === 'map') {
      this.map.flyTo({ center: [this.store.lon[i], this.store.lat[i]], zoom: 17.5, duration: 1200 });
      return;
    }
    const pos = this.pos, N = this.N;
    const [tx, ty, tz] = [pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2]];
    const d2 = new Float32Array(N);
    for (let j = 0; j < N; j++) d2[j] = (pos[j * 3] - tx) ** 2 + (pos[j * 3 + 1] - ty) ** 2 + (pos[j * 3 + 2] - tz) ** 2;
    const r = Math.max(Math.sqrt(kth(d2, FLY_NEIGHBORS)), 1e-3);
    const half = Math.max(this.orbitEl.clientWidth, this.orbitEl.clientHeight) / 2;
    const vs = this.orbitVS;
    const rotationX = Math.abs(vs.rotationX) < 25 ? 35 : vs.rotationX;
    this.glyphUnit = null;   // re-derive glyph size at the destination
    this.deck.setProps({
      initialViewState: {
        ...vs, target: [tx, ty, tz], rotationX, zoom: Math.min(ORBIT0.maxZoom, Math.log2(half / r)),
        transitionDuration: 1200, transitionInterpolator: new LinearInterpolator(['target', 'zoom', 'rotationX'])
      }
    });
  }

  resetOrbit() {
    this.deck.setProps({ initialViewState: { ...ORBIT0, transitionDuration: 800, transitionInterpolator: new LinearInterpolator(['target', 'zoom', 'rotationX', 'rotationOrbit']) } });
  }

  // ---- layers ----------------------------------------------------------------------------
  render() {
    const map = this.mode === 'map';
    const coord = map
      ? { coordinateSystem: COORDINATE_SYSTEM.LNGLAT_OFFSETS, coordinateOrigin: [ORIGIN[0], ORIGIN[1], 0] }
      : { coordinateSystem: COORDINATE_SYSTEM.CARTESIAN };
    const pos = this.pos;
    const at = (i) => [pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2]];
    // Points face the camera. Unbillboarded circles lie flat in the XY plane and vanish edge-on,
    // which showed as an empty band at the camera's height.
    const layers = [
      new ScatterplotLayer({
        id: 'points', data: this.data, ...coord, billboard: true,
        radiusUnits: 'pixels', getRadius: this.pointSize, radiusMinPixels: 1, stroked: false, pickable: true
      })
    ];
    const g = this.glyphData;
    if (g.paths.length) {
      // The faint lot fill is there to be hovered and clicked: the whole lot picks, not just its point.
      layers.push(new SolidPolygonLayer({
        id: 'glyph-lots', data: g.lots, ...coord, getPolygon: (d) => d.ring, getFillColor: (d) => d.color, pickable: true
      }));
      layers.push(new PathLayer({
        id: 'glyph-outlines', data: g.paths, ...coord, getPath: (d) => d.path,
        getColor: [82, 81, 78, 200], widthUnits: 'pixels', getWidth: 1
      }));
      layers.push(new SolidPolygonLayer({
        id: 'glyph-buildings', data: g.polys, ...coord, extruded: true, pickable: true,
        getPolygon: (d) => d.rings, getElevation: (d) => d.h, getFillColor: (d) => d.color,
        material: { ambient: 0.5, diffuse: 0.6, shininess: 8 }
      }));
    }
    if (this.wake.size) {
      // Points in the wake grow and turn opaque; lots drawn as glyphs get a darker outline instead.
      const c = this.base, dots = [], outlines = [];
      for (const [i, h] of this.wake) {
        const e = h * (2 - h);   // ease out
        if (!this.hidden.has(i)) dots.push({ i, e });
        else for (const p of g.pathsByLot.get(i) || []) outlines.push({ path: p.path, e });
      }
      layers.push(new ScatterplotLayer({
        id: 'wake', data: dots, ...coord, billboard: true, radiusUnits: 'pixels',
        getPosition: (d) => at(d.i), getRadius: (d) => this.pointSize * (1 + WAKE_GROW * d.e),
        getFillColor: (d) => [c[d.i * 4], c[d.i * 4 + 1], c[d.i * 4 + 2], 140 + 115 * d.e],
        stroked: true, lineWidthUnits: 'pixels', getLineWidth: 1,
        getLineColor: (d) => [...INK, d.i === this.hovered ? 255 * d.e : 0]
      }));
      layers.push(new PathLayer({
        id: 'wake-outlines', data: outlines, ...coord, getPath: (d) => d.path, widthUnits: 'pixels',
        getWidth: (d) => 1 + 1.5 * d.e, getColor: (d) => [...INK, 255 * d.e]
      }));
    }
    if (this.highlight.length || this.selected >= 0) {
      const ring = this.highlight.map((i) => ({ i, sel: false }));
      if (this.selected >= 0) ring.push({ i: this.selected, sel: true });
      layers.push(new ScatterplotLayer({
        id: 'highlight', data: ring, ...coord, billboard: true, getPosition: (d) => at(d.i),
        radiusUnits: 'pixels', getRadius: (d) => (d.sel ? 9 : 5), stroked: true, filled: false,
        lineWidthUnits: 'pixels', getLineWidth: (d) => (d.sel ? 2.5 : 1.5), getLineColor: [...INK, 230],
        updateTriggers: { getPosition: this.data }
      }));
    }
    if (!map && this.axes) {
      layers.push(new LineLayer({
        id: 'axes', data: this.axes.lines, getSourcePosition: (d) => d.from, getTargetPosition: (d) => d.to,
        getColor: [82, 81, 78, 160], getWidth: 1
      }));
      layers.push(new TextLayer({
        id: 'axis-labels', data: this.axes.labels, getPosition: (d) => d.position, getText: (d) => d.text,
        getSize: (d) => (d.title ? 13 : 11), getColor: [...INK, 220], getTextAnchor: (d) => d.anchor || 'middle',
        fontFamily: "'Roboto Mono', ui-monospace, monospace", characterSet: 'auto',
        background: true, getBackgroundColor: [244, 244, 242, 220], backgroundPadding: [2, 1]
      }));
    }
    if (map) {
      this.overlay.setProps({ layers });
      this.deck.setProps({ layers: [] });
    } else {
      this.deck.setProps({ layers });
      this.overlay.setProps({ layers: [] });
    }
  }

  // ---- glyphs: lot outlines and extruded footprints when zoomed in -----------------------
  _scheduleGlyphs(delay = 250) {
    clearTimeout(this.glyphTimer);
    this.glyphTimer = setTimeout(() => this._updateGlyphs(), delay);
  }

  _clearGlyphs() {
    this.glyphToken = (this.glyphToken || 0) + 1;
    if (this.hidden.size) {
      this.hidden = new Set();
      this.colors.set(this.base);
      this._bump();
    }
    this.glyphData = { paths: [], polys: [], lots: [], pathsByLot: new Map() };
    this.glyphUnit = null;
    this.onGlyphs(false);
  }

  // Lots in view, nearest the camera target first, or [] if more than the trigger are in view.
  // `spread` is the distance from the target to its GLYPH_NEIGHBORS-th nearest lot (orbit only).
  _nearInView() {
    const pos = this.pos, N = this.N;
    const { trigger, cap } = GLYPHS[this.mode];
    const cand = [];
    const none = { lots: [], spread: 0 };
    if (this.mode === 'map') {
      const c = this.map.getCenter(), z = this.map.getZoom();
      const mpp = (40075016.686 * Math.cos((c.lat * Math.PI) / 180)) / (512 * 2 ** z);
      const w = this.mapEl.clientWidth / 2 * mpp, h = this.mapEl.clientHeight / 2 * mpp;
      const dx = w / (111320 * Math.cos((c.lat * Math.PI) / 180)), dy = h / 110540;
      const cx = c.lng - ORIGIN[0], cy = c.lat - ORIGIN[1];
      for (let i = 0; i < N; i++) {
        const ox = pos[i * 3] - cx, oy = pos[i * 3 + 1] - cy;
        if (Math.abs(ox) < dx && Math.abs(oy) < dy) {
          cand.push([i, (ox / dx) ** 2 + (oy / dy) ** 2]);
          if (cand.length >= trigger) return none;
        }
      }
    } else {
      const vs = this.orbitVS, [tx, ty, tz] = vs.target;
      const r = Math.max(this.orbitEl.clientWidth, this.orbitEl.clientHeight) / 2 / 2 ** vs.zoom;
      const r2 = r * r;
      for (let i = 0; i < N; i++) {
        const d = (pos[i * 3] - tx) ** 2 + (pos[i * 3 + 1] - ty) ** 2 + (pos[i * 3 + 2] - tz) ** 2;
        if (d < r2) {
          cand.push([i, d]);
          if (cand.length >= trigger) return none;
        }
      }
    }
    cand.sort((a, b) => a[1] - b[1]);
    const spread = cand.length ? Math.sqrt(cand[Math.min(GLYPH_NEIGHBORS, cand.length) - 1][1]) : 0;
    const out = [], shards = new Set();
    for (const [i] of cand) {
      const s = Math.floor(i / 1000);
      if (!shards.has(s) && shards.size >= GLYPH_MAX_SHARDS) continue;
      shards.add(s);
      out.push(i);
      if (out.length >= cap) break;
    }
    return { lots: out, spread };
  }

  async _updateGlyphs() {
    const { lots, spread } = this._nearInView();
    const token = ++this.glyphToken;
    if (!lots.length) {
      if (this.glyphData.paths.length || this.hidden.size) {
        this._clearGlyphs();
        this._applyColors();
      }
      return;
    }
    const size = this.store.m.glyphs.shard_size;
    const shardIds = [...new Set(lots.map((i) => Math.floor(i / size)))];
    const shards = new Map();
    await Promise.all(shardIds.map(async (s) => shards.set(s, await this.store.glyphShard(s))));
    if (token !== this.glyphToken) return;

    const q = this.store.m.glyphs.quant_ft;
    const map = this.mode === 'map';
    // Orbit glyphs are sized to the point spacing around the target when they first turn on, then
    // keep that size while they stay on, so zooming in makes them grow like the rest of the scene.
    if (!map && this.glyphUnit == null) {
      const spacing = spread * Math.cbrt((4 * Math.PI) / 3 / GLYPH_NEIGHBORS);
      this.glyphUnit = Math.max(spacing, 1e-4) * 0.5 / GLYPH_LOT_FT;
    }
    const pos = this.pos, sc = this.glyphUnit * this.glyphSize;
    const paths = [], polys = [], fills = [], pathsByLot = new Map();
    const c = this.base;
    for (const i of lots) {
      const s = Math.floor(i / size), g = shards.get(s), j = i - s * size;
      const px = pos[i * 3], py = pos[i * 3 + 1], pz = pos[i * 3 + 2];
      const fill = [c[i * 4], c[i * 4 + 1], c[i * 4 + 2], 45];
      const kx = map ? (q * FT) / (111320 * Math.cos((this.store.lat[i] * Math.PI) / 180)) : q * sc;
      const ky = map ? (q * FT) / 110540 : q * sc;
      const ring = (xy, a, b) => {
        const out = new Array(b - a);
        for (let k = a; k < b; k++) out[k - a] = [px + xy[k * 2] * kx, py + xy[k * 2 + 1] * ky, pz];
        return out;
      };
      const own = [];
      for (let r = g.lotRing[j]; r < g.lotRing[j + 1]; r++) {
        const p = { i, path: ring(g.outlineXY, g.ringCoord[r], g.ringCoord[r + 1]) };
        paths.push(p);
        own.push(p);
        fills.push({ i, ring: p.path, color: fill });   // holes fill too; it only needs to be hoverable
      }
      pathsByLot.set(i, own);
      for (let p = g.lotPoly[j]; p < g.lotPoly[j + 1]; p++) {
        const rings = [];
        for (let r = g.polyRing[p]; r < g.polyRing[p + 1]; r++) {
          rings.push(ring(g.polyXY, g.polyRingCoord[r], g.polyRingCoord[r + 1]));
        }
        const hft = g.heights[p] === 65535 ? 0 : g.heights[p] * 0.1;
        polys.push({ i, rings, h: map ? hft * FT : hft * sc, color: [c[i * 4], c[i * 4 + 1], c[i * 4 + 2], 235] });
      }
    }
    this.glyphData = { paths, polys, lots: fills, pathsByLot };
    this.hidden = new Set(lots);
    this._applyColors();
    this.onGlyphs(true);
  }
}

// k-th smallest value (0-based); sorts `a` in place.
function kth(a, k) {
  a.sort();
  return a[Math.min(k, a.length - 1)];
}
