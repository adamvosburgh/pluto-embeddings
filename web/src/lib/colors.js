// Colors follow the dataviz reference palette (light mode, the Positron basemap is light).
// Categorical slots in fixed order; clusters past slot 8 fold into one "other" gray.
// Sequential: one blue ramp, steps 250 -> 700. Missing values: neutral gray in every mode.
const hex = (h) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];

export const CATEGORICAL = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'].map(hex);
export const OTHER = hex('#7d7c76');
export const MISSING = hex('#c9c8c2');
export const RAMP = ['#86b6ef', '#6da7ec', '#5598e7', '#3987e5', '#2a78d6', '#256abf', '#1c5cab', '#184f95', '#104281', '#0d366b'].map(hex);
export const SURFACE = '#f4f4f2';
export const INK = [11, 11, 11];

export function clusterColor(c) {
  return c < CATEGORICAL.length ? CATEGORICAL[c] : OTHER;
}

// t in [0, 1] -> ramp color
export function ramp(t) {
  const x = Math.min(1, Math.max(0, t)) * (RAMP.length - 1);
  const i = Math.min(RAMP.length - 2, Math.floor(x));
  const f = x - i, a = RAMP[i], b = RAMP[i + 1];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}

export const css = (c) => `rgb(${c[0] | 0},${c[1] | 0},${c[2] | 0})`;
export const rampCss = `linear-gradient(to right, ${RAMP.map((c) => css(c)).join(',')})`;
