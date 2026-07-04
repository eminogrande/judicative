/**
 * Secure key storage for the Nuri wallet — run 2.
 *
 * Native (React Native): expo-secure-store, hardware-backed, requires user
 * verification (biometric/PIN) on every read.
 *
 * Web (PWA): the seed is encrypted at rest with a NON-EXTRACTABLE AES-GCM
 * CryptoKey held in IndexedDB; only ciphertext is persisted. Residual risk,
 * stated honestly: a same-origin XSS payload cannot exfiltrate the wrapping
 * key, but it CAN ask this module to decrypt while the page is compromised.
 * The web platform offers no user-verification gate for IndexedDB; deploy a
 * strict CSP alongside this module.
 *
 * All mutating operations are serialized through a mutex: concurrent
 * createAndStoreSeed()/wipeAllKeychainData() calls cannot interleave, and
 * duplicate in-flight create calls resolve to the same seed.
 */

import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';

const SEED_ALIAS = 'nuri.wallet.seed';
const WRAP_KEY_ALIAS = 'nuri.wallet.wrapkey';
// Every alias this module ever writes must be listed here so wipe() is complete.
const ALL_ALIASES = [SEED_ALIAS, WRAP_KEY_ALIAS];

const SEED_BYTES = 32;
const IDB_NAME = 'nuri-secure-store';
const IDB_STORE = 'keys';

export class KeyStorageError extends Error {
  constructor(message: string, readonly cause?: unknown) {
    super(message);
    this.name = 'KeyStorageError';
  }
}

/** Zero out a buffer that held secret material. Call as soon as a secret is no longer needed. */
export function zeroize(bytes: Uint8Array): void {
  bytes.fill(0);
}

/** Generate a cryptographically secure random seed. */
export function generateSeed(): Uint8Array {
  const seed = new Uint8Array(SEED_BYTES);
  globalThis.crypto.getRandomValues(seed);
  return seed;
}

function assertSeedShape(bytes: Uint8Array): Uint8Array {
  if (bytes.length !== SEED_BYTES) {
    throw new KeyStorageError(
      `Stored seed is corrupted: expected ${SEED_BYTES} bytes, got ${bytes.length}`
    );
  }
  return bytes;
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

// ---------- Mutex: serialize all mutating storage operations ----------

let opChain: Promise<unknown> = Promise.resolve();

function withLock<T>(op: () => Promise<T>): Promise<T> {
  const run = opChain.then(op, op);
  // Keep the chain alive even if this op rejects; the rejection still
  // propagates to this op's caller via `run`.
  opChain = run.catch(() => undefined);
  return run;
}

let inFlightCreate: Promise<Uint8Array> | null = null;

// ---------- Web (PWA) backend: encrypted at rest in IndexedDB ----------

let dbPromise: Promise<IDBDatabase> | null = null;

function openDb(): Promise<IDBDatabase> {
  // Cache the connection; reopen only if a previous attempt failed.
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(IDB_NAME, 1);
      req.onupgradeneeded = () => {
        req.result.createObjectStore(IDB_STORE);
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => {
        dbPromise = null;
        reject(new KeyStorageError('Failed to open secure store', req.error));
      };
    });
  }
  return dbPromise;
}

async function idbPut(alias: string, value: unknown): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, 'readwrite');
    tx.objectStore(IDB_STORE).put(value, alias);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(new KeyStorageError('Failed to write key', tx.error));
  });
}

async function idbGet<T>(alias: string): Promise<T | null> {
  const db = await openDb();
  return new Promise<T | null>((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, 'readonly');
    const req = tx.objectStore(IDB_STORE).get(alias);
    req.onsuccess = () => resolve((req.result as T) ?? null);
    req.onerror = () => reject(new KeyStorageError('Failed to read key', req.error));
  });
}

async function idbDelete(alias: string): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, 'readwrite');
    tx.objectStore(IDB_STORE).delete(alias);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(new KeyStorageError('Failed to delete key', tx.error));
  });
}

/** Get or create the non-extractable AES-GCM key that wraps the seed at rest. */
async function getWrappingKey(): Promise<CryptoKey> {
  const existing = await idbGet<CryptoKey>(WRAP_KEY_ALIAS);
  if (existing) {
    return existing;
  }
  const key = await globalThis.crypto.subtle.generateKey(
    { name: 'AES-GCM', length: 256 },
    /* extractable */ false,
    ['encrypt', 'decrypt']
  );
  await idbPut(WRAP_KEY_ALIAS, key);
  return key;
}

interface EncryptedSeed {
  iv: Uint8Array;
  ciphertext: ArrayBuffer;
}

async function webStoreSeed(seed: Uint8Array): Promise<void> {
  const key = await getWrappingKey();
  const iv = new Uint8Array(12);
  globalThis.crypto.getRandomValues(iv);
  const ciphertext = await globalThis.crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, seed);
  await idbPut(SEED_ALIAS, { iv, ciphertext } satisfies EncryptedSeed);
}

async function webLoadSeed(): Promise<Uint8Array | null> {
  const entry = await idbGet<EncryptedSeed>(SEED_ALIAS);
  if (!entry || !(entry.iv instanceof Uint8Array) || !entry.ciphertext) {
    return entry ? Promise.reject(new KeyStorageError('Stored seed entry is malformed')) : null;
  }
  const key = await getWrappingKey();
  const plain = await globalThis.crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: entry.iv },
    key,
    entry.ciphertext
  );
  return assertSeedShape(new Uint8Array(plain));
}

// ---------- Native (React Native) backend ----------

async function assertNativeAvailable(): Promise<void> {
  // OTA updates cannot ship native modules: fail loudly and early if this
  // binary does not include expo-secure-store, instead of crashing mid-call.
  if (typeof SecureStore.isAvailableAsync !== 'function' || !(await SecureStore.isAvailableAsync())) {
    throw new KeyStorageError(
      'Secure storage is not available in this app binary. Update the app to store keys.'
    );
  }
}

async function nativeStoreSeed(seed: Uint8Array): Promise<void> {
  await assertNativeAvailable();
  // SecureStore only accepts strings; base64 is unavoidable here. The string
  // copy cannot be zeroized (JS strings are immutable) — documented residual.
  await SecureStore.setItemAsync(SEED_ALIAS, toBase64(seed), {
    keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
    requireAuthentication: true,
  });
}

async function nativeLoadSeed(): Promise<Uint8Array | null> {
  await assertNativeAvailable();
  const encoded = await SecureStore.getItemAsync(SEED_ALIAS, { requireAuthentication: true });
  return encoded ? assertSeedShape(fromBase64(encoded)) : null;
}

// ---------- Public API ----------

const isWeb = Platform.OS === 'web';

/**
 * Generate a new seed and persist it. Concurrent calls are deduplicated:
 * every caller receives the SAME seed as the one that was persisted.
 * Throws KeyStorageError if storage fails — surface it to the user; there is
 * deliberately no fallback to weaker storage.
 *
 * Ownership: the returned Uint8Array is the caller's copy — call zeroize()
 * on it as soon as it has been used.
 */
export function createAndStoreSeed(): Promise<Uint8Array> {
  if (inFlightCreate) {
    return inFlightCreate;
  }
  inFlightCreate = withLock(async () => {
    const seed = generateSeed();
    try {
      if (isWeb) {
        await webStoreSeed(seed);
      } else {
        await nativeStoreSeed(seed);
      }
      return seed;
    } catch (error) {
      zeroize(seed);
      console.error('secureKeyStorage: failed to persist seed', error);
      throw error instanceof KeyStorageError
        ? error
        : new KeyStorageError('Could not store the signing key securely', error);
    }
  }).finally(() => {
    inFlightCreate = null;
  });
  return inFlightCreate;
}

/**
 * Load the stored seed, or null if none exists. Throws on storage failure or
 * corrupted data. Caller owns the returned buffer — zeroize() it after use.
 */
export function loadSeed(): Promise<Uint8Array | null> {
  return withLock(async () => {
    try {
      return isWeb ? await webLoadSeed() : await nativeLoadSeed();
    } catch (error) {
      console.error('secureKeyStorage: failed to load seed', error);
      throw error instanceof KeyStorageError
        ? error
        : new KeyStorageError('Could not read the signing key', error);
    }
  });
}

/**
 * Remove ALL entries this module owns (seed AND the web wrapping key).
 * Iterates the alias registry so newly added aliases are wiped too; attempts
 * every alias and throws an aggregate error if any deletion failed — a failed
 * wipe is fatal, never silent.
 */
export function wipeAllKeychainData(): Promise<void> {
  return withLock(async () => {
    const failures: unknown[] = [];
    for (const alias of ALL_ALIASES) {
      try {
        if (isWeb) {
          await idbDelete(alias);
        } else {
          await assertNativeAvailable();
          await SecureStore.deleteItemAsync(alias);
        }
      } catch (error) {
        console.error(`secureKeyStorage: failed to wipe ${alias}`, error);
        failures.push(error);
      }
    }
    if (failures.length > 0) {
      throw new KeyStorageError(`Failed to wipe ${failures.length} keychain entries`, failures[0]);
    }
  });
}
