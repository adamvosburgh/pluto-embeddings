<script>
  import { ACS_NOTE, MISSING, LOTS_LIKE_THIS } from '../lib/strings.js';
  import { fmt } from '../lib/scale.js';

  // d: details record; extra: { cluster, acs: {label: value...} | null }
  // compact: the hover tooltip's version, smaller and without buttons
  let { d, extra, codes, onsimilar, onclose, compact = false } = $props();

  const pad2 = (x) => (x == null ? null : String(x).padStart(2, '0'));
  const v = (x) => (x == null || x === '' ? MISSING : x);
  const landUse = $derived(d && d.landuse != null ? `${pad2(d.landuse)} · ${codes.LandUse[pad2(d.landuse)] ?? MISSING}` : MISSING);
  const bldg = $derived.by(() => {
    if (!d || !d.bldgclass) return MISSING;
    const full = codes.BldgClass[d.bldgclass];
    const grp = codes.BldgClassGroup[d.bldgclass[0]];
    return `${d.bldgclass} · ${grp ?? ''}${full ? ` — ${full}` : ''}`;
  });
  const species = $derived(d?.species?.length ? d.species.slice(0, 6).join(', ') + (d.species.length > 6 ? ', …' : '') : null);
</script>

{#if d}
  <div class="card" class:compact>
    {#if !compact}<button class="x" type="button" onclick={onclose} aria-label="Close">×</button>{/if}
    <h2>{v(d.address)}</h2>
    <div class="bbl">BBL {String(d.bbl)}</div>
    <dl>
      <dt>Land use</dt><dd>{landUse}</dd>
      <dt>Building class</dt><dd>{bldg}</dd>
      <dt>Zoning</dt><dd>{v(d.zone1)}{d.zone2 ? `, ${d.zone2}` : ''}</dd>
      <dt>Year built</dt><dd>{v(d.yearbuilt)}</dd>
      <dt>Floors</dt><dd>{v(d.floors)}</dd>
      <dt>Residential units</dt><dd>{v(d.unitsres)}</dd>
      <dt>Roof height (max)</dt><dd>{d.height_max == null ? MISSING : fmt(d.height_max, 'ft')}</dd>
      <dt>Frontage</dt><dd>{d.frontage_ft == null ? MISSING : fmt(d.frontage_ft, 'ft')}</dd>
      <dt>Trees on frontage</dt><dd>{v(d.trees_n)}{species ? ` (${species})` : ''}</dd>
      <dt>Cluster</dt><dd>{extra.cluster == null ? MISSING : extra.cluster + 1}</dd>
    </dl>
    {#if extra.acs}
      <h3>Block group</h3>
      <dl>
        {#each extra.acs as a}
          <dt>{a.label}</dt><dd>{a.value == null ? MISSING : fmt(a.value, a.unit)}</dd>
        {/each}
      </dl>
      {#if !compact}<p class="note">{ACS_NOTE}</p>{/if}
    {/if}
    {#if !compact}<button type="button" class="primary" onclick={onsimilar}>{LOTS_LIKE_THIS}</button>{/if}
  </div>
{/if}

<style>
  .card { position: relative; }
  h2 { font-size: 0.85rem; margin: 0 1.5rem 0.1rem 0; }
  h3 { font-size: 0.65rem; margin: 0.9rem 0 0.4rem; text-transform: lowercase; letter-spacing: 0.06em; font-weight: 700; }
  .bbl { color: var(--text-secondary); font-size: 0.68rem; margin-bottom: 0.7rem; }
  dl { display: grid; grid-template-columns: max-content 1fr; gap: 0.2rem 0.75rem; margin: 0; font-size: 0.7rem; }
  dt { color: var(--text-secondary); }
  dd { margin: 0; font-variant-numeric: tabular-nums; }
  .x { position: absolute; top: -0.4rem; right: -0.4rem; border: 0; background: none; font-size: 1rem; line-height: 1; padding: 0.2rem 0.35rem; color: var(--text-secondary); }
  .x:hover { color: var(--text-primary); background: none; }
  .note { font-size: 0.65rem; color: var(--text-secondary); margin: 0.4rem 0 0; }
  .primary { margin-top: 1rem; width: 100%; }

  .compact h2 { font-size: 0.7rem; margin: 0 0 0.05rem; }
  .compact .bbl { font-size: 0.58rem; margin-bottom: 0.35rem; }
  .compact h3 { font-size: 0.56rem; margin: 0.45rem 0 0.2rem; }
  .compact dl { font-size: 0.6rem; gap: 0.05rem 0.6rem; line-height: 1.4; }
</style>
