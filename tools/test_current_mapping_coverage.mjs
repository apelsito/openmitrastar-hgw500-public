import assert from "node:assert/strict";
import fs from "node:fs";

const root = new URL("../versions/openmitrastar-0.7-radio-control/src/", import.meta.url);
const html = fs.readFileSync(new URL("index.html", root), "utf8");
const js = fs.readFileSync(new URL("app.js", root), "utf8");

for (const [formId, dataName] of [["form24", "b24"], ["form5", "b5"]]) {
  const form = html.match(new RegExp(`<form id="${formId}"[\\s\\S]*?</form>`))?.[0];
  assert.ok(form, `${formId} not found`);
  const names = [...form.matchAll(/<(?:input|select)\b[^>]*\bname="([^"]+)"[^>]*>/g)]
    .map(match => match[1])
    .filter(name => name !== "band");
  const mappingSource = js.match(
    new RegExp(`rememberForm\\(\\$\\("#${formId}"\\),${dataName},(\\{[^;]+?\\})\\);`),
  )?.[1];
  assert.ok(mappingSource, `${formId} current-value mapping not found`);
  const mapping = JSON.parse(mappingSource);
  assert.deepEqual(
    names.filter(name => !(name in mapping)),
    [],
    `${formId} has controls without current-value mapping`,
  );
  assert.deepEqual(
    Object.keys(mapping).filter(name => !names.includes(name)),
    [],
    `${formId} mapping references controls absent from HTML`,
  );
}

console.log("all editable WiFi controls have current-value mappings");
