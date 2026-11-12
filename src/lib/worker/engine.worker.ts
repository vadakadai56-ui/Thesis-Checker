/// <reference lib="webworker" />
// The Web Worker that runs the Python engine with Pyodide (Python compiled to
// WebAssembly). It never touches the page: it only receives and posts messages
// (see messages.ts).
//
// Start-up, each step reported as a `progress` message:
//   1. load Pyodide from OUR origin (/pyodide/) — never from a CDN,
//   2. load lxml + typing-extensions + micropip from /pyodide/,
//   3. install python-docx from /wheels/ with micropip,
//   4. unpack our engine (/engine/thesischeck.zip) and import it.

import type { PyodideInterface } from 'pyodide';

import { ERROR_MESSAGES } from '../errors';
import bridgeSource from './bridge.py?raw';
import {
  MESSAGE_VERSION,
  requestSchema,
  type EngineRequest,
  type EngineResponse,
  type ErrorCode,
} from './messages';

declare const self: DedicatedWorkerGlobalScope;

// Absolute URL of the app's root, e.g. "https://example.org/".
const ROOT = new URL(import.meta.env.BASE_URL, self.location.origin).href;
const PYODIDE_URL = `${ROOT}pyodide/`;
const DOCX_WHEEL = `${ROOT}wheels/python_docx-1.2.0-py3-none-any.whl`;
const ENGINE_DIR = '/engine';

interface Bridge {
  engine_version(): string;
  check: BridgeFn;
  fix: BridgeFn;
  annotate: BridgeFn;
}
type BridgeFn = (
  data: Uint8Array,
  profileJson: string,
  fileName: string,
  now?: string,
) => { toJs(): [string, Uint8Array | undefined]; destroy(): void };

let pyodide: PyodideInterface | undefined;
let bridge: Bridge | undefined;
let starting: Promise<{ engineVersion: string; pyodideVersion: string }> | undefined;
const profiles = new Map<string, string>();

function post(message: Record<string, unknown> & { id: string; type: EngineResponse['type'] }) {
  self.postMessage({ version: MESSAGE_VERSION, ...message });
}

function postError(id: string, code: ErrorCode, message = '', detail = '') {
  post({ id, type: 'error', code, message: message || ERROR_MESSAGES[code] || '', detail });
}

const megabytes = (bytes: number) => `${(bytes / 1e6).toFixed(1)} MB`;

async function fetchOk(url: string): Promise<Response> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} for ${url}`);
  return response;
}

async function start(id: string) {
  const progress = (stage: string, pct: number, detail: string) =>
    post({ id, type: 'progress', stage, pct, detail });

  // File sizes, written at setup time, so the progress text can show megabytes.
  const sizes: Record<string, number> = await (
    await fetchOk(`${PYODIDE_URL}thesischeck-files.json`)
  ).json();
  const size = (prefix: string) =>
    Object.entries(sizes)
      .filter(([name]) => name.startsWith(prefix))
      .reduce((sum, [, bytes]) => sum + bytes, 0);
  const runtime = size('pyodide/pyodide.') + size('pyodide/python_stdlib');

  progress('runtime', 5, `Loading Python (${megabytes(runtime)})`);
  // Imported at run time from our own /pyodide/ folder, so Pyodide's files are
  // served exactly as published (not bundled or modified).
  const { loadPyodide } = (await import(/* @vite-ignore */ `${PYODIDE_URL}pyodide.mjs`)) as {
    loadPyodide: (options: Record<string, unknown>) => Promise<PyodideInterface>;
  };
  pyodide = await loadPyodide({ indexURL: PYODIDE_URL, packageBaseUrl: PYODIDE_URL });

  const wheels = size('pyodide/lxml') + size('pyodide/typing') + size('pyodide/micropip');
  progress('packages', 50, `Loading document tools (${megabytes(wheels + size('wheels/'))})`);
  await pyodide.loadPackage(['lxml', 'typing-extensions', 'micropip'], {
    messageCallback: () => {},
  });
  const micropip = pyodide.pyimport('micropip');
  await micropip.install(DOCX_WHEEL, { deps: false });
  micropip.destroy();

  progress('engine', 85, 'Starting the checker');
  const archive = await (await fetchOk(`${ROOT}engine/thesischeck.zip`)).arrayBuffer();
  pyodide.FS.mkdirTree(ENGINE_DIR);
  pyodide.unpackArchive(archive, 'zip', { extractDir: ENGINE_DIR });
  pyodide.FS.writeFile(`${ENGINE_DIR}/tc_bridge.py`, bridgeSource);
  pyodide.runPython(`import sys; sys.path.insert(0, "${ENGINE_DIR}")`);
  bridge = pyodide.pyimport('tc_bridge') as unknown as Bridge;

  progress('ready', 100, 'Ready');
  return { engineVersion: bridge.engine_version(), pyodideVersion: pyodide.version };
}

/** Start the engine once; later calls wait for (or reuse) the same start. */
function ensureStarted(id: string) {
  starting ??= start(id);
  return starting;
}

async function loadProfile(profileId: string): Promise<string> {
  if (!/^[a-z0-9][a-z0-9-]*$/.test(profileId)) throw new Error(`bad profile id: ${profileId}`);
  let json = profiles.get(profileId);
  if (json === undefined) {
    json = await (await fetchOk(`${ROOT}profiles/${profileId}.json`)).text();
    profiles.set(profileId, json);
  }
  return json;
}

async function runJob(request: Extract<EngineRequest, { type: 'check' | 'fix' | 'annotate' }>) {
  await ensureStarted(request.id);
  const profileJson = await loadProfile(request.profileId);
  post({ id: request.id, type: 'progress', stage: request.type, pct: 0, detail: 'Working…' });

  const proxy = bridge![request.type](
    request.bytes,
    profileJson,
    request.fileName ?? 'document.docx',
    request.now,
  );
  const [json, bytes] = proxy.toJs();
  proxy.destroy();
  const outcome = JSON.parse(json);
  if (!outcome.ok) {
    postError(request.id, outcome.error.code, outcome.error.message, outcome.error.detail);
    return;
  }
  if (request.type === 'check') {
    post({ id: request.id, type: 'result', report: outcome.report });
    return;
  }
  const result = outcome.result;
  post({
    id: request.id,
    type: 'fileResult',
    kind: result.kind,
    fileName: result.file_name,
    bytes,
    report: result.report,
    before: result.before,
    fixedFindings: result.fixed_findings,
    fixes: result.fixes,
    ...(result.comments === undefined ? {} : { comments: result.comments }),
  });
}

self.onmessage = async (event: MessageEvent) => {
  const parsed = requestSchema.safeParse(event.data);
  if (!parsed.success) {
    const id = typeof event.data?.id === 'string' ? event.data.id : 'unknown';
    postError(id, 'INTERNAL', '', `invalid message: ${parsed.error.message}`);
    return;
  }
  const request = parsed.data;
  try {
    if (request.type === 'init') {
      try {
        post({ id: request.id, type: 'ready', ...(await ensureStarted(request.id)) });
      } catch (error) {
        starting = undefined; // allow "Retry"
        postError(request.id, 'ENGINE_LOAD_FAILED', '', String(error));
      }
    } else if (request.type === 'cancel') {
      // Python runs to completion once started; the page cancels by ending this
      // worker (client.ts). Nothing to do here.
    } else {
      await runJob(request);
    }
  } catch (error) {
    const text = String(error);
    const code: ErrorCode = /out of memory|MemoryError|allocation/i.test(text)
      ? 'OUT_OF_MEMORY'
      : bridge
        ? 'INTERNAL'
        : 'ENGINE_LOAD_FAILED';
    postError(request.id, code, '', text);
  }
};
