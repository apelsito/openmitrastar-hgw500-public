import { useEffect } from "preact/hooks";
import { computed, signal } from "@preact/signals";
import { loadSnapshot } from "./api";
import { ApiError } from "./transport.ts";
import RadioWorkbench from "./radio-workbench";
import ChannelExplorer from "./channel-explorer";
import type { RadioState, Snapshot } from "./types";

const views = ["Resumen", "Radios", "Optimización", "Hardware", "Sistema", "Seguridad"] as const;
type View = (typeof views)[number];

const snapshot = signal<Snapshot | null>(null);
const busy = signal(true);
const loadError = signal<ApiError | null>(null);
let refreshing = false;
const activeView = signal<View>("Resumen");
const darkMode = signal(false);
const uptime = computed(() => {
  const total = snapshot.value?.uptimeSeconds ?? 0;
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  return `${hours} h ${minutes} min`;
});

const iconFor = (view: View) => view === "Radios" ? "radio" : view === "Hardware" ? "chip" : view === "Seguridad" ? "shield" : "pulse";

const Icon = ({ name }: { name: string }) => {
  const paths: Record<string, string> = {
    pulse: "M3 12h4l2-6 4 12 2-6h6",
    radio: "M5 9a10 10 0 0 1 14 0M8 12a6 6 0 0 1 8 0M11 15a2 2 0 0 1 2 0",
    shield: "M12 3l7 3v5c0 4.6-2.8 8-7 10-4.2-2-7-5.4-7-10V6z",
    chip: "M8 8h8v8H8zM9 2v3m3-3v3m3-3v3M9 19v3m3-3v3m3-3v3M2 9h3m-3 3h3m-3 3h3m14-6h3m-3 3h3m-3 3h3",
    storage: "M4 6c0-2 16-2 16 0s-16 2-16 0zm0 0v6c0 2 16 2 16 0V6m-16 6v6c0 2 16 2 16 0v-6"
  };
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d={paths[name] ?? paths.pulse} /></svg>;
};

function Metric({ label, value }: { label: string; value: string }) {
  return <div class="metric"><span>{label}</span><strong>{value}</strong></div>;
}

function RadioCard({ radio }: { radio: RadioState }) {
  const ready = ["ready", "enabled"].includes(radio.state.toLowerCase());
  return <article class="panel radio-card">
    <div class="panel-head">
      <div class="icon-box"><Icon name="radio" /></div>
      <div><span class="eyebrow">Radio {radio.id === "2g" ? "2,4 GHz" : "5 GHz"}</span><h3>{radio.ssid}</h3></div>
      <span class={`pill ${ready ? "ok" : "warn"}`}>{radio.state}</span>
    </div>
    <div class="radio-grid">
      <Metric label="Canal" value={String(radio.channel || "—")} />
      <Metric label="Ancho" value={`${radio.bandwidth || "—"} MHz`} />
      <Metric label="Clientes" value={String(radio.clients)} />
      <Metric label="Potencia" value={radio.txPower ?? "automática"} />
    </div>
    <div class="security-line"><Icon name="shield" /><span>{radio.security}</span></div>
  </article>;
}

function DefinitionGrid({ rows }: { rows: Array<[string, string]> }) {
  return <dl class="definition-grid">{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>;
}

function OptimizationCard({ data }: { data: Snapshot }) {
  return <article class="panel optimize">
    <div class="panel-head"><div class="icon-box violet"><Icon name="pulse" /></div><div><span class="eyebrow">Lyoko Radiod</span><h3>Optimización autónoma</h3></div><span class="pill warn">{data.optimization.mode}</span></div>
    <div class="decision"><span>Decisión actual</span><strong>{data.optimization.decision}</strong></div>
    <div class="progress" aria-label="Estabilidad observada"><i style={{ width: `${Math.min(100, (data.optimization.stableFor / 1800) * 100)}%` }} /></div>
    <p>Exige {data.optimization.threshold}% de mejora y 30 minutos de estabilidad antes de proponer un cambio.</p>
    <button class="secondary" onClick={() => activeView.value = "Optimización"}>Abrir laboratorio de radio</button>
  </article>;
}

function Capabilities({ data }: { data: Snapshot }) {
  return <section class="panel capabilities">
    <div class="section-title"><div><span class="eyebrow">Contrato de plataforma</span><h3>Catálogo publicado</h3></div><span>{data.capabilities.length} entradas</span></div>
    <div class="chips">{data.capabilities.map((item) => <span key={item}>{item}</span>)}</div>
  </section>;
}

function Overview({ data }: { data: Snapshot }) {
  const live = data.source === "router";
  return <>
    <section class="hero panel">
      <div><span class="eyebrow">Estado del superordenador</span><h2>{live ? data.health === "ready" ? "Todos los sistemas nominales" : "Estado del equipo por revisar" : "Demostración · datos simulados"}</h2><p>{data.version}</p></div>
      <div class="orb"><div /><span>{live ? data.health : "DEMO"}</span></div>
    </section>
    <section class="quick-grid">
      <article class="mini panel"><Icon name="pulse" /><div><span>Uptime</span><strong>{uptime.value}</strong></div></article>
      <article class="mini panel"><Icon name="chip" /><div><span>RAM libre</span><strong>{data.memoryFreeMiB.toFixed(1)} MiB</strong></div></article>
      <article class="mini panel"><Icon name="shield" /><div><span>Seguridad</span><strong>Fail-closed</strong></div></article>
      <article class="mini panel"><Icon name="storage" /><div><span>Persistencia</span><strong>F318 offline</strong></div></article>
    </section>
    <section class="content-grid">
      <div class="radios">{data.radios.map((item) => <RadioCard key={item.id} radio={item} />)}</div>
      <OptimizationCard data={data} />
    </section>
    <Capabilities data={data} />
  </>;
}

function ViewContent({ data }: { data: Snapshot }) {
  switch (activeView.value) {
    case "Radios":
      return <><section class="radios full">{data.radios.map((item) => <RadioCard key={item.id} radio={item} />)}</section><ChannelExplorer /><RadioWorkbench enabled={data.source === "router"} /></>;
    case "Optimización":
      return <section class="content-grid single"><OptimizationCard data={data} /><article class="panel detail"><span class="eyebrow">Motor de decisión</span><h2>Observar antes de actuar</h2><DefinitionGrid rows={[["Modo", data.optimization.mode], ["Supervisor", data.optimization.supervisorRunning ? "Activo" : "No disponible"], ["Motor", data.optimization.engineRunning ? "Activo" : "No disponible"], ["Secuencia", String(data.optimization.lastSequence)], ["Persistencia", data.optimization.persistence], ["Estabilidad", `${data.optimization.stableFor} s`], ["Umbral", `${data.optimization.threshold}%`], ["Aplicación automática", data.optimization.automaticApply ? "Activa" : "Desactivada"]]} /></article></section>;
    case "Hardware":
      return <section class="panel detail"><span class="eyebrow">Perfil de placa</span><h2>HGW-500BNA-QCv2 A2</h2><DefinitionGrid rows={[["CPU", "ARC700"], ["Kernel", data.kernel], ["RAM libre", `${data.memoryFreeMiB.toFixed(1)} MiB`], ["Temperatura", data.temperature == null ? "No publicada" : `${data.temperature.toFixed(1)} °C`], ["SPI", "Sin proveedor de escritura"], ["Flash normal", "mtd4/linux_live"]]} /></section>;
    case "Sistema":
      return <section class="panel detail"><span class="eyebrow">Identidad de ejecución</span><h2>{data.version}</h2><DefinitionGrid rows={[["Kernel", data.kernel], ["Salud", data.health], ["Uptime", uptime.value], ["Origen", data.source === "router" ? "API del router" : "Instantánea de laboratorio"], ["Actualización", "15 segundos"]]} /></section>;
    case "Seguridad":
      return <section class="panel detail"><span class="eyebrow">Plano de control</span><h2>Seguro por defecto</h2><div class="chips vertical"><span><b>✓</b>API del mismo origen y sesión autenticada</span><span><b>✓</b>Sin CDN, fuentes remotas ni HTML dinámico</span><span><b>✓</b>Mutaciones separadas en plan, apply, readback y rollback</span><span><b>✓</b>mtd0, mtd1, mtd2, mtd3 y mtd5 protegidas</span></div></section>;
    default:
      return <Overview data={data} />;
  }
}

function Navigation({ mobile = false }: { mobile?: boolean }) {
  return <nav class={mobile ? "mobile-nav" : ""} aria-label={mobile ? "Navegación móvil" : "Navegación principal"}>
    {views.map((item) => <button key={item} aria-current={activeView.value === item ? "page" : undefined} class={activeView.value === item ? "active" : ""} onClick={() => activeView.value = item}>
      <Icon name={iconFor(item)} /><span>{item}</span>
    </button>)}
  </nav>;
}

function App() {
  const demo = new URLSearchParams(window.location.search).get("demo") === "1";
  const refresh = async () => {
    if (refreshing) return;
    refreshing = true;
    busy.value = true;
    try {
      snapshot.value = await loadSnapshot({ demo });
      loadError.value = null;
    } catch (error) {
      snapshot.value = null;
      loadError.value = error instanceof ApiError ? error : new ApiError("No se pudo actualizar el estado.");
    } finally {
      busy.value = false;
      refreshing = false;
    }
  };

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => {
      if (!demo && loadError.value?.code !== "auth") void refresh();
    }, 15000);
    return () => window.clearInterval(timer);
  }, []);

  const data = snapshot.value;
  return <div class={`shell ${darkMode.value ? "theme-dark" : ""}`}>
    <aside>
      <div class="brand"><div class="brand-mark">L</div><div><strong>LYOKO</strong><span>Foundation OS</span></div></div>
      <Navigation />
      <div class="sidebar-foot"><span class={`status-dot ${!data || demo ? "unavailable" : ""}`} />{data?.source === "router" ? "API conectada" : demo ? "Demostración explícita" : "Sin estado confirmado"}</div>
    </aside>
    <main aria-busy={busy.value}>
      <header>
        <div><span class="eyebrow">Sector 5 · Núcleo de red</span><h1>{activeView.value}</h1></div>
        <div class="header-actions"><span class="pill neutral">{data?.kernel ?? "Sin lectura"}</span><button class="avatar subtle" aria-label={darkMode.value ? "Usar tema claro" : "Usar modo Lyoko oscuro"} onClick={() => darkMode.value = !darkMode.value}>◐</button><button class="avatar" aria-label="Actualizar estado" disabled={busy.value} onClick={() => void refresh()}>{busy.value ? "…" : "↻"}</button></div>
      </header>
      {loadError.value ? <section class="panel detail" role="alert">
        <h2>{loadError.value.code === "auth" ? "Vuelve a iniciar sesión" : "No hay estado confirmado"}</h2>
        <p>{loadError.value.message}</p>
        <p><a href="/index.cgi">Ir al acceso del router</a></p>
        {["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname) && <p><a href="?demo=1">Abrir demostración local</a></p>}
      </section> : data ? <><p class="source-notice">{demo ? "Datos simulados. Ningún control de esta vista actúa sobre un router." : "Lecturas de la API. La disponibilidad de cada operación depende de su contrato."}</p><ViewContent data={data} /></> : <section class="hero panel"><h2>Sincronizando sectores…</h2></section>}
    </main>
    <Navigation mobile />
  </div>;
}

export default App;
