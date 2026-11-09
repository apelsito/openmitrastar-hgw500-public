import { createPortal } from "preact/compat";
import { useEffect, useState } from "preact/hooks";
import { CHANNEL_CATALOGUE, describeChannel } from "./channel-policy.ts";
import type { ChannelWidth } from "./channel-policy.ts";
import { durationLabel, loadDfsObservation } from "./dfs-observation.ts";
import type { DfsObservation } from "./dfs-observation.ts";
import { ApiError } from "./transport.ts";
import "./classic/dfs-console.css";

const phaseLabels: Record<string, string> = { running: "Escuchando antes de transmitir", required: "Pendiente de iniciar", complete: "Completado según el driver", "not-required": "No requerido en este canal", unknown: "Sin lectura de CAC", inconsistent: "Lectura incoherente" };

function DfsConsole() {
  const [reading, setReading] = useState<DfsObservation | null>(null);
  const [received, setReceived] = useState<number | null>(null);
  const [stale, setStale] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const [selected, setSelected] = useState(36);
  const [width, setWidth] = useState<ChannelWidth>(80);
  const [selectionNote, setSelectionNote] = useState("");

  useEffect(() => {
    let disposed = false, inFlight = false, nativeSeen = false;
    let retryCount = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let ageTimer: ReturnType<typeof setTimeout> | undefined;
    const visible = () => !document.hidden && document.getElementById("page-wifi")?.hidden === false;
    const refresh = async (force = false) => {
      if (disposed || inFlight || (!force && !visible())) return;
      inFlight = true; setBusy(true);
      try {
        const next = await loadDfsObservation();
        if (disposed) return;
        setReading(next); setReceived(Date.now()); setError(""); setStale(false);
        nativeSeen = next.kind === "native"; retryCount = 0;
        clearTimeout(ageTimer);
        ageTimer = setTimeout(() => { if (!disposed) setStale(true); }, 45000);
        // Older firmware needs the heavier diagnostics fallback: manual only.
        if (next.kind === "native") timer = setTimeout(() => void refresh(), 15000);
      } catch (failure) {
        if (!disposed) { setError(failure instanceof Error ? failure.message : "No se pudo leer DFS."); setStale(true); }
        if (!disposed && nativeSeen && !(failure instanceof ApiError && failure.code === "auth")) {
          retryCount++; timer = setTimeout(() => void refresh(), Math.min(60000, 15000 * 2 ** Math.min(retryCount, 2)));
        }
      } finally { inFlight = false; if (!disposed) setBusy(false); }
    };
    const activate = () => { clearTimeout(timer); if (visible()) void refresh(); };
    const onVisibility = () => { if (document.hidden) { clearTimeout(timer); setStale(true); } else activate(); };
    const onRefresh = () => { clearTimeout(timer); void refresh(true); };
    const page = document.getElementById("page-wifi");
    const observer = new MutationObserver(activate);
    if (page) observer.observe(page, { attributes: true, attributeFilter: ["hidden"] });
    document.addEventListener("visibilitychange", onVisibility);
    document.getElementById("refresh")?.addEventListener("click", onRefresh);
    void refresh(true);
    return () => { disposed = true; clearTimeout(timer); clearTimeout(ageTimer); observer.disconnect();
      document.removeEventListener("visibilitychange", onVisibility); document.getElementById("refresh")?.removeEventListener("click", onRefresh); };
  }, [refreshToken]);

  const channel = describeChannel(selected, width);
  const mode = error ? "Sin conexión" : stale ? "Lectura anterior" : reading?.simulation ? "Simulación · sin RF" : reading ? "Lectura del backend" : "Consultando";
  const backend = !reading || reading.backendReady === null ? "Sin confirmar" : reading.backendReady ? "Preparado" : "Proveedor pendiente";
  const running = reading?.detectorRunning === true ? (reading.detectorLiveness === true ? "Actividad verificada por el backend" : "Marcado activo; continuidad sin verificar") : reading?.detectorRunning === false ? "Detector detenido" : "Actividad no publicada";
  const tx = reading?.txAuthorized === false ? "No autorizado" : reading?.txAuthorized === true ? "Autorizado según el backend" : "Permiso no demostrado";
  const inspect = (value: number) => { setSelected(value); setSelectionNote(""); };
  const sendToForm = () => {
    const channelInput = document.querySelector<HTMLSelectElement>("#r5-channel");
    const widthInput = document.querySelector<HTMLSelectElement>("#r5-bandwidth");
    if (!channelInput || !widthInput) return;
    if (Number(widthInput.value) !== width) {
      setSelectionNote(`Selecciona primero ${width} MHz en el formulario de radio y revisa su impacto.`);
      return;
    }
    if (!Array.from(channelInput.options).some(option => Number(option.value) === selected)) {
      setSelectionNote("El formulario no ofrece este canal. Se mantiene como inspección."); return;
    }
    document.querySelector<HTMLButtonElement>('.band-button[data-radio-target="5g"]')?.click();
    document.querySelector<HTMLButtonElement>('.radio-form[data-radio="5g"] .config-tab[data-pane="radio"]')?.click();
    channelInput.focus(); channelInput.value = String(selected);
    channelInput.dispatchEvent(new Event("input", { bubbles: true }));
    setSelectionNote("Canal llevado al formulario. Revisa y prepara allí la transacción; no se ha aplicado ningún cambio.");
  };

  return <section id="dfs-console" class="dfs-console" aria-labelledby="dfs-console-title">
    <div class="dfs-console-heading"><div><span class="eyebrow">5 GHz · radar y disponibilidad</span><h2 id="dfs-console-title">Cada canal, con su estado real</h2><p>Inspecciona el espectro y distingue la selección del permiso para transmitir.</p></div><div class="dfs-console-actions"><span class={`status-pill ${error || stale || reading?.simulation ? "warning" : ""}`} role="status">{mode}</span><button type="button" class="secondary" disabled={busy} onClick={() => setRefreshToken(value => value + 1)}>{busy ? "Leyendo…" : "Actualizar DFS"}</button></div></div>
    {error && <p class="dfs-read-error" role="alert">{error} Los controles conservan las restricciones del firmware.</p>}
    {stale && received && <p class="dfs-stale" role="status">La última lectura ya no acredita el estado actual. Actualiza antes de decidir.</p>}
    <div class="dfs-phases">
      <article><span class="dfs-phase-label">01 · Detector</span><strong>{backend}</strong><p>{running}</p></article>
      <article><span class="dfs-phase-label">02 · CAC</span><strong>{phaseLabels[reading?.cac.state ?? "unknown"]}</strong><p>{reading?.cac.remaining != null ? `${durationLabel(reading.cac.remaining)} restantes en la lectura` : "Tiempo restante no publicado"}</p></article>
      <article><span class="dfs-phase-label">03 · No ocupación</span><strong>{reading?.nop.active === true ? "Canal en NOP" : reading?.nop.active === false && reading.nop.complete ? "Sin NOP en la lectura" : "Sin inventario completo"}</strong><p>{reading?.nop.entries.length ? reading.nop.entries.map(entry => `Canal ${entry.channel} · ${durationLabel(entry.remaining)}`).join("; ") : reading?.nop.complete ? "No hay canales en espera en esta lectura." : "El firmware no publica la lista completa de canales en espera."}</p></article>
      <article><span class="dfs-phase-label">04 · Transmisión</span><strong>{tx}</strong><p>{reading?.simulation ? "Estado simulado; no hay emisión física." : "Un detector preparado no acredita CAC ni permiso de TX."}</p></article>
    </div>
    <div class="dfs-observation-line"><span>Canal observado <b>{reading?.channel ?? "—"}</b></span><span>Ancho <b>{reading?.bandwidth ? `${reading.bandwidth} MHz` : "—"}</b></span><span>Región observada <b>{reading?.region ?? "No publicada"}</b></span><span>{received ? `Leído a las ${new Date(received).toLocaleTimeString("es-ES")}` : "Sin lectura todavía"}</span></div>
    <div class="dfs-spectrum-heading"><div><h3>Explorar canales</h3><p>Elige un ancho para ver su ocupación y el CAC previsto por el perfil ES.</p></div><div class="dfs-widths" role="group" aria-label="Ancho para inspección">{([20, 40, 80] as const).map(value => <button type="button" aria-pressed={width === value} onClick={() => { setWidth(value); setSelectionNote(""); }}>{value} MHz</button>)}</div></div>
    <div class="dfs-channel-grid" role="group" aria-label="Canales de 5 GHz para inspección">{CHANNEL_CATALOGUE.map(value => {
      const info = describeChannel(value, width);
      const label = info.category === "non-dfs" ? "Sin DFS" : info.category === "weather-dfs" ? "CAC 10 min" : info.category === "dfs" ? "CAC 60 s" : "Inspección";
      return <button type="button" class={`dfs-channel ${info.category}`} aria-pressed={selected === value} aria-label={`Canal ${value}, ${label}${reading?.channel === value ? ", observado" : ""}`} onClick={() => inspect(value)}><strong>{value}</strong><small>{label}</small>{reading?.channel === value && <span class="dfs-channel-current">Observado</span>}</button>;
    })}</div>
    <div class="dfs-selection"><div><span class="eyebrow">Selección para revisar</span><h3>Canal {selected} <span>· {width} MHz</span></h3><p>{channel.reason}</p><dl><div><dt>Bloque nominal</dt><dd>{channel.lowMHz !== null ? `${channel.lowMHz}–${channel.highMHz} MHz` : "No documentado"}</dd></div><div><dt>CAC mínimo del perfil</dt><dd>{channel.cacSeconds === 0 ? "No requerido" : durationLabel(channel.cacSeconds)}</dd></div><div><dt>NOP tras radar</dt><dd>{channel.nopSeconds ? durationLabel(channel.nopSeconds) : "No aplica al perfil"}</dd></div></dl></div><button type="button" class="secondary" onClick={sendToForm}>Llevar al formulario</button></div>
    {selectionNote && <p class="dfs-selection-note" role="status">{selectionNote}</p>}
    <p class="dfs-footnote">La selección no cambia la radio. CAC y NOP se observan en el backend; esta consola no los acorta ni los da por completados con un temporizador local. El firmware valida cada transacción.</p>
    <details class="dfs-evidence"><summary>Procedencia y límites de esta lectura</summary><p>{reading?.endpoint ?? "/api/v1/radios/5g/dfs"} · {reading?.kind === "legacy" ? "Contrato anterior: no publica todos los estados." : "Contrato de observación DFS."}</p><p>Los valores no publicados se conservan como desconocidos. La región, la calibración y la aceptación física no se cambian desde este panel.</p></details>
  </section>;
}

export default function ClassicDfs() {
  const [target, setTarget] = useState<HTMLElement | null>(null);
  useEffect(() => {
    const policy = document.querySelector<HTMLElement>(".channel-policy");
    if (!policy) return;
    const mount = document.createElement("div"); mount.className = "dfs-console-mount";
    policy.before(mount); setTarget(mount);
    const link = document.createElement("a"); link.className = "section-link";
    link.href = "#developer/wifi/dfs-console"; link.dataset.page = "wifi";
    link.dataset.focus = "dfs-console"; link.dataset.minMode = "advanced";
    const mark = document.createElement("span"); mark.className = "nav-mark";
    mark.textContent = "≈"; mark.setAttribute("aria-hidden", "true");
    link.append(mark, "Canales y DFS");
    document.querySelector('.section-nav .section-link[data-focus="5g"]')?.after(link);
    return () => { mount.remove(); link.remove(); };
  }, []);
  return target ? createPortal(<DfsConsole />, target) : null;
}
