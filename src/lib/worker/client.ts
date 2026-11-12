// The page's side of the engine: the ONLY module that talks to the worker
// (BUILD_PROMPT §7). It turns messages into ordinary async functions:
//
//   const engine = new EngineClient();
//   await engine.init((p) => showProgress(p));
//   const report = await engine.check('demo', file);
//
// Thesis bytes are sent as a structured CLONE (a copy), never transferred, so the
// page keeps the original (§4d).

import { EngineFailure } from '../errors';
import {
  MESSAGE_VERSION,
  responseSchema,
  type EngineResponse,
  type FileResult,
  type Progress,
  type Ready,
  type Report,
} from './messages';

export const MAX_FILE_BYTES = 50 * 1024 * 1024; // input cap (BUILD_PROMPT §8)
const JOB_TIMEOUT_MS = 5 * 60 * 1000;

type ProgressHandler = (progress: Progress) => void;
interface Pending {
  resolve: (response: EngineResponse) => void;
  reject: (error: Error) => void;
  onProgress?: ProgressHandler;
  timer?: ReturnType<typeof setTimeout>;
}
export interface JobOptions {
  fileName?: string;
  now?: string; // fixed date-time for reproducible reports (tests)
  onProgress?: ProgressHandler;
}

const createWorker = () =>
  new Worker(new URL('./engine.worker.ts', import.meta.url), { type: 'module' });

/** Read a File into bytes, refusing files over the size cap BEFORE reading them. */
export async function readFile(file: Blob): Promise<Uint8Array> {
  if (file.size > MAX_FILE_BYTES) throw new EngineFailure('FILE_TOO_LARGE', '');
  return new Uint8Array(await file.arrayBuffer());
}

export class EngineClient {
  private worker: Worker | undefined;
  private pending = new Map<string, Pending>();
  private counter = 0;
  private ready: Promise<Ready> | undefined;

  constructor(private readonly workerFactory: () => Worker = createWorker) {}

  private getWorker(): Worker {
    if (!this.worker) {
      this.worker = this.workerFactory();
      this.worker.onmessage = (event) => this.receive(event.data);
      this.worker.onerror = (event) => {
        this.failAll(new EngineFailure('ENGINE_LOAD_FAILED', '', event.message ?? ''));
        this.reset();
      };
    }
    return this.worker;
  }

  private receive(data: unknown) {
    const parsed = responseSchema.safeParse(data);
    if (!parsed.success) {
      console.error('ThesisCheck: invalid message from the engine', parsed.error);
      return;
    }
    const response = parsed.data;
    const entry = this.pending.get(response.id);
    if (!entry) return;
    if (response.type === 'progress') {
      entry.onProgress?.(response);
      return;
    }
    this.pending.delete(response.id);
    clearTimeout(entry.timer);
    if (response.type === 'error') {
      entry.reject(new EngineFailure(response.code, response.message, response.detail));
    } else {
      entry.resolve(response);
    }
  }

  private request(
    message: Record<string, unknown>,
    onProgress?: ProgressHandler,
    timeoutMs?: number,
  ): { id: string; done: Promise<EngineResponse> } {
    const id = `m${++this.counter}`;
    const done = new Promise<EngineResponse>((resolve, reject) => {
      const entry: Pending = { resolve, reject, onProgress };
      if (timeoutMs) {
        entry.timer = setTimeout(() => {
          this.cancel(id, new EngineFailure('TIMEOUT', ''));
        }, timeoutMs);
      }
      this.pending.set(id, entry);
    });
    // No transfer list: the bytes are copied, the page keeps its own.
    this.getWorker().postMessage({ version: MESSAGE_VERSION, id, ...message });
    return { id, done };
  }

  /** Start the engine (safe to call more than once). */
  init(onProgress?: ProgressHandler): Promise<Ready> {
    this.ready ??= this.request({ type: 'init' }, onProgress).done.then(
      (response) => response as Ready,
      (error) => {
        this.ready = undefined; // let the user retry
        throw error;
      },
    );
    return this.ready;
  }

  private async job(
    type: 'check' | 'fix' | 'annotate',
    profileId: string,
    file: Blob | Uint8Array,
    options: JobOptions = {},
  ): Promise<EngineResponse> {
    const bytes = file instanceof Uint8Array ? file : await readFile(file);
    if (bytes.byteLength > MAX_FILE_BYTES) throw new EngineFailure('FILE_TOO_LARGE', '');
    const fileName = options.fileName ?? (file instanceof File ? file.name : 'document.docx');
    const message = { type, profileId, bytes, fileName, ...(options.now ? { now: options.now } : {}) };
    return this.request(message, options.onProgress, JOB_TIMEOUT_MS).done;
  }

  async check(profileId: string, file: Blob | Uint8Array, options?: JobOptions): Promise<Report> {
    const response = await this.job('check', profileId, file, options);
    return (response as Extract<EngineResponse, { type: 'result' }>).report;
  }

  async fix(profileId: string, file: Blob | Uint8Array, options?: JobOptions): Promise<FileResult> {
    return (await this.job('fix', profileId, file, options)) as FileResult;
  }

  async annotate(
    profileId: string,
    file: Blob | Uint8Array,
    options?: JobOptions,
  ): Promise<FileResult> {
    return (await this.job('annotate', profileId, file, options)) as FileResult;
  }

  /**
   * Stop everything in progress. Python can't be interrupted mid-run, so we end
   * the worker; the next request starts a fresh one.
   */
  cancel(_targetId?: string, reason: Error = new EngineFailure('INTERNAL', 'Cancelled.')) {
    this.failAll(reason);
    this.reset();
  }

  private failAll(error: Error) {
    for (const entry of this.pending.values()) {
      clearTimeout(entry.timer);
      entry.reject(error);
    }
    this.pending.clear();
  }

  private reset() {
    this.worker?.terminate();
    this.worker = undefined;
    this.ready = undefined;
  }
}
