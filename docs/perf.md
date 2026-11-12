# Performance

Written by `npm run perf` (scripts/perf-budget.mjs). Do not edit by hand.

Budgets are from BUILD_PROMPT §8. Sizes are exact. **Times were measured in headless
Chromium on the development computer, not on a phone**: phones are slower (often
3–5×). Real phone timings are measured in stage 7 and added here.

## Budgets

| What | Measured | Budget | Result |
|---|---:|---|---|
| Shell (page + scripts), compressed | 66 KB | ≤ 250 KB | ✅ within budget |
| Engine total, compressed | 8.09 MB | ≤ 9.00 MB | ✅ within budget |
| Engine ready, first visit (this computer) | 3.3 s | ≤ 8 s on a mid-range phone | ✅ on this computer; phone in stage 7 |
| Engine ready, second visit (this computer) | 3.1 s | ≤ 3 s cached on a mid-range phone | measured (see note) |
| Check, 125 pages / 38533 words (this computer) | 0.56 s | ≤ 10 s for 100 pages | ✅ on this computer; phone in stage 7 |
| Fix + re-check, same thesis, 729 findings (this computer) | 1.70 s | ≤ 20 s | ✅ on this computer; phone in stage 7 |

Note: until the service worker arrives (stage 6), a second visit still re-requests
every file from the server, so "second visit" is not yet a true cached start.

## Engine files (downloaded once, then kept for offline use)

Pyodide 314.0.7. The checker itself (`engine/thesischeck.zip`) is tiny; almost
all of the download is the Python runtime.

| File | Size | gzip | Brotli |
|---|---:|---:|---:|
| `pyodide/pyodide.asm.wasm` | 9373 KB | 3509 KB | 3030 KB |
| `pyodide/python_stdlib.zip` | 2486 KB | 2445 KB | 2436 KB |
| `pyodide/lxml-6.1.3-cp314-cp314-pyemscripten_2026_0_wasm32.whl` | 2096 KB | 2087 KB | 2084 KB |
| `wheels/python_docx-1.2.0-py3-none-any.whl` | 247 KB | 236 KB | 234 KB |
| `pyodide/pyodide.asm.mjs` | 1221 KB | 255 KB | 226 KB |
| `pyodide/micropip-0.11.1-py3-none-any.whl` | 113 KB | 109 KB | 108 KB |
| `engine/thesischeck.zip` | 86 KB | 83 KB | 82 KB |
| `pyodide/typing_extensions-4.15.0-py3-none-any.whl` | 44 KB | 43 KB | 43 KB |
| `pyodide/pyodide-lock.json` | 116 KB | 25 KB | 24 KB |
| `pyodide/pyodide.mjs` | 18 KB | 7 KB | 7 KB |
| `profiles/rtu-fcsite-bachelor.json` | 23 KB | 5 KB | 4 KB |
| `engine/manifest.json` | 0 KB | 0 KB | 0 KB |
| **Total** | **15822 KB** | **8804 KB** | **8279 KB** |

## Shell files (needed to show the page)

| File | Size | gzip | Brotli |
|---|---:|---:|---:|
| `assets/index-DH9wmMIc.js` | 131 KB | 41 KB | 39 KB |
| `assets/engine.worker-CAJAOBqe.js` | 98 KB | 28 KB | 26 KB |
| `index.html` | 0 KB | 0 KB | 0 KB |
| `icons/icon.svg` | 0 KB | 0 KB | 0 KB |
| `assets/index-e_omRaX_.css` | 0 KB | 0 KB | 0 KB |
| **Total** | **231 KB** | **70 KB** | **66 KB** |
