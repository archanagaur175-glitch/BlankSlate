<script lang="ts">
  let { level, listening }: { level: number; listening: boolean } = $props();

  const bars = Array.from({ length: 28 });
  const capped = $derived(Math.min(1, Math.max(0, level)));

  function barOpacity(i: number): number {
    const reach = i / bars.length;
    if (capped <= 0) return 0.06;
    if (Math.abs(i - capped * bars.length) < 1) return 1;
    return i <= capped * bars.length ? 0.25 + 0.75 * (1 - i / bars.length) : 0.06;
  }
</script>

<div class="vu {listening ? 'on' : 'off'}">
  {#each bars as _, i}
    <span class="bar" style="opacity: {barOpacity(i)}"></span>
  {/each}
</div>

<style>
  .vu {
    display: flex;
    align-items: flex-end;
    gap: 2px;
    height: 34px;
    margin-top: 6px;
  }
  .bar {
    flex: 1;
    height: 100%;
    border-radius: 2px;
    background: linear-gradient(180deg, var(--accent), #4a62c4);
    transition: opacity 90ms linear;
  }
  .vu.off .bar {
    background: var(--fg-muted);
  }
</style>