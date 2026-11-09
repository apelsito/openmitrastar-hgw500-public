/** Preserve REA returned observations as authenticated portable Evidence.
 * This serializes retained local results; it does not rerun the provider.
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
const [runtime, source, output] = process.argv.slice(2);
if (![runtime, source, output].every(x => x && path.isAbsolute(x))) throw new Error('RUNTIME EXPORT NEW_OUTPUT absolute paths required');
fs.mkdirSync(output, { recursive: false });
const { createEvidence, parseEvidence } = await import(pathToFileURL(path.join(runtime, 'dist/domain/evidence.js')).href);
const result = JSON.parse(fs.readFileSync(path.join(source, 'result.json')));
const target = JSON.parse(fs.readFileSync(path.join(source, 'open.json'))).value;
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const records = [], index = [], pins = {};
function add(operation, parameters, observation, filename) {
  if (!observation?.ok) return;
  const v = observation.value;
  const ev = createEvidence(target, v.provider, { operation, parameters, result: v.result,
    rawResult: v.rawResult, analysisProfile: v.analysisProfile,
    authority: 'analyst-inference', confidence: 'observed',
    limitations: [...(v.limitations || []),
      'Observation comes from an analysis-only linked ELF derived from a separately pinned original module.',
      'Synthetic external addresses are not runtime addresses; no hardware executed.'],
    ...(v.relationshipCoverage ? { relationshipCoverage: v.relationshipCoverage } : {}), locations: v.locations || [] });
  const verified = parseEvidence(JSON.parse(JSON.stringify(ev)));
  const evidence_id = verified.evidence_id;
  records.push(ev); index.push({ evidence_id, operation, parameters, source: filename });
}
const inventoryFile = path.join(source, 'procedures.json');
pins['procedures.json'] = sha(fs.readFileSync(inventoryFile));
add('list_procedures', {}, JSON.parse(fs.readFileSync(inventoryFile)), 'procedures.json');
for (const fn of result.functions) {
  const filename = `function-${String(fn.index).padStart(4, '0')}.json`;
  const bytes = fs.readFileSync(path.join(source, filename)); pins[filename] = sha(bytes);
  const row = JSON.parse(bytes); const params = { procedure: fn.address };
  for (const [operation, field] of [['procedure_info','info'],['procedure_pseudo_code','pseudocode'],['procedure_assembly','assembly'],['procedure_references','references']])
    add(operation, params, row[field], filename);
}
const serialize = (name, value) => fs.writeFileSync(path.join(output, name), JSON.stringify(value, null, 2) + '\n', { flag: 'wx' });
serialize('records.json', { records }); serialize('index.json', index); serialize('input-pins.json', pins);
for (const [name,h] of Object.entries(pins)) if (sha(fs.readFileSync(path.join(source,name))) !== h) throw new Error('Input drift');
serialize('manifest.json', { schema: 'openmitrastar.retained-rea-evidence-seal/v1',
  classification: 'PORTABLE_AUTHENTICATED_RECORDS_FROM_RETAINED_REA_RESULTS', source,
  target_sha256: result.target_sha256, records: records.length,
  record_identifiers_verified: true, inputs_unchanged: true,
  records_sha256: sha(fs.readFileSync(path.join(output,'records.json'))),
  hardware_accessed: false, reran_analysis: false,
  limits: ['Serialized through REA createEvidence with canonical identifiers.',
    'This is a new portable seal of returned observations, not the earlier empty session-record ledger.',
    'Linked ELF observations retain analyst-inference authority and synthetic-address limitations.'] });
console.log(JSON.stringify({ output, records: records.length, target_sha256: result.target_sha256 }));
