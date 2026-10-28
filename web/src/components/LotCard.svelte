<script>
  import { ACS_NOTE, MISSING, LOTS_LIKE_THIS } from '../lib/strings.js';
  import { fmt } from '../lib/scale.js';

  // d: details record; extra: { cluster, acs: {label: value...} | null }
  let { d, extra, codes, onsimilar, onclose } = $props();

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
  <div class="card">
    <button class="x" type="button" onclick={onclose} aria-label="Close">×</button>
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
      <p class="note">{ACS_NOTE}</p>
    {/if}
    <button type="button" class="primary" onclick={onsimilar}>{LOTS_LIKE_THIS}</button>
  </div>
{/if}

<style>
  .card { position: relative; }
  h2 { font-size: 15px; margin: 0 24px 2px 0; }
  h3 { font-size: 12px; margin: 10px 0 4px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-secondary); }
  .bbl { color: var(--text-secondary); font-size: 12px; margin-bottom: 8px; }
  dl { display: grid; grid-template-columns: max-content 1fr; gap: 3px 10px; margin: 0; font-size: 12.5px; }
  dt { color: var(--text-secondary); }
  dd { margin: 0; }
  .x { position: absolute; top: -4px; right: -4px; border: 0; background: none; font-size: 18px; line-height: 1; padding: 4px 6px; }
  .note { font-size: 11.5px; color: var(--text-secondary); margin: 6px 0 0; }
  .primary { margin-top: 10px; width: 100%; }
</style>
