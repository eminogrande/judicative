/**
 * types.ts - Shared type definitions for the secure key storage module.
 */

/** Platform-agnostic secure storage interface. */
export interface SecureStorageAdapter {
  /** Store a value securely. Rejects on failure. */
  setItem(key: string, value: string): Promise<void>;

  /** Retrieve a value. Returns null if not found. Rejects on storage errors. */
  getItem(key: string): Promise<string | null>;

  /** Remove a specific key. */
  removeItem(key: string): Promise<void>;

  /** Remove ALL entries from secure storage. */
  wipe(): Promise<void>;

  /** Check whether this adapter is available on the current platform. */
  isAvailable(): boolean;
}

/**
 * Error thrown by all secure storage operations.
 * The `cause` field preserves the original error for debugging.
 */
export class SecureStorageError extends Error {
  constructor(message: string, public readonly cause?: unknown) {
    super(message);
    this.name = "SecureStorageError";
  }
}

/**
 * Error kind for distinguishing transient vs non-transient failures.
 * Callers can use `isTransient` to decide whether to retry.
 */
export class TransientStorageError extends SecureStorageError {
  constructor(message: string, public readonly cause?: unknown) {
    super(message, cause);
    this.name = "TransientStorageError";
  }
}
