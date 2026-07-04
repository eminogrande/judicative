/**
 * Secure key storage for the Nuri wallet.
 *
 * Stores the wallet signing seed in the platform keychain (expo-secure-store
 * on React Native, IndexedDB-backed non-extractable storage on web). Never
 * touches localStorage.
 */

import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';

const SEED_ALIAS = 'nuri.wallet.seed';
// Every alias this module ever writes must be listed here so wipe() is complete.
const ALL_ALIASES = [SEED_ALIAS];

const IDB_NAME = 'nuri-secure-store';
const IDB_STORE = 'keys';

export class KeyStorageError extends Error {
  constructor(message: string, readonly cause?: unknown) {
    super(message);
    this.name = 'KeyStorageError';
  }
}

/** Generate a 32-byte cryptographically secure random seed. */
export function generateSeed(): Uint8Array {
  const seed = new Uint8Array(32);
  // crypto.getRandomValues exists in RN (via react-native-get-random-values) and web
  globalThis.crypto.getRandomValues(seed);
  return seed;
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

// ---------- Web (PWA) backend: IndexedDB, never localStorage ----------

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(IDB_NAME, 1);
    req.onupgradeneeded = () => {
      req.result.createObjectStore(IDB_STORE);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(new KeyStorageError('Failed to open secure store', req.error));
  });
}

async function idbPut(alias: string, value: string): Promise<void> {
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

async function idbGet(alias: string): Promise<string | null> {
  const db = await openDb();
  try {
    return await new Promise<string | null>((resolve, reject) => {
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

// ---------- Public API ----------

const isWeb = Platform.OS === 'web';

/**
 * Generate a new seed and persist it in the platform keychain.
 * Throws KeyStorageError if storage fails — callers must surface this to the
 * user; there is no silent fallback to weaker storage.
 */
export async function createAndStoreSeed(): Promise<Uint8Array> {
  const seed = generateSeed();
  const encoded = toBase64(seed);
  try {
    if (isWeb) {
      await idbPut(SEED_ALIAS, encoded);
    } else {
      await SecureStore.setItemAsync(SEED_ALIAS, encoded, {
        keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
        requireAuthentication: true,
      });
    }
  } catch (error) {
    console.error('secureKeyStorage: failed to persist seed', error);
    throw new KeyStorageError('Could not store the signing key securely', error);
  }
  return seed;
}

/** Load the stored seed, or null if none exists. Throws on storage failure. */
export async function loadSeed(): Promise<Uint8Array | null> {
  try {
    const encoded = isWeb
      ? await idbGet(SEED_ALIAS)
      : await SecureStore.getItemAsync(SEED_ALIAS, { requireAuthentication: true });
    return encoded ? fromBase64(encoded) : null;
  } catch (error) {
    console.error('secureKeyStorage: failed to load seed', error);
    throw new KeyStorageError('Could not read the signing key', error);
  }
}

/**
 * Remove ALL keychain entries this module owns. Iterates the alias registry
 * so newly added aliases are wiped too; collects failures instead of stopping
 * at the first one.
 */
export async function wipeAllKeychainData(): Promise<void> {
  const failures: unknown[] = [];
  for (const alias of ALL_ALIASES) {
    try {
      if (isWeb) {
        await idbDelete(alias);
      } else {
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
}
