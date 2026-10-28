// Axis and color scaling: optional sign-preserving log, percentile clip, rescale to [0, 1].
export const slog = (v) => Math.sign(v) * Math.log1p(Math.abs(v));
export const unslog = (v) => Math.sign(v) * Math.expm1(Math.abs(v));

// Percentiles from a strided sample (fast on 857k values).
function percentiles(vals, ps, log) {
  const step = Math.max(1, Math.floor(vals.length / 100000));
  const s = [];
  for (let i = 0; i < vals.length; i += step) {
    const v = vals[i];
    if (Number.isFinite(v)) s.push(log ? slog(v) : v);
  }
  if (!s.length) return ps.map(() => 0);
  s.sort((a, b) => a - b);
  return ps.map((p) => s[Math.min(s.length - 1, Math.floor((p / 100) * (s.length - 1)))]);
}

// Returns { t: Float32Array in [0,1] (NaN missing), lo, hi, ticks: [value at 0, .5, 1] in field units }
export function normalize(vals, { log = false, clip = [1, 99] } = {}) {
  const [lo, hi0] = clip ? percentiles(vals, clip, log) : percentiles(vals, [0, 100], log);
  const hi = hi0 > lo ? hi0 : lo + 1;
  const t = new Float32Array(vals.length);
  for (let i = 0; i < vals.length; i++) {
    const v = vals[i];
    if (!Number.isFinite(v)) { t[i] = NaN; continue; }
    const x = ((log ? slog(v) : v) - lo) / (hi - lo);
    t[i] = x < 0 ? 0 : x > 1 ? 1 : x;
  }
  const back = (x) => (log ? unslog(x) : x);
  return { t, lo, hi, ticks: [back(lo), back((lo + hi) / 2), back(hi)] };
}

export function fmt(v, unit = '') {
  if (v == null || !Number.isFinite(v)) return '—';
  const a = Math.abs(v);
  let s;
  if (unit === 'year') s = String(Math.round(v));
  else if (unit === '°') s = v.toFixed(3);
  else if (a >= 1e9) s = `${(v / 1e9).toFixed(1)}B`;
  else if (a >= 1e6) s = `${(v / 1e6).toFixed(1)}M`;
  else if (a >= 1e4) s = `${(v / 1e3).toFixed(0)}k`;
  else if (a >= 100) s = Math.round(v).toLocaleString('en-US');
  else if (a >= 1) s = v.toFixed(1);
  else s = v.toFixed(2);
  if (unit === 'share') return `${(v * 100).toFixed(0)}%`;
  if (unit === '$') return `$${s}`;
  return unit && !['year', '°', 'count', 'ratio'].includes(unit) ? `${s} ${unit}` : s;
}
