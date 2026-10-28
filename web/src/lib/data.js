// Loads the files written by data/scripts/09_export.py. Everything is lot_index order.
const BASE = `${import.meta.env.BASE_URL}data/`;

async function get(path, kind) {
  const r = await fetch(BASE + path);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return kind === 'json' ? r.json() : r.arrayBuffer();
}

export class Store {
  constructor(manifest) {
    this.m = manifest;
    this.N = manifest.n_lots;
    this.fields = new Map(manifest.fields.map((f) => [f.key, f]));
    this.files = new Map();     // file name -> Promise<ArrayBuffer>
    this.details = new Map();   // shard -> Promise<array>
    this.glyphs = new Map();    // shard -> Promise<parsed>
    this.decoded = new Map();   // field key -> Float32Array (NaN = missing)
    this.variants = new Map(manifest.variants.map((v) => [v.key, v]));
    this.acs = null;
  }

  static async open() {
    return new Store(await get('manifest.json', 'json'));
  }

  file(name) {
    if (!this.files.has(name)) this.files.set(name, get(name));
    return this.files.get(name);
  }

  async loadLots() {
    const N = this.N;
    const buf = await this.file('lots.bin');
    this.bbl = new Float64Array(buf, 0, N);
    this.lon = new Float32Array(buf, N * 8, N);
    this.lat = new Float32Array(buf, N * 12, N);
    this.bg = new Uint16Array(buf, N * 16, N);
  }

  async raw(key) {
    const f = this.fields.get(key);
    const buf = await this.file(f.file);
    return new Uint16Array(buf, f.offset, this.N);
  }

  // Decoded values as Float32Array with NaN for missing. Cached.
  async values(key) {
    if (this.decoded.has(key)) return this.decoded.get(key);
    const f = this.fields.get(key);
    const q = await this.raw(key);
    const out = new Float32Array(this.N);
    for (let i = 0; i < this.N; i++) out[i] = q[i] === 65535 ? NaN : f.min + q[i] * f.scale;
    this.decoded.set(key, out);
    return out;
  }

  async layout(v) {
    return new Float32Array(await this.file(this.variants.get(v).layout));
  }

  async latent(v) {
    return new Int8Array(await this.file(this.variants.get(v).latent));
  }

  async loadAcs() {
    if (!this.acs) this.acs = get(this.m.acs_bg.file, 'json');
    return this.acs;
  }

  detail(i) {
    const s = Math.floor(i / this.m.details.shard_size);
    if (!this.details.has(s)) this.details.set(s, get(`${this.m.details.dir}/${s}.json`, 'json'));
    return this.details.get(s).then((rows) => rows[i - s * this.m.details.shard_size]);
  }

  glyphShard(s) {
    if (!this.glyphs.has(s)) this.glyphs.set(s, get(`${this.m.glyphs.dir}/${s}.bin`).then(parseGlyphs));
    return this.glyphs.get(s);
  }

  findBbl(bbl) {
    let lo = 0, hi = this.N - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (this.bbl[mid] === bbl) return mid;
      if (this.bbl[mid] < bbl) lo = mid + 1; else hi = mid - 1;
    }
    return -1;
  }
}

// Layout documented in manifest.glyphs.layout.
function parseGlyphs(buf) {
  const h = new Int32Array(buf, 0, 8);
  const [n, nR, nRC, nP, nPR, nPC] = h;
  let o = 32;
  const i32 = (len) => { const a = new Int32Array(buf, o, len); o += len * 4; return a; };
  const lotRing = i32(n + 1), ringCoord = i32(nR + 1), lotPoly = i32(n + 1), polyRing = i32(nP + 1), polyRingCoord = i32(nPR + 1);
  const heights = new Uint16Array(buf, o, nP);
  o += (nP + (nP % 2)) * 2;
  const outlineXY = new Int16Array(buf, o, nRC * 2);
  o += nRC * 4;
  const polyXY = new Int16Array(buf, o, nPC * 2);
  return { n, lotRing, ringCoord, lotPoly, polyRing, polyRingCoord, heights, outlineXY, polyXY };
}
