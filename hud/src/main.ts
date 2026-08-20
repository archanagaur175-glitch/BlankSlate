import { mount } from "svelte";
import "./app.css";
import App from "./App.svelte";

const target = document.getElementById("app");
if (!target) {
  throw new Error("missing #app mount point");
}

mount(App, { target });

// Persist the theme across restarts (the <html> attribute is set first paint).
const saved = localStorage.getItem("blankslate-theme") ?? "dark";
document.documentElement.dataset.theme = saved;