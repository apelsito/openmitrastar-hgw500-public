import { useEffect, useRef, useState } from "preact/hooks";
import { CHANNEL_CATALOGUE, describeChannel } from "./channel-policy.ts";
import type { ChannelWidth } from "./channel-policy.ts";

type Choice = { channel: number; width: ChannelWidth };
export default function ChannelExplorer({ useChoice }: { useChoice?: (choice: Choice) => void }) {
  const [choice, setChoice] = useState<Choice>({ channel: 36, width: 20 });
  const [manual, setManual] = useState("");
  const [pending, setPending] = useState<Choice | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const info = describeChannel(choice.channel, choice.width);
  const propose = (next: Choice) => {
    const result = describeChannel(next.channel, next.width);
    if (result.category === "outside-profile" || result.category === "unknown") setPending(next);
    else setChoice(next);
  };
  useEffect(() => {
    if (pending && !dialog.current?.open) dialog.current?.showModal();
    if (!pending && dialog.current?.open) dialog.current.close();
  }, [pending]);
  const warning = pending && describeChannel(pending.channel, pending.width);
  return <section class="panel detail channel-explorer">
    <span class="eyebrow">Mapa completo · 5 GHz</span><h2>Canales y condiciones de uso</h2>
    <p>Este mapa permite inspeccionar canales. La selección no ordena ninguna transmisión.</p>
    <div class="settings-grid">
      <div class="setting-row"><label for="catalogue-channel">Canal primario</label><select id="catalogue-channel" value={choice.channel}
        onChange={event => propose({ ...choice, channel: Number(event.currentTarget.value) })}>
        {!CHANNEL_CATALOGUE.includes(choice.channel) && <option value={choice.channel}>{choice.channel} · manual</option>}
        {CHANNEL_CATALOGUE.map(channel => <option key={channel} value={channel}>{channel}</option>)}
      </select></div>
      <div class="setting-row"><label for="catalogue-width">Ancho nominal</label><select id="catalogue-width" value={choice.width}
        onChange={event => propose({ ...choice, width: Number(event.currentTarget.value) as ChannelWidth })}>
        {[20, 40, 80].map(width => <option key={width} value={width}>{width} MHz</option>)}
      </select></div>
      <div class="setting-row"><label for="manual-channel">Otro número de canal</label><input id="manual-channel" type="number" min="1" max="255" value={manual} onInput={event => setManual(event.currentTarget.value)} />
        <button class="secondary" disabled={!/^\d+$/.test(manual) || Number(manual) < 1 || Number(manual) > 255} onClick={() => propose({ ...choice, channel: Number(manual) })}>Inspeccionar</button></div>
    </div>
    <dl class="definition-grid">
      <div><dt>Intervalo nominal</dt><dd>{info.lowMHz === null ? "Sin verificar" : `${info.lowMHz}–${info.highMHz} MHz`}</dd></div>
      <div><dt>CAC del perfil</dt><dd>{info.cacSeconds === null ? "Sin determinar" : info.cacSeconds === 0 ? "No requiere DFS" : `${info.cacSeconds} segundos`}</dd></div>
      <div><dt>NOP tras radar</dt><dd>{info.nopSeconds ? `${info.nopSeconds / 60} minutos` : "No indicado para esta selección"}</dd></div>
    </dl>
    <p class="control-message">{info.reason}</p>
    <p>La frecuencia central por sí sola no basta: importan el bloque completo, el dominio, la potencia y la calibración. Una espera adicional impuesta por el backend debe conservarse.</p>
    {useChoice && <button class="secondary" onClick={() => useChoice(choice)}>Llevar esta selección al formulario</button>}
    <dialog ref={dialog} onCancel={event => { event.preventDefault(); setPending(null); }} aria-labelledby="channel-warning-title">
      <h2 id="channel-warning-title">Selección fuera del perfil verificado</h2>
      {warning && <><p>Canal {warning.channel} · {warning.width} MHz.</p><p>{warning.reason}</p></>}
      <p>Continuar solo permite inspeccionar y planificar. No cambia el dominio ni habilita un controlador que no soporte esa selección.</p>
      <div class="control-actions"><button class="secondary" autoFocus onClick={() => setPending(null)}>Volver</button>
        <button class="secondary" onClick={() => { if (pending) setChoice(pending); setPending(null); }}>Entendido, inspeccionar canal</button></div>
    </dialog>
  </section>;
}
