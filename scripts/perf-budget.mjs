// Measures download sizes against the budgets in BUILD_PROMPT §8 and writes
// docs/perf.md. Exits with an error if a budget is exceeded.
//
//   npm run build && npx playwright test   (timings come from the browser tests)
//   npm run perf
//
// "Compressed" = Brotli, which static hosts such as Cloudflare Pages use for text
// files. .wasm compresses well too; .whl and .zip files are already compressed.

import { existsSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { brotliCompressSync, constants, gzipSync } from 'node:zlib';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const DIST = join(ROOT, 'dist');
const RESULTS = join(ROOT, 'tests-e2e', '.results');

const BUDGETS = {
  shellBytes: 250 * 1024, // shell ≤ 250 KB compressed
  engineBytes: 9 * 1024 * 1024, // engine total ≤ 9 MB compressed
  engineReadyFirstMs: 8000,
  engineReadyCachedMs: 3000,
  check100PagesMs: 10_000,
  fix100PagesMs: 20_000,
};
const ENGINE_DIRS = ['pyodide', 'wheels', 'engine', 'profiles'];
// Files the worker never downloads (kept for tooling / documentation only).
const NOT_DOWNLOADED = new Set(['pyodide/thesischeck-files.json', 'profiles/index.json']);

function walk(dir) {
  if (!existsSync(dir)) return [];
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    return entry.isDirectory() ? walk(path) : [path];
  });
}

function measure(path) {
  const data = readFileSync(path);
  const brotli = brotliCompressSync(data, {
    params: { [constants.BROTLI_PARAM_QUALITY]: 9, [constants.BROTLI_PARAM_SIZE_HINT]: data.length },
  }).length;
  const gzip = gzipSync(data, { level: 9 }).length;
  // A host never serves a "compressed" version that is bigger than the file.
  return { raw: data.length, gzip: Math.min(gzip, data.length), brotli: Math.min(brotli, data.length) };
}

const kb = (bytes) => `${(bytes / 1024).toFixed(0)} KB`;
const mb = (bytes) => `${(bytes / 1024 / 1024).toFixed(2)} MB`;
const readJson = (name) =>
  existsSync(join(RESULTS, name)) ? JSON.parse(readFileSync(join(RESULTS, name), 'utf8')) : null;

if (!existsSync(DIST)) {
  console.error('perf-budget: dist/ not found — run `npm run build` first.');
  process.exit(1);
}

const rows = { shell: [], engine: [] };
for (const path of walk(DIST)) {
  const name = relative(DIST, path).split('\\').join('/');
  const top = name.split('/')[0];
  if (ENGINE_DIRS.includes(top)) {
    if (!NOT_DOWNLOADED.has(name) && !(top === 'profiles' && !name.endsWith('.json'))) {
      rows.engine.push({ name, ...measure(path) });
    }
  } else if (!name.startsWith('icons/') || name.endsWith('.svg')) {
    rows.shell.push({ name, ...measure(path) });
  }
}
// One profile is downloaded per check, not all of them: count the largest.
const profiles = rows.engine.filter((r) => r.name.startsWith('profiles/'));
const largestProfile = profiles.sort((a, b) => b.brotli - a.brotli)[0];
rows.engine = rows.engine.filter((r) => !r.name.startsWith('profiles/') || r === largestProfile);

const sum = (list, key) => list.reduce((n, r) => n + r[key], 0);
const shell = sum(rows.shell, 'brotli');
const engine = sum(rows.engine, 'brotli');
const first = readJson('engine-ready.json');
const cached = readJson('engine-ready-cached.json');
const big = readJson('big.json');

const checks = [
  ['Shell (page + scripts), compressed', kb(shell), `≤ ${kb(BUDGETS.shellBytes)}`, shell <= BUDGETS.shellBytes],
  ['Engine total, compressed', mb(engine), `≤ ${mb(BUDGETS.engineBytes)}`, engine <= BUDGETS.engineBytes],
];
if (first) checks.push(['Engine ready, first visit (this computer)', `${(first.readyMs / 1000).toFixed(1)} s`, `≤ ${BUDGETS.engineReadyFirstMs / 1000} s on a mid-range phone`, first.readyMs <= BUDGETS.engineReadyFirstMs]);
if (cached) checks.push(['Engine ready, second visit (this computer)', `${(cached.readyMs / 1000).toFixed(1)} s`, `≤ ${BUDGETS.engineReadyCachedMs / 1000} s cached on a mid-range phone`, null]);
if (big) {
  checks.push([`Check, ${big.stats.pages_estimate} pages / ${big.stats.words} words (this computer)`, `${(big.checkMs / 1000).toFixed(2)} s`, `≤ ${BUDGETS.check100PagesMs / 1000} s for 100 pages`, big.checkMs <= BUDGETS.check100PagesMs]);
  checks.push([`Fix + re-check, same thesis, ${big.findings} findings (this computer)`, `${(big.fixMs / 1000).toFixed(2)} s`, `≤ ${BUDGETS.fix100PagesMs / 1000} s`, big.fixMs <= BUDGETS.fix100PagesMs]);
}

const table = (list) =>
  ['| File | Size | gzip | Brotli |', '|---|---:|---:|---:|']
    .concat(list.sort((a, b) => b.brotli - a.brotli).map((r) => `| \`${r.name}\` | ${kb(r.raw)} | ${kb(r.gzip)} | ${kb(r.brotli)} |`))
    .concat([`| **Total** | **${kb(sum(list, 'raw'))}** | **${kb(sum(list, 'gzip'))}** | **${kb(sum(list, 'brotli'))}** |`])
    .join('\n');
// Time budgets are for a mid-range PHONE, so a pass on this computer is not yet a pass.
const mark = (ok, isTime) =>
  ok === null
    ? 'measured (see note)'
    : !ok
      ? '❌ OVER BUDGET'
      : isTime
        ? '✅ on this computer; phone in stage 7'
        : '✅ within budget';

const pyodide = JSON.parse(readFileSync(join(ROOT, 'node_modules', 'pyodide', 'package.json'), 'utf8')).version;
const md = `# Performance

Written by \`npm run perf\` (scripts/perf-budget.mjs). Do not edit by hand.

Budgets are from BUILD_PROMPT §8. Sizes are exact. **Times were measured in headless
Chromium on the development computer, not on a phone**: phones are slower (often
3–5×). Real phone timings are measured in stage 7 and added here.

## Budgets

| What | Measured | Budget | Result |
|---|---:|---|---|
${checks.map(([what, value, budget, ok]) => `| ${what} | ${value} | ${budget} | ${mark(ok, /\bs\b/.test(value))} |`).join('\n')}

Note: until the service worker arrives (stage 6), a second visit still re-requests
every file from the server, so "second visit" is not yet a true cached start.

## Engine files (downloaded once, then kept for offline use)

Pyodide ${pyodide}. The checker itself (\`engine/thesischeck.zip\`) is tiny; almost
all of the download is the Python runtime.

${table(rows.engine)}

## Shell files (needed to show the page)

${table(rows.shell)}
`;
writeFileSync(join(ROOT, 'docs', 'perf.md'), md);
console.log(md.split('## Engine files')[0]);
const failed = checks.filter(([, , , ok]) => ok === false);
if (failed.length) {
  console.error(`perf-budget: ${failed.length} budget(s) exceeded.`);
  process.exit(1);
}
