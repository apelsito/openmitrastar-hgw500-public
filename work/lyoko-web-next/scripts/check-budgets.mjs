import { brotliCompressSync, gzipSync } from "node:zlib";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const root = new URL("../dist", import.meta.url).pathname.replace(/^\/(.:)/, "$1");
const files = [];
const walk = (dir) => readdirSync(dir).forEach((name) => {
  const path = join(dir, name); const stat = statSync(path);
  if (stat.isDirectory()) walk(path); else files.push(path);
});
walk(root);
const rows = files.map((path) => {
  const data = readFileSync(path);
  return { file: relative(root, path).replaceAll("\\", "/"), bytes: data.length, gzip: gzipSync(data).length, brotli: brotliCompressSync(data).length };
});
const js = rows.filter((r) => r.file.endsWith(".js")).reduce((sum, r) => sum + r.brotli, 0);
const css = rows.filter((r) => r.file.endsWith(".css")).reduce((sum, r) => sum + r.brotli, 0);
if (js > 48 * 1024) throw new Error(`JS Brotli budget exceeded: ${js}`);
if (css > 16 * 1024) throw new Error(`CSS Brotli budget exceeded: ${css}`);
console.log(JSON.stringify({ status: "PASS", budgets: { js_brotli: js, css_brotli: css }, files: rows }, null, 2));
