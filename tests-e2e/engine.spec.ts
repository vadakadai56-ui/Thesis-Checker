// Stage 4 test: the engine running in Chromium must give exactly the reports
// that plain Python gives for the same samples (BUILD_PROMPT §17, stage 4).
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { expect, test, type BrowserContext, type Page } from '@playwright/test';

import {
  ANNOTATE_SAMPLES,
  CHECK_SAMPLES,
  EXPECTED,
  FIX_SAMPLES,
  NOW,
  RESULTS,
  SAMPLES,
} from './shared';

const expected = (name: string) => JSON.parse(readFileSync(join(EXPECTED, name), 'utf8'));
const sample = (name: string) => join(SAMPLES, `${name}.docx`);

/** Records problems that must never happen: other-site requests, CSP blocks, JS errors. */
function watch(page: Page) {
  const problems: string[] = [];
  const origin = 'http://localhost:4173';
  page.on('request', (request) => {
    const url = request.url();
    if (!url.startsWith(origin) && !url.startsWith('blob:') && !url.startsWith('data:')) {
      problems.push(`request left the app's origin: ${url}`);
    }
  });
  page.on('response', (response) => {
    if (response.status() >= 400) problems.push(`HTTP ${response.status()} for ${response.url()}`);
  });
  page.on('pageerror', (error) => problems.push(`page error: ${error.message}`));
  page.on('console', (message) => {
    if (message.type() === 'error') problems.push(`console error: ${message.text()}`);
  });
  return problems;
}

async function openApp(page: Page) {
  await page.goto(`/?now=${encodeURIComponent(NOW)}`);
  await expect(page.getByTestId('engine-status')).toContainText('Engine ready', {
    timeout: 90_000,
  });
  await page.getByTestId('profile').selectOption('demo');
}

async function runJob(page: Page, name: string, button: 'check' | 'fix' | 'annotate') {
  await page.getByTestId('file').setInputFiles(sample(name));
  await page.getByTestId(button).click();
  await expect(page.getByTestId('result')).toBeVisible({ timeout: 60_000 });
  return JSON.parse((await page.getByTestId('result-json').textContent()) ?? '');
}

/** A fixed file's hash differs between runs (ZIP timestamps); everything else must match. */
function withoutFileHash(result: any) {
  const copy = structuredClone(result);
  delete copy.byteLength;
  delete copy.bytes;
  delete copy.id;
  delete copy.type;
  delete copy.version;
  copy.report.document_sha256 = '(differs per run)';
  return copy;
}

test.describe.configure({ mode: 'serial' });

let context: BrowserContext;
let page: Page;
let problems: string[];

test.beforeAll(async ({ browser }) => {
  context = await browser.newContext();
  page = await context.newPage();
  problems = watch(page);
});

test.afterAll(async () => {
  await context.close();
});

test('the shell appears before the engine and the engine starts', async () => {
  await page.goto(`/?now=${encodeURIComponent(NOW)}`);
  // The page is usable while the engine is still loading.
  await expect(page.getByRole('heading', { name: /ThesisCheck/ })).toBeVisible();
  await expect(page.getByTestId('file')).toBeEnabled();
  await expect(page.getByTestId('engine-status')).toContainText('Engine ready', {
    timeout: 90_000,
  });
  await expect(page.getByTestId('engine-status')).toContainText('Pyodide 314.0.7');
  await page.getByTestId('profile').selectOption('demo');
  const readyMs = Number(await page.locator('html').getAttribute('data-engine-ready-ms'));
  writeFileSync(join(RESULTS, 'engine-ready.json'), JSON.stringify({ readyMs }));
});

for (const name of CHECK_SAMPLES) {
  test(`check ${name}: browser report equals the Python report`, async () => {
    const result = await runJob(page, name, 'check');
    expect(result).toEqual(expected(`check-${name}.json`));
  });
}

for (const name of FIX_SAMPLES) {
  test(`fix ${name}: browser result equals the Python result`, async () => {
    const result = await runJob(page, name, 'fix');
    expect(withoutFileHash(result)).toEqual(withoutFileHash(expected(`fix-${name}.json`)));
    expect(result.byteLength).toBeGreaterThan(10_000);
    await expect(page.getByTestId('download')).toHaveAttribute('download', `${name}_fixed.docx`);
  });
}

for (const name of ANNOTATE_SAMPLES) {
  test(`annotate ${name}: browser result equals the Python result`, async () => {
    const result = await runJob(page, name, 'annotate');
    expect(withoutFileHash(result)).toEqual(withoutFileHash(expected(`annotate-${name}.json`)));
    expect(result.comments).toBe(1);
  });
}

test('the fixed file downloads, is a .docx, and re-checks clean', async () => {
  await runJob(page, 'TEXT-01', 'fix');
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByTestId('download').click(),
  ]);
  const path = await download.path();
  expect(download.suggestedFilename()).toBe('TEXT-01_fixed.docx');
  expect(readFileSync(path).subarray(0, 4).toString('latin1')).toBe('PK\u0003\u0004');
  await page.getByTestId('file').setInputFiles(path);
  await page.getByTestId('check').click();
  await expect(page.getByTestId('result')).toContainText('Score 100/100');
});

test('a file that is not a .docx gets a friendly message', async () => {
  await page.getByTestId('file').setInputFiles({
    name: 'notes.docx',
    mimeType: 'application/octet-stream',
    buffer: Buffer.from('this is plain text, not a Word file'),
  });
  await page.getByTestId('check').click();
  await expect(page.getByTestId('error')).toContainText("NOT_DOCX: This doesn't look like a Word");
});

test('timing of a check is recorded', async () => {
  const started = Date.now();
  await runJob(page, 'STRUCT-04', 'check'); // the longest sample
  const jobMs = Number(await page.locator('html').getAttribute('data-last-job-ms'));
  writeFileSync(join(RESULTS, 'check.json'), JSON.stringify({ jobMs, wallMs: Date.now() - started }));
  expect(jobMs).toBeLessThan(10_000);
});

test('a 100+ page thesis: check and fix times are recorded', async () => {
  const big = join(EXPECTED, 'big.docx');
  const timed = async (button: 'check' | 'fix') => {
    await page.getByTestId('file').setInputFiles(big);
    await page.getByTestId(button).click();
    await expect(page.getByTestId('result')).toBeVisible({ timeout: 90_000 });
    return Number(await page.locator('html').getAttribute('data-last-job-ms'));
  };
  const checkMs = await timed('check');
  const report = JSON.parse((await page.getByTestId('result-json').textContent()) ?? '');
  const fixMs = await timed('fix');
  await expect(page.getByTestId('result')).toContainText('Score 100/100');
  writeFileSync(
    join(RESULTS, 'big.json'),
    JSON.stringify({ checkMs, fixMs, stats: report.stats, findings: report.findings.length }),
  );
  expect(report.stats.pages_estimate).toBeGreaterThanOrEqual(100);
  expect(checkMs).toBeLessThan(10_000); // budget: 100-page check ≤ 10 s
  expect(fixMs).toBeLessThan(20_000); // budget: fix + re-check ≤ 20 s
});

test('nothing left the origin, no CSP violations, no errors', async () => {
  // The bad-file test logs nothing to the console; any entry here is a real problem.
  expect(problems).toEqual([]);
});

test('second visit (same browser profile) still works', async () => {
  const second = await context.newPage();
  const more = watch(second);
  await openApp(second);
  const readyMs = Number(await second.locator('html').getAttribute('data-engine-ready-ms'));
  writeFileSync(join(RESULTS, 'engine-ready-cached.json'), JSON.stringify({ readyMs }));
  const result = await runJob(second, 'clean', 'check');
  expect(result.findings).toEqual([]);
  expect(more).toEqual([]);
  await second.close();
});
