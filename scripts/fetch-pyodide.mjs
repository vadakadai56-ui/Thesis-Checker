// Copies everything the Python engine needs to run in the browser into public/:
//
//   public/pyodide/   Pyodide itself (Python compiled to WebAssembly) + the lxml,
//                     typing-extensions and micropip packages
//   public/wheels/    the python-docx package (a "wheel" file from PyPI)
//
// The app must never download code from another site at RUNTIME ("no CDN"), so we
// fetch these once at SETUP time and serve them from our own origin.
//
// Every file's SHA-256 is checked against scripts/pyodide-files.lock.json, so a
// corrupted or tampered download is refused. Run with --update-lock only when
// deliberately changing versions; it rewrites the lock file from what was fetched.
//
// Pyodide's files are copied byte-for-byte and never modified (MPL-2.0).

import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { copyFileSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const NPM_PYODIDE = join(ROOT, 'node_modules', 'pyodide');
const OUT_PYODIDE = join(ROOT, 'public', 'pyodide');
const OUT_WHEELS = join(ROOT, 'public', 'wheels');
const CACHE = join(ROOT, 'node_modules', '.cache', 'thesischeck');
const LOCK_PATH = join(ROOT, 'scripts', 'pyodide-files.lock.json');
const UPDATE_LOCK = process.argv.includes('--update-lock');

// Files that come with the `pyodide` npm package.
const RUNTIME_FILES = [
  'pyodide.mjs',
  'pyodide.asm.mjs',
  'pyodide.asm.wasm',
  'python_stdlib.zip',
  'pyodide-lock.json',
];
// Python packages from Pyodide's own package set (exact versions are in pyodide-lock.json).
const PYODIDE_PACKAGES = ['lxml', 'typing-extensions', 'micropip'];
// Pure-Python package from PyPI.
const PYPI = { name: 'python-docx', version: '1.2.0', file: 'python_docx-1.2.0-py3-none-any.whl' };

const sha256 = (path) => createHash('sha256').update(readFileSync(path)).digest('hex');
const pyodideVersion = JSON.parse(readFileSync(join(NPM_PYODIDE, 'package.json'), 'utf8')).version;
const pyodideLock = JSON.parse(readFileSync(join(NPM_PYODIDE, 'pyodide-lock.json'), 'utf8'));

function fail(message) {
  console.error(`\nfetch-pyodide: ${message}`);
  process.exit(1);
}

/** Download a URL to a file. Uses curl when available (it honours proxy settings). */
async function download(url, dest) {
  mkdirSync(dirname(dest), { recursive: true });
  const curl = spawnSync('curl', ['-fsSL', '--retry', '3', '-o', dest, url], { stdio: 'pipe' });
  if (curl.status === 0) return true;
  if (curl.error?.code !== 'ENOENT') return false; // curl exists but the download failed
  try {
    const response = await fetch(url);
    if (!response.ok) return false;
    writeFileSync(dest, Buffer.from(await response.arrayBuffer()));
    return true;
  } catch {
    return false;
  }
}

/**
 * Fallback when the jsDelivr CDN is unreachable: stream Pyodide's official GitHub
 * release archive (~340 MB) through tar and keep only the few wheels we need.
 */
function fetchWheelsFromGithub(fileNames) {
  const url = `https://github.com/pyodide/pyodide/releases/download/${pyodideVersion}/pyodide-${pyodideVersion}.tar.bz2`;
  console.log(`  CDN unreachable; extracting from ${url} (large download, please wait)…`);
  mkdirSync(CACHE, { recursive: true });
  const members = fileNames.map((f) => `pyodide/${f}`).join(' ');
  const cmd = `curl -fsSL --retry 3 "${url}" | tar -xj -C "${CACHE}" --strip-components=1 ${members}`;
  const result = spawnSync('sh', ['-c', cmd], { stdio: 'inherit' });
  // tar may exit non-zero when curl is cut off after the last file; the hashes decide.
  return result.status === 0 || fileNames.every((f) => existsSync(join(CACHE, f)));
}

async function main() {
  if (!existsSync(NPM_PYODIDE)) fail('node_modules/pyodide is missing — run `npm ci` first.');
  const lock = existsSync(LOCK_PATH) ? JSON.parse(readFileSync(LOCK_PATH, 'utf8')) : { files: {} };
  if (!UPDATE_LOCK && lock.pyodide !== pyodideVersion) {
    fail(`lock file is for Pyodide ${lock.pyodide}, but ${pyodideVersion} is installed.`);
  }
  const fetched = {}; // public-relative path -> absolute source path

  // 1. Runtime files: straight from node_modules.
  for (const file of RUNTIME_FILES) fetched[`pyodide/${file}`] = join(NPM_PYODIDE, file);

  // 2. Pyodide packages: cache -> jsDelivr -> GitHub release.
  const wheels = PYODIDE_PACKAGES.map((name) => {
    const entry = pyodideLock.packages[name];
    if (!entry) fail(`package ${name} is not in pyodide-lock.json`);
    return { name, file: entry.file_name, sha256: entry.sha256 };
  });
  const isGood = (w) => existsSync(join(CACHE, w.file)) && sha256(join(CACHE, w.file)) === w.sha256;
  for (const wheel of wheels.filter((w) => !isGood(w))) {
    const url = `https://cdn.jsdelivr.net/pyodide/v${pyodideVersion}/full/${wheel.file}`;
    console.log(`  downloading ${wheel.file}`);
    await download(url, join(CACHE, wheel.file));
  }
  const missing = wheels.filter((w) => !isGood(w));
  if (missing.length) fetchWheelsFromGithub(missing.map((w) => w.file));
  for (const wheel of wheels) {
    // Pyodide publishes each wheel's hash in pyodide-lock.json; check against it too.
    if (!isGood(wheel)) fail(`could not get a valid copy of ${wheel.file}`);
    fetched[`pyodide/${wheel.file}`] = join(CACHE, wheel.file);
  }

  // 3. python-docx from PyPI (the download URL comes from PyPI's JSON API).
  const pypiDest = join(CACHE, PYPI.file);
  if (!existsSync(pypiDest)) {
    const metaPath = join(CACHE, 'pypi.json');
    const ok = await download(`https://pypi.org/pypi/${PYPI.name}/${PYPI.version}/json`, metaPath);
    if (!ok) fail('could not reach pypi.org');
    const meta = JSON.parse(readFileSync(metaPath, 'utf8'));
    const release = meta.urls.find((u) => u.filename === PYPI.file);
    if (!release) fail(`${PYPI.file} not found on PyPI`);
    console.log(`  downloading ${PYPI.file}`);
    if (!(await download(release.url, pypiDest))) fail(`could not download ${PYPI.file}`);
  }
  fetched[`wheels/${PYPI.file}`] = pypiDest;

  // 4. Verify against the lock file (or rewrite it), then copy into public/.
  const files = {};
  for (const [relative, source] of Object.entries(fetched)) {
    const entry = { sha256: sha256(source), bytes: readFileSync(source).length };
    files[relative] = entry;
    if (!UPDATE_LOCK) {
      const expected = lock.files[relative];
      if (!expected) fail(`${relative} is not in the lock file (run with --update-lock?)`);
      if (expected.sha256 !== entry.sha256) {
        rmSync(source, { force: true });
        fail(`SHA-256 mismatch for ${relative}\n  expected ${expected.sha256}\n  got      ${entry.sha256}`);
      }
    }
  }
  if (UPDATE_LOCK) {
    writeFileSync(LOCK_PATH, JSON.stringify({ pyodide: pyodideVersion, files }, null, 2) + '\n');
    console.log(`  wrote ${LOCK_PATH}`);
  }
  for (const dir of [OUT_PYODIDE, OUT_WHEELS]) {
    rmSync(dir, { recursive: true, force: true });
    mkdirSync(dir, { recursive: true });
  }
  for (const [relative, source] of Object.entries(fetched)) {
    copyFileSync(source, join(ROOT, 'public', relative));
  }
  // Sizes for the loading screen ("Python runtime, 9.6 MB"). Our own file, not Pyodide's.
  const sizes = Object.fromEntries(
    Object.entries(files).map(([relative, f]) => [relative, f.bytes]),
  );
  writeFileSync(join(OUT_PYODIDE, 'thesischeck-files.json'), JSON.stringify(sizes, null, 2) + '\n');
  const total = Object.values(files).reduce((sum, f) => sum + f.bytes, 0);
  console.log(
    `fetch-pyodide: ${Object.keys(files).length} files verified (${(total / 1e6).toFixed(1)} MB) -> public/pyodide, public/wheels`,
  );
}

await main();
