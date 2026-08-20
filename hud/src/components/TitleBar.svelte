<script lang="ts">
  import { getCurrentWindow } from "@tauri-apps/api/window";

  let { theme, onToggleTheme }: { theme: string; onToggleTheme: () => void } = $props();

  const appWindow = getCurrentWindow();

  function min() {
    void appWindow.minimize();
  }
  function hide() {
    void appWindow.hide();
  }
</script>

<header class="titlebar" data-tauri-drag-region>
  <span class="brand">BlankSlate</span>
  <div class="actions">
    <button class="ctrl" title="Toggle theme" onclick={onToggleTheme}>
      {theme === "dark" ? "◐" : "◑"}
    </button>
    <button class="ctrl" title="Minimize to tray" onclick={min}>─</button>
    <button class="ctrl close" title="Hide to tray" onclick={hide}>✕</button>
  </div>
</header>

<style>
  .titlebar {
    height: var(--titlebar-h);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 8px 0 14px;
    border-bottom: 1px solid var(--stroke);
  }
  .brand {
    font-weight: 600;
    letter-spacing: 0.4px;
    color: var(--fg-muted);
  }
  .actions {
    display: flex;
    gap: 4px;
  }
  .ctrl {
    width: 28px;
    height: 26px;
    border: none;
    border-radius: 7px;
    background: transparent;
    color: var(--fg-muted);
    font-size: 13px;
    cursor: pointer;
    line-height: 1;
  }
  .ctrl:hover {
    background: var(--accent-soft);
    color: var(--fg);
  }
  .close:hover {
    background: var(--danger);
    color: #fff;
  }
</style>