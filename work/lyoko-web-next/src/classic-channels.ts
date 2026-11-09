import { CHANNEL_CATALOGUE, channelLabelForWidth, describeChannel } from "./channel-policy.ts";
import type { ChannelWidth } from "./channel-policy.ts";

/** Add channel information to the existing console. No API or RF calls. */
export function installClassicChannels(doc: Document): () => void {
  const channel = doc.querySelector<HTMLSelectElement>("#r5-channel");
  const bandwidth = doc.querySelector<HTMLSelectElement>("#r5-bandwidth");
  const form = channel?.closest("form");
  const policy = doc.querySelector(".channel-policy");
  if (!channel || !bandwidth || !form || !policy) throw new Error("Classic channel controls missing");

  type Choice = { channel: string; width: string };
  const current = (): Choice => ({ channel: channel.value, width: bandwidth.value });
  let previous = current();
  let pending: { choice: Choice; previous: Choice; target: HTMLSelectElement } | null = null;
  let approvedEvent = false;
  const note = doc.createElement("p");
  note.className = "policy-footnote";
  note.id = "channel-bandwidth-policy";
  note.setAttribute("aria-live", "polite");
  channel.closest(".config-field")?.after(note);

  const dialog = doc.createElement("dialog");
  dialog.className = "risk-dialog";
  dialog.setAttribute("aria-labelledby", "channel-boundary-title");
  const title = doc.createElement("h2");
  title.id = "channel-boundary-title";
  title.textContent = "Canal fuera del perfil verificado";
  const reason = doc.createElement("p");
  const boundary = doc.createElement("p");
  boundary.textContent = "Esta confirmación permite revisar el canal en el formulario. No habilita emisión ni cambia el dominio, la calibración o los bloqueos del backend.";
  const buttons = doc.createElement("div");
  buttons.className = "button-row";
  const cancel = doc.createElement("button");
  cancel.type = "button"; cancel.className = "secondary"; cancel.textContent = "Volver";
  const confirm = doc.createElement("button");
  confirm.type = "button"; confirm.textContent = "Entendido, revisar canal";
  buttons.append(cancel, confirm); dialog.append(title, reason, boundary, buttons); doc.body.append(dialog);

  function ensureOption(value: string) {
    if (!Array.from(channel!.options).some(option => option.value === value)) {
      const option = doc.createElement("option"); option.value = value; channel!.add(option);
    }
  }
  function paint() {
    const choice = current();
    for (const value of CHANNEL_CATALOGUE) ensureOption(String(value));
    if (choice.channel) channel!.value = choice.channel;
    const width = Number(bandwidth!.value) as ChannelWidth;
    for (const option of Array.from(channel!.options)) {
      const label = channelLabelForWidth(Number(option.value), width);
      if (option.textContent !== label) option.textContent = label;
    }
    const info = describeChannel(Number(channel!.value), width);
    const timers = info.cacSeconds === null ? "CAC no determinado." : info.cacSeconds === 0 ? "Sin CAC DFS." : `CAC: ${info.cacSeconds} s. NOP tras radar: ${info.nopSeconds / 60} min.`;
    note.textContent = `${timers} ${info.reason} Seleccionar no transmite.`;
  }
  const remember = () => { if (!pending) previous = current(); };
  const input = (event: Event) => {
    if (event.target !== channel && event.target !== bandwidth) return;
    const info = describeChannel(Number(channel.value), Number(bandwidth.value) as ChannelWidth);
    if (!approvedEvent && (info.category === "outside-profile" || info.category === "unknown")) {
      event.stopImmediatePropagation();
      pending = { choice: current(), previous, target: event.target as HTMLSelectElement };
      reason.textContent = `Canal ${info.channel}, ${info.width} MHz. ${info.reason}`;
      if (!dialog.open) dialog.showModal();
      cancel.focus();
      return;
    }
    previous = current();
    queueMicrotask(paint);
  };
  function settle(accept: boolean) {
    if (!pending) return;
    const saved = pending;
    const choice = accept ? saved.choice : saved.previous;
    ensureOption(choice.channel);
    channel!.value = choice.channel; bandwidth!.value = choice.width;
    pending = null; dialog.close();
    approvedEvent = true;
    try { saved.target.dispatchEvent(new Event("input", { bubbles: true })); }
    finally { approvedEvent = false; }
    previous = current(); paint();
  }
  cancel.addEventListener("click", () => settle(false));
  confirm.addEventListener("click", () => settle(true));
  dialog.addEventListener("cancel", event => { event.preventDefault(); settle(false); });

  const manual = doc.createElement("details");
  const summary = doc.createElement("summary"); summary.textContent = "Inspeccionar otro número de canal";
  const label = doc.createElement("label"); label.textContent = "Canal (soporte pendiente de verificar) ";
  const entry = doc.createElement("input"); entry.type = "number"; entry.min = "1"; entry.max = "255";
  const inspect = doc.createElement("button"); inspect.type = "button"; inspect.className = "secondary"; inspect.textContent = "Revisar selección";
  label.append(entry); manual.append(summary, label, inspect); policy.append(manual);
  inspect.addEventListener("click", () => {
    if (!/^\d+$/.test(entry.value) || Number(entry.value) < 1 || Number(entry.value) > 255) { entry.reportValidity(); return; }
    previous = current(); ensureOption(entry.value); channel!.value = entry.value;
    channel!.dispatchEvent(new Event("input", { bubbles: true }));
  });

  channel.addEventListener("focus", remember);
  bandwidth.addEventListener("focus", remember);
  form.addEventListener("input", input, true);
  // Legacy refresh recreates the options. Keep the broader catalogue and its
  // bandwidth labels without altering the legacy state or sending requests.
  const observer = new MutationObserver(paint);
  observer.observe(channel, { childList: true, subtree: true });
  paint();
  return () => { observer.disconnect(); form.removeEventListener("input", input, true);
    channel.removeEventListener("focus", remember); bandwidth.removeEventListener("focus", remember);
    note.remove(); dialog.remove(); manual.remove(); };
}
