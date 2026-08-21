<script lang="ts">
  import { onMount } from "svelte";
  import TitleBar from "./components/TitleBar.svelte";
  import VuMeter from "./components/VuMeter.svelte";
  import {
    agentEvents,
    connected,
    conDetail,
    lastTurn,
    lastWake,
    listening,
    recallDigest,
    rms,
    status,
    transcript,
    wakeEnabled,
    pttActive,
    initDaemon,
    setListening,
    setWake,
    startDictation,
    stopDictation,
    sendCommand,
    type AgentEvent,
  } from "./lib/daemon";

  let theme = $state(
    (localStorage.getItem("blankslate-theme") as string) || "dark",
  );

  function toggleTheme() {
    theme = theme === "dark" ? "light" : "dark";
    localStorage.setItem("blankslate-theme", theme);
    document.documentElement.dataset.theme = theme;
  }

  function toggleListening() {
    void setListening(!$listening);
  }

  function toggleWake() {
    void setWake(!$wakeEnabled);
  }

  function clearAgentLog() {
    agentEvents.set([]);
  }

  function chipClass(e: AgentEvent): string {
    return e.kind;
  }

  function statusLabel(s: string): string {
    if ($pttActive) {
      return "Dictating…";
    }
    switch (s) {
      case "capturing":
        return "Listening…";
      case "processing":
        return "Thinking…";
      case "ready":
        return "Ready";
      default:
        return "Idle";
    }
  }

  let pttPressed = $state(false);

  function pttDown() {
    pttPressed = true;
    void startDictation();
  }

  function pttUp() {
    if (!pttPressed) {
      return;
    }
    pttPressed = false;
    void stopDictation();
  }

  onMount(() => {
    // Refresh status on mount; the Rust side auto-reconnects every 2s.
    void initDaemon();
    const timer = setInterval(() => {
      void sendCommand({ type: "ping" });
    }, 15000);
    return () => clearInterval(timer);
  });
</script>

<main class="shell">
  <TitleBar theme={theme} onToggleTheme={toggleTheme} />

  <section class="hero">
    <div class="orb {$status == 'capturing' || $pttActive ? 'capturing' : ''}">
      <div class="orb-inner {$status == 'capturing' || $pttActive ? 'pulse' : ''}">
        <span class="mic">{$status == 'capturing' || $pttActive ? '🎙️' : '●'}</span>
      </div>
      <VuMeter level={$rms} listening={$listening} />
    </div>
    <div class="state-row">
      <span class="dot {$connected ? 'ok' : 'warn'}"></span>
      <span class="state-text">{$connected ? statusLabel($status) : "daemon offline"}</span>
    </div>
    <span class="detail">{$conDetail}</span>
  </section>

  <section class="feed">
    {#if $lastWake}
      <div class="chip wake">
        wake: {$lastWake.model} ({($lastWake.score ?? 0).toFixed(2)})
      </div>
    {/if}

    {#if $lastTurn && $lastTurn.role === 'user'}
      <div class="turn user">{$lastTurn.text}</div>
    {/if}

    {#if $transcript}
      <div class="transcript">{$transcript}</div>
    {/if}

    <div class="event-list" aria-live="polite">
      {#each $agentEvents.slice(-12) as e (e.label + e.kind)}
        <div class="chip {chipClass(e)}">{e.label}{e.detail ? ` · ${e.detail}` : ''}</div>
      {/each}
    </div>

    {#if $lastTurn && $lastTurn.role === 'assistant'}
      <div class="turn assistant">{$lastTurn.text}</div>
    {/if}

    {#if $recallDigest}
      <div class="digest">recall: {$recallDigest}</div>
    {/if}
  </section>

  <footer class="controls">
    <button class="pill primary" onclick={toggleListening}>
      {$status == 'capturing' ? 'Listening…' : $listening ? 'Pause' : 'Resume'}
    </button>
    <button
      class="pill ptt {$pttActive ? 'active' : ''}"
      onpointerdown={pttDown}
      onpointerup={pttUp}
      onpointerleave={pttUp}
    >
      {$pttActive ? 'Release to send' : 'Push to talk'}
    </button>
    <button class="pill" onclick={toggleWake}>
      Wake: {$wakeEnabled ? 'on' : 'off'}
    </button>
    <button class="pill" onclick={clearAgentLog}>Clear log</button>
  </footer>
</main>

<style>
  .shell {
    display: flex;
    flex-direction: column;
    height: 100%;
    background: var(--bg);
    border: 1px solid var(--stroke);
    border-radius: var(--radius);
    overflow: hidden;
    backdrop-filter: blur(24px) saturate(1.4);
    -webkit-backdrop-filter: blur(24px) saturate(1.4);
  }

  .hero {
    padding: 18px 20px 10px;
    text-align: center;
  }
  .orb {
    margin: 6px auto 12px;
    width: 96px;
    height: 96px;
    display: grid;
    place-items: center;
  }
  .orb-inner {
    width: 84px;
    height: 84px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    background:
      radial-gradient(circle at 32% 28%, var(--accent-soft), transparent 70%),
      var(--bg-elev);
    border: 1px solid var(--stroke);
    transition: transform 0.25s ease;
  }
  .orb.capturing .orb-inner {
    transform: scale(1.12);
    border-color: var(--accent);
    box-shadow:
      0 0 28px var(--accent-soft),
      inset 0 0 22px var(--accent-soft);
  }
  .pulse {
    animation: pulse 1.4s ease-in-out infinite;
  }
  @keyframes pulse {
    0%,
    100% {
      box-shadow: 0 0 10px var(--accent-soft);
    }
    50% {
      box-shadow: 0 0 30px var(--accent);
    }
  }
  .mic {
    font-size: 24px;
    color: var(--fg);
  }
  .state-row {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    font-weight: 600;
  }
  .dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--warn);
  }
  .dot.ok {
    background: var(--ok);
    box-shadow: 0 0 8px var(--ok);
  }
  .dot.warn {
    background: var(--warn);
  }
  .detail {
    color: var(--fg-muted);
    font-size: 12px;
    margin-top: 4px;
  }

  .feed {
    flex: 1;
    overflow-y: auto;
    padding: 6px 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .turn {
    padding: 10px 12px;
    border-radius: 10px;
    background: var(--bg-elev);
    border: 1px solid var(--stroke);
    line-height: 1.45;
  }
  .turn.user {
    align-self: flex-end;
    background: var(--accent-soft);
    border-color: transparent;
  }
  .turn.assistant {
    align-self: flex-start;
  }
  .transcript {
    color: var(--fg-muted);
    font-style: italic;
    font-size: 13px;
  }
  .event-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .chip {
    font-size: 12px;
    padding: 4px 8px;
    border-radius: 8px;
    background: var(--bg-elev);
    border: 1px solid var(--stroke);
    color: var(--fg-muted);
    overflow-wrap: anywhere;
  }
  .chip.tool {
    border-left: 3px solid var(--accent);
  }
  .chip.step {
    color: var(--warn);
  }
  .chip.reply {
    color: var(--ok);
  }
  .digest {
    font-size: 12px;
    color: var(--fg-muted);
    border-top: 1px dashed var(--stroke);
    padding-top: 6px;
  }

  .controls {
    display: flex;
    gap: 10px;
    padding: 12px 16px;
    border-top: 1px solid var(--stroke);
  }
  .pill {
    flex: 1;
    padding: 10px;
    border-radius: 10px;
    border: 1px solid var(--stroke);
    background: var(--bg-elev);
    color: var(--fg);
    font-weight: 600;
    cursor: pointer;
  }
  .pill.primary {
    background: linear-gradient(135deg, var(--accent), #4a62c4);
    color: #fff;
    border-color: transparent;
  }
  .pill.ptt.active {
    background: var(--accent-soft);
    border-color: var(--accent);
    color: var(--fg);
  }
  .pill:active {
    transform: scale(0.98);
  }
</style>