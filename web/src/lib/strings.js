// Strings from build doc §6, used as written. Strings added during the build are below the line.
export const ACS_NOTE = 'Note: high margin of error for block-group level data.';
export const SIMILARITY_LEGEND = 'Distance in embedding space (nearer = more alike).';
export const MISSING = '—';

// ---- added during the build (listed in the summary for review) ----
export const VIEW_LABELS = { embedding: 'Embedding', custom: 'Custom axes', map: 'Map', year: 'Year built' };
export const COLOR_LABELS = { cluster: 'Cluster', field: 'A field', similarity: 'Similarity' };
export const LOTS_LIKE_THIS = 'Lots like this one';
export const OTHER_CLUSTERS = 'Other clusters';
export const NO_LOT = 'No lot with that BBL.';
export const diagBg = (s) => `Same block group among a lot's 20 nearest neighbors: ${pct(s)}.`;
export const diagBoro = (acc, base) =>
  `Borough guessed from the 20 nearest neighbors: ${pct(acc)} correct (largest borough alone: ${pct(base)}).`;
export const trainLine = (t) =>
  `Latent ${t.settings.latent}, ${t.settings.epochs} epochs; held-out loss ${t.held_out_total.toFixed(3)} ` +
  `(predicting the mean: ${t.baseline_total.toFixed(3)}).`;

function pct(x) {
  return `${Math.round(x * 100)}%`;
}
