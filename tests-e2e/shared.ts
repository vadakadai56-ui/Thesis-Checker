import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
export const ROOT = join(HERE, '..');
export const SAMPLES = join(ROOT, 'engine', 'tests', 'samples');
export const EXPECTED = join(HERE, '.expected'); // written by global-setup.ts
export const RESULTS = join(HERE, '.results'); // measurements for docs/perf.md

// A fixed "now" so reports are identical in Python and in the browser.
export const NOW = '2026-11-10T12:00:00+00:00';

export const CHECK_SAMPLES = ['clean', 'TEXT-01', 'CITE-04', 'STRUCT-01', 'TOC-02', 'FIG-02'];
export const FIX_SAMPLES = ['clean', 'TEXT-01', 'PAGE-01', 'HEAD-02', 'TEXT-08'];
export const ANNOTATE_SAMPLES = ['CITE-04'];
