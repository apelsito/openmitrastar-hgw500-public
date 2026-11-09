import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { ApiError } from "./transport.ts";
import { RadioControl, scalar } from "./radio-control.ts";
import type { Action, Band, ControlContext, Setting } from "./radio-control.ts";

function SettingInput({ setting, value, disabled, change }: { setting: Setting; value: string; disabled: boolean; change: (value: string) => void }) {
  const id = `setting-${setting.id}`;
  if (setting.type === "boolean") return <select id={id} value={value} disabled={disabled} onChange={event => change(event.currentTarget.value)}>
    <option value="true">Activado</option><option value="false">Desactivado</option>
  </select>;
  if (Array.isArray(setting.allowed_values) && setting.type === "enum") {
    const values = [...new Set([...setting.allowed_values, ...(Array.isArray(setting.candidate_values) ? setting.candidate_values : [])].map(scalar))];
    return <select id={id} value={value} disabled={disabled} onChange={event => change(event.currentTarget.value)}>
      {values.map(option => <option key={option} value={option}>{option}</option>)}
    </select>;
  }
  if (setting.type === "integer" || setting.type === "string") return <input id={id} type={setting.type === "integer" ? "number" : "text"}
    value={value} disabled={disabled} autoComplete="off" onInput={event => change(event.currentTarget.value)} />;
  return <output id={id}>{scalar(setting.current) || "No publicado"}</output>;
}

export default function RadioWorkbench({ enabled }: { enabled: boolean }) {
  const client = useMemo(() => new RadioControl(), []);
  const [band, setBand] = useState<Band>("2g");
  const [context, setContext] = useState<ControlContext | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [notice, setNotice] = useState("");
  const [dfsAccepted, setDfsAccepted] = useState(false);
  const revision = useRef(0);
  const inFlight = useRef(false);

  const install = (value: ControlContext) => {
    setContext(value);
    setDraft(Object.fromEntries(value.contract.settings.map(setting => [setting.id, scalar(setting.current)])));
    setDfsAccepted(false);
  };
  useEffect(() => {
    const run = ++revision.current;
    setContext(null); setError(null); setNotice(""); setDfsAccepted(false);
    if (enabled) {
      setBusy(true);
      client.context(band).then(value => { if (run === revision.current) install(value); })
        .catch(reason => { if (run === revision.current) setError(reason); })
        .finally(() => { if (run === revision.current) setBusy(false); });
    }
    return () => { revision.current++; };
  }, [enabled, band]);

  const perform = async (task: () => Promise<string>) => {
    if (!enabled || busy || inFlight.current) return;
    inFlight.current = true; setBusy(true); setError(null); setNotice("");
    const run = revision.current;
    try {
      const message = await task();
      const fresh = await client.context(band);
      if (run === revision.current) { install(fresh); setNotice(message); }
    } catch (reason) {
      if (run === revision.current) {
        setContext(null);
        setError(reason instanceof ApiError ? reason : new ApiError("No se pudo completar la operación. Relee el estado."));
      }
    } finally {
      inFlight.current = false;
      if (run === revision.current) setBusy(false);
    }
  };
  const original = Object.fromEntries((context?.contract.settings ?? []).map(setting => [setting.id, scalar(setting.current)]));
  const changes = Object.fromEntries(Object.entries(draft).filter(([id, value]) => Object.prototype.hasOwnProperty.call(original, id) && value !== original[id]));
  const planChanges = Object.fromEntries(Object.entries(changes).filter(([id]) => ["channel", "bandwidth"].includes(id)));
  const allWritable = context && Object.keys(changes).every(id => context.contract.settings.find(setting => setting.id === id)?.writable === true);
  const dfs = band === "5g" && Number(changes.channel) >= 52;
  const dfsReady = context?.contract.settings.find(setting => setting.id === "channel")?.dfs_backend_ready === true;
  const pending = context?.pending;
  const canPrepare = !!context && Object.keys(changes).length > 0 && allWritable && (!dfs || (dfsReady && dfsAccepted)) &&
    (!pending || (pending.owned && pending.phase === "staged" && pending.band === band));
  const act = (action: Action) => perform(async () => {
    if (!pending?.owned) throw new ApiError("Falta una transacción propia");
    const result = await client.act(action, pending.id);
    return action === "apply" ? result.commit === "no-op" ? "Configuración ya coincidente; no se ha cambiado la radio." : "Aplicado y leído. Confirma para conservarlo; el watchdog revertirá si no confirmas."
      : action === "commit" ? "Configuración confirmada en RAM. No se ha escrito persistencia."
      : "Configuración anterior restaurada y leída.";
  });

  return <section class="panel detail radio-workbench" aria-busy={busy}>
    <div class="section-title"><div><span class="eyebrow">Ajustes de radio</span><h2>Preparar, comprobar y confirmar</h2></div>
      <button class="secondary" disabled={!enabled || busy} onClick={() => void perform(async () => "Estado actualizado.")}>Releer estado</button></div>
    <div class="band-switch" role="group" aria-label="Radio a configurar">
      <button class="secondary" aria-pressed={band === "2g"} disabled={busy} onClick={() => setBand("2g")}>2,4 GHz</button>
      <button class="secondary" aria-pressed={band === "5g"} disabled={busy} onClick={() => setBand("5g")}>5 GHz</button>
    </div>
    {!enabled && <p>La demostración no carga ni modifica ajustes de un equipo. Con una sesión real aparecerán los controles publicados por su API.</p>}
    {error && <div class="control-message" role="alert"><p>{error.message}</p>
      <p>{error.ambiguous ? "No repitas el envío: relee la transacción para comprobar qué ocurrió." : "Los controles quedan bloqueados hasta releer el estado."}</p>
      {error.code === "auth" && <a href="/index.cgi">Iniciar sesión</a>}
    </div>}
    {notice && <p class="control-message" role="status">{notice}</p>}
    {context && <>
      <form onSubmit={event => { event.preventDefault(); if (canPrepare) void perform(async () => {
        await client.prepare(band, changes, original, dfsAccepted);
        return "Cambio preparado, todavía no aplicado. Revisa el antes/después.";
      }); }}>
        <div class="settings-grid">{context.contract.settings.map(setting => {
          const inspect = band === "5g" && ["channel", "bandwidth"].includes(setting.id) && setting.type === "enum";
          const disabled = busy || (!setting.writable && !inspect) || scalar(setting.current) === "";
          return <div class="setting-row" key={setting.id}>
            <label for={`setting-${setting.id}`}>{setting.label}</label>
            <SettingInput setting={setting} value={draft[setting.id] ?? ""} disabled={disabled} change={value => { setDraft({ ...draft, [setting.id]: value }); setDfsAccepted(false); }} />
            <small>{setting.writable ? "Editable según el backend" : inspect ? "Solo planificación; aplicación bloqueada" : "Solo lectura"}</small>
            {(setting.blocked_reason || setting.risk || setting.recommended) && <details><summary>Estado y ayuda</summary>
              {setting.blocked_reason && <p>{setting.blocked_reason}</p>}
              {setting.recommended && <p>Recomendación del contrato: {setting.recommended}</p>}
              {setting.risk && <p>{setting.risk}</p>}
            </details>}
          </div>;
        })}</div>
        {Object.keys(changes).length > 0 && <div class="change-preview"><h3>Revisión del cambio</h3>
          <dl class="definition-grid">{Object.entries(changes).map(([id, value]) => <div key={id}><dt>{context.contract.settings.find(s => s.id === id)?.label ?? id}</dt><dd>{original[id]} → {value}</dd></div>)}</dl>
        </div>}
        {dfs && <label class="dfs-confirm"><input type="checkbox" disabled={!dfsReady || busy} checked={dfsAccepted} onChange={event => setDfsAccepted(event.currentTarget.checked)} />
          Acepto la política ES/DFS para este cambio. {dfsReady ? "El backend declara proveedor operativo." : "Bloqueado: falta proveedor operativo."}</label>}
        <div class="control-actions">
          <button class="secondary" type="submit" disabled={busy || !canPrepare}>Preparar cambio</button>
          {band === "5g" && <button class="secondary" type="button" disabled={busy || !Object.keys(planChanges).length} onClick={() => void perform(async () => {
            const result = await client.plan5g(planChanges, original);
            return `Plan calculado sin aplicar. Aplicación declarada por el backend: ${result.apply_allowed === true ? "permitida" : "bloqueada"}.`;
          })}>Planificar canal/ancho</button>}
        </div>
      </form>
      {pending && <section class="transaction-review" aria-label="Transacción pendiente"><h3>{pending.owned ? `Cambio ${pending.phase === "staged" ? "preparado" : "aplicado"} · ${pending.band}` : "Transacción de otra sesión"}</h3>
        {pending.owned && <><dl class="definition-grid">{Object.keys(pending.after).map(id => <div key={id}><dt>{id}</dt><dd>{scalar(pending.before[id])} → {scalar(pending.after[id])}</dd></div>)}</dl>
          <p>Aplicar puede desconectar clientes. Tras aplicar, el backend verifica y activa el rollback automático hasta que confirmes.</p>
          <div class="control-actions">
            <button class="secondary" disabled={busy || pending.phase !== "staged" || !context.applyEnabled} onClick={() => void act("apply")}>Aplicar cambio preparado</button>
            <button class="secondary" disabled={busy || pending.phase !== "applied"} onClick={() => void act("commit")}>Confirmar en RAM</button>
            <button class="secondary" disabled={busy || pending.phase !== "applied"} onClick={() => void act("rollback")}>Revertir al estado anterior</button>
          </div></>}
      </section>}
    </>}
  </section>;
}
