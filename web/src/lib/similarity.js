// Brute-force Euclidean distance from one lot to every lot in an int8 latent (N x dim).
export function distances(latent, scale, i, N) {
  const dim = scale.length;
  const q = new Float32Array(dim);
  for (let d = 0; d < dim; d++) q[d] = latent[i * dim + d] * scale[d];
  const out = new Float32Array(N);
  for (let j = 0, o = 0; j < N; j++) {
    let s = 0;
    for (let d = 0; d < dim; d++, o++) {
      const x = latent[o] * scale[d] - q[d];
      s += x * x;
    }
    out[j] = Math.sqrt(s);
  }
  return out;
}

// Indices of the k smallest distances, excluding `self`, nearest first.
export function nearest(dist, k, self) {
  const best = [];
  let worst = Infinity;
  for (let j = 0; j < dist.length; j++) {
    if (j === self) continue;
    const d = dist[j];
    if (best.length < k || d < worst) {
      best.push([j, d]);
      if (best.length > k) {
        best.sort((a, b) => a[1] - b[1]);
        best.length = k;
      }
      worst = best.length === k ? Math.max(...best.map((b) => b[1])) : Infinity;
    }
  }
  return best.sort((a, b) => a[1] - b[1]);
}
