import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [svelte()],
  // Svelte 5 exports `mount` from the client entry only under the `browser`
  // condition; Vite's production build otherwise falls back to the SSR stub
  // (which throws "mount not available on the server"), leaving a blank window.
  resolve: {
    conditions: ["browser", "module", "import", "default"],
  },
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    watch: { ignored: ["**/src-tauri/**"] },
  },
  build: { target: "es2021" },
});