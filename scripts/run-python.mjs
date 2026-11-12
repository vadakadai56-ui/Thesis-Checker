// Runs Python from the project's virtual environment (.venv) if there is one,
// otherwise the system Python. Usage: node scripts/run-python.mjs <args…>
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const candidates = [
  join(ROOT, '.venv', 'bin', 'python'), // macOS / Linux
  join(ROOT, '.venv', 'Scripts', 'python.exe'), // Windows
];
export const python = candidates.find(existsSync) ?? 'python3';

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const result = spawnSync(python, process.argv.slice(2), { stdio: 'inherit', cwd: ROOT });
  if (result.error) {
    console.error(`Could not run Python (${python}). Create the venv first — see README.`);
    process.exit(1);
  }
  process.exit(result.status ?? 1);
}
