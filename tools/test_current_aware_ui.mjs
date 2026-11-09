import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const html = fs.readFileSync(
  new URL("../versions/openmitrastar-0.7-radio-control/src/index.html", import.meta.url),
  "utf8",
);
const source = fs.readFileSync(
  new URL("../versions/openmitrastar-0.7-radio-control/src/app.js", import.meta.url),
  "utf8",
);
assert.match(html, /app\.js\?v=0\.9\.1/, "app.js must be cache-busted across firmware upgrades");
for (const stylesheet of ["app.css", "visibility.css", "telemetry.css"]) {
  assert.ok(html.includes(`${stylesheet}?v=0.9.1`), `${stylesheet} must be cache-busted`);
}
const start = source.indexOf("function currentLabel");
const end = source.indexOf("function rememberForm", start);
assert.ok(start >= 0 && end > start, "current-aware functions not found");

const context = {
  document: {createElement: () => ({className: "", textContent: ""})},
};
vm.createContext(context);
vm.runInContext(`${source.slice(start, end)}; this.currentLabel=currentLabel; this.showCurrent=showCurrent`, context);

assert.equal(context.currentLabel("channel.wlan1", "0"), "Automático");
assert.equal(context.currentLabel("bandwidth.wlan1", "1"), "40 MHz");
assert.equal(context.currentLabel("security.wifi0", "wpa2_aes"), "WPA2 · AES");
assert.equal(context.currentLabel("passphrase.wifi0", "yes"), "Configurada");
assert.equal(context.currentLabel("dtim.wifi0", "2"), "2 balizas");
assert.equal(context.currentLabel("scs.wifi0", "1"), "Activo");
assert.equal(context.currentLabel("band.wlan1", "11"), "802.11 b/g/n");
assert.equal(context.currentLabel("shortgi.wlan1", "1"), "Corto");
assert.equal(context.currentLabel("bcnint.wlan1", "100"), "100 ms");
assert.equal(context.currentLabel("beamforming.wifi0", "1"), "Activo");
assert.equal(context.currentLabel("ssid_broadcast.wifi0", "0"), "Oculta");

const description = {className: "description"};
const label = {
  badge: null,
  querySelector(selector) { return selector === ".current-setting" ? this.badge : description; },
  insertBefore(node) { this.badge = node; },
};
const select = {
  name: "pmf.wifi0",
  tagName: "SELECT",
  options: [{textContent: "Sin cambio"}],
  closest() { return {querySelector: () => label}; },
  dataset: {},
};
context.showCurrent(select, "0");
assert.equal(label.badge.textContent, "Actual: Apagado");
assert.equal(select.options[0].textContent, "Conservar · actual: Apagado");

const password = {
  name: "passphrase.wifi0",
  tagName: "INPUT",
  type: "password",
  closest() { return {querySelector: () => label}; },
  dataset: {},
};
context.showCurrent(password, "yes");
assert.equal(password.placeholder, "Configurada · escribe para cambiar");

console.log("current-aware UI tests passed");
