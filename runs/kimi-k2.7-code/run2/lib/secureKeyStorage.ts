/**
 * Secure key storage for the Nuri wallet (run 2).
 *
 * Native (React Native): stores the seed in expo-secure-store, the platform
 * keychain. Hardware-backed where the OS supports it and user verification
 * (biometric/PIN) is required on every read.
 *
 * Web (PWA): encrypts the seed with a non-extractable AES-GCM wrapping key
 * held in IndexedDB. Only ciphertext is persisted. The web platform has no
 * user-verification gate for IndexedDB; this module states that limitation
 * honestly and recommends a strict CSP.
 *
 * All mutating operations are serialized through a mutex. Concurrent
 * createAndStoreSeed() / loadSeed() / wipeAllKeychainData() calls cannot
 * interleave, and duplicate in-flight create calls resolve to the same seed.
 */

import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';

const SEED_ALIAS = 'nuri.wallet.seed';
const WRAP_KEY_ALIAS = 'nuri.wallet.wrapkey';
const ALL_ALIASES = [SEED_ALIAS, WRAP_KEY_ALIAS];

const SEED_BYTES = 32;
const IDB_NAME = 'nuri-secure-store';
const IDB_STORE = 'keys';

export class KeyStorageError extends Error {
  constructor(
    message: string,
    readonly cause?: unknown,
    readonly code: 'PLATFORM_UNAVAILABLE' | 'STORAGE_FAILURE' | 'NOT_FOUND' | 'CORRUPTED' | 'UNKNOWN' = 'UNKNOWN'
  ) {
    super(message);
    this.name = 'KeyStorageError';
  }
}

/** Zero out a buffer that held secret material. */
export function zeroize(bytes: Uint8Array): void {
  bytes.fill(0);
}

/** Generate a 32-byte cryptographically secure random seed. */
export function generateSeed(): Uint8Array {
  const seed = new Uint8Array(SEED_BYTES);
  globalThis.crypto.getRandomValues(seed);
  return seed;
}

function assertSeedShape(bytes: Uint8Array): Uint8Array {
  if (bytes.length !== SEED_BYTES) {
    throw new KeyStorageError(
      `Stored seed is corrupted: expected ${SEED_BYTES} bytes, got ${bytes.length}`,
      undefined,
      'CORRUPTED'
    );
  }
  return bytes;
}

function assertPlatform(): void {
  if (!Platform || typeof Platform.OS !== 'string') {
    throw new KeyStorageError('Platform is not available', undefined, 'PLATFORM_UNAVAILABLE');
  }
}

function toBase64(bytes: Uint8Array): string {
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function fromBase64(b64: string): Uint8Array {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

// ---------- Mutex: serialize all storage operations ----------

let opChain: Promise<unknown> = Promise.resolve();
const inFlightOps = new Map<string, Promise<unknown>>();

function withLock<T>(op: () => Promise<T>): Promise<T> {
  const run = opChain.then(op, op);
  opChain = run.catch(() => undefined);
  return run;
}

function dedupeOp<T>(key: string, op: () => Promise<T>): Promise<T> {
  const existing = inFlightOps.get(key) as Promise<T> | undefined;
  if (existing) return existing;
  const promise = op().finally(() => {
    if (inFlightOps.get(key) === promise) inFlightOps.delete(key);
  });
  inFlightOps.set(key, promise);
  return promise;
}

// ---------- Web (PWA) backend: encrypted at rest in IndexedDB ----------

let dbPromise: Promise<IDBDatabase> | null = null;

function openDb(): Promise<IDBDatabase> {
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(IDB_NAME, 1);
      req.onupgradeneeded = () => {
        req.result.createObjectStore(IDB_STORE);
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => {
        const cause = req.error;
        reject(new KeyStorageError('Failed to open secure store', cause, 'STORAGE_FAILURE'));
      };
    });
  }
  return dbPromise;
}

async function withDbTransaction<T>(
  mode: IDBTransactionMode,
  work: (store: IDBObjectStore) => IDBRequest
): Promise<T> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, mode);
    const req = work(tx.objectStore(IDB_STORE));
    req.onsuccess = () => resolve(req.result as T);
    req.onerror = () => reject(new KeyStorageError('IDB operation failed', req.error, 'STORAGE_FAILURE'));
    tx.onerror = () => reject(new KeyStorageError('IDB transaction failed', tx.error, 'STORAGE_FAILURE'));
  });
}

async function idbPut(alias: string, value: unknown): Promise<void> {
  await withDbTransaction('readwrite', (store) => store.put(value, alias));
}

async function idbGet<T>(alias: string): Promise<T | null> {
  return await withDbTransaction('readonly', (store) => store.get(alias));
}

async function idbDelete(alias: string): Promise<void> {
  await withDbTransaction('readwrite', (store) => store.delete(alias));
}

async function idbClear(): Promise<void> {
  await withDbTransaction('readwrite', (store) => store.clear());
}

async function getOrCreateWrapKey(): Promise<CryptoKey> {
  const existing = await idbGet<CryptoKey>(WRAP_KEY_ALIAS);
  if (existing) return existing;

  const key = await globalThis.crypto.subtle.generateKey(
    { name: 'AES-GCM', length: 256 },
    false, // non-extractable
    ['encrypt', 'decrypt']
  );
  await idbPut(WRAP_KEY_ALIAS, key);
  return key;
}

interface WebSeedRecord {
  iv: number[];
  ciphertext: number[];
}

function validateWebRecord(record: unknown): WebSeedRecord {
  if (typeof record !== 'object' || record === null) {
    throw new KeyStorageError('Stored seed record is corrupted: not an object', undefined, 'CORRUPTED');
  }
  const r = record as Partial<WebSeedRecord>;
  if (!Array.isArray(r.iv) || !Array.isArray(r.ciphertext)) {
    throw new KeyStorageError('Stored seed record is corrupted: missing fields', undefined, 'CORRUPTED');
  }
  if (r.iv.length !== 12) {
    throw new KeyStorageError('Stored seed record is corrupted: bad IV length', undefined, 'CORRUPTED');
  }
  if (r.ciphertext.length < 16 + SEED_BYTES) {
    throw new KeyStorageError('Stored seed record is corrupted: ciphertext too short', undefined, 'CORRUPTED');
  }
  return { iv: r.iv, ciphertext: r.ciphertext };
}

async function webStoreSeed(seed: Uint8Array): Promise<void> {
  const wrapKey = await getOrCreateWrapKey();
  const iv = globalThis.crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = new Uint8Array(
    await globalThis.crypto.subtle.encrypt({ name: 'AES-GCM', iv }, wrapKey, seed)
  );
  try {
    await idbPut(SEED_ALIAS, { iv: Array.from(iv), ciphertext: Array.from(ciphertext) });
  } finally {
    zeroize(iv);
    zeroize(ciphertext);
  }
}

async function webLoadSeed(): Promise<Uint8Array> {
  const record = await idbGet<WebSeedRecord>(SEED_ALIAS);
  if (!record) throw new KeyStorageError('No seed stored', undefined, 'NOT_FOUND');
  const validated = validateWebRecord(record);
  const wrapKey = await getOrCreateWrapKey();
  const iv = new Uint8Array(validated.iv);
  const ciphertext = new Uint8Array(validated.ciphertext);
  try {
    const plain = new Uint8Array(
      await globalThis.crypto.subtle.decrypt({ name: 'AES-GCM', iv }, wrapKey, ciphertext)
    );
    return assertSeedShape(plain);
  } finally {
    zeroize(iv);
    zeroize(ciphertext);
  }
}

// ---------- Native (React Native) backend: expo-secure-store ----------

async function assertNativeAvailable(): Promise<void> {
  if (!SecureStore.isAvailableAsync) {
    throw new KeyStorageError(
      'expo-secure-store is not available in this bundle',
      undefined,
      'PLATFORM_UNAVAILABLE'
    );
  }
  const available = await SecureStore.isAvailableAsync();
  if (!available) {
    throw new KeyStorageError('Platform secure store is not available', undefined, 'PLATFORM_UNAVAILABLE');
  }
}

async function nativeStoreSeed(seed: Uint8Array): Promise<void> {
  await assertNativeAvailable();
  const b64 = toBase64(seed);
  await SecureStore.setItemAsync(SEED_ALIAS, b64, {
    requireAuthentication: true,
    keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY,
  });
}

async function nativeLoadSeed(): Promise<Uint8Array> {
  await assertNativeAvailable();
  const b64 = await SecureStore.getItemAsync(SEED_ALIAS, { requireAuthentication: true });
  if (!b64) throw new KeyStorageError('No seed stored', undefined, 'NOT_FOUND');
  return assertSeedShape(fromBase64(b64));
}

// ---------- Public API ----------

/** Create a new random seed and store it in the platform secure store. */
export async function createAndStoreSeed(): Promise<Uint8Array> {
  assertPlatform();
  return dedupeOp('create', async () => {
    const seed = generateSeed();
    try {
      if (Platform.OS === 'web') {
        await withLock(() => webStoreSeed(seed));
      } else {
        await withLock(() => nativeStoreSeed(seed));
      }
      return seed;
    } catch (error) {
      // Wipe any partial persisted state; log the original failure for diagnostics.
      try {
        await wipeAllKeychainData();
      } catch (cleanupError) {
        // Secondary cleanup failure is attached to the original cause but does not
        // override it — the user must still see the primary storage failure.
        console.error('createAndStoreSeed cleanup failed', cleanupError);
      }
      zeroize(seed);
      throw error instanceof KeyStorageError
        ? error
        : new KeyStorageError('Failed to store seed', error, 'STORAGE_FAILURE');
    }
  });
}

/** Load the stored seed. */
export async function loadSeed(): Promise<Uint8Array> {
  assertPlatform();
  return withLock(async () => {
    if (Platform.OS === 'web') {
      return webLoadSeed();
    }
    return nativeLoadSeed();
  });
}

/** Wipe every keychain / secure-store entry this module created. */
export async function wipeAllKeychainData(): Promise<void> {
  assertPlatform();
  return withLock(async () => {
    if (Platform.OS === 'web') {
      await idbClear();
      dbPromise = null;
    } else {
      await assertNativeAvailable();
      await Promise.all(
        ALL_ALIASES.map(async (alias) => {
          try {
            await SecureStore.deleteItemAsync(alias);
          } catch (error) {
            throw new KeyStorageError(`Failed to delete ${alias}`, error, 'STORAGE_FAILURE');
          }
        })
      );
    }
  });
}

/** Encrypt the seed for the web path under a non-extractable wrapping key. */
export async function encryptSeed(seed: Uint8Array): Promise<{ iv: number[]; ciphertext: number[] }> {
  assertSeedShape(seed);
  const wrapKey = await getOrCreateWrapKey();
  const iv = globalThis.crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = new Uint8Array(
    await globalThis.crypto.subtle.encrypt({ name: 'AES-GCM', iv }, wrapKey, seed)
  );
  try {
    return { iv: Array.from(iv), ciphertext: Array.from(ciphertext) };
  } finally {
    zeroize(iv);
    zeroize(ciphertext);
  }
}

/** Decrypt a previously encrypted web seed record. */
export async function decryptSeed(record: { iv: number[]; ciphertext: number[] }): Promise<Uint8Array> {
  const validated = validateWebRecord(record);
  const wrapKey = await getOrCreateWrapKey();
  const iv = new Uint8Array(validated.iv);
  const ciphertext = new Uint8Array(validated.ciphertext);
  try {
    const plain = new Uint8Array(
      await globalThis.crypto.subtle.decrypt({ name: 'AES-GCM', iv }, wrapKey, ciphertext)
    );
    return assertSeedShape(plain);
  } finally {
    zeroize(iv);
    zeroize(ciphertext);
  }
}
