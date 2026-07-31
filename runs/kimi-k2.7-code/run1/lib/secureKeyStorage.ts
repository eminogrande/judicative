/**
 * Secure key storage for the Nuri wallet.
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
 * createAndStoreSeed() / wipeAllKeychainData() calls cannot interleave,
 * and duplicate in-flight create calls resolve to the same seed.
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
  constructor(message: string, readonly cause?: unknown) {
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
      `Stored seed is corrupted: expected ${SEED_BYTES} bytes, got ${bytes.length}`
    );
  }
  return bytes;
}

function assertPlatform() {
  if (!Platform || typeof Platform.OS !== 'string') {
    throw new KeyStorageError('Platform is not available');
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

// ---------- Mutex: serialize all mutating storage operations ----------

let opChain: Promise<unknown> = Promise.resolve();

function withLock<T>(op: () => Promise<T>): Promise<T> {
  const run = opChain.then(op, op);
  opChain = run.catch(() => undefined);
  return run;
}

let inFlightCreate: Promise<Uint8Array> | null = null;

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
      req.onerror = () => reject(new KeyStorageError('Failed to open secure store', req.error));
    });
  }
  return dbPromise;
}

async function idbPut(alias: string, value: unknown): Promise<void> {
  const db = await openDb();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(IDB_STORE, 'readwrite');
      tx.objectStore(IDB_STORE).put(value, alias);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(new KeyStorageError('Failed to write key', tx.error));
    });
  } finally {
    db.close();
  }
}

async function idbGet<T>(alias: string): Promise<T | null> {
  const db = await openDb();
  try {
    return await new Promise<T | null>((resolve, reject) => {
      const tx = db.transaction(IDB_STORE, 'readonly');
      const req = tx.objectStore(IDB_STORE).get(alias);
      req.onsuccess = () => resolve(req.result ?? null);
      req.onerror = () => reject(new KeyStorageError('Failed to read key', req.error));
    });
  } finally {
    db.close();
  }
}

async function idbDelete(alias: string): Promise<void> {
  const db = await openDb();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(IDB_STORE, 'readwrite');
      tx.objectStore(IDB_STORE).delete(alias);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(new KeyStorageError('Failed to delete key', tx.error));
    });
  } finally {
    db.close();
  }
}

async function idbClear(): Promise<void> {
  const db = await openDb();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(IDB_STORE, 'readwrite');
      tx.objectStore(IDB_STORE).clear();
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(new KeyStorageError('Failed to clear secure store', tx.error));
    });
  } finally {
    db.close();
  }
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
    throw new KeyStorageError('Stored seed record is corrupted: not an object');
  }
  const r = record as Partial<WebSeedRecord>;
  if (!Array.isArray(r.iv) || !Array.isArray(r.ciphertext)) {
    throw new KeyStorageError('Stored seed record is corrupted: missing fields');
  }
  if (r.iv.length !== 12) {
    throw new KeyStorageError('Stored seed record is corrupted: bad IV length');
  }
  if (r.ciphertext.length < 16) {
    throw new KeyStorageError('Stored seed record is corrupted: ciphertext too short');
  }
  return { iv: r.iv, ciphertext: r.ciphertext };
}

async function webStoreSeed(seed: Uint8Array): Promise<void> {
  const wrapKey = await getOrCreateWrapKey();
  const iv = globalThis.crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = new Uint8Array(
    await globalThis.crypto.subtle.encrypt(
      { name: 'AES-GCM', iv },
      wrapKey,
      seed
    )
  );
  await idbPut(SEED_ALIAS, { iv: Array.from(iv), ciphertext: Array.from(ciphertext) });
  zeroize(iv);
  zeroize(ciphertext);
}

async function webLoadSeed(): Promise<Uint8Array> {
  const record = await idbGet<WebSeedRecord>(SEED_ALIAS);
  if (!record) throw new KeyStorageError('No seed stored');
  const validated = validateWebRecord(record);
  const wrapKey = await getOrCreateWrapKey();
  const iv = new Uint8Array(validated.iv);
  const ciphertext = new Uint8Array(validated.ciphertext);
  try {
    const plain = new Uint8Array(
      await globalThis.crypto.subtle.decrypt(
        { name: 'AES-GCM', iv },
        wrapKey,
        ciphertext
      )
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
    throw new KeyStorageError('expo-secure-store is not available in this bundle');
  }
  const available = await SecureStore.isAvailableAsync();
  if (!available) {
    throw new KeyStorageError('Platform secure store is not available');
  }
}

async function nativeStoreSeed(seed: Uint8Array): Promise<void> {
  await assertNativeAvailable();
  const b64 = toBase64(seed);
  try {
    await SecureStore.setItemAsync(SEED_ALIAS, b64, {
      requireAuthentication: true,
      keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY,
    });
  } finally {
    // Cannot zeroize immutable strings; the Uint8Array caller owns clearing.
  }
}

async function nativeLoadSeed(): Promise<Uint8Array> {
  await assertNativeAvailable();
  const b64 = await SecureStore.getItemAsync(SEED_ALIAS, {
    requireAuthentication: true,
  });
  if (!b64) throw new KeyStorageError('No seed stored');
  const seed = assertSeedShape(fromBase64(b64));
  return seed;
}

// ---------- Public API ----------

/** Create a new random seed and store it in the platform secure store. */
export async function createAndStoreSeed(): Promise<Uint8Array> {
  assertPlatform();
  if (inFlightCreate) return inFlightCreate;

  const promise = withLock(async () => {
    const seed = generateSeed();
    try {
      if (Platform.OS === 'web') {
        await webStoreSeed(seed);
      } else {
        await nativeStoreSeed(seed);
      }
      return seed;
    } catch (error) {
      // On failure, clear any partial persisted material and zeroize the seed.
      try {
        await wipeAllKeychainData();
      } catch (_) {
        // ignore nested cleanup errors
      }
      zeroize(seed);
      throw new KeyStorageError('Failed to store seed', error);
    }
  });

  inFlightCreate = promise;
  promise.finally(() => {
    if (inFlightCreate === promise) inFlightCreate = null;
  });
  return promise;
}

/** Load the stored seed. */
export async function loadSeed(): Promise<Uint8Array> {
  assertPlatform();
  if (Platform.OS === 'web') {
    return webLoadSeed();
  }
  return nativeLoadSeed();
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
            throw new KeyStorageError(`Failed to delete ${alias}`, error);
          }
        })
      );
    }
  });
}
