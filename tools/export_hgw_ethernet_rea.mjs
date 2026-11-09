/** Offline whole-module REA export. Uses the existing project ARC lane only. */
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { pathToFileURL } from 'node:url';

const [lab, target, destination, seeds] = process.argv.slice(2);
if (!lab || !target || !destination) throw new Error('Usage: LAB TARGET NEW_OUTPUT');
if (![lab, target, destination].every(path.isAbsolute)) throw new Error('Absolute paths required');
fs.mkdirSync(destination, { recursive: false });
const manifestPath = path.join(lab, 'manifest.json');
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
const digest = p => createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const original = digest(target);
const env = { ...process.env, GHIDRA_INSTALL_DIR: manifest.ghidra,
  JAVA_HOME: '/usr/lib/jvm/java-21-openjdk-amd64',
  REA_GHIDRA_LANGUAGE_ID: manifest.language_id,
  REA_GHIDRA_COMPILER_SPEC_ID: manifest.compiler_spec_id,
  REA_ANALYSIS_PROVIDER: 'ghidra', REA_LOG_LEVEL: 'silent',
  ...(seeds ? { REA_GHIDRA_SEED_FILE: seeds } : {}) };
const load = async relative => import(pathToFileURL(path.join(manifest.runtime, 'dist', relative)).href);
const { parseConfig } = await load('config/parseConfig.js');
const { createBinarySession } = await load('composition/binary.js');
const { silentLogger } = await load('logger.js');
const config = parseConfig(env);
if (!config.ok) throw new Error(JSON.stringify(config.error));
const session = createBinarySession(config.value, silentLogger, env);
const write = (name, value) => fs.writeFileSync(path.join(destination, name), JSON.stringify(value, null, 2) + '\n', { flag: 'wx' });
const rows = [];
const started = new Date().toISOString();
let failure = null;
try {
  const opened = await session.open(target, { providerId: 'ghidra' });
  write('open.json', opened);
  if (!opened.ok) throw new Error(JSON.stringify(opened.error));
  const overview = await session.execute('binary_overview', {});
  write('overview.json', overview);
  const inventory = await session.execute('list_procedures', {});
  write('procedures.json', inventory);
  if (!inventory.ok) throw new Error(JSON.stringify(inventory.error));
  const procedures = inventory.value.result.filter(p => !p.procedure?.external);
  console.log(JSON.stringify({ started, target, functions: procedures.length, output: destination }));
  const c = fs.openSync(path.join(destination, 'recovered-pseudocode.c'), 'wx');
  const asm = fs.openSync(path.join(destination, 'recovered-assembly.txt'), 'wx');
  try {
    for (const [index, procedure] of procedures.entries()) {
      const selector = { procedure: procedure.address };
      const info = await session.execute('procedure_info', selector);
      const pseudo = await session.execute('procedure_pseudo_code', selector);
      const assembly = await session.execute('procedure_assembly', selector);
      const references = await session.execute('procedure_references', selector);
      write(`function-${String(index).padStart(4, '0')}.json`, { procedure, info, pseudocode: pseudo, assembly, references });
      fs.writeSync(c, `\n/* REA reconstruction; ${procedure.address} ${procedure.value}; not original source */\n`);
      fs.writeSync(c, pseudo.ok && typeof pseudo.value.result === 'string' ? pseudo.value.result + '\n' : '/* UNRESOLVED */\n');
      fs.writeSync(asm, `\n${procedure.address} ${procedure.value}\n`);
      fs.writeSync(asm, assembly.ok ? JSON.stringify(assembly.value.result, null, 2) + '\n' : 'UNRESOLVED\n');
      const row = { index, address: procedure.address, name: procedure.value,
        pseudocode: pseudo.ok && typeof pseudo.value.result === 'string', assembly: assembly.ok,
        info: info.ok ? info.value.result : null,
        references: references.ok,
        warnings: pseudo.ok && typeof pseudo.value.result === 'string' ?
          [...pseudo.value.result.matchAll(/WARNING:[^\n]*/g)].map(x => x[0]) : [],
        errors: [info, pseudo, assembly, references].filter(x => !x.ok).map(x => x.error) };
      rows.push(row);
      if ((index + 1) % 10 === 0 || index + 1 === procedures.length)
        console.log(JSON.stringify({ target: path.basename(target), completed: index + 1, total: procedures.length, pseudocode: rows.filter(x => x.pseudocode).length }));
    }
  } finally { fs.closeSync(c); fs.closeSync(asm); }
} catch (error) { failure = String(error.stack || error); }
finally {
  // Export retained complete evidence before closing the ephemeral database.
  write('evidence-bundle.json', session.exportEvidenceBundle());
  const closed = await session.close();
  write('close.json', closed);
  const result = { schema: 'openmitrastar.ethernet-rea-module/v1',
    status: failure ? 'NO_GO_REA_EXPORT' : 'PASS_INVENTORY_EXPORT_WITH_EXPLICIT_LIMITS',
    target, target_sha256: original, target_unchanged: digest(target) === original,
    lab_manifest_sha256: digest(manifestPath), started_utc: started, finished_utc: new Date().toISOString(),
    functions: rows, total: rows.length, pseudocode_returned: rows.filter(x => x.pseudocode).length,
    assembly_returned: rows.filter(x => x.assembly).length,
    warning_functions: rows.filter(x => x.warnings.length).length, failure, session_closed: closed.ok,
    hardware_accessed: false, firmware_eligible: false,
    limits: ['Project-local ARC700 REA adaptation; not upstream support.',
      'Derived ET_EXEC external addresses are synthetic, never runtime addresses.',
      'Pseudocode is reconstruction, not original C or global source equivalence.',
      'Provider inventory coverage must be compared against original ELF symbols and body ranges.',
      'Decoder warnings and unresolved calls remain explicit; no hardware or traffic acceptance.'] };
  write('result.json', result);
  console.log(JSON.stringify({ status: result.status, total: result.total, pseudocode_returned: result.pseudocode_returned, warning_functions: result.warning_functions, failure }));
}
if (failure) process.exitCode = 1;
