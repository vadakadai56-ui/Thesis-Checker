// The ONLY way the page and the engine talk to each other (BUILD_PROMPT §6d, §7).
//
// The engine runs in a Web Worker (a background thread), so the page stays smooth
// while Python works. Page and worker exchange plain messages; every message is
// checked with Zod on arrival, so a malformed message is caught at the boundary
// instead of causing a confusing error deep inside.
//
// All messages carry { version: 1, id, type }. A reply uses the id of the request
// it answers.

import { z } from 'zod';

export const MESSAGE_VERSION = 1;

const base = { version: z.literal(MESSAGE_VERSION), id: z.string().min(1) };
const bytes = z.instanceof(Uint8Array);
// Optional fixed "now" (ISO date-time) so tests get reproducible reports.
const job = { ...base, profileId: z.string().min(1), bytes, now: z.string().optional() };

// ------------------------------------------------------------- page -> worker

export const requestSchema = z.discriminatedUnion('type', [
  z.object({ ...base, type: z.literal('init') }),
  z.object({ ...job, type: z.literal('check'), fileName: z.string() }),
  z.object({ ...job, type: z.literal('fix'), fileName: z.string().optional() }),
  z.object({ ...job, type: z.literal('annotate'), fileName: z.string().optional() }),
  z.object({ ...base, type: z.literal('cancel'), targetId: z.string() }),
]);
export type EngineRequest = z.infer<typeof requestSchema>;

// ------------------------------------------------------------- worker -> page

export const ERROR_CODES = [
  'ENGINE_LOAD_FAILED',
  'FILE_TOO_LARGE',
  'NOT_DOCX',
  'LEGACY_DOC',
  'ODT',
  'ENCRYPTED',
  'MACRO_DOCM',
  'CORRUPT',
  'ZIP_BOMB',
  'OUT_OF_MEMORY',
  'TIMEOUT',
  'INTERNAL',
] as const;
export const errorCodeSchema = z.enum(ERROR_CODES);
export type ErrorCode = z.infer<typeof errorCodeSchema>;

const locationSchema = z.object({
  part: z.string(),
  paragraph_index: z.number().int().nullable(),
  section_index: z.number().int().nullable(),
  page_estimate: z.number().int().nullable(),
  heading_path: z.array(z.string()),
  snippet: z.string(),
});

export const findingSchema = z.object({
  version: z.literal(1),
  id: z.string(),
  rule_id: z.string(),
  category: z.string(),
  severity: z.enum(['error', 'warning', 'info']),
  message: z.string(),
  rule_text: z.string(),
  guideline_ref: z.string(),
  location: locationSchema,
  expected: z.unknown(),
  found: z.unknown(),
  fixable: z.boolean(),
  fixed: z.boolean(),
  how_to_fix: z.string(),
});
export type Finding = z.infer<typeof findingSchema>;

const scoreSchema = z.object({
  version: z.literal(1),
  value: z.number().int().min(0).max(100),
  band: z.enum(['Ready', 'Nearly ready', 'Needs work']),
  penalty: z.number(),
  capped: z.boolean(),
});

export const reportSchema = z.object({
  version: z.literal(1),
  engine_version: z.string(),
  document_sha256: z.string().length(64),
  file_name: z.string(),
  profile: z.object({ id: z.string(), version: z.number(), status: z.enum(['draft', 'verified']) }),
  created_at: z.string(),
  stats: z.object({
    paragraphs: z.number().int(),
    pages_estimate: z.number().int(),
    words: z.number().int(),
  }),
  findings: z.array(findingSchema),
  score: scoreSchema,
  skipped_rules: z.array(z.object({ rule_id: z.string(), reason: z.string() })),
});
export type Report = z.infer<typeof reportSchema>;

const fixSummarySchema = z.object({
  rule_id: z.string(),
  title: z.string(),
  findings: z.number().int(),
  changes: z.number().int(),
});

export const responseSchema = z.discriminatedUnion('type', [
  z.object({
    ...base,
    type: z.literal('progress'),
    stage: z.string(),
    pct: z.number().min(0).max(100),
    detail: z.string(),
  }),
  z.object({
    ...base,
    type: z.literal('ready'),
    engineVersion: z.string(),
    pyodideVersion: z.string(),
  }),
  z.object({ ...base, type: z.literal('result'), report: reportSchema }),
  z.object({
    ...base,
    type: z.literal('fileResult'),
    kind: z.enum(['fixed', 'annotated']),
    fileName: z.string(),
    bytes,
    report: reportSchema,
    before: z.object({ score: scoreSchema, findings: z.number().int() }),
    fixedFindings: z.array(findingSchema),
    fixes: z.array(fixSummarySchema),
    comments: z.number().int().optional(),
  }),
  z.object({
    ...base,
    type: z.literal('error'),
    code: errorCodeSchema,
    message: z.string(),
    detail: z.string(),
  }),
]);
export type EngineResponse = z.infer<typeof responseSchema>;
export type FileResult = Extract<EngineResponse, { type: 'fileResult' }>;
export type Progress = Extract<EngineResponse, { type: 'progress' }>;
export type Ready = Extract<EngineResponse, { type: 'ready' }>;
