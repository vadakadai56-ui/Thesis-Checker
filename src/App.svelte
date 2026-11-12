<script lang="ts">
  // Stage 4: a BARE test page — just enough to run the engine in the browser.
  // The real, responsive interface arrives in stage 5.
  import { onMount } from 'svelte';

  import { EngineFailure } from './lib/errors';
  import { EngineClient } from './lib/worker/client';
  import type { FileResult, Report } from './lib/worker/messages';

  interface ProfileEntry {
    id: string;
    name: string;
    status: string;
    demo: boolean;
  }

  const engine = new EngineClient();
  // Test hook: ?now=2026-11-10T12:00:00+00:00 makes reports reproducible.
  const now = new URLSearchParams(location.search).get('now') ?? undefined;

  let status = $state('Starting…');
  let engineInfo = $state('');
  let profiles = $state<ProfileEntry[]>([]);
  let profileId = $state('');
  let file = $state<File | undefined>();
  let busy = $state(false);
  let error = $state('');
  let report = $state<Report | undefined>();
  let fileResult = $state<FileResult | undefined>();
  let downloadUrl = $state('');

  onMount(() => {
    void loadProfiles();
    // Start the engine only after the page has painted, so the shell shows first.
    requestAnimationFrame(() => setTimeout(startEngine, 0));
  });

  async function loadProfiles() {
    const response = await fetch(`${import.meta.env.BASE_URL}profiles/index.json`);
    profiles = (await response.json()).profiles;
    profileId = profiles[0]?.id ?? '';
  }

  async function startEngine() {
    const started = performance.now();
    try {
      const ready = await engine.init((p) => (status = `${p.detail} — ${p.pct}%`));
      const seconds = ((performance.now() - started) / 1000).toFixed(1);
      status = 'Engine ready';
      engineInfo = `engine ${ready.engineVersion}, Pyodide ${ready.pyodideVersion}, ${seconds} s`;
      document.documentElement.dataset.engineReadyMs = String(Math.round(performance.now() - started));
    } catch (e) {
      status = 'Engine failed';
      error = e instanceof Error ? e.message : String(e);
    }
  }

  function clearResults() {
    error = '';
    report = undefined;
    fileResult = undefined;
    if (downloadUrl) URL.revokeObjectURL(downloadUrl);
    downloadUrl = '';
  }

  async function run(kind: 'check' | 'fix' | 'annotate') {
    if (!file || !profileId) return;
    clearResults();
    busy = true;
    const started = performance.now();
    try {
      if (kind === 'check') {
        report = await engine.check(profileId, file, { now });
      } else {
        fileResult = await engine[kind](profileId, file, { now });
        report = fileResult.report;
        const blob = new Blob([fileResult.bytes as BlobPart], {
          type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        });
        downloadUrl = URL.createObjectURL(blob);
      }
      document.documentElement.dataset.lastJobMs = String(Math.round(performance.now() - started));
    } catch (e) {
      error =
        e instanceof EngineFailure ? `${e.code}: ${e.message}` : e instanceof Error ? e.message : String(e);
    } finally {
      busy = false;
    }
  }

  const resultJson = $derived(
    fileResult
      ? JSON.stringify({ ...fileResult, bytes: undefined, byteLength: fileResult.bytes.byteLength })
      : report
        ? JSON.stringify(report)
        : '',
  );
</script>

<main>
  <h1>ThesisCheck <small>(stage 4 test page)</small></h1>
  <p>
    ThesisCheck checks formatting and referencing. It is not a plagiarism or AI-text detector and
    does not judge academic integrity — at RTU, people make those decisions.
  </p>

  <p data-testid="engine-status" aria-live="polite"><strong>{status}</strong> {engineInfo}</p>

  <label>
    Profile
    <select bind:value={profileId} data-testid="profile">
      {#each profiles as p (p.id)}
        <option value={p.id}>{p.name}</option>
      {/each}
    </select>
  </label>

  <label>
    Thesis (.docx)
    <input
      type="file"
      data-testid="file"
      accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
      onchange={(e) => {
        file = e.currentTarget.files?.[0];
        clearResults();
      }}
    />
  </label>

  <p>
    <button data-testid="check" disabled={!file || busy} onclick={() => run('check')}>Check</button>
    <button data-testid="fix" disabled={!file || busy} onclick={() => run('fix')}>Fix</button>
    <button data-testid="annotate" disabled={!file || busy} onclick={() => run('annotate')}>
      Annotate
    </button>
    {#if busy}<span data-testid="busy">Working…</span>{/if}
  </p>

  {#if error}
    <p role="alert" data-testid="error">{error}</p>
  {/if}

  {#if report}
    <section data-testid="result">
      <h2>
        Score {report.score.value}/100 — {report.score.band}
        ({report.findings.length} finding{report.findings.length === 1 ? '' : 's'})
      </h2>
      {#if fileResult}
        <p>
          Before: {fileResult.before.score.value}/100.
          <a href={downloadUrl} download={fileResult.fileName} data-testid="download">
            Download {fileResult.fileName}
          </a>
        </p>
      {/if}
      <ul>
        {#each report.findings as f (f.id)}
          <li><strong>[{f.rule_id}]</strong> {f.severity}: {f.message}</li>
        {/each}
      </ul>
      <details>
        <summary>Raw result (JSON)</summary>
        <pre data-testid="result-json">{resultJson}</pre>
      </details>
    </section>
  {/if}
</main>

<style>
  main {
    max-width: 48rem;
    margin: 0 auto;
    padding: 1rem;
    font: 16px/1.5 system-ui, sans-serif;
  }
  label {
    display: block;
    margin: 0.75rem 0;
  }
  button {
    min-height: 44px;
    min-width: 6rem;
    font-size: 1rem;
  }
  pre {
    overflow-x: auto;
    white-space: pre-wrap;
    word-break: break-all;
  }
  [role='alert'] {
    color: #b00020;
  }
</style>
