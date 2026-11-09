import { ApiError, object, requestApi } from "./transport.ts";
import type { Fetcher, Json } from "./transport.ts";

export type DfsObservation = {
  kind: "native" | "legacy";
  simulation: boolean;
  backendReady: boolean | null;
  detectorRunning: boolean | null;
  detectorLiveness: boolean | null;
  channel: number | null;
  bandwidth: number | null;
  region: string | null;
  cac: { state: string; active: boolean | null; remaining: number | null };
  nop: { active: boolean | null; complete: boolean; entries: { channel: number; remaining: number | null }[] };
  txAuthorized: boolean | null;
  endpoint: string;
};

const bool = (value: unknown): boolean | null => typeof value === "boolean" ? value : null;
const integer = (value: unknown): number | null => typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
const positive = (value: unknown): number | null => { const n = integer(value); return n !== null && n > 0 ? n : null; };
const string = (value: unknown): string | null => typeof value === "string" && value.length > 0 && value.length <= 120 ? value : null;
const nativeEndpoint = "/api/v1/radios/5g/dfs";
const legacyEndpoint = "/api/v1/diagnostics";

/** Normalize evidence, never infer permission from a backend or a local timer. */
export function normalizeDfs(payload: Json, endpoint = nativeEndpoint): DfsObservation {
  const legacy = payload.schema === "lyoko.api.diagnostics/v1" ? object(payload.dfs) : payload;
  const schema = legacy.schema;
  const native = schema === "lyoko.radio.dfs-observation/v1";
  if (!native && schema !== "lyoko.radio.dfs/v1" && schema !== "lyoko.api.radar-native/v1" && schema !== "lyoko.api.radar-shadow/v1") {
    throw new ApiError("El firmware no publica un contrato DFS reconocido.", 0, "dfs-schema");
  }
  const simulation = payload.simulation === true || legacy.simulation === true;
  const detector = object(legacy.detector);
  const cac = object(legacy.cac);
  const nop = object(legacy.nop);
  const tx = object(legacy.tx);
  const channel = positive(legacy.current_channel);
  const states = new Set(["running", "required", "complete", "not-required", "unknown", "inconsistent"]);
  const reportedState = typeof cac.state === "string" && states.has(cac.state) ? cac.state : "unknown";
  // The old native v1 field equates readiness with authorization. Ignore it.
  const backendReady = bool(legacy.backend_ready) ?? (legacy.writable === false ? false : null);
  const detectorRunning = native ? bool(detector.running) : null;
  const cacActive = native ? bool(cac.active) : null;
  const nopEntriesValid = Array.isArray(nop.entries) && nop.entries.length <= 64 && nop.entries.every(raw => {
    const row = object(raw); const ch = positive(row.channel);
    return ch !== null && ch <= 255 && (row.remaining_seconds == null || integer(row.remaining_seconds) !== null);
  });
  const entries = native && Array.isArray(nop.entries) ? nop.entries.flatMap(raw => {
    const row = object(raw); const ch = positive(row.channel);
    return ch !== null && ch <= 255 ? [{ channel: ch, remaining: integer(row.remaining_seconds) }] : [];
  }).slice(0, 64) : [];
  const nopActive = native ? bool(nop.active) : null;
  const reportedTx = native ? bool(tx.authorized) : null;
  const remaining = native ? integer(cac.remaining_seconds) : null;
  const contradictoryCac = (reportedState === "complete" || reportedState === "not-required") &&
    (cacActive === true || (remaining !== null && remaining > 0));
  const nopComplete = native && nop.complete === true && nopEntriesValid;
  // A contradictory reading can close permission, but cannot grant it.
  const txAuthorized = reportedTx === false ? false : reportedTx === true && backendReady === true && detectorRunning === true &&
    cacActive === false && (reportedState === "complete" || reportedState === "not-required") && nopActive === false &&
    entries.length === 0 && nopComplete && !contradictoryCac ? true : null;
  return {
    kind: native ? "native" : "legacy", simulation, backendReady, detectorRunning,
    detectorLiveness: native ? bool(detector.liveness_verified) : null,
    channel: channel !== null && channel <= 255 ? channel : null,
    bandwidth: [20, 40, 80].includes(Number(legacy.bandwidth_mhz)) ? positive(legacy.bandwidth_mhz) : null,
    region: string(legacy.region),
    cac: { state: contradictoryCac ? "inconsistent" : native ? reportedState : "unknown", active: cacActive, remaining },
    nop: { active: nopActive, complete: nopComplete, entries }, txAuthorized, endpoint,
  };
}

async function loadLegacyDfsObservation(fetcher: Fetcher): Promise<DfsObservation> {
  const payload = await requestApi(legacyEndpoint, {}, fetcher);
  if (payload.ok !== true || payload.schema !== "lyoko.api.diagnostics/v1" || object(payload.dfs).ok !== true) {
    throw new ApiError("El firmware no publica un contrato DFS reconocido.", 0, "dfs-schema");
  }
  const observation = normalizeDfs(payload, legacyEndpoint);
  if (observation.kind !== "legacy") {
    throw new ApiError("El firmware no publica un contrato DFS heredado reconocido.", 0, "dfs-schema");
  }
  return observation;
}

export async function loadDfsObservation(fetcher: Fetcher = fetch): Promise<DfsObservation> {
  let payload: Json;
  try { payload = await requestApi(nativeEndpoint, {}, fetcher); }
  catch (error) {
    // Authentication errors, malformed data and timeouts must remain visible.
    if (!(error instanceof ApiError) || error.status !== 404 || error.code === "invalid-json") throw error;
    return loadLegacyDfsObservation(fetcher);
  }
  // F314's CGI ignores PATH_INFO and serves ordinary 5 GHz status for /dfs.
  // Only that explicit legacy contract permits the diagnostics fallback.
  if (payload.ok === true && payload.schema === "lyoko.radio.status/v1" && payload.id === "5g") {
    return loadLegacyDfsObservation(fetcher);
  }
  return normalizeDfs(payload);
}

export function durationLabel(seconds: number | null): string {
  if (seconds === null) return "No publicado";
  return seconds >= 60 ? `${Math.floor(seconds / 60)} min${seconds % 60 ? ` ${seconds % 60} s` : ""}` : `${seconds} s`;
}
