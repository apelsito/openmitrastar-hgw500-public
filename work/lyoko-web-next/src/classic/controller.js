const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const modeOrder = { normal: 0, advanced: 1, developer: 2 };
const fixedMode = "developer";
const pages = new Set(["home", "network", "wifi", "system", "diagnostics"]);
const pageMinimum = { home: "normal", network: "normal", wifi: "normal", system: "advanced", diagnostics: "developer" };
const dfsChannels = new Set([52, 56, 60, 64, 100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140]);
const weatherRadarChannels = new Set([120, 124, 128]);
const state = { pending: null, applyEnabled: false, mode: fixedMode, page: "home", focus: "", radios: {}, settings: {}, contractsReady: { "2g": false, "5g": false }, packages: null, packageBusy: false, packageQuery: "", selectedPackage: "", packagePlan: null, hardware: null, ledBusy: false, configStore: null, configStoreBusy: false, previousDiagnostics: null, activeRadio: "2g", selectedProfile: "home", dfsAcknowledged: false, dfsBackendReady: false };

const settingHelp = {
  "2g:Nombre de red (SSID)": { values: "1–32 caracteres", recommended: "Un nombre reconocible sin datos personales", lower: "No aplica", higher: "No aplica", risk: "Cambiarlo desconecta temporalmente a los clientes hasta que vuelvan a asociarse." },
  "2g:Emisión del SSID": { values: "Visible u oculto", recommended: "Visible", lower: "Oculto dificulta el alta y no aporta seguridad real", higher: "Visible simplifica roaming, soporte y diagnóstico", risk: "Control pendiente de integrar en la transacción del driver." },
  "2g:Canal": { values: "1–13 en el dominio ES", recommended: "Empieza por 1, 6 u 11 y mide el entorno", lower: "No implica menos potencia; sólo cambia la frecuencia", higher: "Puede evitar interferencia si el canal actual está ocupado", risk: "Los canales intermedios son válidos, pero se solapan con más vecinos." },
  "2g:Ancho": { values: "20 o 40 MHz", recommended: "20 MHz en entornos con muchas redes", lower: "20 MHz mejora convivencia y estabilidad", higher: "40 MHz aumenta PHY, pero duplica espectro ocupado", risk: "40 MHz puede empeorar rendimiento real si hay interferencia." },
  "2g:Potencia TX": { values: "Tabla calibrada y límites ETSI", recommended: "Automática OEM", lower: "Reduce cobertura e interferencia", higher: "Amplía señal, calor e interferencia; debe respetar EIRP", risk: "Bloqueado hasta validar calibración y límites regulatorios." },
  "2g:Canal automático": { values: "Análisis → propuesta → apply con rollback", recommended: "Evaluar 1/6/11 con tráfico real", lower: "Menos sensibilidad puede ignorar congestión", higher: "Más sensibilidad puede provocar cambios innecesarios", risk: "Función planificada; todavía no ejecuta cambios." },
  "2g:Seguridad": { values: "WPA2‑PSK / CCMP", recommended: "WPA2‑PSK con clave única", lower: "No debe reducirse a TKIP o red abierta", higher: "WPA3 requerirá soporte y pruebas adicionales", risk: "La PSK es write-only y nunca se devuelve por API." },
  "2g:Aislamiento de clientes": { values: "Activado o desactivado", recommended: "Activado para invitados; desactivado para LAN doméstica", lower: "Permite impresoras, cast y tráfico lateral", higher: "Reduce movimiento lateral entre clientes", risk: "Pendiente de prueba con bridge y multicast." },
  "2g:WMM": { values: "Activado o desactivado", recommended: "Activado", lower: "Desactivarlo limita QoS y puede degradar 802.11n", higher: "Prioriza voz y vídeo mediante colas de acceso", risk: "Fijado para preservar el datapath probado." },
  "2g:Short GI": { values: "Activado o desactivado", recommended: "Activado con señal limpia", lower: "Más robustez ante multitrayecto", higher: "Mejora capacidad PHY con mayor sensibilidad al ruido", risk: "Fijado hasta tener benchmark comparativo." },
  "2g:Beacon / DTIM": { values: "Beacon 20–1000 ms; DTIM 1–255", recommended: "100 ms / DTIM 1", lower: "Menor intervalo reduce latencia y aumenta consumo", higher: "Mayor intervalo ahorra energía pero retrasa descubrimiento/tráfico", risk: "Valores OEM conservados como baseline." },
  "5g:Nombre de red (SSID)": { values: "1–32 caracteres", recommended: "Nombre distinto de 2,4 GHz durante validación", lower: "No aplica", higher: "No aplica", risk: "Unificar nombres sólo será recomendable cuando band steering esté probado." },
  "5g:Región": { values: "ES / ETSI", recommended: "ES", lower: "No aplica", higher: "No aplica", risk: "Cambiar país sin autorización puede incumplir canales y potencia legal." },
  "5g:Canal": { values: "36–48 sin DFS; 52–140 con DFS según hardware", recommended: "36–48 para cambio inmediato; DFS sólo con radar activo", lower: "Canales bajos evitan CAC", higher: "DFS abre más espectro, pero obliga a esperar y abandonar ante radar", risk: "Aceptar el riesgo no desactiva DFS, CAC ni los límites de potencia." },
  "5g:Ancho": { values: "20, 40 u 80 MHz", recommended: "80 MHz con señal limpia", lower: "20/40 MHz mejora convivencia y alcance útil", higher: "80 MHz aumenta capacidad máxima y sensibilidad a interferencia", risk: "Debe medirse junto a latencia, pérdidas y estabilidad." },
  "5g:Potencia TX": { values: "Tabla de potencia calibrada ES", recommended: "21 dBm readback actual", lower: "Reduce cobertura e interferencia", higher: "Aumenta cobertura, calor e interferencia", risk: "Bloqueado hasta validar tabla RF y EIRP." },
  "5g:Canal automático": { values: "Ocupación + DFS + clientes + rollback", recommended: "Proponer, no aplicar sin verificación", lower: "Menos cambios pero posible congestión persistente", higher: "Más adaptación, con riesgo de interrupciones", risk: "Función planificada y todavía inactiva." },
  "5g:Seguridad": { values: "WPA2‑PSK / CCMP", recommended: "WPA2‑PSK con clave única", lower: "Nunca usar abierto/TKIP", higher: "WPA3 requiere soporte del stack Quantenna", risk: "La PSK se mantiene fuera de las respuestas API." },
  "5g:Aislamiento": { values: "Activado o desactivado", recommended: "Según uso de LAN o invitados", lower: "Permite comunicación local", higher: "Mejora aislamiento entre estaciones", risk: "Pendiente de validar multicast y bridge." },
  "5g:DFS / CAC": { values: "Hardware QT4 presente; proveedor Linux 5.10 pendiente", recommended: "Fail-closed hasta completar el port", lower: "Mantiene 52–140 fuera de TX", higher: "Abrirá más espectro con CAC, radar, evacuación y NOP", risk: "El firmware OEM tenía radar.ko; Lyoko todavía debe portar y probar el detector." },
  "5g:Agregación BA": { values: "Perfil estable; ventanas avanzadas pendientes", recommended: "Baseline probado", lower: "Menos agregación reduce latencia y throughput", higher: "Más agregación puede subir throughput y presión de colas", risk: "Sólo se ajusta con tres benchmarks comparables." },
};

const radioProfiles = {
  home: {
    label: "Casa",
    description: "Equilibra cobertura, capacidad, consumo y compatibilidad para el uso diario.",
    values: {
      "2g": { ssid_broadcast: true, channel: 1, bandwidth: 20, client_isolation: false, wmm: true, short_gi: true, beacon_interval: 100, dtim_period: 3, max_clients: 32 },
      "5g": { ssid_broadcast: true, channel: 36, bandwidth: 80, client_isolation: false, wmm: true, short_gi: true, beacon_interval: 100, dtim_period: 3, ldpc: true, forty_only: false },
    },
  },
  iot: {
    label: "Domótica",
    description: "Prioriza descubrimiento local, multicast y compatibilidad con dispositivos sencillos.",
    values: {
      "2g": { ssid_broadcast: true, channel: 1, bandwidth: 20, client_isolation: false, wmm: true, short_gi: false, beacon_interval: 100, dtim_period: 1, max_clients: 48 },
      "5g": { ssid_broadcast: true, channel: 36, bandwidth: 40, client_isolation: false, wmm: true, short_gi: false, beacon_interval: 100, dtim_period: 1, ldpc: true, forty_only: false, multicast_rate: 1000 },
    },
  },
  performance: {
    label: "Rendimiento",
    description: "Busca capacidad máxima con WMM, agregación y anchos altos cuando el entorno está limpio.",
    values: {
      "2g": { ssid_broadcast: true, channel: 1, bandwidth: 40, client_isolation: false, wmm: true, short_gi: true, beacon_interval: 100, dtim_period: 1, max_clients: 32 },
      "5g": { ssid_broadcast: true, channel: 36, bandwidth: 80, client_isolation: false, wmm: true, short_gi: true, beacon_interval: 100, dtim_period: 1, ldpc: true, forty_only: false },
    },
  },
  stability: {
    label: "Estabilidad",
    description: "Reduce sensibilidad a interferencias y conserva parámetros de asociación previsibles.",
    values: {
      "2g": { ssid_broadcast: true, channel: 1, bandwidth: 20, client_isolation: false, wmm: true, short_gi: false, beacon_interval: 100, dtim_period: 3, max_clients: 24 },
      "5g": { ssid_broadcast: true, channel: 36, bandwidth: 40, client_isolation: false, wmm: true, short_gi: false, beacon_interval: 100, dtim_period: 3, ldpc: true, forty_only: false },
    },
  },
};

const diagnosticHelp = {
  irq20: { title: "IRQ20 · Ethernet", copy: "Interrupciones atendidas por el EMAC que enlaza Lyoko con la red cableada.", rule: "Debe aumentar cuando circula tráfico." },
  napiPolls: { title: "Ciclos NAPI", copy: "Veces que Linux ha ejecutado el procesador de paquetes del EMAC.", rule: "Actividad alta es normal; importa compararla con trabajo y agotamientos." },
  napiBudget: { title: "NAPI agotado", copy: "Ciclos que consumieron todo el presupuesto antes de vaciar la cola RX.", rule: "Incrementos repetidos indican presión sostenida sobre la CPU o el anillo." },
  noDescIrq: { title: "Eventos sin descriptor", copy: "El DMA intentó recibir cuando no encontraba un descriptor disponible.", rule: "Debe permanecer cerca de cero durante tráfico normal." },
  noDescSamples: { title: "Estado NO_RX_DESC", copy: "Muestras del bit de falta de descriptor. Un valor alto puede ser un único evento que quedó latched.", rule: "F288/F290 limpian este estado al atenderlo." },
  rxFaults: { title: "Fallos RX observados", copy: "Número de observaciones directas de RX_STOPPED, NO_RX_DESC o RX_MISSED.", rule: "Permite relacionar un reinicio posterior con su causa hardware." },
  rxRestarts: { title: "Recuperaciones RX", copy: "Reinicios controlados del motor DMA de recepción para recuperar conectividad.", rule: "Un incremento aislado puede ser recuperación correcta; una ráfaga requiere investigación." },
  restartStagnant: { title: "Recuperación por estancamiento", copy: "El puntero RX dejó de avanzar mientras el descriptor seguía bajo control del DMA.", rule: "Debe correlacionarse con la edad y estado del último fallo RX." },
  restartFaultAge: { title: "Edad del fallo al recuperar", copy: "Milisegundos entre el último fallo RX observado y la recuperación DMA.", rule: "F290 observó 6150 ms; cero significa que aún no hubo recuperación." },
  restartIdle: { title: "Espera antes de recuperar", copy: "Tiempo sin progreso RX medido justo cuando se reinició el motor DMA.", rule: "Sirve para ajustar el watchdog sin confundir reposo normal con un bloqueo." },
  macRxFrames: { title: "Tramas vistas por el chip", copy: "Contador físico del MAC Ethernet antes de que Linux procese los descriptores.", rule: "Si aumenta pero los paquetes Linux no avanzan, el bloqueo está entre el MAC y el ring RX." },
  macRxProgress: { title: "Avances del MAC físico", copy: "Número de muestras en las que el contador físico de recepción avanzó durante una espera RX.", rule: "Permite demostrar que existía demanda real y no sólo reposo de la red." },
  macRxProgressAge: { title: "Edad del último tráfico físico", copy: "Milisegundos desde la última vez que el MAC vio nuevas tramas.", rule: "Una edad cercana al reinicio indica que se recuperó un atasco con tráfico real." },
  dmaMissed: { title: "Tramas perdidas por DMA", copy: "Tramas que el hardware no pudo depositar en memoria para que Linux las procesara.", rule: "Debe permanecer en cero; un incremento localiza la pérdida antes de NAPI." },
  macReadFailures: { title: "Lecturas del contador fallidas", copy: "Fallos al consultar de forma acotada el contador físico Arasan.", rule: "Debe permanecer en cero; si aumenta, la telemetría física deja de ser fiable." },
  restartHardwareDemand: { title: "Recuperación por demanda física", copy: "Reinicios RX autorizados después de confirmar que el MAC sigue recibiendo tráfico aunque Linux no avance.", rule: "F300 exige dos muestras consecutivas y conserva el fallback de 16 pokes." },
  macRxProgressStreak: { title: "Racha actual de demanda", copy: "Muestras consecutivas en las que FramesRxTotal avanza durante un posible atasco RX.", rule: "F300 puede recuperar al alcanzar dos muestras si todos los demás gates siguen válidos." },
  macRxProgressStreakMax: { title: "Racha máxima de demanda", copy: "Mayor secuencia consecutiva observada desde el arranque.", rule: "Ayuda a separar demanda sostenida de una muestra aislada." },
  restartMacProgressStreak: { title: "Racha al reiniciar", copy: "Número de muestras de progreso MAC capturado exactamente al activar la recuperación.", rule: "Debe ser al menos dos para una recuperación F300 por demanda física." },
  restartTriggerPokes: { title: "Poke de activación", copy: "Muestra de vigilancia en la que se decidió recuperar RX.", rule: "La ruta F300 debe disparar antes del fallback fijo de 16 pokes." },
  restartMacAge: { title: "Tráfico físico antes del reinicio", copy: "Edad del último avance del MAC capturada exactamente cuando se reinició RX.", rule: "Distingue un bloqueo con demanda de una recuperación disparada durante reposo." },
  tqeRx: { title: "TQE RX", copy: "Paquetes recibidos por el acelerador de tráfico Quantenna.", rule: "Cero es esperado mientras FWT/TQE permanezcan fuera del datapath activo." },
  tqeTx: { title: "TQE TX", copy: "Paquetes transmitidos por el acelerador de tráfico Quantenna.", rule: "Se habilitará por etapas cuando exista rollback y tráfico comparativo." },
};

const esc = value => String(value ?? "-").replace(
  /[&<>"']/g,
  character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character],
);

const stateLabels = {
  ready: "Preparado",
  ENABLED: "Activo",
  ro: "Sólo lectura",
  available: "Disponible",
  readonly: "Solo lectura",
  experimental: "Experimental",
  blocked: "Bloqueada",
  unsupported: "No soportada",
  certification_required: "Pendiente de prueba física",
  "traffic-proven": "Probado con tráfico",
  "physical-baseline": "Baseline físico",
  "transaction-experimental": "Escritura experimental",
  "dynamic-experimental": "Escritura experimental",
  "boot-proven-dynamic-experimental": "Arranque probado; cambio experimental",
};

async function api(path, init = {}) {
  const response = await fetch(path, { cache: "no-store", ...init });
  if (response.status === 403) {
    location.href = "/index.cgi";
    throw new Error("Sesión caducada");
  }
  const text = await response.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error(`Respuesta inválida de ${path}`);
  }
  if (!response.ok || data.ok === false) {
    const error = new Error(data.detail ? `${data.error || `HTTP ${response.status}`}: ${data.detail}` : (data.error || `HTTP ${response.status}`));
    error.code = data.error || "request-failed";
    error.detail = data.detail || "";
    error.status = response.status;
    error.transactionId = data.transaction_id || "";
    throw error;
  }
  return data;
}

function human(value) {
  return stateLabels[value] || value || "No disponible";
}

function datum(label, value) {
  return `<div class="datum"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
}

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function transactionFieldRows(transaction) {
  const before = transaction?.snapshot?.before || {};
  const after = transaction?.snapshot?.after || transaction?.snapshot || {};
  const keys = [...new Set([...Object.keys(before), ...Object.keys(after)])].filter(key => !["id", "state", "lifecycle", "clients", "security", "passphrase_set"].includes(key));
  if (!keys.length) return '<p class="transaction-empty">Sin valores pendientes.</p>';
  return keys.map(key => `<div class="transaction-change"><span>${esc(key)}</span><strong>${esc(before[key] ?? "—")}</strong><b>→</b><strong>${esc(after[key] ?? "—")}</strong></div>`).join("");
}

function renderTransaction(transaction = null, error = null) {
  const title = $("#transaction-title");
  const review = $("#transaction-review");
  const failure = $("#transaction-error");
  if (error) {
    failure.hidden = false;
    failure.textContent = `${error.code || "error"}${error.detail ? ` · ${error.detail}` : ""}`;
  } else {
    failure.hidden = true;
    failure.textContent = "";
  }
  if (!transaction) {
    title.textContent = "Sin cambios pendientes";
    review.innerHTML = '<p class="transaction-empty">Selecciona un ajuste para preparar una transacción verificable.</p>';
    return;
  }
  const phase = transaction.phase || (transaction.applied ? "applied" : transaction.rolled_back ? "rolled-back" : "staged");
  const labels = { staged: "Preparada", applied: "Aplicada; esperando confirmación", committed: "Confirmada", "rolled-back": "Rollback verificado" };
  title.textContent = `${labels[phase] || phase} · ${transaction.band === "5g" ? "5 GHz" : "2,4 GHz"}`;
  review.innerHTML = `${transactionFieldRows(transaction)}<div class="transaction-meta"><span>Estado: ${esc(labels[phase] || phase)}</span><span>ID: ${esc((transaction.transaction_id || "").slice(0, 12) || "—")}</span><span>${transaction.expires_in_seconds ? `Caduca en ${esc(transaction.expires_in_seconds)} s` : (transaction.commit ? `Commit: ${esc(transaction.commit)}` : "")}</span></div>`;
}

function renderCapabilities(items) {
  return items.map(item => `
    <div class="capability-row">
      <div><strong>${esc(item.title || item.id)}</strong><small class="capability-id">${esc(item.id)} · ${esc(item.domain)}</small></div>
      <span class="capability-state" data-state="${esc(item.state)}">${esc(human(item.state))}</span>
      <small class="capability-evidence"><span>${esc(item.description || "Sin descripción")}</span><code>${esc(item.evidence)}</code></small>
    </div>`).join("");
}

function toast(message, bad = false) {
  const node = $("#toast");
  node.textContent = message;
  node.className = bad ? "bad" : "";
  node.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { node.hidden = true; }, 5000);
}

function closeDrawer() {
  document.body.classList.remove("nav-open");
  $("#nav-toggle").setAttribute("aria-expanded", "false");
  $("#nav-scrim").hidden = true;
}

function modeAllows(mode, minimum = "normal") {
  return modeOrder[fixedMode] >= modeOrder[minimum];
}

function settingAllowedInMode() {
  return true;
}

function visibleFocus(mode, page, requestedFocus) {
  const links = $$('.section-link').filter(link => link.dataset.page === page && modeAllows(mode, link.dataset.minMode || "normal"));
  if (!links.length) return "";
  const exact = links.find(link => (link.dataset.focus || "") === requestedFocus);
  return (exact || links[0]).dataset.focus || "";
}

function selectVisibleConfigPane(form, preferred = "") {
  const available = $$('.config-tab', form).filter(button => modeAllows(state.mode, button.dataset.minMode || "normal"));
  const selected = available.find(button => button.dataset.pane === preferred) || available.find(button => button.classList.contains("active")) || available[0];
  if (selected) selectConfigPane(form, selected.dataset.pane);
}

function setRoute(mode, page, focus = "", updateHash = true) {
  const nextMode = fixedMode;
  const requestedPage = pages.has(page) ? page : "home";
  const nextPage = modeAllows(nextMode, pageMinimum[requestedPage]) ? requestedPage : "home";
  const nextFocus = visibleFocus(nextMode, nextPage, focus);
  state.mode = nextMode;
  state.page = nextPage;
  state.focus = nextFocus;
  document.body.dataset.mode = nextMode;
  const modeState = $("#mode-state");
  modeState.textContent = "Developer";
  modeState.dataset.mode = nextMode;
  $$(".mode-button").forEach(button => {
    const selected = button.dataset.mode === nextMode;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
  $$(".section-link").forEach(link => {
    const minimum = link.dataset.minMode || "normal";
    const visible = modeAllows(nextMode, minimum);
    const selected = visible && link.dataset.page === nextPage && (link.dataset.focus || "") === nextFocus;
    link.hidden = !visible;
    link.classList.toggle("active", selected);
    if (selected) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
    link.href = `#${fixedMode}/${link.dataset.page}${link.dataset.focus ? `/${link.dataset.focus}` : ""}`;
  });
  $$("[data-page-panel]").forEach(panel => {
    const selected = panel.dataset.pagePanel === nextPage;
    panel.classList.toggle("active", selected);
    panel.hidden = !selected;
  });
  $$('[data-min-mode]:not(.section-link):not([data-page-panel]):not(.config-pane):not(.config-tab)').forEach(element => {
    element.hidden = !modeAllows(nextMode, element.dataset.minMode);
  });
  $$('.radio-form').forEach(form => selectVisibleConfigPane(form));
  if (nextPage === "wifi" && (nextFocus === "2g" || nextFocus === "5g")) selectRadio(nextFocus);
  if (nextFocus && !["2g", "5g"].includes(nextFocus)) {
    requestAnimationFrame(() => document.getElementById(nextFocus)?.scrollIntoView({ block: "start" }));
  }
  const route = `#${nextMode}/${nextPage}${nextFocus ? `/${nextFocus}` : ""}`;
  if (location.hash !== route) {
    if (updateHash) history.pushState(null, "", route);
    else history.replaceState(null, "", route);
  }
  $$('.radio-form').forEach(form => updateRadioSubmit(form, form.dataset.radio));
  closeDrawer();
}

function routeFromHash() {
  const parts = location.hash.replace(/^#/, "").split("/").filter(Boolean);
  if (Object.hasOwn(modeOrder, parts[0])) parts.shift();
  setRoute(fixedMode, parts[0] || "home", parts[1] || "", false);
}

function radioValues(form) {
  const values = {};
  for (const control of [...form.elements]) {
    if (!control.name || control.disabled) continue;
    values[control.name] = control.type === "checkbox" ? String(control.checked) : String(control.value);
  }
  return values;
}

function changedRadioValues(form, radio) {
  const current = state.radios[radio] || {};
  return Object.fromEntries(Object.entries(radioValues(form)).filter(([key, value]) => settingAllowedInMode(key) && value !== String(current[key] ?? "")));
}

function updateRadioSubmit(form, radio) {
  const changes = changedRadioValues(form, radio);
  const writable = Object.keys(changes).every(key => state.settings[radio]?.[key]?.writable === true);
  const dfsSelected = radio === "5g" && Object.hasOwn(changes, "channel") && dfsChannels.has(Number(changes.channel));
  const dfsAllowed = !dfsSelected || (state.dfsAcknowledged && state.dfsBackendReady);
  const submit = form.querySelector('button[type="submit"]');
  submit.textContent = "Preparar cambio";
  submit.disabled = !state.contractsReady[radio] || !writable || !dfsAllowed || Object.keys(changes).length === 0;
  submit.title = dfsSelected && !state.dfsBackendReady
    ? "El backend radar todavía no puede garantizar DFS/CAC"
    : dfsSelected && !state.dfsAcknowledged ? "Acepta las condiciones DFS para continuar" : "";
  const dfsState = $("#dfs-mode-state");
  if (dfsState && radio === "5g") {
    dfsState.textContent = !dfsSelected
      ? "Canal sin DFS"
      : !state.dfsBackendReady ? "Bloqueado: radar no disponible"
      : state.dfsAcknowledged ? "Aceptado para esta sesión" : "Requiere confirmación";
  }
  if (radio === "5g" && $("#radio5-plan")) {
    const planned = Object.keys(changes).filter(key => ["channel", "bandwidth"].includes(key));
    $("#radio5-plan").disabled = !state.contractsReady[radio] || planned.length === 0;
  }
}

async function planRadio5() {
  const form = $('.radio-form[data-radio="5g"]');
  const changes = Object.fromEntries(Object.entries(changedRadioValues(form, "5g")).filter(([key]) => ["channel", "bandwidth"].includes(key)));
  if (!Object.keys(changes).length) return;
  try {
    const result = await api("/api/v1/radios/5g/plan", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded", "X-OM-CSRF": window.lyokoCsrf || "" },
      body: new URLSearchParams(changes),
    });
    const actions = [];
    if (result.wext_mode_write_required) actions.push("modo PHY");
    if (result.wext_channel_write_required) actions.push("canal WEXT");
    if (result.hostapd_restart_required) actions.push("reconfiguración del AP");
    const before = {};
    const after = {};
    for (const key of ["channel", "bandwidth"]) {
      if (result.changes?.[key]) {
        before[key] = state.radios["5g"]?.[key];
        after[key] = result.target?.[key];
      }
    }
    renderTransaction({ phase: "plan", band: "5g", transaction_id: "read-only", snapshot: { before, after } });
    $("#transaction-title").textContent = result.mutation_required ? `Plan 5 GHz · ${actions.join(" · ")}` : "Plan 5 GHz · sin cambios";
    toast(result.apply_allowed ? "Plan calculado; backend disponible" : "Plan calculado; aplicación bloqueada");
  } catch (error) {
    if (error.code === "qtn-setting-material-change-not-certified") {
      const before = {};
      const after = {};
      const actions = [];
      for (const [key, value] of Object.entries(changes)) {
        before[key] = state.radios["5g"]?.[key];
        after[key] = value;
        if (key === "channel") actions.push("canal WEXT");
        if (key === "bandwidth") actions.push("modo PHY");
      }
      renderTransaction({ phase: "plan", band: "5g", transaction_id: "ui-preview", snapshot: { before, after } });
      $("#transaction-title").textContent = `Simulación 5 GHz · ${actions.join(" · ")} · sin escritura`;
      toast("Plan local calculado; el backend F312 mantiene la escritura bloqueada");
      return;
    }
    renderTransaction(null, error);
    toast(error.message, true);
  }
}

function resetRadioSettingsContract(radio) {
  state.contractsReady[radio] = false;
  state.settings[radio] = {};
  const form = $(`.radio-form[data-radio="${radio}"]`);
  if (!form) return;
  $$('input[name], select[name], button[type="submit"]', form).forEach(control => { control.disabled = true; });
}

function updateCoverage(radio) {
  const values = radioValues($(`.radio-form[data-radio="${radio}"]`));
  $("#coverage-band").textContent = radio === "2g" ? "2,4 GHz" : "5 GHz";
  $("#coverage-channel").textContent = values.channel || state.radios[radio]?.channel || "—";
  $("#coverage-width").textContent = `${values.bandwidth || state.radios[radio]?.bandwidth || "—"} MHz`;
  $("#coverage-radar").className = `coverage-radar band-${radio}`;
}

function channelLabel(radio, value) {
  const channel = Number(value);
  if (radio === "2g") {
    return `${channel} · ${2407 + channel * 5} MHz${[1, 6, 11].includes(channel) ? " · recomendado" : ""}`;
  }
  if (!dfsChannels.has(channel)) return `${channel} · sin DFS`;
  return `${channel} · DFS · ${weatherRadarChannels.has(channel) ? "CAC 10 min" : "CAC mínimo 60 s"}`;
}

function openDfsDialog(form) {
  const dialog = $("#dfs-risk-dialog");
  const setting = state.settings["5g"]?.channel;
  state.dfsBackendReady = setting?.dfs_backend_ready === true;
  $("#dfs-risk-accept").checked = false;
  $("#dfs-risk-confirm").disabled = true;
  $("#dfs-risk-backend").textContent = state.dfsBackendReady
    ? "Radar operativo: Lyoko mantendrá TX bloqueado durante CAC y aplicará el periodo de no ocupación."
    : "El hardware radar QT4 está presente. El proveedor Linux 5.10 aún no está terminado, por lo que Lyoko mantiene TX bloqueado en canales DFS.";
  dialog.dataset.previousChannel = String(state.radios["5g"]?.channel || 36);
  dialog.dataset.formRadio = form.dataset.radio;
  if (typeof dialog.showModal === "function") dialog.showModal(); else dialog.setAttribute("open", "");
}

function profileAssessment(profileId = state.selectedProfile, radio = state.activeRadio) {
  const profile = radioProfiles[profileId] || radioProfiles.home;
  const targets = profile.values[radio] || {};
  const editable = [];
  const previewable = [];
  const pending = [];
  for (const [id, value] of Object.entries(targets)) {
    const setting = state.settings[radio]?.[id];
    if (!setting) continue;
    const item = { id, value, label: setting.label || id };
    if (setting.writable === true) editable.push(item);
    else if (radio === "5g" && ["channel", "bandwidth"].includes(id)) previewable.push(item);
    else pending.push(item);
  }
  return { profile, editable, previewable, pending };
}

function renderProfile() {
  const assessment = profileAssessment();
  $("#profile-band").textContent = state.activeRadio === "2g" ? "2,4 GHz" : "5 GHz";
  $("#profile-name").textContent = assessment.profile.label;
  $("#profile-description").textContent = assessment.profile.description;
  $$(".profile-button").forEach(button => button.classList.toggle("active", button.dataset.profile === state.selectedProfile));
  const button = $("#profile-apply");
  const loadable = assessment.editable.length + assessment.previewable.length;
  button.disabled = loadable === 0;
  button.textContent = loadable ? `Cargar ${loadable} valores para revisar` : "Perfil informativo";
  const pendingText = assessment.pending.length
    ? `${assessment.pending.length} recomendaciones permanecen visibles pero requieren ampliar el backend.`
    : "Todo el perfil publicado por el backend puede prepararse desde esta consola.";
  const previewText = assessment.previewable.length ? ` ${assessment.previewable.length} valores se cargarán como plan sin escritura.` : "";
  $("#profile-impact").textContent = `${assessment.editable.length} valores configurables ahora.${previewText} ${pendingText}`;
}

function loadSelectedProfile() {
  const radio = state.activeRadio;
  const form = $(`.radio-form[data-radio="${radio}"]`);
  const assessment = profileAssessment();
  let changed = 0;
  let firstField = null;
  for (const item of [...assessment.editable, ...assessment.previewable]) {
    const control = form?.elements.namedItem(item.id);
    if (!control || control.disabled) continue;
    const next = String(item.value);
    const before = control.type === "checkbox" ? String(control.checked) : String(control.value);
    if (control.type === "checkbox") control.checked = item.value === true;
    else control.value = next;
    if (before !== next) {
      changed += 1;
      firstField ||= control.closest(".config-field");
    }
  }
  updateRadioSubmit(form, radio);
  updateCoverage(radio);
  if (firstField) {
    selectConfigPane(form, firstField.closest(".config-pane")?.dataset.panePanel || "general");
    showSetting(firstField);
  }
  toast(changed ? `${assessment.profile.label}: ${changed} valores cargados para revisar` : `${assessment.profile.label}: los valores ya coinciden`);
}

function selectRadio(radio) {
  state.activeRadio = radio;
  $$(".band-button").forEach(button => {
    const selected = button.dataset.radioTarget === radio;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
  $$(".radio-form").forEach(form => {
    const selected = form.dataset.radio === radio;
    form.hidden = !selected;
    form.classList.toggle("active", selected);
  });
  updateCoverage(radio);
  renderProfile();
  const firstField = $(`.radio-form[data-radio="${radio}"] .config-pane.active .config-field`);
  if (firstField) showSetting(firstField);
}

function selectConfigPane(form, pane) {
  $$(".config-tab", form).forEach(button => {
    const allowed = modeAllows(state.mode, button.dataset.minMode || "normal");
    const selected = allowed && button.dataset.pane === pane;
    button.hidden = !allowed;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
  });
  $$("[data-pane-panel]", form).forEach(panel => {
    const allowed = modeAllows(state.mode, panel.dataset.minMode || "normal");
    const selected = allowed && panel.dataset.panePanel === pane;
    panel.hidden = !selected;
    panel.classList.toggle("active", selected);
  });
  const firstField = $(`.config-pane[data-pane-panel="${pane}"] .config-field`, form);
  if (firstField) showSetting(firstField);
}

function settingName(field) {
  return field.querySelector("label, .field-label")?.textContent.trim() || "Ajuste Wi‑Fi";
}

function allowedValuesText(value) {
  if (Array.isArray(value)) return value.length ? value.join(", ") : "No configurable";
  if (value && typeof value === "object") {
    if (value.min_length && value.max_length) return `${value.min_length}–${value.max_length} caracteres`;
    return Object.entries(value).map(([key, item]) => `${key}: ${item}`).join(" · ");
  }
  return String(value || "No configurable");
}

function settingValues(radio, setting) {
  return [...new Set([...(Array.isArray(setting.allowed_values) ? setting.allowed_values : []), ...(setting.candidate_values || [])])];
}

function settingState(setting) {
  if (setting.writable === true) return { label: "Editable ahora", className: "available" };
  const blockedLabels = {
    "qtn-dynamic-control-disabled-after-management-loss": ["Edición pendiente", "pending"],
    "dfs-radar-backend-unavailable": ["Port DFS pendiente", "pending"],
    "dfs-linux510-provider-pending": ["Port DFS pendiente", "pending"],
    "qtn-channel-material-change-not-certified": ["Plan disponible", "planned"],
    "qtn-bandwidth-material-change-not-certified": ["Plan disponible", "planned"],
    "qtn-visibility-material-change-not-certified": ["Edición pendiente", "pending"],
    "qtn-wmm-material-change-not-certified": ["Edición pendiente", "pending"],
    "qtn-beacon-material-change-not-certified": ["Edición pendiente", "pending"],
    "qtn-dtim-material-change-not-certified": ["Edición pendiente", "pending"],
    "qtn-current-dfs-without-radar": ["Protección DFS activa", "blocked"],
    "calibration-and-eirp-not-certified": ["Calibración protegida", "readonly"],
    "rf-power-table-not-certified": ["Calibración protegida", "readonly"],
    "psk-write-flow-not-certified": ["Flujo de clave pendiente", "pending"],
    "regulatory-domain-locked": ["Fijo a ES", "readonly"],
    "qtn-bridge-semantics-not-certified": ["Edición pendiente", "pending"],
    "qtn-rate-profile-not-certified": ["Edición pendiente", "pending"],
    "benchmark-and-rollback-required": ["Benchmark requerido", "pending"],
    "module-or-firmware-rebuild-required": ["Cambio por firmware", "firmware"],
    "module-reload-and-benchmark-required": ["Cambio por firmware", "firmware"],
    "spectrum-scan-engine-not-implemented": ["Motor ACS pendiente", "planned"],
    "regulatory-control-not-certified": ["Control regulatorio", "readonly"],
    "multicast-traffic-not-certified": ["Validación multicast", "pending"],
  };
  if (setting.blocked_reason) {
    const mapped = blockedLabels[setting.blocked_reason] || ["Edición no disponible", "pending"];
    return { label: mapped[0], className: mapped[1] };
  }
  return { label: human(setting.certification || "readonly"), className: "readonly" };
}

function operationalState(setting) {
  if (setting.id === "dfs" && setting.dfs_hardware_present !== false) return { label: "Hardware presente", className: "hardware" };
  if (setting.current === "unavailable" || setting.current === null || setting.current === undefined) return { label: "No implementado", className: "unavailable" };
  if (setting.id === "driver_profile") return { label: "Perfil activo", className: "operational" };
  if (setting.id === "region") return { label: "Activo · ES", className: "operational" };
  return { label: "Operativo", className: "operational" };
}

function currentValue(setting) {
  if (!setting) return "No publicado";
  if (typeof setting.current === "boolean") return setting.current ? "Activado" : "Desactivado";
  if (setting.current === "hardware-present-linux510-port-pending") return "QT4 detectado · proveedor Linux 5.10 pendiente";
  if (setting.current === "unavailable") return "No implementado";
  return String(setting.current ?? "No publicado");
}

function configurationGuide(setting) {
  if (!setting) return "El backend no publica este ajuste.";
  if (setting.writable === true) return "Modifica el control, revisa el delta y prepara la transacción. Nada se aplica hasta pulsar Aplicar y verificar.";
  if (["channel", "bandwidth"].includes(setting.id) && setting.blocked_reason?.startsWith("qtn-")) return "Puedes explorar valores y calcular el plan. La escritura se habilitará cuando su prueba física y rollback estén incorporados al backend.";
  if (setting.blocked_reason?.includes("firmware") || setting.blocked_reason?.includes("module")) return "Este valor se materializa en una imagen versionada; no es un ajuste seguro en caliente.";
  if (setting.id === "dfs") return "Se activará al completar el proveedor radar: adquisición, clasificación, CAC, evacuación y NOP.";
  if (setting.id === "region") return "Se deriva del dominio ES/ETSI y permanece fijo para conservar canales y potencia legales.";
  return "Estado visible ahora; la edición necesita una operación backend verificable antes de habilitarse.";
}

function renderFieldStates(field, setting) {
  let slot = field.querySelector(".setting-state");
  if (!slot) {
    slot = field.querySelector(".support-badge") || document.createElement("span");
    if (!slot.isConnected) field.append(slot);
  }
  const operational = operationalState(setting);
  const editability = settingState(setting);
  slot.className = "field-state-stack setting-state";
  slot.innerHTML = `<span class="support-badge ${esc(operational.className)}">${esc(operational.label)}</span><span class="support-badge ${esc(editability.className)}">${esc(editability.label)}</span>`;
}

function applyRadioSettingsContract(radio, contract) {
  const settings = contract?.settings?.settings || [];
  state.contractsReady[radio] = settings.length > 0;
  const backendPath = contract?.settings?.control_backend?.path || "sin backend";
  state.settings[radio] = Object.fromEntries(settings.map(setting => [setting.id, {
    ...setting,
    source: setting.source || backendPath,
    apply_effect: setting.apply_effect || (setting.writable === true ? "Reinicio controlado del AP, readback y rollback" : "No se aplica; sólo lectura"),
  }]));
  const form = $(`.radio-form[data-radio="${radio}"]`);
  if (!form) return;
  const backendAvailable = contract?.settings?.control_backend?.available === true;
  const writableCount = settings.filter(setting => setting.writable === true).length;
  const backendState = $(`#radio${radio === "2g" ? "2" : "5"}-control-state`);
  if (backendState) {
    backendState.textContent = backendAvailable
      ? `${writableCount} editables · ${settings.length - writableCount} observables`
      : "Estado disponible · edición aislada";
    backendState.className = `support-badge ${backendAvailable ? "available" : "readonly"}`;
  }
  for (const setting of settings) {
    const field = $(`.config-field[data-setting="${setting.id}"]`, form);
    if (!field) continue;
    const control = form.elements.namedItem(setting.id);
    if (control && control.tagName === "SELECT" && Array.isArray(setting.allowed_values)) {
      const selected = String(control.value || setting.current || "");
      const values = settingValues(radio, setting);
      control.replaceChildren(...values.map(value => {
        const option = document.createElement("option");
        option.value = String(value);
        option.textContent = setting.id === "channel" ? channelLabel(radio, value) : String(value);
        if (setting.id === "channel") option.dataset.dfs = String(dfsChannels.has(Number(value)));
        return option;
      }));
      control.value = selected;
    }
    if (radio === "5g" && setting.id === "channel") state.dfsBackendReady = setting.dfs_backend_ready === true;
    const inspectOnlyChannel = radio === "5g" && ["channel", "bandwidth"].includes(setting.id);
    if (control) {
      if (control.type === "checkbox") control.checked = setting.current === true || setting.current === "true" || setting.current === 1 || setting.current === "1";
      else control.value = String(setting.current ?? "");
      if (control.type === "number" && setting.allowed_values && !Array.isArray(setting.allowed_values)) {
        if (setting.allowed_values.min !== undefined) control.min = setting.allowed_values.min;
        if (setting.allowed_values.max !== undefined) control.max = setting.allowed_values.max;
      }
      control.disabled = setting.writable !== true && !inspectOnlyChannel;
    }
    const readback = field.querySelector(`[data-readback="${setting.id}"]`);
    if (readback) {
      const value = setting.current;
      readback.textContent = typeof value === "boolean" ? (value ? "Activado" : "Desactivado") : String(value ?? "No disponible");
    }
    renderFieldStates(field, setting);
    field.dataset.writable = String(setting.writable === true);
    field.dataset.certification = setting.certification || "unknown";
  }
  if (state.activeRadio === radio) {
    const selected = $(".config-field.setting-selected", form) || $(".config-pane.active .config-field", form);
    if (selected) showSetting(selected);
    renderProfile();
  }
}

function showSetting(field) {
  const form = field.closest(".radio-form");
  const radio = form?.dataset.radio || state.activeRadio;
  $$(".config-field").forEach(item => item.classList.toggle("setting-selected", item === field));
  const title = settingName(field);
    const setting = state.settings[radio]?.[field.dataset.setting];
  const help = setting ? {
    values: allowedValuesText(Array.isArray(setting.allowed_values) ? settingValues(radio, setting) : setting.allowed_values),
    recommended: setting.recommended,
    lower: setting.lower_effect,
    higher: setting.higher_effect,
    risk: setting.blocked_reason ? `${setting.risk} Estado de edición: ${settingState(setting).label}.` : setting.risk,
  } : settingHelp[`${radio}:${title}`] || {
    values: "Consulta el control disponible",
    recommended: "Mantener el valor actual hasta disponer de medición",
    lower: "Depende del ajuste",
    higher: "Depende del ajuste",
    risk: "Este ajuste requiere validación y rollback antes de aplicarse.",
  };
  $("#setting-title").textContent = title;
  $("#setting-summary").textContent = field.querySelector("small")?.textContent || "Configuración de la radio seleccionada.";
  $("#setting-current").textContent = currentValue(setting);
  $("#setting-values").textContent = help.values;
  $("#setting-recommended").textContent = help.recommended;
  $("#setting-lower").textContent = help.lower;
  $("#setting-higher").textContent = help.higher;
  $("#setting-risk").textContent = help.risk;
  const support = setting ? settingState(setting) : { label: "No existe en el contrato", className: "blocked" };
  $("#setting-support").textContent = support.label;
  $("#setting-support").dataset.state = support.className;
  const operational = setting ? operationalState(setting) : { label: "No publicado", className: "unavailable" };
  $("#setting-operational").textContent = operational.label;
  $("#setting-operational").dataset.state = operational.className;
  $("#setting-how").textContent = configurationGuide(setting);
  $("#setting-source").textContent = setting?.source || "No publicado por el backend";
  $("#setting-apply").textContent = setting?.apply_effect || "No disponible";
}

function populateRadioForm(radio, data) {
  const form = $(`.radio-form[data-radio="${radio}"]`);
  if (!form || !data) return;
  const current = { ...(state.radios[radio] || {}), ...Object.fromEntries(Object.entries(data).map(([key, value]) => [key, typeof value === "boolean" ? String(value) : String(value ?? "")])) };
  state.radios[radio] = current;
  for (const [name, value] of Object.entries(current)) {
    const control = form.elements.namedItem(name);
    if (control?.type === "checkbox") control.checked = value === "true" || value === "1";
    else if (control) control.value = value;
  }
  updateRadioSubmit(form, radio);
  if (state.activeRadio === radio) updateCoverage(radio);
}

function bindForm(form, radio) {
  form.addEventListener("input", event => {
    if (radio === "5g" && event.target.name === "channel") {
      state.dfsAcknowledged = false;
      if (dfsChannels.has(Number(event.target.value))) openDfsDialog(form);
    }
    updateRadioSubmit(form, radio);
    updateCoverage(radio);
  });
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const changes = changedRadioValues(form, radio);
    if (!Object.keys(changes).length) return;
    if (radio === "5g" && dfsChannels.has(Number(changes.channel))) {
      if (!state.dfsBackendReady) {
        renderTransaction(null, { code: "dfs-radar-backend-unavailable", detail: "Lyoko mantiene TX bloqueado hasta disponer de detección radar real." });
        return;
      }
      if (!state.dfsAcknowledged) {
        openDfsDialog(form);
        return;
      }
    }
    if (!state.contractsReady[radio] || Object.keys(changes).some(key => state.settings[radio]?.[key]?.writable !== true)) {
      renderTransaction(null, { code: "control-backend-unavailable", detail: "Esta radio permanece en solo lectura." });
      return;
    }
    const body = new URLSearchParams(changes);
    try {
      const headers = { "Content-Type": "application/x-www-form-urlencoded", "X-OM-CSRF": window.lyokoCsrf || "" };
      if (radio === "5g" && dfsChannels.has(Number(changes.channel)) && state.dfsAcknowledged) {
        headers["X-OM-Regulatory-Ack"] = "OPENMITRASTAR_ES_DFS_V1";
      }
      const result = await api(`/api/v1/radios/${radio}/stage`, {
        method: "POST",
        headers,
        body,
      });
      state.pending = result;
      renderTransaction(result);
      $("#apply").disabled = !state.applyEnabled;
      setRoute(fixedMode, "wifi", radio);
      toast(state.applyEnabled ? "Cambios preparados; aún no aplicados" : "Cambios preparados; aplicación material bloqueada");
    } catch (error) {
      renderTransaction(state.pending, error);
      toast(error.message, true);
    }
  });
}

function renderStatus(status, firmware, frontend) {
  if (status) {
    window.lyokoCsrf = status.csrf || "";
    state.applyEnabled = status.config_apply_enabled === true;
    $("#health").textContent = human(status.health);
    const degraded = status.degraded_services || [];
    $("#health-detail").textContent = degraded.length ? `Pendiente: ${degraded.map(item => item.service).join(", ")}` : "Sin degradaciones";
    $("#uptime").textContent = `${Math.floor(status.uptime_seconds / 60)} min`;
    $("#memory").textContent = `${Math.round(status.memory.available_kb / 1024)} MiB`;
    $("#memory-detail").textContent = `de ${Math.round(status.memory.total_kb / 1024)} MiB`;
  }
  if (firmware) $("#build").textContent = firmware.version;
  if (frontend) {
    $("#runtime-origin").textContent = frontend.runtime === "emulator" ? "Emulador" : `Router · ${human(status?.persistence)}`;
    $("#runtime-origin").className = frontend.runtime === "emulator" ? "status-pill warning" : "status-pill ok";
    $("#ui-version").textContent = `UI ${frontend.ui_version} · ${frontend.build_id}`;
  }
}

function renderRadios(radio2, radio5) {
  if (radio2) {
    $("#radio2-state").textContent = human(radio2.state);
    $("#radio2-detail").textContent = `${radio2.ssid} · canal ${radio2.channel} · ${radio2.bandwidth} MHz`;
    $("#radio2-badge").className = `status-dot ${radio2.state === "ENABLED" ? "ok" : ""}`;
    populateRadioForm("2g", radio2);
  }
  if (radio5) {
    $("#radio5-state").textContent = human(radio5.state);
    $("#radio5-detail").textContent = `${radio5.ssid} · canal ${radio5.channel} · ${radio5.tx_power_dbm} dBm`;
    $("#radio5-badge").className = `status-dot ${radio5.state === "ready" ? "ok" : ""}`;
    populateRadioForm("5g", radio5);
  }
}

function renderNetwork(network, clients, status) {
  if (network) {
    $("#network-overview").innerHTML = [
      datum("Gestión", network.management_ipv4), datum("Gateway", network.gateway),
      datum("Bridge", (network.bridge_members || []).join(" + ")), datum("Persistencia", human(status?.persistence)),
      datum("IGMP snooping", network.multicast?.available ? (network.multicast.snooping === "0" ? "Desactivado hasta validar" : `Estado ${network.multicast.snooping}`) : "No disponible"),
    ].join("");
    const multicast = network.multicast || {};
    const vlan = network.vlan || {};
    if ($("#network-services-data")) {
      $("#network-services-data").innerHTML = [
        datum("Snooping", multicast.snooping === "1" ? "Activo" : multicast.snooping === "0" ? "Desactivado" : "No disponible"),
        datum("Querier", multicast.querier === "1" ? "Activo" : multicast.querier === "0" ? "Desactivado" : "No disponible"),
        datum("Multicast router", multicast.router ?? "No disponible"),
        datum("IGMP", multicast.igmp_version ? `v${multicast.igmp_version}` : "No disponible"),
        datum("Interfaces IGMPv4", multicast.igmp_v4_interfaces ?? "—"),
        datum("Grupos IGMPv4 / IPv6", `${multicast.igmp_v4_groups ?? "—"} / ${multicast.igmp_v6_groups ?? "—"}`),
        datum("VLAN configuradas", vlan.configured_interfaces ?? "—"),
        datum("Filtrado VLAN bridge", vlan.bridge_filtering_available ? (vlan.bridge_filtering === "1" ? "Activo" : "Desactivado") : "No expuesto"),
      ].join("");
    }
  }
  if (clients) {
    $("#clients").innerHTML = [
      datum("2,4 GHz", clients.band24.count), datum("5 GHz", clients.band5.count),
      datum("Privacidad", "Identidades ocultas"),
    ].join("");
  }
}

function renderHardware(hardware) {
  if (!hardware) return;
  state.hardware = hardware;
  const temperature = hardware.temperature.available ? (hardware.temperature.raw || "Disponible") : (hardware.temperature.source || "No disponible");
  const buttonCount = Object.values(hardware.buttons).filter(item => item.registered).length;
  const ledCount = Object.values(hardware.leds).filter(item => item.present).length;
  const watchdog = hardware.watchdog.present ? "Registrado" : (hardware.watchdog.state || "No disponible");
  $("#hardware-summary").innerHTML = [
    datum("Modelo", hardware.model), datum("Temperatura", temperature), datum("IRQ Ethernet", hardware.irq20),
    datum("Botones registrados", `${buttonCount}/3`), datum("LEDs detectados", `${ledCount}/6`), datum("Watchdog", watchdog),
    datum("Thermal zones / hwmon", `${hardware.temperature.thermal_zones ?? 0} / ${hardware.temperature.hwmon_devices ?? 0}`),
    datum("GPIO sysfs", hardware.gpio?.sysfs_class_present ? `${hardware.gpio.gpiochips} gpiochips` : "No expuesto"),
  ].join("");
  const buttonLabels = { wifi2g: "Wi-Fi 2,4 GHz", wifi5g: "Wi-Fi 5 GHz", reset: "Reset" };
  $("#hardware-buttons").innerHTML = Object.entries(hardware.buttons || {}).map(([id, item]) => `
    <div class="hardware-row"><div><strong>${esc(buttonLabels[id] || id)}</strong><small>${esc(item.registered ? `GPIO${item.gpio} · ${item.event || "sin event"} · ${item.phys || "input"}` : `${id} · subsistema input`)}</small></div><span class="status-pill ${item.registered ? "ok" : "bad"}">${item.registered ? "Registrado" : "Ausente"}</span></div>`).join("");
  const ledLabels = { wifi2g: "Wi-Fi 2,4 GHz", wifi5g: "Wi-Fi 5 GHz", signal_blue: "Señal azul", signal_green: "Señal verde", signal_red: "Señal roja", stage0: "Stage 0" };
  $("#hardware-leds").innerHTML = Object.entries(hardware.leds || {}).map(([id, item]) => {
    const physical = item.physical_state === "on" ? "Encendido" : item.physical_state === "off" ? "Apagado" : "Estado físico no calibrado";
    const detail = item.present ? `sysfs ${item.brightness}/${item.max_brightness} · ${item.polarity || "unknown"} · ${item.provider || "provider unknown"}` : "Sin dispositivo LED class";
    return `<div class="hardware-row"><div><strong>${esc(ledLabels[id] || id)}</strong><small>${esc(detail)}</small></div><span class="status-pill ${item.physical_state === "on" ? "ok" : ""}">${esc(item.present ? physical : "Ausente")}</span></div>`;
  }).join("");
  $("#led-identify").disabled = state.ledBusy || hardware.led_control?.enabled !== true;
}

async function identifyLeds() {
  if (!state.hardware?.led_control?.enabled || state.ledBusy) return;
  state.ledBusy = true; renderHardware(state.hardware);
  const errorNode = $("#led-error"); errorNode.hidden = true;
  try {
    const body = new URLSearchParams({ action: "identify", seconds: $("#led-seconds").value });
    const result = await api("/api/v1/hardware-led-test", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded", "X-OM-CSRF": window.lyokoCsrf || "", "X-OM-Confirm": "OPENMITRASTAR_LED_IDENTIFY_V1" }, body });
    toast(result.restored ? "Secuencia LED completada y restaurada" : "La restauración LED no fue confirmada", !result.restored);
  } catch (error) {
    errorNode.textContent = error.code || "led-identification-failed"; errorNode.hidden = false; toast(error.message, true);
  } finally { state.ledBusy = false; await load(); }
}

function renderStorage(storage, configStore) {
  if (!storage) return;
  state.configStore = configStore || null;
  const mib = bytes => bytes ? `${(Number(bytes) / 1048576).toFixed(2)} MiB` : "No disponible";
  const probe = storage.spi_probe || {};
  const protection = storage.protection_probe || {};
  const protectionState = protection.loaded
    ? "Cargado · sólo lectura"
    : protection.packaged ? "Disponible · no cargado" : "No incluido";
  const protectionIdentity = protection.loaded
    ? `${protection.jedec_matches ? "Macronix verificada" : "JEDEC inesperado"} · 0x${Number(protection.jedec_id || 0).toString(16).padStart(6, "0")}`
    : "Pendiente de lectura física";
  const protectionBlocks = protection.loaded
    ? `${numeric(protection.dpb_nonzero_count)}/${numeric(protection.dpb_scan_count)} DPB no cero`
    : "28 bloques pendientes";
  $("#storage").innerHTML = [
    datum("Rootfs", `${mib(storage.rootfs?.bytes)} · solo lectura`),
    datum("Lyoko store", storage.store?.present ? `${mib(storage.store.bytes)} · ${storage.store.mounted ? "montado" : "sin montar"}` : "No presente"),
    datum("SPI NOR", probe.expected_device === "Y" ? `MX25L12836E · ${probe.jedec_id || "ID pendiente"}` : (probe.status || "Pendiente")),
    datum("Escrituras", storage.store?.writes_enabled ? "Habilitadas" : "Bloqueadas"),
    datum("Observador de protección", protectionState),
    datum("Identidad SPI", protectionIdentity),
    datum("Protección por bloque", protectionBlocks),
    datum("Control SPI restaurado", protection.loaded ? (protection.control_restored ? "Sí" : "No") : "Pendiente"),
    datum("Journal configuración", configStore?.store_ready ? `${configStore.format} · ${configStore.active_valid ? "válido" : "sin estado válido"}` : "No montado"),
    datum("Persistencia config", configStore?.enabled ? "Habilitada" : "Bloqueada"),
  ].join("");
  $("#storage-raw").textContent = pretty(storage);
  const writable = configStore?.enabled === true && configStore?.store_ready === true && configStore?.boot_consumer === true;
  $("#config-store-commit").disabled = state.configStoreBusy || !writable;
  $("#config-store-rollback").disabled = state.configStoreBusy || !writable || configStore?.active_valid !== true;
}

async function runConfigStoreAction(action) {
  if (state.configStoreBusy || !state.configStore?.enabled || !state.configStore?.store_ready) return;
  state.configStoreBusy = true;
  const errorNode = $("#config-store-error"); errorNode.hidden = true;
  try {
    const body = new URLSearchParams({ action });
    await api("/api/v1/config/store", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded", "X-OM-CSRF": window.lyokoCsrf || "", "X-OM-Confirm": "OPENMITRASTAR_CONFIG_STORE_V1" }, body });
    toast(action === "commit" ? "Estado guardado en el journal" : "Snapshot anterior seleccionado");
  } catch (error) { errorNode.textContent = error.code || "config-store-action-failed"; errorNode.hidden = false; toast(error.message, true); }
  finally { state.configStoreBusy = false; await load(); }
}

function renderPackages(packages) {
  if (!packages) return;
  state.packages = packages;
  const trusted = packages.feed?.signature_verified && packages.feed?.runtime_signature_available;
  $("#package-summary").innerHTML = [
    datum("Catálogo", `${packages.feed?.available_count || 0} paquetes`),
    datum("Firma", trusted ? "Ed25519 verificada" : "No verificada"),
    datum("ABI", packages.architecture || "No disponible"),
    datum("Instalación", packages.runtime_install_enabled ? "RAM habilitada" : "Bloqueada"),
    datum("Persistencia", "Desactivada"),
    datum("Actualizaciones", packages.manager?.upgrade_model === "new-signed-firmware" ? "Nueva imagen firmada" : "No disponible"),
    datum("CLI", packages.manager?.cli_compatibility === "opkg-subset-v1" ? "opkg compatible" : "lyoko-pkg"),
  ].join("");
  const installed = new Set((packages.runtime_installed || []).map(item => item.name));
  const available = packages.available || [];
  const query = state.packageQuery.trim().toLowerCase();
  const visible = available.filter(item => !query || [item.name, item.description, ...(item.dependencies || [])].join(" ").toLowerCase().includes(query));
  if (!state.selectedPackage || !visible.some(item => item.name === state.selectedPackage)) state.selectedPackage = visible[0]?.name || "";
  $("#package-list").innerHTML = visible.length ? visible.map(item => {
    const active = installed.has(item.name);
    const action = active ? "remove" : "install";
    const selected = state.selectedPackage === item.name;
    return `<article class="package-item ${selected ? "selected" : ""}" data-package-select="${esc(item.name)}"><div><strong>${esc(item.name)}</strong><small>${esc(item.description || "Paquete Lyoko")}</small><small>${esc(item.version)} · ${esc(item.installed_size_kb || 0)} KiB</small>${active ? '<span class="package-state">Instalado en RAM</span>' : ""}</div><div class="package-actions"><button type="button" class="secondary" data-package-action="plan" data-package-name="${esc(item.name)}" ${trusted && !state.packageBusy ? "" : "disabled"}>Plan</button><button type="button" class="${active ? "secondary" : ""}" data-package-action="${action}" data-package-name="${esc(item.name)}" ${packages.runtime_install_enabled && !state.packageBusy ? "" : "disabled"}>${active ? "Eliminar" : "Instalar"}</button></div></article>`;
  }).join("") : '<p class="transaction-empty">No hay paquetes que coincidan con la búsqueda.</p>';
  const selected = available.find(item => item.name === state.selectedPackage);
  const plan = state.packagePlan?.package === selected?.name ? state.packagePlan.items : null;
  $("#package-inspector").innerHTML = selected ? [
    `<div class="package-inspector-head"><div><span>Paquete seleccionado</span><strong>${esc(selected.name)}</strong></div><span class="status-pill ${trusted ? "ok" : "bad"}">${trusted ? "Firmado" : "Bloqueado"}</span></div>`,
    `<p>${esc(selected.description || "Paquete Lyoko")}</p>`,
    `<dl class="package-meta"><div><dt>Versión</dt><dd>${esc(selected.version)}</dd></div><div><dt>ABI</dt><dd>${esc(selected.architecture)}</dd></div><div><dt>Tamaño instalado</dt><dd>${esc(selected.installed_size_kb || 0)} KiB</dd></div><div><dt>Persistencia</dt><dd>RAM, se borra al reiniciar</dd></div></dl>`,
    `<div class="package-dependencies"><span>Dependencias directas</span><strong>${selected.dependencies?.length ? selected.dependencies.map(esc).join(" → ") : "Ninguna"}</strong></div>`,
    plan ? `<div class="package-plan"><span>Plan verificado</span><ol>${plan.map(name => `<li>${esc(name)}</li>`).join("")}</ol></div>` : "",
  ].join("") : '<p class="transaction-empty">El catálogo firmado está vacío.</p>';
  $("#package-update").disabled = state.packageBusy;
  $("#packages-raw").textContent = pretty(packages);
}

async function runPackageAction(action, name = "") {
  if (!state.packages || state.packageBusy || (action !== "plan" && !state.packages.runtime_install_enabled)) return;
  const endpoint = state.packages.actions?.endpoint;
  if (!endpoint) return;
  state.packageBusy = true;
  renderPackages(state.packages);
  const errorNode = $("#package-error");
  errorNode.hidden = true;
  try {
    let result;
    if (action === "plan") {
      result = await api(`${endpoint}?view=plan&package=${encodeURIComponent(name)}`);
    } else {
      const body = new URLSearchParams({ action, package: name });
      const confirmation = state.packages.actions?.[`${action}_confirmation`];
      const headers = { "Content-Type": "application/x-www-form-urlencoded", "X-OM-CSRF": window.lyokoCsrf || "" };
      if (confirmation) headers["X-OM-Confirm"] = confirmation;
      result = await api(endpoint, { method: "POST", headers, body });
    }
    state.selectedPackage = name;
    if (action === "plan") state.packagePlan = { package: name, items: result.plan || [] };
    else state.packagePlan = null;
    toast(action === "install" ? `${name} instalado en RAM` : action === "remove" ? `${name} eliminado de RAM` : `${name}: plan verificado`);
    return result;
  } catch (error) {
    errorNode.textContent = `${error.code || "package-error"}${error.detail ? ` · ${error.detail}` : ""}`;
    errorNode.hidden = false;
    toast(error.message, true);
  } finally {
    state.packageBusy = false;
    await load();
  }
}

function numeric(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function diagnosticMetric(key, label, value, previous) {
  const delta = previous === null ? "muestra inicial" : `${value - previous >= 0 ? "+" : ""}${value - previous}`;
  return `<button class="diagnostic-metric" type="button" data-diagnostic-key="${esc(key)}"><span>${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(delta)}</small></button>`;
}

function diagnosticStage(label, stateLabel, detail, tone) {
  return `<div class="rx-stage ${esc(tone)}"><span>${esc(label)}</span><strong>${esc(stateLabel)}</strong><small>${esc(detail)}</small></div>`;
}

function renderRxPath(current) {
  const target = $("#rx-path");
  if (!target) return;
  const macActive = current.macRxFramesValid && current.macRxFramesDelta > 0;
  const dmaPressure = current.dmaMissedDelta > 0;
  const descriptorPressure = current.noDescDelta > 0;
  const napiActive = current.napiWorkDelta > 0;
  const recoveryActive = current.restartDelta > 0;
  target.innerHTML = [
    diagnosticStage("Entrada MAC", macActive ? "Tráfico detectado" : "Sin tráfico nuevo", `+${current.macRxFramesDelta} tramas`, macActive ? "ok" : "idle"),
    diagnosticStage("DMA", dmaPressure ? "Pérdida detectada" : "Sin pérdidas nuevas", `+${current.dmaMissedDelta} missed`, dmaPressure ? "bad" : "ok"),
    diagnosticStage("Descriptores", descriptorPressure ? "Presión RX" : "Disponibles", `+${current.noDescDelta} NO_RX_DESC`, descriptorPressure ? "warning" : "ok"),
    diagnosticStage("NAPI", napiActive ? "Procesando" : "En espera", `+${current.napiWorkDelta} paquetes`, napiActive ? "ok" : "idle"),
    diagnosticStage("Recuperación", recoveryActive ? "Activada" : "No necesaria", `+${current.restartDelta} reinicios`, recoveryActive ? "warning" : "ok"),
  ].join("");
}

function showDiagnosticHelp(key, current) {
  const help = diagnosticHelp[key] || diagnosticHelp.rxRestarts;
  const title = $("#diagnostic-help-title");
  const copy = $("#diagnostic-help-copy");
  const rule = $("#diagnostic-help-rule");
  const health = $("#diagnostic-help-state");
  if (!title || !copy || !rule || !health) return;
  title.textContent = help.title;
  copy.textContent = help.copy;
  rule.textContent = help.rule;
  const recentFault = current.lastFaultStatus !== "00000000" && current.lastFaultAgeMs <= 10000;
  health.textContent = current.fatal > 0
    ? "Fallo fatal"
    : current.macReadFailureDelta > 0
      ? "No se pudo leer el contador físico"
      : current.restartDelta > 0 && current.hardwareDemandAtRestart
        ? "El chip vio tráfico antes del bloqueo"
    : current.restartDelta > 0 && recentFault
      ? "Recuperación ligada a fallo RX reciente"
      : current.restartDelta > 0
        ? "Recuperación sin demanda física reciente"
        : current.noDescDelta > 0
          ? "Presión RX atendida"
          : "Sin incidencia nueva";
  $$(".diagnostic-metric", $("#diagnostics")).forEach(node => node.classList.toggle("active", node.dataset.diagnosticKey === key));
}

function renderDiagnostics(diagnostics) {
  if (!diagnostics) return;
  const emac = diagnostics.emac || {};
  const irq = diagnostics.irq || {};
  const tqe = diagnostics.tqe || {};
  const dfs = diagnostics.dfs || {};
  const current = {
    irq20: numeric(irq.emac),
    irq28: numeric(irq.realtek),
    irq8: numeric(irq.qmac),
    napiPolls: numeric(emac.napi_polls),
    napiWork: numeric(emac.napi_rx_work),
    napiBudget: numeric(emac.napi_budget_exhaustions),
    noDescIrq: numeric(emac.irq_no_rx_desc),
    noDesc: numeric(emac.dma_no_rx_desc_samples),
    rxFaults: numeric(emac.rx_fault_observations),
    rxRestarts: numeric(emac.rx_restart_total),
    restartNoDesc: numeric(emac.rx_restart_reason_no_desc),
    restartStagnant: numeric(emac.rx_restart_reason_stagnant),
    restartHardwareDemand: numeric(emac.rx_restart_reason_hw_demand),
    lastFaultStatus: String(emac.last_rx_fault_status || "00000000"),
    lastFaultAgeMs: numeric(emac.last_rx_fault_age_ms),
    restartIdleMs: numeric(emac.rx_restart_last_idle_ms),
    restartFaultAgeMs: numeric(emac.rx_restart_last_fault_age_ms),
    macRxFramesValid: numeric(emac.mac_rx_frames_valid) === 1,
    macRxFrames: numeric(emac.mac_rx_frames),
    macRxFramesSampleDelta: numeric(emac.mac_rx_frames_delta),
    macRxProgress: numeric(emac.mac_rx_progress_observations),
    macRxProgressAgeMs: numeric(emac.mac_rx_progress_age_ms),
    macRxProgressStreak: numeric(emac.mac_rx_progress_streak),
    macRxProgressStreakMax: numeric(emac.mac_rx_progress_streak_max),
    macRxReadFailures: numeric(emac.mac_rx_read_failures),
    dmaMissed: numeric(emac.dma_missed_frames_total),
    restartMacProgressAgeMs: numeric(emac.rx_restart_last_mac_rx_progress_age_ms),
    restartMacProgressStreak: numeric(emac.rx_restart_last_mac_rx_progress_streak),
    restartTriggerPokes: numeric(emac.rx_restart_last_trigger_pokes),
    restartDmaMissed: numeric(emac.rx_restart_last_dma_missed_frames_total),
    tqeRx: numeric(tqe.rx_packets),
    tqeTx: numeric(tqe.tx_packets),
    fatal: numeric(diagnostics.fatal_count),
  };
  const previous = state.previousDiagnostics;
  const prior = key => previous ? previous[key] : null;
  current.noDescDelta = previous ? current.noDesc - previous.noDesc : 0;
  current.restartDelta = previous ? current.rxRestarts - previous.rxRestarts : 0;
  current.macRxFramesDelta = previous ? current.macRxFrames - previous.macRxFrames : 0;
  current.macRxProgressDelta = previous ? current.macRxProgress - previous.macRxProgress : 0;
  current.macReadFailureDelta = previous ? current.macRxReadFailures - previous.macRxReadFailures : 0;
  current.dmaMissedDelta = previous ? current.dmaMissed - previous.dmaMissed : 0;
  current.napiWorkDelta = previous ? current.napiWork - previous.napiWork : 0;
  const restartProgressAgeValid = current.restartMacProgressAgeMs >= 0
    && current.restartMacProgressAgeMs < 0xffffffff;
  const restartProgressEvidence = current.restartMacProgressStreak >= 2
    || current.macRxFramesSampleDelta > 0
    || current.macRxProgressDelta > 0;
  current.hardwareDemandAtRestart = current.restartDelta > 0 && (
    (current.macRxFramesValid && restartProgressAgeValid && restartProgressEvidence)
    || current.restartDmaMissed > 0
  );
  renderRxPath(current);
  $("#diagnostics").innerHTML = [
    diagnosticMetric("irq20", "IRQ20 EMAC", current.irq20, prior("irq20")),
    diagnosticMetric("napiPolls", "Ciclos NAPI", current.napiPolls, prior("napiPolls")),
    diagnosticMetric("napiBudget", "NAPI agotado", current.napiBudget, prior("napiBudget")),
    diagnosticMetric("noDescIrq", "IRQ sin descriptor", current.noDescIrq, prior("noDescIrq")),
    diagnosticMetric("noDescSamples", "NO_RX_DESC observado", current.noDesc, prior("noDesc")),
    diagnosticMetric("rxFaults", "Fallos RX observados", current.rxFaults, prior("rxFaults")),
    diagnosticMetric("rxRestarts", "Recuperaciones RX", current.rxRestarts, prior("rxRestarts")),
    diagnosticMetric("restartStagnant", "Reinicio por estancamiento", current.restartStagnant, prior("restartStagnant")),
    diagnosticMetric("restartHardwareDemand", "Reinicio por demanda", current.restartHardwareDemand, prior("restartHardwareDemand")),
    diagnosticMetric("restartFaultAge", "Edad del fallo al reinicio", current.restartFaultAgeMs, prior("restartFaultAgeMs")),
    diagnosticMetric("restartIdle", "Espera antes de recuperar", current.restartIdleMs, prior("restartIdleMs")),
    diagnosticMetric("macRxFrames", "Tramas físicas RX", current.macRxFrames, prior("macRxFrames")),
    diagnosticMetric("macRxProgress", "Avances MAC RX", current.macRxProgress, prior("macRxProgress")),
    diagnosticMetric("macRxProgressAge", "Edad tráfico físico", current.macRxProgressAgeMs, prior("macRxProgressAgeMs")),
    diagnosticMetric("macRxProgressStreak", "Racha demanda MAC", current.macRxProgressStreak, prior("macRxProgressStreak")),
    diagnosticMetric("macRxProgressStreakMax", "Racha máxima MAC", current.macRxProgressStreakMax, prior("macRxProgressStreakMax")),
    diagnosticMetric("dmaMissed", "Pérdidas DMA", current.dmaMissed, prior("dmaMissed")),
    diagnosticMetric("macReadFailures", "Fallos lectura MAC", current.macRxReadFailures, prior("macRxReadFailures")),
    diagnosticMetric("restartMacAge", "Tráfico antes del reinicio", current.restartMacProgressAgeMs, prior("restartMacProgressAgeMs")),
    diagnosticMetric("restartMacProgressStreak", "Racha al reinicio", current.restartMacProgressStreak, prior("restartMacProgressStreak")),
    diagnosticMetric("restartTriggerPokes", "Poke de activación", current.restartTriggerPokes, prior("restartTriggerPokes")),
    diagnosticMetric("tqeRx", "TQE RX", current.tqeRx, prior("tqeRx")),
    diagnosticMetric("tqeTx", "TQE TX", current.tqeTx, prior("tqeTx")),
  ].join("");
  const health = $("#diagnostics-health");
  if (current.fatal > 0) {
    health.textContent = `${current.fatal} fallos fatales`;
    health.className = "status-pill bad";
  } else if (current.macReadFailureDelta > 0) {
    health.textContent = "Telemetría física no fiable";
    health.className = "status-pill bad";
  } else if (current.restartDelta > 0) {
    const recent = current.lastFaultStatus !== "00000000" && current.restartFaultAgeMs <= 10000;
    health.textContent = current.hardwareDemandAtRestart
      ? "Bloqueo RX con tráfico físico"
      : recent ? "Recuperación RX causada" : "Reinicio RX sin demanda visible";
    health.className = "status-pill warning";
  } else if (current.noDescDelta > 0) {
    health.textContent = `Presión RX atendida · +${current.noDescDelta}`;
    health.className = "status-pill warning";
  } else {
    health.textContent = previous ? "Sin nuevos stalls" : "Muestra base";
    health.className = "status-pill ok";
  }
  $$(".diagnostic-metric", $("#diagnostics")).forEach(node => {
    const select = () => showDiagnosticHelp(node.dataset.diagnosticKey, current);
    node.addEventListener("click", select);
    node.addEventListener("focus", select);
    node.addEventListener("mouseenter", select);
  });
  showDiagnosticHelp(current.restartDelta > 0 ? "restartMacAge" : "macRxFrames", current);
  $("#diagnostics-raw").textContent = pretty(diagnostics);
  if ($("#dfs-diagnostics")) {
    const raw = dfs.driver_raw || {};
    const policy = dfs.channel_policy || {};
    $("#dfs-diagnostics").innerHTML = [
      datum("Región", dfs.region || "No disponible"),
      datum("Canal actual", dfs.current_channel ?? "No disponible"),
      datum("Canal DFS", dfs.current_channel_dfs === true ? "Sí" : "No"),
      datum("Modo / ancho", `${dfs.mode || "—"} · ${dfs.bandwidth_mhz ?? "—"} MHz`),
      datum("802.11h", raw.doth === 1 ? "Activo" : `Raw ${raw.doth ?? "—"}`),
      datum("CAC", `Raw ${raw.cac_status ?? "—"}`),
      datum("Cambios CSA", raw.dfs_csa_count ?? "—"),
      datum("Disponibilidad", `Raw ${raw.channel_availability ?? "—"}`),
      datum("Política", dfs.policy || "fail-closed"),
      datum("Hardware DFS", dfs.hardware?.present === true ? "Presente · bloque QT4" : "No confirmado"),
      datum("Proveedor Linux 5.10", dfs.writable === true ? "Operativo" : "Pendiente · fail-closed"),
      datum("CAC requerido", policy.cac_seconds ? `${policy.cac_seconds} s` : "No aplica al canal actual"),
      datum("No ocupación", policy.non_occupancy_seconds ? `${Math.round(policy.non_occupancy_seconds / 60)} min` : "No disponible"),
    ].join("");
  }
  state.previousDiagnostics = current;
}

async function load() {
  resetRadioSettingsContract("2g");
  resetRadioSettingsContract("5g");
  const endpoints = {
    status: "/api/v1/status", network: "/api/v1/network", radio2: "/api/v1/radios/2g", radio5: "/api/v1/radios/5g",
    clients: "/api/v1/clients", hardware: "/api/v1/hardware", storage: "/api/v1/storage", diagnostics: "/api/v1/diagnostics", privacy: "/api/v1/privacy",
    firmware: "/api/v1/firmware", packages: "/api/v1/packages", capabilities: "/api/v1/capabilities", frontend: "/api/v1/frontend", session: "/api/v1/session", ssh: "/api/v1/ssh", transaction: "/api/v1/config/status", configStore: "/api/v1/config/store",
    radio2Contract: "/api/v1/radios/2g?view=contract", radio5Contract: "/api/v1/radios/5g?view=contract",
  };
  const names = Object.keys(endpoints);
  const settled = await Promise.allSettled(names.map(name => api(endpoints[name])));
  const data = {};
  const failures = [];
  settled.forEach((result, index) => {
    if (result.status === "fulfilled") data[names[index]] = result.value;
    else failures.push(names[index]);
  });

  renderStatus(data.status, data.firmware, data.frontend);
  applyRadioSettingsContract("2g", data.radio2Contract);
  applyRadioSettingsContract("5g", data.radio5Contract);
  renderRadios(data.radio2, data.radio5);
  renderNetwork(data.network, data.clients, data.status);
  renderHardware(data.hardware);
  renderStorage(data.storage, data.configStore);
  if (data.session) {
    $("#session").innerHTML = [
      datum("Autenticación", data.session.authenticated ? "Activa" : "No autenticada"),
      datum("Caduca en", `${Math.max(0, Math.floor(data.session.expires_in_seconds / 60))} min`),
      datum("Cookie", `HttpOnly · SameSite ${data.session.cookie.same_site}`),
    ].join("");
  }
  if (data.ssh) {
    const identityLabels = { persisted: "Persistente", "firmware-device-bound": "Vinculada al dispositivo", ephemeral: "Efímera" };
    $("#ssh").innerHTML = [
      datum("Servicio", data.ssh.running ? "Activo" : "Detenido"),
      datum("Puerto", data.ssh.port || "No disponible"),
      datum("Identidad", identityLabels[data.ssh.host_identity.persistence] || "No disponible"),
      datum("Fingerprint", data.ssh.host_identity.fingerprint || "No disponible"),
      datum("Contraseña SSH", data.ssh.password_authentication ? "Permitida" : "Desactivada"),
      datum("Forwarding", data.ssh.forwarding ? "Permitido" : "Desactivado"),
    ].join("");
  }
  renderDiagnostics(data.diagnostics);
  if (data.capabilities) $("#capabilities").innerHTML = renderCapabilities(data.capabilities.items || []);
  renderPackages(data.packages);
  if (data.firmware) $("#firmware").textContent = pretty(data.firmware);
  if (data.privacy) $("#privacy").textContent = pretty(data.privacy);
  if (data.radio2Contract) $("#radio2-contract").textContent = pretty(data.radio2Contract);
  if (data.radio5Contract) $("#radio5-contract").textContent = pretty(data.radio5Contract);
  if (data.transaction?.owned_by_session === true && data.transaction.transaction_id) {
    state.pending = data.transaction;
    renderTransaction(data.transaction);
    $("#apply").disabled = !state.applyEnabled || data.transaction.phase !== "staged";
    $("#rollback").disabled = data.transaction.phase !== "applied";
    $("#commit").disabled = data.transaction.phase !== "applied";
  } else if (data.transaction?.pending !== true) {
    state.pending = null;
    renderTransaction();
    $("#apply").disabled = true;
    $("#rollback").disabled = true;
    $("#commit").disabled = true;
  }
  if (failures.includes("transaction")) {
    state.pending = null;
    renderTransaction(null, { code: "transaction-status-unavailable", detail: "La aplicación queda desactivada hasta recuperar el estado del backend." });
    $("#apply").disabled = true;
    $("#rollback").disabled = true;
    $("#commit").disabled = true;
  }

  if (failures.length) {
    $("#connection").textContent = `Parcial ${names.length - failures.length}/${names.length}`;
    $("#connection").className = "status-pill warning";
    toast(`No disponibles: ${failures.join(", ")}`, true);
  } else {
    $("#connection").textContent = "Online";
    $("#connection").className = "status-pill ok";
  }
}

$$('.section-link').forEach(link => link.addEventListener("click", event => {
  event.preventDefault();
  setRoute(state.mode, link.dataset.page, link.dataset.focus || "");
}));
$$('.radio-form').forEach(form => bindForm(form, form.dataset.radio));
$$('.band-button').forEach(button => button.addEventListener("click", () => setRoute(state.mode, "wifi", button.dataset.radioTarget)));
$$('.profile-button').forEach(button => button.addEventListener("click", () => {
  state.selectedProfile = button.dataset.profile;
  renderProfile();
}));
$("#profile-apply").addEventListener("click", loadSelectedProfile);
$$('.config-tab').forEach(button => button.addEventListener("click", () => selectConfigPane(button.closest(".radio-form"), button.dataset.pane)));
$$('.config-field').forEach(field => {
  field.addEventListener("click", () => showSetting(field));
  field.addEventListener("focusin", () => showSetting(field));
});
$("#nav-toggle").addEventListener("click", () => {
  const open = !document.body.classList.contains("nav-open");
  document.body.classList.toggle("nav-open", open);
  $("#nav-toggle").setAttribute("aria-expanded", String(open));
  $("#nav-scrim").hidden = !open;
});
$("#nav-scrim").addEventListener("click", closeDrawer);
document.addEventListener("keydown", event => { if (event.key === "Escape") closeDrawer(); });
window.addEventListener("hashchange", routeFromHash);
window.addEventListener("popstate", routeFromHash);
$("#dfs-risk-accept").addEventListener("change", event => {
  $("#dfs-risk-confirm").disabled = !event.target.checked;
});
$("#dfs-risk-dialog").addEventListener("close", event => {
  const dialog = event.currentTarget;
  const accepted = dialog.returnValue === "confirm" && $("#dfs-risk-accept").checked;
  state.dfsAcknowledged = accepted;
  if (!accepted) {
    $("#r5-channel").value = dialog.dataset.previousChannel || String(state.radios["5g"]?.channel || 36);
  }
  updateRadioSubmit($('.radio-form[data-radio="5g"]'), "5g");
  updateCoverage("5g");
});
$("#refresh").addEventListener("click", load);
$("#package-list").addEventListener("click", event => {
  const button = event.target.closest("[data-package-action]");
  if (button) { runPackageAction(button.dataset.packageAction, button.dataset.packageName); return; }
  const item = event.target.closest("[data-package-select]");
  if (item) { state.selectedPackage = item.dataset.packageSelect; renderPackages(state.packages); }
});
$("#package-search").addEventListener("input", event => { state.packageQuery = event.target.value; renderPackages(state.packages); });
$("#package-update").addEventListener("click", async () => {
  if (state.packageBusy) return;
  state.packageBusy = true; renderPackages(state.packages);
  try {
    const result = await api("/api/v1/packages?view=update");
    toast(`Catálogo verificado · ${result.packages} paquetes`);
  } catch (error) {
    toast(error.message, true);
  } finally {
    state.packageBusy = false; await load();
  }
});
$("#led-identify").addEventListener("click", identifyLeds);
$("#radio5-plan").addEventListener("click", planRadio5);
$("#config-store-commit").addEventListener("click", () => runConfigStoreAction("commit"));
$("#config-store-rollback").addEventListener("click", () => runConfigStoreAction("rollback"));
$("#apply").addEventListener("click", async () => {
  try {
    if (!state.pending?.transaction_id) throw new Error("No hay una transacción válida preparada");
    const result = await api("/api/v1/config/apply", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded", "X-OM-CSRF": window.lyokoCsrf || "", "X-OM-Confirm": "OPENMITRASTAR_CONFIG_TRANSACTION_V1", "X-OM-Transaction": state.pending.transaction_id },
      body: new URLSearchParams({ _confirm: "OPENMITRASTAR_CONFIG_TRANSACTION_V1", _transaction: state.pending.transaction_id }),
    });
    state.pending = result;
    renderTransaction(result);
    $("#rollback").disabled = result.rollback_available !== true;
    $("#commit").disabled = result.confirmation_required !== true;
    toast("Configuración aplicada; confirma antes de que expire");
    await load();
  } catch (error) {
    renderTransaction(state.pending, error);
    toast(error.message, true);
  }
});
$("#commit").addEventListener("click", async () => {
  try {
    if (!state.pending?.transaction_id) throw new Error("No hay una transacción aplicada para confirmar");
    const result = await api("/api/v1/config/commit", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded", "X-OM-CSRF": window.lyokoCsrf || "", "X-OM-Confirm": "OPENMITRASTAR_CONFIG_TRANSACTION_V1", "X-OM-Transaction": state.pending.transaction_id },
      body: new URLSearchParams({ _confirm: "OPENMITRASTAR_CONFIG_TRANSACTION_V1", _transaction: state.pending.transaction_id }),
    });
    state.pending = null;
    renderTransaction({ ...result, phase: "committed" });
    $("#commit").disabled = true;
    $("#rollback").disabled = true;
    toast("Configuración confirmada");
    await load();
  } catch (error) {
    renderTransaction(state.pending, error);
    toast(error.message, true);
  }
});
$("#rollback").addEventListener("click", async () => {
  try {
    if (!state.pending?.transaction_id) throw new Error("No hay una transacción aplicada para revertir");
    const result = await api("/api/v1/config/rollback", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded", "X-OM-CSRF": window.lyokoCsrf || "", "X-OM-Confirm": "OPENMITRASTAR_CONFIG_TRANSACTION_V1", "X-OM-Transaction": state.pending.transaction_id },
      body: new URLSearchParams({ _confirm: "OPENMITRASTAR_CONFIG_TRANSACTION_V1", _transaction: state.pending.transaction_id }),
    });
    state.pending = null;
    renderTransaction(result);
    $("#rollback").disabled = true;
    $("#commit").disabled = true;
    toast("Rollback ejecutado");
    await load();
  } catch (error) {
    renderTransaction(state.pending, error);
    toast(error.message, true);
  }
});

routeFromHash();
if (!["2g", "5g"].includes(state.focus)) selectRadio("2g");
load();
