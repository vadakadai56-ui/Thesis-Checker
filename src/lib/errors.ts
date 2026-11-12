// Friendly error messages (BUILD_PROMPT §9) for problems the worker or page detects
// itself. Messages about the FILE (password, macros, damaged, …) come from the engine.

import type { ErrorCode } from './worker/messages';

export const ERROR_MESSAGES: Partial<Record<ErrorCode, string>> = {
  ENGINE_LOAD_FAILED:
    "The checking engine couldn't start. Check your connection for the first visit, then reload. After that it works offline.",
  FILE_TOO_LARGE: 'This file is too big to check (the limit is 50 MB).',
  OUT_OF_MEMORY:
    'Your phone ran out of memory for this file. Try closing other apps, or use a computer.',
  TIMEOUT: 'Checking took too long and was stopped. Try again, or use a computer for big files.',
  INTERNAL: 'Something went wrong inside ThesisCheck. Please try again.',
};

/** An error with one of the codes from BUILD_PROMPT §6d. */
export class EngineFailure extends Error {
  constructor(
    readonly code: ErrorCode,
    message: string,
    readonly detail = '',
  ) {
    super(message || ERROR_MESSAGES[code] || ERROR_MESSAGES.INTERNAL);
    this.name = 'EngineFailure';
  }
}
