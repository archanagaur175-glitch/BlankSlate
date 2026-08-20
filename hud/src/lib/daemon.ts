import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { writable, type Writable } from "svelte/store";

export interface ConStatus {
  connected: boolean;
  detail: string;
}

export interface AgentEvent {
  kind: "tool" | "step" | "reply";
  label: string;
  detail?: string;
}

export interface Turn {
  role: "user" | "assistant";
  text: string;
}

interface WakeHit {
  model?: string;
  score?: number;
}

export const connected: Writable<boolean> = writable(false);
export const conDetail: Writable<string> = writable("connecting…");
export const listening: Writable<boolean> = writable(true);
export const status: Writable<string> = writable("idle");
export const rms: Writable<number> = writable(0);
export const transcript: Writable<string> = writable("");
export const lastWake: Writable<WakeHit | null> = writable(null);
export const lastTurn: Writable<Turn | null> = writable(null);
export const agentEvents: Writable<AgentEvent[]> = writable([]);
export const recallDigest: Writable<string> = writable("");

let unlisteners: UnlistenFn[] = [];

export async function initDaemon(): Promise<void> {
  for (const un of unlisteners) {
    un();
  }
  unlisteners = [];
  unlisteners.push(
    await listen<string>("daemon_event", (e) => {
      try {
        applyDaemonEvent(JSON.parse(String(e.payload)) as Record<string, unknown>);
      } catch {
        /* ignore malformed frames */
      }
    }),
  );
  unlisteners.push(
    await listen<ConStatus>("daemon_status", (e) => {
      const s = e.payload as ConStatus;
      connected.set(!!s?.connected);
      conDetail.set(s?.detail ?? "unknown");
    }),
  );

  const status_ = await invoke<ConStatus>("get_daemon_status");
  connected.set(!!status_?.connected);
  conDetail.set(status_?.detail ?? "unknown");
}

export async function sendCommand(payload: Record<string, unknown>): Promise<void> {
  await invoke("send_message", { payload: JSON.stringify(payload) });
}

export async function setListening(value: boolean): Promise<void> {
  listening.set(value);
  await sendCommand({ type: "set_listening", value });
}

function applyDaemonEvent(ev: Record<string, unknown>): void {
  switch (ev.type) {
    case "welcome":
      status.set("ready");
      break;
    case "state":
      listening.set(Boolean(ev.listening));
      status.set(String(ev.status ?? "idle"));
      break;
    case "levels":
      rms.set(Number(ev.rms ?? 0) * 4);
      break;
    case "transcript":
      if (ev.source === "voice" || ev.source === "dictation") {
        transcript.set(String(ev.text ?? ""));
        if (ev.final) {
          lastTurn.set({ role: "user", text: String(ev.text ?? "") });
        }
      }
      break;
    case "wake":
      lastWake.set({
        model: String(ev.model ?? ""),
        score: Number(ev.score ?? 0),
      });
      break;
    case "intent":
      if ((ev.source_input as string) === "voice") {
        // visible only for debugging; keep the UI clean otherwise
      }
      break;
    case "recall_digest":
      recallDigest.set(String(ev.summary ?? ""));
      break;
    case "agent.agent_start": {
      agentEvents.update((list) => [
        ...list,
        { kind: "step", label: String(ev.query ?? "") },
      ]);
      break;
    }
    case "agent.plan_step": {
      agentEvents.update((list) => [
        ...list,
        { kind: "step", label: `step ${ev.index}: ${String(ev.step ?? "")}` },
      ]);
      break;
    }
    case "agent.tool_call": {
      agentEvents.update((list) => [
        ...list,
        {
          kind: "tool",
          label: String(ev.name ?? ""),
          detail: JSON.stringify(ev.arguments ?? {}),
        },
      ]);
      break;
    }
    case "agent.step_result": {
      agentEvents.update((list) => [...list, { kind: "reply", label: String(ev.result ?? "") }]);
      break;
    }
    case "agent.agent_reply": {
      lastTurn.set({ role: "assistant", text: String(ev.text ?? "") });
      agentEvents.update((list) => [
        ...list,
        { kind: "reply", label: String(ev.text ?? "") },
      ]);
      break;
    }
    default:
      if (String(ev.type ?? "").startsWith("agent.")) {
        agentEvents.update((list) => [
          ...list,
          { kind: "step", label: `agent: ${String(ev.type)}` },
        ]);
      }
  }
}