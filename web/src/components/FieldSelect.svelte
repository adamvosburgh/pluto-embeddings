<script>
  // Searchable dropdown of every field in the manifest, grouped by its group.
  let { fields, groups, value, label = '', onchange } = $props();
  let open = $state(false);
  let query = $state('');
  let input = $state();

  const current = $derived(fields.find((f) => f.key === value));
  const filtered = $derived.by(() => {
    const q = query.trim().toLowerCase();
    return groups
      .map((g) => ({
        group: g,
        items: fields.filter((f) => f.group === g && (!q || f.label.toLowerCase().includes(q) || f.key.toLowerCase().includes(q)))
      }))
      .filter((g) => g.items.length);
  });

  function toggle() {
    open = !open;
    query = '';
    if (open) queueMicrotask(() => input?.focus());
  }
  function pick(key) {
    open = false;
    onchange(key);
  }
</script>

<div class="fs">
  {#if label}<span class="lbl">{label}</span>{/if}
  <button type="button" class="cur" onclick={toggle} aria-expanded={open}>
    {current ? current.label : value}<span class="caret">▾</span>
  </button>
  {#if open}
    <div class="pop">
      <input bind:this={input} bind:value={query} placeholder="Search fields"
        onkeydown={(e) => { if (e.key === 'Escape') open = false; if (e.key === 'Enter' && filtered[0]) pick(filtered[0].items[0].key); }} />
      <div class="list">
        {#each filtered as g}
          <div class="grp">{g.group}</div>
          {#each g.items as f}
            <button type="button" class="opt" class:on={f.key === value} onclick={() => pick(f.key)}>
              {f.label}{#if f.unit}<span class="unit"> {f.unit}</span>{/if}
            </button>
          {/each}
        {/each}
      </div>
    </div>
  {/if}
</div>

<style>
  .fs { position: relative; display: flex; align-items: center; gap: 6px; }
  .lbl { width: 14px; color: var(--text-secondary); font-weight: 600; }
  .cur { flex: 1; text-align: left; display: flex; justify-content: space-between; min-width: 0; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .caret { color: var(--text-secondary); margin-left: 6px; }
  .pop { position: absolute; z-index: 20; top: 100%; left: 20px; right: 0; margin-top: 2px; background: var(--surface-1);
    border: 1px solid var(--border); border-radius: 6px; box-shadow: 0 6px 20px rgb(0 0 0 / 0.12); }
  input { width: 100%; box-sizing: border-box; border: 0; border-bottom: 1px solid var(--border); padding: 6px 8px; font: inherit; background: transparent; color: inherit; }
  .list { max-height: 300px; overflow-y: auto; padding: 4px 0; }
  .grp { font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-secondary); padding: 6px 8px 2px; }
  .opt { display: block; width: 100%; text-align: left; border: 0; background: none; padding: 3px 12px; border-radius: 0; }
  .opt:hover, .opt.on { background: var(--hover); }
  .unit { color: var(--text-secondary); font-size: 11px; }
</style>
