// The message schemas accept what the engine really sends and reject broken data.
import { describe, expect, it } from 'vitest';

import { requestSchema, responseSchema } from './messages';

const bytes = new Uint8Array([80, 75, 3, 4]);
const score = { version: 1, value: 97, band: 'Ready', penalty: 2, capped: false };
const finding = {
  version: 1,
  id: 'TEXT-01#1',
  rule_id: 'TEXT-01',
  category: 'text',
  severity: 'error',
  message: 'Body text uses Arial.',
  rule_text: 'Use Times New Roman.',
  guideline_ref: 'DEMO',
  location: {
    part: 'body',
    paragraph_index: 3,
    section_index: 1,
    page_estimate: 2,
    heading_path: ['Introduction'],
    snippet: 'The aim…',
  },
  expected: 'Times New Roman',
  found: 'Arial',
  fixable: true,
  fixed: false,
  how_to_fix: 'Change the style.',
};
const report = {
  version: 1,
  engine_version: '0.1.0',
  document_sha256: 'a'.repeat(64),
  file_name: 't.docx',
  profile: { id: 'demo', version: 1, status: 'draft' },
  created_at: '2026-11-10T12:00:00+00:00',
  stats: { paragraphs: 10, pages_estimate: 2, words: 300 },
  findings: [finding],
  score,
  skipped_rules: [{ rule_id: 'PAGE-03', reason: 'Not checked yet.' }],
};

describe('requests (page → worker)', () => {
  it('accepts every request type', () => {
    const base = { version: 1, id: 'm1' };
    const job = { ...base, profileId: 'demo', bytes };
    for (const message of [
      { ...base, type: 'init' },
      { ...job, type: 'check', fileName: 't.docx' },
      { ...job, type: 'fix' },
      { ...job, type: 'annotate', now: '2026-11-10T12:00:00+00:00' },
      { ...base, type: 'cancel', targetId: 'm0' },
    ]) {
      expect(requestSchema.safeParse(message).success, message.type).toBe(true);
    }
  });

  it('rejects wrong versions, unknown types and missing bytes', () => {
    const bad = [
      { version: 2, id: 'm1', type: 'init' },
      { version: 1, id: 'm1', type: 'explode' },
      { version: 1, id: '', type: 'init' },
      { version: 1, id: 'm1', type: 'check', profileId: 'demo', fileName: 't.docx' },
      { version: 1, id: 'm1', type: 'check', profileId: 'demo', fileName: 't.docx', bytes: [1, 2] },
    ];
    for (const message of bad) expect(requestSchema.safeParse(message).success).toBe(false);
  });
});

describe('responses (worker → page)', () => {
  const base = { version: 1, id: 'm1' };

  it('accepts progress, ready, result, fileResult and error', () => {
    const messages = [
      { ...base, type: 'progress', stage: 'runtime', pct: 5, detail: 'Loading Python (13.4 MB)' },
      { ...base, type: 'ready', engineVersion: '0.1.0', pyodideVersion: '314.0.7' },
      { ...base, type: 'result', report },
      {
        ...base,
        type: 'fileResult',
        kind: 'fixed',
        fileName: 't_fixed.docx',
        bytes,
        report,
        before: { score, findings: 2 },
        fixedFindings: [{ ...finding, fixed: true }],
        fixes: [{ rule_id: 'TEXT-01', title: 'Body font', findings: 1, changes: 2 }],
      },
      { ...base, type: 'error', code: 'NOT_DOCX', message: 'Not a Word file.', detail: '' },
    ];
    for (const message of messages) {
      const parsed = responseSchema.safeParse(message);
      expect(parsed.success, `${message.type}: ${parsed.error?.message}`).toBe(true);
    }
  });

  it('rejects unknown error codes and impossible scores', () => {
    const unknownCode = { ...base, type: 'error', code: 'EXPLODED', message: '', detail: '' };
    expect(responseSchema.safeParse(unknownCode).success).toBe(false);
    const badScore = { ...report, score: { ...score, value: 140 } };
    expect(responseSchema.safeParse({ ...base, type: 'result', report: badScore }).success).toBe(
      false,
    );
    const badSeverity = { ...report, findings: [{ ...finding, severity: 'fatal' }] };
    expect(
      responseSchema.safeParse({ ...base, type: 'result', report: badSeverity }).success,
    ).toBe(false);
  });
});
