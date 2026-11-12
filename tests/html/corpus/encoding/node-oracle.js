// Supplemental oracle. Primary expectations arrive unchanged from pinned fixtures.
const fs = require('fs');
const assert = require('assert');
const controls = [
  ['utf-8', [240,144,128,128], [65536], false, -1],
  ['utf-16le', [0,216,0,220], [65536], false, -1],
  ['utf-8', [65,255], [65], true, -2],
];
for (const [encoding, bytes, points, fatal, terminal] of controls) {
  const decoder = new TextDecoder(encoding, {fatal});
  let text = '', outcome = -1;
  try { for (const byte of bytes) text += decoder.decode(Uint8Array.of(byte), {stream:true}); text += decoder.decode(); }
  catch (problem) { outcome = -2; }
  assert.deepStrictEqual(Array.from(text, c => c.codePointAt(0)), points);
  assert.strictEqual(outcome, terminal);
}
for (const points of [[202,772], [202,780], [234,772], [234,780]]) {
  assert.deepStrictEqual(Array.from(String.fromCodePoint(...points), c => c.codePointAt(0)), points);
}
const rows = JSON.parse(fs.readFileSync(0, 'utf8'));
const differences = [], skipped = [];
let checked = 0;
for (let index = 0; index < rows.length; index++) {
  const row = rows[index];
  let decoder;
  try { decoder = new TextDecoder(row.encoding, {fatal: row.fatal, ignoreBOM: row.bom}); }
  catch (problem) { skipped.push({case: row.case, encoding: row.encoding, reason: problem.name}); continue; }
  let text = '', actual;
  try {
    // Byte streaming retains scalar output preceding a fatal error.
    for (const byte of row.data) text += decoder.decode(Uint8Array.of(byte), {stream: true});
    text += decoder.decode();
    actual = {terminal: -1, points: Array.from(text, c => c.codePointAt(0))};
  } catch (problem) { actual = {terminal: -2, points: Array.from(text, c => c.codePointAt(0))}; }
  checked++;
  if (actual.terminal !== row.terminal || JSON.stringify(actual.points) !== JSON.stringify(row.points)) {
    differences.push({case: row.case, encoding: row.encoding, data: row.data, fatal: row.fatal, bom: row.bom,
                      expected: {terminal: row.terminal, points: row.points}, actual});
  }
}
process.stdout.write(JSON.stringify({versions: process.versions, protocol_controls_passed: controls.length + 4, checked, skipped, differences}) + '\n');
