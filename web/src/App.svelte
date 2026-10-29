<script>
  import { onMount, onDestroy } from 'svelte';
  import { Store } from './lib/data.js';
  import { Viewer } from './lib/viewer.js';
  import { normalize, fmt } from './lib/scale.js';
  import { distances, nearest } from './lib/similarity.js';
  import { clusterColor, CATEGORICAL, OTHER, MISSING as MISSING_RGB, ramp, css, rampCss } from './lib/colors.js';
  import * as S from './lib/strings.js';
  import FieldSelect from './components/FieldSelect.svelte';
  import LotCard from './components/LotCard.svelte';

  const N_NEAREST = 50;                 // placeholder
  const CLIP = [1, 99];                 // placeholder percentile clip
  const ALPHA = 200;
  const YEAR = { x: { key: 'lon', log: false, clip: true }, y: { key: 'lat', log: false, clip: true }, z: { key: 'YearBuilt', log: false, clip: true } };
  const CARD_MEDIANS = ['med_rent', 'med_value', 'med_year_built', 'med_age'];

  // Large arrays live outside Svelte state.
  let store, viewer, dist = null;
  const layouts = new Map();
  const LUT = Array.from({ length: 256 }, (_, k) => ramp(k / 255));

  let orbitEl = $state(), mapEl = $state();
  let manifest = $state.raw(null);
  let status = $state('Loading…');
  let view = $state('embedding');
  let variant = $state('pluto');
  let colorMode = $state('cluster');
  let colorField = $state('BldgArea');
  let axes = $state({ x: { key: 'lon', log: false, clip: true }, y: { key: 'lat', log: false, clip: true }, z: { key: 'BldgArea', log: false, clip: true } });
  let selected = $state(-1);
  let card = $state.raw(null);
  let cardExtra = $state.raw({ cluster: null, acs: null });
  let near = $state.raw([]);
  let panelOpen = $state(true);
  let pointSize = $state(1.6);
  let glyphLog = $state(0);     // log2 of the glyph size multiplier
  let glyphsOn = $state(false);
  let bblInput = $state('');
  let bblMsg = $state('');
  let tip = $state.raw(null);
  let legend = $state.raw(null);
  let busy = $state(false);

  const vmeta = $derived(manifest?.variants.find((v) => v.key === variant));
  const isAcs = $derived(!!vmeta && vmeta.acs_groups.length > 0);
  const fieldList = $derived(manifest ? manifest.fields : []);
  const groups = $derived(manifest ? manifest.field_groups : []);

  onMount(async () => {
    try {
      store = await Store.open();
      manifest = store.m;
      status = 'Loading lots…';
      await store.loadLots();
      viewer = new Viewer({ orbitEl, mapEl, store, onHover, onClick, onGlyphs: (on) => (glyphsOn = on) });
      await applyView();
      await recolor();
      status = '';
      store.loadAcs();   // in the background, for tooltips and cards
    } catch (e) {
      status = `Could not load data: ${e.message}. Run the pipeline first (see README).`;
      console.error(e);
    }
  });
  onDestroy(() => viewer?.destroy());

  // ---- positions ---------------------------------------------------------------------------
  async function layout(v) {
    if (!layouts.has(v)) layouts.set(v, await store.layout(v));
    return layouts.get(v);
  }

  async function axisPositions(spec) {
    const N = store.N, pos = new Float32Array(N * 3);
    const dims = ['x', 'y', 'z'];
    const norms = [];
    for (const d of dims) {
      const a = spec[d];
      norms.push(normalize(await store.values(a.key), { log: a.log, clip: a.clip ? CLIP : null }));
    }
    for (let k = 0; k < 3; k++) {
      const t = norms[k].t;
      for (let i = 0; i < N; i++) pos[i * 3 + k] = (Number.isFinite(t[i]) ? t[i] : 0) * 100 - 50;
    }
    const lines = [], labels = [];
    const o = [-50, -50, -50];
    dims.forEach((d, k) => {
      const end = [...o]; end[k] = 50;
      lines.push({ from: o, to: end });
      const f = store.fields.get(spec[d].key);
      const off = k === 2 ? [-6, -6, 0] : k === 0 ? [0, -9, 0] : [-9, 0, 0];
      norms[k].ticks.forEach((v, j) => {
        const p = [...o]; p[k] = -50 + j * 50;
        labels.push({ position: [p[0] + off[0] * 0.5, p[1] + off[1] * 0.5, p[2] + off[2]], text: fmt(v, f.unit) });
      });
      const tp = [...o]; tp[k] = 58;
      labels.push({ position: tp, text: `${f.label}${spec[d].log ? ' (log)' : ''}`, title: true });
    });
    return { pos, axes: { lines, labels } };
  }

  async function applyView() {
    busy = true;
    try {
      if (view === 'map') {
        viewer.setAxes(null);
        viewer.setPositions(null, 'map');
      } else if (view === 'embedding') {
        const L = await layout(variant);
        viewer.setAxes(null);
        viewer.setPositions(L, 'orbit');
      } else {
        const { pos, axes: a } = await axisPositions(view === 'year' ? YEAR : axes);
        viewer.setAxes(a);
        viewer.setPositions(pos, 'orbit');
      }
    } finally {
      busy = false;
    }
  }

  // ---- color -----------------------------------------------------------------------------
  async function recolor() {
    const N = store.N, out = new Uint8Array(N * 4);
    const put = (i, c) => { out[i * 4] = c[0]; out[i * 4 + 1] = c[1]; out[i * 4 + 2] = c[2]; out[i * 4 + 3] = ALPHA; };
    if (colorMode === 'similarity' && dist) {
      const n = normalize(dist, { clip: [0, 95] });
      for (let i = 0; i < N; i++) put(i, LUT[Math.round((1 - n.t[i]) * 255)]);
      legend = { type: 'similarity', lo: n.ticks[0], hi: n.ticks[2] };
    } else if (colorMode === 'field') {
      const f = store.fields.get(colorField);
      const n = normalize(await store.values(colorField), { clip: CLIP });
      for (let i = 0; i < N; i++) put(i, Number.isFinite(n.t[i]) ? LUT[Math.round(n.t[i] * 255)] : MISSING_RGB);
      legend = { type: 'ramp', label: f.label, lo: fmt(n.ticks[0], f.unit), hi: fmt(n.ticks[2], f.unit) };
    } else {
      const c = await store.values(`cluster_${variant}`);
      for (let i = 0; i < N; i++) put(i, Number.isFinite(c[i]) ? clusterColor(c[i]) : MISSING_RGB);
      const sizes = vmeta.diagnostics.cluster_sizes;
      legend = {
        type: 'cluster',
        items: CATEGORICAL.map((col, k) => ({ color: css(col), label: `Cluster ${k + 1}`, n: sizes[k] })).filter((x) => x.n != null),
        other: sizes.length > CATEGORICAL.length ? { color: css(OTHER), label: `${S.OTHER_CLUSTERS} (${CATEGORICAL.length + 1}–${sizes.length})`, n: sizes.slice(CATEGORICAL.length).reduce((a, b) => a + b, 0) } : null
      };
    }
    viewer.setColors(out);
  }

  // ---- selection, card, similarity ---------------------------------------------------------
  async function cardDetails(i) {
    const cl = (await store.values(`cluster_${variant}`))[i];
    let acs = null;
    if (isAcs && store.bg[i] !== 65535) {
      const a = await store.loadAcs();
      const row = a.rows[store.bg[i]];
      const labels = manifest.acs_bg.labels;
      acs = CARD_MEDIANS.map((k) => ({ label: labels[k].label, unit: labels[k].unit, value: row[a.columns.indexOf(k)] }));
    } else if (isAcs) {
      acs = CARD_MEDIANS.map((k) => ({ label: manifest.acs_bg.labels[k].label, unit: '', value: null }));
    }
    return { cluster: Number.isFinite(cl) ? cl : null, acs };
  }

  async function select(i) {
    selected = i;
    near = [];
    dist = null;
    viewer.setHighlight(i, []);
    const [d, x] = await Promise.all([store.detail(i), cardDetails(i)]);
    if (selected !== i) return;
    card = d;
    cardExtra = x;
    if (colorMode === 'similarity') await similar();
  }

  async function similar() {
    if (selected < 0) return;
    busy = true;
    const i = selected;
    const latent = await store.latent(variant);
    dist = distances(latent, vmeta.latent_scale, i, store.N);
    const nn = nearest(dist, N_NEAREST, i);
    viewer.setHighlight(i, nn.map((x) => x[0]));
    colorMode = 'similarity';
    await recolor();
    busy = false;
    near = nn.map(([j, d]) => ({ i: j, d, address: null }));
    const rows = await Promise.all(nn.map(([j]) => store.detail(j)));
    if (selected === i) near = nn.map(([j, d], k) => ({ i: j, d, address: rows[k]?.address || `BBL ${store.bbl[j]}` }));
  }

  function clearSelection() {
    selected = -1;
    card = null;
    near = [];
    dist = null;
    viewer.setHighlight(-1, []);
    if (colorMode === 'similarity') { colorMode = 'cluster'; recolor(); }
  }

  function onClick(i) {
    if (i < 0) return;
    select(i);
    viewer.flyTo(i);
  }

  function onHover(i, info) {
    tip = i >= 0 ? { i, x: info.x, y: info.y } : null;
  }

  // The value the points are colored by, above the lot card in the tooltip.
  const tipLines = $derived.by(() => {
    if (!tip || !store) return [];
    const i = tip.i;
    const lines = [];
    if (colorMode === 'field') {
      const f = store.fields.get(colorField), v = store.decoded.get(colorField)?.[i];
      lines.push(`${f.label}: ${fmt(v, f.unit)}`);
    } else if (colorMode === 'similarity' && dist) {
      lines.push(`Distance: ${dist[i].toFixed(2)}`);
    } else {
      const c = store.decoded.get(`cluster_${variant}`)?.[i];
      if (Number.isFinite(c)) lines.push(`Cluster ${c + 1}`);
    }
    return lines;
  });
  // The same record as the lot card. Keyed on the lot, so moving within one lot doesn't refetch.
  let tipCard = $state.raw(null);
  const tipLot = $derived(tip ? tip.i : -1);
  $effect(() => {
    const i = tipLot;
    tipCard = null;
    if (i < 0) return;
    Promise.all([store.detail(i), cardDetails(i)]).then(([d, extra]) => {
      if (tipLot === i) tipCard = { d, extra };
    });
  });
  const TIP_W = 250;
  const tipPos = $derived.by(() => {
    if (!tip) return '';
    const left = tip.x + 14 + TIP_W > window.innerWidth ? tip.x - 14 - TIP_W : tip.x + 14;
    const top = Math.min(tip.y + 14, window.innerHeight - 330);
    return `left:${Math.max(4, left)}px; top:${Math.max(4, top)}px; width:${TIP_W}px`;
  });

  // ---- controls ----------------------------------------------------------------------------
  function setView(v) {
    view = v;
    if (v !== 'map') viewer.resetOrbit();
    applyView();
  }

  async function setVariant(v) {
    variant = v;
    if (view === 'embedding') await applyView();
    if (selected >= 0) {
      cardExtra = await cardDetails(selected);
      if (dist || near.length) { await similar(); return; }
    }
    if (colorMode === 'similarity') colorMode = 'cluster';
    await recolor();
  }

  function setColorMode(m) {
    if (m === 'similarity') { similar(); return; }
    colorMode = m;
    recolor();
  }

  function setAxis(d, patch) {
    axes = { ...axes, [d]: { ...axes[d], ...patch } };
    applyView();
  }

  function findBbl(e) {
    e.preventDefault();
    const n = Number(bblInput.replace(/\D/g, ''));
    const i = n ? store.findBbl(n) : -1;
    if (i < 0) { bblMsg = S.NO_LOT; return; }
    bblMsg = '';
    select(i);
    viewer.flyTo(i);
  }
</script>

<div class="stage">
  <div class="layer" bind:this={orbitEl}></div>
  <div class="layer" bind:this={mapEl} style="display:none"></div>
</div>

<aside class:collapsed={!panelOpen}>
  <button class="toggle" type="button" onclick={() => (panelOpen = !panelOpen)} aria-label="Toggle panel">{panelOpen ? '‹' : '›'}</button>
  {#if panelOpen}
    <div class="panel">
      <h1>PLUTO Embeddings</h1>
      {#if status}<p class="status">{status}</p>{/if}
      {#if manifest}
        <section>
          <h4>View</h4>
          <div class="seg">
            {#each Object.entries(S.VIEW_LABELS) as [k, l]}
              <button type="button" class:on={view === k} onclick={() => setView(k)}>{l}</button>
            {/each}
          </div>
          <label class="row">Point size
            <input type="range" min="0.5" max="6" step="0.1" bind:value={pointSize} oninput={() => viewer.setPointSize(pointSize)} />
          </label>
          {#if view !== 'map'}
            <label class="row">Lot size
              <input type="range" min="-2" max="2" step="0.1" bind:value={glyphLog} disabled={!glyphsOn}
                oninput={() => viewer.setGlyphSize(2 ** glyphLog)} />
            </label>
            {#if !glyphsOn}<p class="note">{S.GLYPH_HINT}</p>{/if}
          {/if}
        </section>

        <section>
          <h4>Embedding</h4>
          <div class="seg col2">
            {#each manifest.variants as v}
              <button type="button" class:on={variant === v.key} onclick={() => setVariant(v.key)}>{v.label}</button>
            {/each}
          </div>
          {#if isAcs}<p class="note">{S.ACS_NOTE}</p>{/if}
        </section>

        <section>
          <h4>Color by</h4>
          <div class="seg">
            {#each Object.entries(S.COLOR_LABELS) as [k, l]}
              <button type="button" class:on={colorMode === k} disabled={k === 'similarity' && selected < 0}
                onclick={() => setColorMode(k)}>{l}</button>
            {/each}
          </div>
          {#if colorMode === 'field'}
            <FieldSelect fields={fieldList} {groups} value={colorField} onchange={(k) => { colorField = k; recolor(); }} />
          {/if}
          {#if legend}
            <div class="legend">
              {#if legend.type === 'cluster'}
                {#each legend.items as it}
                  <div class="key"><span class="sw" style="background:{it.color}"></span>{it.label}<span class="n">{it.n.toLocaleString('en-US')}</span></div>
                {/each}
                {#if legend.other}
                  <div class="key"><span class="sw" style="background:{legend.other.color}"></span>{legend.other.label}<span class="n">{legend.other.n.toLocaleString('en-US')}</span></div>
                {/if}
              {:else if legend.type === 'ramp'}
                <div class="ramp" style="background:{rampCss}"></div>
                <div class="ends"><span>{legend.lo}</span><span>{legend.hi}</span></div>
                <div class="key"><span class="sw" style="background:{css(MISSING_RGB)}"></span>Missing</div>
              {:else}
                <div class="ramp" style="background:{rampCss}; transform: scaleX(-1)"></div>
                <div class="ends"><span>{legend.lo.toFixed(2)}</span><span>{legend.hi.toFixed(2)}+</span></div>
                <p class="note">{S.SIMILARITY_LEGEND}</p>
              {/if}
            </div>
          {/if}
        </section>

        {#if view === 'custom'}
          <section>
            <h4>Axes</h4>
            {#each ['x', 'y', 'z'] as d}
              <div class="axis">
                <FieldSelect fields={fieldList} {groups} label={d.toUpperCase()} value={axes[d].key} onchange={(k) => setAxis(d, { key: k })} />
                <div class="opts">
                  <label><input type="checkbox" checked={axes[d].log} onchange={(e) => setAxis(d, { log: e.currentTarget.checked })} /> log</label>
                  <label><input type="checkbox" checked={axes[d].clip} onchange={(e) => setAxis(d, { clip: e.currentTarget.checked })} /> clip {CLIP[0]}–{CLIP[1]}%</label>
                </div>
              </div>
            {/each}
          </section>
        {/if}

        <section>
          <h4>Find a lot by BBL</h4>
          <form onsubmit={findBbl} class="row">
            <input bind:value={bblInput} placeholder="e.g. 1000010001" inputmode="numeric" />
            <button type="submit">Go</button>
          </form>
          {#if bblMsg}<p class="note">{bblMsg}</p>{/if}
        </section>

        {#if near.length}
          <section>
            <h4>{S.LOTS_LIKE_THIS}</h4>
            <ol class="near">
              {#each near as n}
                <li><button type="button" onclick={() => { viewer.flyTo(n.i); }}>
                  <span>{n.address ?? '…'}</span><span class="n">{n.d.toFixed(2)}</span>
                </button></li>
              {/each}
            </ol>
          </section>
        {/if}

        {#if vmeta}
          <section>
            <h4>About this embedding</h4>
            <p class="note">{S.diagBg(vmeta.diagnostics.bg_overlap_20nn)}</p>
            <p class="note">{S.diagBoro(vmeta.diagnostics.borough_knn_accuracy, vmeta.diagnostics.borough_largest_share)}</p>
            <p class="note">{S.trainLine(vmeta.training)}</p>
          </section>
        {/if}
      {/if}
    </div>
  {/if}
</aside>

{#if card}
  <div class="cardwrap">
    <LotCard d={card} extra={cardExtra} codes={manifest.codes} onsimilar={similar} onclose={clearSelection} />
  </div>
{/if}

{#if tip}
  <div class="tip" style={tipPos}>
    {#each tipLines as l}<div class="val">{l}</div>{/each}
    {#if tipCard}
      <LotCard d={tipCard.d} extra={tipCard.extra} codes={manifest.codes} compact />
    {:else}
      <div class="dim">BBL {store.bbl[tip.i]}</div>
    {/if}
  </div>
{/if}

{#if busy}<div class="busy">Working…</div>{/if}
