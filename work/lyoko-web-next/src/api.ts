import type { RadioState, Snapshot } from "./types";
import { ApiError, object, requestApi } from "./transport.ts";
import type { Fetcher } from "./transport.ts";

type Json = Record<string, unknown>;
type EndpointResult = Json | null;

const endpoints = {
  status: "/api/v1/status",
  firmware: "/api/v1/firmware",
  radio2: "/api/v1/radios/2g",
  radio5: "/api/v1/radios/5g",
  hardware: "/api/v1/hardware",
  optimization: "/api/v1/optimization",
  capabilities: "/api/v1/capabilities"
};

const text = (value: unknown, fallback = "desconocido") =>
  typeof value === "string" && value.trim() ? value.trim() : fallback;
const number = (value: unknown, fallback = 0) =>
  typeof value === "number" && Number.isFinite(value) ? value : fallback;

async function getOptional(path: string, fetcher: Fetcher): Promise<EndpointResult> {
  try {
    return await requestApi(path, {}, fetcher);
  } catch (error) {
    if (error instanceof ApiError && error.code === "auth") throw error;
    return null;
  }
}

function radio(id: "2g" | "5g", value: Json): RadioState {
  return {
    id,
    state: text(value.state, "offline"),
    ssid: text(value.ssid, "—"),
    channel: number(value.channel),
    bandwidth: typeof value.bandwidth === "string" ? value.bandwidth : number(value.bandwidth),
    clients: number(value.clients),
    security: text(value.security, "—"),
    txPower: value.tx_power_dbm == null ? undefined : `${text(String(value.tx_power_dbm), "—")} dBm`
  };
}

export async function loadSnapshot(options: { demo?: boolean; fetcher?: Fetcher } = {}): Promise<Snapshot> {
  if (options.demo === true) return mockSnapshot;
  const fetcher = options.fetcher ?? fetch;
  const [status, firmware, radio2, radio5, hardware, optimization, capabilities] = await Promise.all([
    getOptional(endpoints.status, fetcher), getOptional(endpoints.firmware, fetcher), getOptional(endpoints.radio2, fetcher),
    getOptional(endpoints.radio5, fetcher), getOptional(endpoints.hardware, fetcher), getOptional(endpoints.optimization, fetcher),
    getOptional(endpoints.capabilities, fetcher)
  ]);
  if (!status && !firmware && !radio2 && !radio5) throw new ApiError("API indisponible. No se muestran datos simulados en lugar del router.", 0, "unavailable");

  const memory = object(status?.memory);
  const temperature = object(hardware?.temperature);
  const capabilityRows = Array.isArray(capabilities?.capabilities) ? capabilities.capabilities :
    Array.isArray(capabilities?.items) ? capabilities.items : [];
  return {
    source: "router",
    version: text(firmware?.version ?? firmware?.product_version, "OpenMitraStar"),
    kernel: text(status?.kernel ?? firmware?.kernel, "No publicado"),
    uptimeSeconds: number(status?.uptime_seconds ?? status?.uptime),
    health: text(status?.health ?? status?.boot_state, "unknown"),
    temperature: typeof hardware?.temperature_c === "number" ? hardware.temperature_c :
      typeof temperature.value_c === "number" ? temperature.value_c : undefined,
    memoryFreeMiB: number(status?.memory_free_mib ?? hardware?.memory_free_mib ??
      (typeof memory.available_kb === "number" ? memory.available_kb / 1024 : undefined)),
    radios: [radio("2g", radio2 ?? {}), radio("5g", radio5 ?? {})],
    optimization: {
      mode: text(optimization?.mode, "observe-only"),
      decision: text(optimization?.decision ?? optimization?.last_decision, "F317 todavía no está activo"),
      stableFor: number(optimization?.stable_for_seconds),
      threshold: number(optimization?.hysteresis_percent, 15),
      persistence: text(optimization?.persistence, "volatile-/run"),
      supervisorRunning: optimization?.supervisor_running === true,
      engineRunning: optimization?.engine_running === true,
      lastSequence: number(optimization?.last_sequence),
      automaticApply: optimization?.automatic_apply === true
    },
    capabilities: capabilityRows.slice(0, 8).map((entry) =>
      typeof entry === "string" ? entry : text((entry as Json).title ?? (entry as Json).label ?? (entry as Json).id)
    )
  };
}

export const mockSnapshot: Snapshot = {
  source: "mock",
  version: "Lyoko Next · hardware desconectado",
  kernel: "5.10.260-openmitrastar-radiohw",
  uptimeSeconds: 15237,
  health: "ready",
  memoryFreeMiB: 31.8,
  radios: [
    { id: "2g", state: "ENABLED", ssid: "OpenMitraStar-Lab", channel: 1, bandwidth: 20, clients: 2, security: "WPA2-PSK-CCMP" },
    { id: "5g", state: "ready", ssid: "MOVISTAR_PLUS_55CB", channel: 36, bandwidth: 80, clients: 1, security: "WPA2-PSK-CCMP", txPower: "21 dBm" }
  ],
  optimization: { mode: "observe", decision: "mantener configuración", stableFor: 1120, threshold: 15, persistence: "volatile-/run", supervisorRunning: true, engineRunning: true, lastSequence: 42, automaticApply: false },
  capabilities: ["Linux 5.10 persistente", "Doble radio", "Control transaccional", "DFS fail-closed", "Paquetes firmados", "Rollback mtd3", "API autenticada", "Board profiles"]
};
