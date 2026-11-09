import { ApiError, object, requestApi } from "./transport.ts";
import type { Fetcher, Json } from "./transport.ts";

export type Band = "2g" | "5g";
export type Action = "apply" | "commit" | "rollback";
export type Setting = {
  id: string; label: string; type: string; current: unknown; writable: boolean;
  allowed_values: unknown; candidate_values?: unknown;
  blocked_reason: string; recommended: string; risk: string; dfs_backend_ready: boolean;
};
export type Contract = { band: Band; settings: Setting[] };
export type Pending = { id: string; band: Band | null; phase: "staged" | "applied"; owned: boolean; before: Json; after: Json };
export type ControlContext = { contract: Contract; csrf: string; applyEnabled: boolean; pending: Pending | null };

const CONFIRM = "OPENMITRASTAR_CONFIG_TRANSACTION_V1";
const SETTINGS = new Set(["ssid", "ssid_broadcast", "client_isolation", "wmm", "short_gi", "channel", "bandwidth",
  "beacon_interval", "dtim_period", "retry_count", "ldpc", "forty_only", "ba_control", "ba_max", "ampdu_density",
  "multicast_rate", "tpc_interval", "max_clients"]);
const text = (value: unknown, fallback = "") => typeof value === "string" ? value : fallback;
export const scalar = (value: unknown) => typeof value === "string" || typeof value === "number" || typeof value === "boolean" ? String(value) : "";
function reject(message: string, code = "contract"): never { throw new ApiError(message, 0, code); }
function requireBand(value: string): asserts value is Band { if (value !== "2g" && value !== "5g") reject("Radio desconocida"); }

export function parseContract(value: Json, band: Band): Contract {
  const settings = object(value.settings);
  if (value.ok !== true || value.schema !== "lyoko.radio.contract/v1" || value.id !== band ||
      !["lyoko.radio.settings/v1", "lyoko.radio.settings/v2"].includes(text(settings.schema)) ||
      settings.id !== band || !Array.isArray(settings.settings)) reject("Contrato de radio incompleto");
  const seen = new Set<string>();
  const rows = (settings.settings as unknown[]).map(raw => {
    const row = object(raw);
    const id = text(row.id);
    if (!/^[a-z][a-z0-9_]{0,63}$/.test(id) || seen.has(id)) reject("Identificador de ajuste inválido o repetido");
    seen.add(id);
    return { id, label: text(row.label, id), type: text(row.type, "readonly"), current: row.current,
      writable: row.writable === true && SETTINGS.has(id) && ["boolean", "string", "enum", "integer"].includes(text(row.type)),
      allowed_values: row.allowed_values, candidate_values: row.candidate_values,
      blocked_reason: text(row.blocked_reason), recommended: text(row.recommended), risk: text(row.risk),
      dfs_backend_ready: row.dfs_backend_ready === true };
  });
  return { band, settings: rows };
}

export function parsePending(value: Json): Pending | null {
  if (value.ok !== true || value.schema !== "lyoko.config.status/v2" || typeof value.pending !== "boolean") reject("Estado de transacción inválido");
  if (!value.pending && value.phase === "none") return null;
  if (!["staged", "applied"].includes(text(value.phase))) reject("Fase de transacción desconocida");
  if (value.owned_by_session !== true) return { id: "", band: null, phase: value.phase as Pending["phase"], owned: false, before: {}, after: {} };
  if (!/^[a-f0-9]{64}$/.test(text(value.transaction_id)) || !["2g", "5g"].includes(text(value.band))) reject("Identidad de transacción inválida");
  const snapshot = object(value.snapshot);
  return { id: text(value.transaction_id), band: value.band as Band, phase: value.phase as Pending["phase"], owned: true,
    before: object(snapshot.before), after: object(snapshot.after) };
}

function validateValue(setting: Setting, value: string, plan: boolean): void {
  const allowed = setting.allowed_values;
  if (setting.type === "boolean") {
    if (value !== "true" && value !== "false") reject(`Valor booleano inválido: ${setting.label}`, "value");
  } else if (setting.type === "enum" || (plan && Array.isArray(allowed))) {
    const options = [...(Array.isArray(allowed) ? allowed : []), ...(plan && Array.isArray(setting.candidate_values) ? setting.candidate_values : [])];
    if (!options.some(item => scalar(item) === value)) reject(`Valor fuera del contrato: ${setting.label}`, "value");
  } else if (setting.type === "integer") {
    const range = object(allowed);
    const n = Number(value);
    if (!/^-?\d+$/.test(value) || !Number.isSafeInteger(n) || typeof range.min !== "number" || typeof range.max !== "number" || n < range.min || n > range.max) reject(`Valor fuera del rango: ${setting.label}`, "value");
  } else if (setting.type === "string" && setting.id === "ssid") {
    const range = object(allowed);
    const min = typeof range.min_length === "number" ? range.min_length : 1;
    const max = typeof range.max_length === "number" ? range.max_length : 32;
    if (value.length < min || value.length > max || !/^[A-Za-z0-9_.:@+ -]+$/.test(value)) reject("SSID fuera del formato permitido", "value");
  } else reject(`Tipo no editable: ${setting.label}`, "value");
}

export function validateChanges(contract: Contract, changes: Record<string, string>, original: Record<string, string>, plan = false): URLSearchParams {
  const body = new URLSearchParams();
  for (const [id, value] of Object.entries(changes)) {
    const setting = contract.settings.find(item => item.id === id);
    if (!setting || !SETTINGS.has(id) || (!plan && !setting.writable) || (plan && !["channel", "bandwidth"].includes(id))) reject(`Ajuste bloqueado: ${id}`, "blocked");
    if (!Object.prototype.hasOwnProperty.call(original, id) || original[id] !== scalar(setting.current)) reject(`El valor de ${setting.label} ha cambiado. Relee el estado.`, "stale");
    if (typeof value !== "string") reject("Valor de ajuste inválido", "value");
    validateValue(setting, value, plan);
    if (value !== scalar(setting.current)) body.set(id, value);
  }
  if (!Array.from(body).length || body.toString().length > 512) reject("No hay cambios válidos o el cuerpo supera el límite de la API", "value");
  return body;
}

export class RadioControl {
  fetcher: Fetcher;
  constructor(fetcher: Fetcher = fetch) { this.fetcher = fetcher; }
  async read(path: string): Promise<Json> { return requestApi(path, {}, this.fetcher); }

  async state(): Promise<{ csrf: string; applyEnabled: boolean; pending: Pending | null }> {
    const [status, txn] = await Promise.all([this.read("/api/v1/status"), this.read("/api/v1/config/status")]);
    if (status.ok !== true || status.schema !== "lyoko.api.status/v1" || !text(status.csrf) || /[\r\n]/.test(text(status.csrf))) reject("Falta una sesión de control válida", "auth");
    return { csrf: text(status.csrf), applyEnabled: status.config_apply_enabled === true, pending: parsePending(txn) };
  }

  async context(band: Band): Promise<ControlContext> {
    requireBand(band);
    const [state, raw] = await Promise.all([this.state(), this.read(`/api/v1/radios/${band}?view=contract`)]);
    return { ...state, contract: parseContract(raw, band) };
  }

  async post(path: string, csrf: string, body: URLSearchParams, headers: Record<string, string> = {}): Promise<Json> {
    return requestApi(path, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded", "X-OM-CSRF": csrf, ...headers }, body }, this.fetcher);
  }

  async prepare(band: Band, changes: Record<string, string>, original: Record<string, string>, dfsAcknowledged = false): Promise<Json> {
    const context = await this.context(band);
    if (context.pending && (!context.pending.owned || context.pending.phase === "applied" || context.pending.band !== band)) reject("Hay otra transacción pendiente", "pending");
    const body = validateChanges(context.contract, changes, original);
    const dfs = band === "5g" && body.has("channel") && Number(body.get("channel")) >= 52;
    if (dfs && (!dfsAcknowledged || context.contract.settings.find(s => s.id === "channel")?.dfs_backend_ready !== true)) reject("DFS requiere proveedor operativo y aceptación explícita", "dfs");
    const result = await this.post(`/api/v1/radios/${band}/stage`, context.csrf, body, dfs ? { "X-OM-Regulatory-Ack": "OPENMITRASTAR_ES_DFS_V1" } : {});
    if (result.ok !== true || result.schema !== "lyoko.config.stage/v2" || !/^[a-f0-9]{64}$/.test(text(result.transaction_id)) || result.band !== band || result.applied !== false) reject("Preparación no confirmada; relee el estado", "result");
    return result;
  }

  async plan5g(changes: Record<string, string>, original: Record<string, string>): Promise<Json> {
    const context = await this.context("5g");
    return this.post("/api/v1/radios/5g/plan", context.csrf, validateChanges(context.contract, changes, original, true));
  }

  async readback(band: Band, expected: Json): Promise<void> {
    if (!Object.keys(expected).length) reject("Falta la instantánea de verificación", "readback");
    const current = await this.read(`/api/v1/radios/${band}`);
    if (current.ok !== true) reject("Lectura de radio inválida", "readback");
    for (const [id, value] of Object.entries(expected)) {
      if (!SETTINGS.has(id) || !Object.prototype.hasOwnProperty.call(current, id) || scalar(current[id]) !== scalar(value)) reject(`Lectura distinta a la esperada: ${id}`, "readback");
    }
  }

  async act(action: Action, expectedId: string): Promise<Json> {
    if (!["apply", "commit", "rollback"].includes(action)) reject("Acción desconocida");
    const state = await this.state();
    const pending = state.pending;
    if (!pending?.owned || !pending.band || pending.id !== expectedId) reject("La transacción ya no pertenece a esta vista/sesión", "stale");
    if (pending.phase !== (action === "apply" ? "staged" : "applied")) reject("La fase de la transacción ha cambiado", "phase");
    if (action === "apply") {
      if (!state.applyEnabled) reject("Aplicación material desactivada por el backend", "apply-disabled");
      const contract = parseContract(await this.read(`/api/v1/radios/${pending.band}?view=contract`), pending.band);
      const changes = Object.fromEntries(Object.entries(pending.after).map(([key, value]) => [key, scalar(value)]));
      const before = Object.fromEntries(Object.entries(pending.before).map(([key, value]) => [key, scalar(value)]));
      validateChanges(contract, changes, before);
      if (pending.band === "5g" && Number(changes.channel) >= 52 && contract.settings.find(s => s.id === "channel")?.dfs_backend_ready !== true) reject("El proveedor DFS ya no está operativo", "dfs");
    }
    if (action === "commit") await this.readback(pending.band, pending.after);
    const body = new URLSearchParams({ _confirm: CONFIRM, _transaction: expectedId });
    const result = await this.post(`/api/v1/config/${action}`, state.csrf, body, { "X-OM-Confirm": CONFIRM, "X-OM-Transaction": expectedId });
    if (result.ok !== true || result.transaction_id !== expectedId) reject("Identidad de respuesta distinta; relee el estado", "result");
    if (action === "commit") {
      if (result.committed !== true) reject("Confirmación no verificada", "result");
    } else {
      const success = action === "apply" ? result.applied : result.rolled_back;
      if (success !== true || result.verified !== true) reject("El backend no ha verificado la operación", "readback");
      await this.readback(pending.band, action === "apply" ? pending.after : pending.before);
    }
    return result;
  }
}
