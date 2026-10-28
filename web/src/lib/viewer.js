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
export const GLYPH_TRIGGER = 5000;      // placeholder: fewer points than this in view -> glyphs
export const GLYPH_CAP = 3000;          // placeholder
const GLYPH_MAX_SHARDS = 150;           // fetch limit per update (shards follow BBL order, see README)
const ORIGIN = [-73.95, 40.7];
const POSITRON = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json';
const ORBIT0 = { target: [0, 0, 0], rotationX: 30, rotationOrbit: -30, zoom: 2.4, minZoom: -2, maxZoom: 14 };
const FT = 0.3048;

export class Viewer {
  constructor({ orbitEl, mapEl, store, onHover, onClick }) {
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
    this.glyphScale = 0.02;   // orbit units per foot
    this.glyphData = { paths: [], polys: [] };
    this.orbitVS = ORBIT0;
    this._bump();

    const pick = (info) => (info && info.layer && info.layer.id === 'points' && info.index >= 0 ? info.index : -1);
    this.deck = new Deck({
      parent: orbitEl,
      views: new OrbitView({ id: 'orbit', orbitAxis: 'Z', fovy: 50 }),
      initialViewState: ORBIT0,
      controller: true,
      onViewStateChange: ({ viewState }) => { this.orbitVS = viewState; this._scheduleGlyphs(); },
      onHover: (info) => onHover(pick(info), info),
      onClick: (info) => onClick(pick(info)),
      layers: []
    });

    // lon/lat offsets from ORIGIN, float32 keeps sub-meter precision this way
    this.mapPos = new Float32Array(this.N * 3);
    for (let i = 0; i < this.N; i++) {
      this.mapPos[i * 3] = store.lon[i] - ORIGIN[0];
      this.mapPos[i * 3 + 1] = store.lat[i] - ORIGIN[1];
    }
    this.map = new MapLibre({ container: mapEl, style: POSITRON, center: ORIGIN, zoom: 10, pitch: 40,
      attributionControl: { compact: true } });
    this.overlay = new MapboxOverlay({
      interleaved: false,
      layers: [],
      onHover: (info) => onHover(pick(info), info),
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

  setGlyphScale(s) {
    this.glyphScale = s;
    this._scheduleGlyphs(0);
  }

  // ---- camera ----------------------------------------------------------------------------
  flyTo(i) {
    if (this.mode === 'map') {
      this.map.flyTo({ center: [this.store.lon[i], this.store.lat[i]], zoom: 17.5, pitch: 50, duration: 1200 });
    } else {
      const target = [this.pos[i * 3], this.pos[i * 3 + 1], this.pos[i * 3 + 2]];
      this.deck.setProps({
        initialViewState: {
          ...this.orbitVS, target, zoom: Math.max(this.orbitVS.zoom, 6),
          transitionDuration: 1200, transitionInterpolator: new LinearInterpolator(['target', 'zoom'])
        }
      });
    }
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
    const layers = [
      new ScatterplotLayer({
        id: 'points', data: this.data, ...coord,
        radiusUnits: 'pixels', getRadius: 1.6, radiusMinPixels: 1, stroked: false, pickable: true
      })
    ];
    if (this.glyphData.paths.length) {
      layers.push(new PathLayer({
        id: 'glyph-outlines', data: this.glyphData.paths, ...coord, getPath: (d) => d.path,
        getColor: [82, 81, 78, 200], widthUnits: 'pixels', getWidth: 1
      }));
      layers.push(new SolidPolygonLayer({
        id: 'glyph-buildings', data: this.glyphData.polys, ...coord, extruded: true,
        getPolygon: (d) => d.rings, getElevation: (d) => d.h, getFillColor: (d) => d.color,
        material: { ambient: 0.5, diffuse: 0.6, shininess: 8 }
      }));
    }
    if (this.highlight.length || this.selected >= 0) {
      const ring = this.highlight.map((i) => ({ i, sel: false }));
      if (this.selected >= 0) ring.push({ i: this.selected, sel: true });
      layers.push(new ScatterplotLayer({
        id: 'highlight', data: ring, ...coord, getPosition: (d) => at(d.i),
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
        fontFamily: 'system-ui, -apple-system, Segoe UI, sans-serif', characterSet: 'auto',
        background: true, getBackgroundColor: [252, 252, 251, 200], backgroundPadding: [2, 1]
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
    this.glyphData = { paths: [], polys: [] };
  }

  // Lots in view, nearest the camera target first, or [] if more than GLYPH_TRIGGER are in view.
  _nearInView() {
    const pos = this.pos, N = this.N;
    const cand = [];
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
          if (cand.length >= GLYPH_TRIGGER) return [];
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
          if (cand.length >= GLYPH_TRIGGER) return [];
        }
      }
    }
    cand.sort((a, b) => a[1] - b[1]);
    const out = [], shards = new Set();
    for (const [i] of cand) {
      const s = Math.floor(i / 1000);
      if (!shards.has(s) && shards.size >= GLYPH_MAX_SHARDS) continue;
      shards.add(s);
      out.push(i);
      if (out.length >= GLYPH_CAP) break;
    }
    return out;
  }

  async _updateGlyphs() {
    const lots = this._nearInView();
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
    const pos = this.pos, sc = this.glyphScale;
    const paths = [], polys = [];
    for (const i of lots) {
      const s = Math.floor(i / size), g = shards.get(s), j = i - s * size;
      const px = pos[i * 3], py = pos[i * 3 + 1], pz = pos[i * 3 + 2];
      const kx = map ? (q * FT) / (111320 * Math.cos((this.store.lat[i] * Math.PI) / 180)) : q * sc;
      const ky = map ? (q * FT) / 110540 : q * sc;
      const ring = (xy, a, b) => {
        const out = new Array(b - a);
        for (let k = a; k < b; k++) out[k - a] = [px + xy[k * 2] * kx, py + xy[k * 2 + 1] * ky, pz];
        return out;
      };
      for (let r = g.lotRing[j]; r < g.lotRing[j + 1]; r++) {
        paths.push({ path: ring(g.outlineXY, g.ringCoord[r], g.ringCoord[r + 1]) });
      }
      for (let p = g.lotPoly[j]; p < g.lotPoly[j + 1]; p++) {
        const rings = [];
        for (let r = g.polyRing[p]; r < g.polyRing[p + 1]; r++) {
          rings.push(ring(g.polyXY, g.polyRingCoord[r], g.polyRingCoord[r + 1]));
        }
        const hft = g.heights[p] === 65535 ? 0 : g.heights[p] * 0.1;
        const c = this.base;
        polys.push({ rings, h: map ? hft * FT : hft * sc, color: [c[i * 4], c[i * 4 + 1], c[i * 4 + 2], 235] });
      }
    }
    this.glyphData = { paths, polys };
    this.hidden = new Set(lots);
    this._applyColors();
  }
}
