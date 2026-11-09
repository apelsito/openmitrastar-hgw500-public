import { requestApi } from "./transport.ts";

/** An explicit emulator-only label; never changes any radio capability. */
export async function installClassicLabLabel(doc: Document): Promise<() => void> {
  if (!["127.0.0.1", "localhost", "[::1]"].includes(doc.location.hostname)) return () => {};
  try {
    const state = await requestApi("/api/v1/lab");
    if (state.schema !== "lyoko.emulator.lab/v1" || state.radio_simulation !== true || state.rf_transmission !== false) return () => {};
    const badge = doc.createElement("span"); badge.className = "status-pill warning";
    badge.textContent = "Laboratorio simulado · sin RF";
    doc.querySelector(".top-actions")?.prepend(badge);
    const heading = doc.querySelector<HTMLParagraphElement>("#page-wifi .page-heading p");
    const oldHeading = heading?.textContent ?? "";
    if (heading) heading.textContent = "Laboratorio simulado: aplica y revierte canales virtuales. No hay emisión ni asociaciones físicas.";
    const backend = doc.getElementById("dfs-risk-backend");
    const message = "Proveedor DFS simulado para probar el flujo. No detecta radar físico ni transmite RF.";
    const observer = new MutationObserver(() => { if (backend && backend.textContent !== message) backend.textContent = message; });
    if (backend) { observer.observe(backend, { childList: true }); backend.textContent = message; }
    return () => { observer.disconnect(); badge.remove(); if (heading) heading.textContent = oldHeading; };
  } catch { return () => {}; }
}
