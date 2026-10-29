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
  .fs { position: relative; display: flex; align-items: center; gap: 0.4rem; }
  .lbl { width: 1rem; font-size: 0.7rem; font-weight: 700; }
  .cur { flex: 1; text-align: left; display: flex; justify-content: space-between; min-width: 0; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; color: var(--text-primary); }
  .caret { color: var(--text-faint); margin-left: 0.4rem; }
  .pop { position: absolute; z-index: 20; top: 100%; left: 1.4rem; right: 0; margin-top: -1px; background: var(--surface-1); border: 1px solid var(--rule); }
  input { width: 100%; box-sizing: border-box; border: 0; border-bottom: 1px solid #eee; padding: 0.35rem 0.5rem; font: inherit; font-size: 0.7rem; background: transparent; color: inherit; }
  .list { max-height: 300px; overflow-y: auto; padding: 0.2rem 0; }
  .grp { font-size: 0.6rem; text-transform: lowercase; letter-spacing: 0.06em; color: var(--text-faint); padding: 0.45rem 0.5rem 0.15rem; }
  .opt { display: block; width: 100%; text-align: left; border: 0; background: none; padding: 0.15rem 0.75rem; font-size: 0.68rem; color: var(--text-primary); }
  .opt:hover:not(:disabled), .opt.on { background: var(--hover); }
  .opt.on { font-weight: 700; }
  .unit { color: var(--text-faint); font-size: 0.6rem; }
</style>
