// Before the browser tests: ask plain Python (the engine tested by pytest) for the
// reports of the test samples. The tests then require the browser to match them.
import { spawnSync } from 'node:child_process';
import { mkdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';

import { python } from '../scripts/run-python.mjs';
import { ANNOTATE_SAMPLES, CHECK_SAMPLES, EXPECTED, FIX_SAMPLES, NOW, RESULTS, ROOT } from './shared';

export default function globalSetup() {
  rmSync(EXPECTED, { recursive: true, force: true });
  mkdirSync(RESULTS, { recursive: true });
  const result = spawnSync(
    python,
    [
      join('engine', 'tools', 'export_reports.py'),
      '--out', EXPECTED,
      '--now', NOW,
      '--check', ...CHECK_SAMPLES,
      '--fix', ...FIX_SAMPLES,
      '--annotate', ...ANNOTATE_SAMPLES,
      '--big',
    ],
    { cwd: ROOT, stdio: 'inherit' },
  );
  if (result.status !== 0) throw new Error('export_reports.py failed (is the Python venv set up?)');
}
