# Blind Review Packet

## Your role

You are one judge on a blind review panel. You do not know who or what wrote
these submissions (human, LLM, junior, senior) and you must not try to guess
or let style hints influence you. Judge only the code in front of you, as a
strict senior reviewer at a Bitcoin wallet company would.

Review each submission INDEPENDENTLY — do not let one submission's quality
recalibrate your standards for another. Penalize only what you can point to in
the code; cite lines in your explanations.

## What to produce

For EVERY submission:
1. `holistic_score` (0-100, integer): your overall verdict as a reviewer.
   Calibration: 90+ = ship it, exemplary; 70-89 = mergeable after nits;
   40-69 = needs significant rework; <40 = reject. Be strict: 100 means you
   found nothing to improve.
2. `verdict`: "PASS" if you would approve the PR, else "FAIL".
3. `strengths` / `weaknesses`: short bullet strings, specific.
4. `rule_deductions`: for each rubric rule below that the submission violates
   (fully or partially), an entry {"rule_id", "score", "explanation"} where
   score is 0.0 (clear violation) to 1.0 (no issue). ONLY list rules you
   deduct on (score < 1.0); unlisted rules count as 1.0. If a rule has no
   applicable surface in the submission, do not list it.

Finally, `ranking`: all submission labels, best first.

## Response format (return EXACTLY this JSON shape)

{
  "judge_id": "<your name/model>",
  "reviews": {
    "SUBMISSION-A": {
      "holistic_score": 72,
      "verdict": "PASS",
      "strengths": ["..."],
      "weaknesses": ["..."],
      "rule_deductions": [
        {"rule_id": "RACE-005", "score": 0.4, "explanation": "lines 12-30: ..."}
      ]
    }
  },
  "ranking": ["SUBMISSION-B", "SUBMISSION-A"]
}

## The task the submissions were asked to solve

Title: Implement a secure key storage module for the Nuri wallet

Description:
We need a module that securely stores the wallet's signing key using the platform's
secure enclave / keychain. The module must:

1. Generate a cryptographically secure random seed
2. Store it in the platform keychain (NOT localStorage)
3. Provide a wipe function that removes ALL keychain entries
4. Handle errors gracefully — if storage fails, surface the error to the user
5. Work in both React Native and PWA (web) contexts

Security requirements:
- Never use Math.random() for key generation
- Never store secrets in localStorage
- Never use eval() or innerHTML with dynamic content
- All catch blocks must log errors, not swallow them silently

## Rubric rules (deduct against these)

- **RACE-003** [major] Async operation without cancellation: Async operations (fetch, subscriptions, timers) started in useEffect or event handlers must have cancellation logic. Without it, in-flight requests leak and stale responses can overwrite fresh state.
- **RACE-004** [major] Missing AbortController for fetch: Fetch calls in React components should use AbortController to cancel on unmount. Without it, responses arriving after unmount cause state updates on unmounted components.
- **RACE-005** [critical] Concurrent state mutation: Multiple async operations writing to the same state without ordering guarantees. Use mutex, queue, or atomic updates to prevent interleaving.
- **STALE-002** [major] Cached data used after async gap: Data fetched or computed before an await is used after the await without revalidation. The data may be stale if state changed during the async gap.
- **STALE-003** [major] Ghost balance display: Balance or amount displayed from cached state without checking if a more recent update is available. Users see incorrect balances.
- **STALE-004** [minor] Missing refetch on focus/reconnect: Data that can change server-side (balances, transaction status) should be refetched on app focus or network reconnect.
- **UI-001** [major] Modal layer isolation: Modals and overlay layers must isolate content — accessibilityViewIsModal, aria-hidden on background, pointerEvents on layers.
- **UI-002** [major] Back handler on layers: Hardware back button must be consumed by visible layers to prevent back falling through to content behind blocking layers.
- **UI-003** [minor] Component prop correctness: Components must receive correct props — wrong types, missing required props, or incorrect conditional rendering.
- **ARCH-001** [major] Circular dependency: Modules that import each other create circular dependencies that cause runtime errors or initialization order issues.
- **ARCH-002** [minor] Separation of concerns: Business logic mixed with UI rendering, or crypto operations in view components. Extract into hooks or services.
- **ARCH-003** [minor] Module structure: Files should have a single responsibility. Mixing unrelated functionality in one file makes the codebase harder to navigate.
- **STYLE-001** [minor] ESLint compliance: Code should pass eslint with the project's configured ruleset.
- **STYLE-002** [nitpick] Import ordering: Imports should be ordered and grouped consistently (stdlib, external, internal, relative).
- **SEC-007** [critical] Signature verification: All signature verification and assertion validation must be performed correctly.
- **SEC-008** [critical] No nonce reuse: Cryptographic nonces must never be reused. In MuSig2, nonce reuse leaks private keys.
- **SEC-009** [major] Sandbox WebView/iframe content: WebView and iframe content must be sandboxed by default.
- **SEC-010** [major] Missing zeroization of sensitive data: Sensitive Uint8Array (seeds, keys, nonces) must be wiped after use. Leaving them in memory increases exposure window.
- **OTA-001** [critical] Native module call in OTA-shippable code: OTA updates cannot change native modules. Code that calls native modules not present in the current binary must be gated or have fallbacks.
- **OTA-002** [major] Fingerprint compatibility check: Code must check the binary fingerprint before calling native APIs that may not exist in older versions.
- **ERR-002** [major] Error propagation: Errors from critical operations must be propagated to the caller or surfaced to the user, not swallowed.
- **ERR-003** [major] Non-transient failure handling: Non-transient failures (e.g., invalid input, permission denied) must not be retried indefinitely. Distinguish from transient failures (network timeout).
- **DATA-001** [major] Unify address sources: When multiple integrations need a default address, they must use a unified source. Divergent sources cause funds to be sent to wrong addresses.
- **DATA-002** [major] No silent storage downgrade: Storage operations must not silently downgrade from persistent to volatile.
- **DATA-003** [major] Clear stale armed results: Starting a new async operation must clear stale results from previous runs.
- **DATA-004** [major] Make failed critical operations fatal: Critical operations like IBAN moves must be fatal on failure.
- **DATA-005** [major] Deduplicate sync requests: Repeated sync requests must be deduplicated to prevent duplicate state writes.
- **TIMEOUT-001** [major] Preserve timeout backoff on failures: When boarding reads fail, the timeout backoff must be preserved, not reset. Resetting causes retry storms.
- **TIMEOUT-002** [major] Re-throw non-transient failures: Non-transient boarding failures must be re-thrown, not swallowed or treated as transient.
- **DEAD-001** [minor] No dead code or unused imports: Unused imports and dead code should be removed.
- **DEAD-002** [minor] No unreachable branches: Code after unconditional returns or throws is unreachable.
- **CATCH-001** [major] Silent catch (LLM check for context): Empty catch blocks that swallow errors. The static check is in error_handling/ERR-001. This LLM rule catches cases where the catch block has code but still swallows errors (e.g., catch but only logs, doesn't propagate).
- **A11Y-003** [minor] ARIA labels on interactive elements: Interactive elements (buttons, links, inputs) need accessible names via aria-label or visible text.
- **DOC-001** [nitpick] Label code fences in docs: Code fences in markdown should have a language label.
- **DOC-002** [minor] Document complex logic: Complex logic, crypto operations, and state machines need inline comments explaining the why.
- **VALID-001** [major] Runtime validation at external boundaries: Data from external sources (API responses, user input, IPC) must be validated at the boundary before use.
- **VALID-002** [major] Per-item validation in arrays: Arrays from external sources must have per-item validation, not just type checks on the array itself.
- **SANDBOX-001** [major] Sandbox iframe content: WebView and iframe content must be sandboxed by default with appropriate sandbox attributes.
- **SANDBOX-002** [major] Content Security Policy: CSP headers must restrict script sources and prevent inline script execution.
- **STATE-001** [critical] No recursive resolveRequest: Calling context.resolveRequest recursively inside a custom resolveRequest causes infinite loops (Maximum call stack size exceeded).
- **STATE-002** [major] State synchronization: Multiple state sources (local state, context, server) must be synchronized to prevent inconsistent UI.
- **PERF-001** [major] Don't initialize expensive resources on every call: Expensive initializations should be cached or lazy-loaded.
- **NAME-001** [minor] Clear naming: Names should be descriptive and not misleading.
- **PRES-001** [major] Don't break existing behavior: Refactors must preserve existing behavior. Don't close sends before a tx is submitted, don't remove fallback paths without replacement.
- **BAL-001** [major] Balance display matches actual state: Displayed balance must match the actual on-chain/server state. Stale balances cause users to make incorrect decisions.
- **TYPE-001** [minor] No unsafe type casts: Avoid `as any` and unsafe type casts. Use proper type guards.
- **TYPE-002** [major] Correct enum usage: Enum values must match the actual library API. Example: BIOMETRIC_STRONG doesn't exist in expo-local-authentication.
- **UV-001** [major] User verification on passkey operations: Passkey signing operations must require user verification (UV). Missing UV allows signing without biometric/PIN.
- **API-001** [critical] Implement required interfaces: WebView shims must implement all required interfaces like injectedJavaScriptObject. Missing interfaces cause runtime crashes.
- **API-002** [major] Handle URL objects in interceptors: Fetch and XMLHttpRequest interceptors must handle URL objects, not just strings.
- **API-003** [minor] Correct HTML attributes: In raw HTML files, use http-equiv not camelCase React JSX props.
- **CLEAN-001** [major] Complete keychain wipe: wipeAllKeychainData must remove ALL aliased entries, not just the primary key.
- **CLEAN-002** [major] Sweep all items, not just first: Sweep operations must process all items, not just the first match.
- **LS-001** [critical] No private keys in localStorage (duplicate hard gate): Duplicate of SEC-001 — kept as LLM rule to avoid double-penalizing with the same regex. The static check is in security_crypto/SEC-001. This LLM rule catches cases the regex misses (e.g., indirect localStorage access via wrapper functions).

## Submissions

### SUBMISSION-A

`lib/secureKeyStorage.ts`:
```
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
```

### SUBMISSION-B

`lib/secureKeyStorage.ts`:
```
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
```

### SUBMISSION-C

`secureKeyStorage.ts`:
```
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const KEYCHAIN_ALIAS = 'nuri_signing_key';

export async function generateSeed(): Promise<Uint8Array> {
  const seed = new Uint8Array(32);
  crypto.getRandomValues(seed);
  return seed;
}

export async function storeSeed(seed: Uint8Array): Promise<void> {
  try {
    if (Platform.OS === 'web') {
      const encrypted = await encryptSeed(seed);
      await indexedDBPut('nuri_secure', KEYCHAIN_ALIAS, encrypted);
    } else {
      await SecureStore.setItemAsync(KEYCHAIN_ALIAS, encodeBase64(seed));
    }
  } catch (error) {
    // Silent catch — should log the error
  }
}

export async function retrieveSeed(): Promise<Uint8Array | null> {
  try {
    if (Platform.OS === 'web') {
      const encrypted = await indexedDBGet('nuri_secure', KEYCHAIN_ALIAS);
      if (!encrypted) return null;
      return await decryptSeed(encrypted);
    } else {
      const stored = await SecureStore.getItemAsync(KEYCHAIN_ALIAS);
      if (!stored) return null;
      return decodeBase64(stored);
    }
  } catch (error) {
    // Silent catch — should surface error to user
  }
}

export async function wipeAllKeychainData(): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(KEYCHAIN_ALIAS);
    // Missing: doesn't remove backup alias
  } catch (error) {
    // Silent catch
  }
}
```

### SUBMISSION-D

`secureKeyStorage.ts`:
```
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';
import { logger } from '../utils/logger';

const KEYCHAIN_ALIAS = 'nuri_signing_key';
const KEYCHAIN_ALIAS_BACKUP = 'nuri_signing_key_backup';

export async function generateSeed(): Promise<Uint8Array> {
  // Use crypto.getRandomValues for cryptographically secure randomness
  const seed = new Uint8Array(32);
  crypto.getRandomValues(seed);
  return seed;
}

export async function storeSeed(seed: Uint8Array): Promise<void> {
  try {
    if (Platform.OS === 'web') {
      // On web, use IndexedDB with encryption, NOT localStorage
      const encrypted = await encryptSeed(seed);
      await indexedDBPut('nuri_secure', KEYCHAIN_ALIAS, encrypted);
    } else {
      // On native, use the platform keychain
      await SecureStore.setItemAsync(KEYCHAIN_ALIAS, encodeBase64(seed), {
        keychainAccessible: SecureStore.WHEN_UNLOCKED,
      });
    }
  } catch (error) {
    logger.error('Failed to store seed in secure storage:', error);
    throw new Error('Secure storage failed — cannot continue without key storage');
  }
}

export async function retrieveSeed(): Promise<Uint8Array | null> {
  try {
    if (Platform.OS === 'web') {
      const encrypted = await indexedDBGet('nuri_secure', KEYCHAIN_ALIAS);
      if (!encrypted) return null;
      return await decryptSeed(encrypted);
    } else {
      const stored = await SecureStore.getItemAsync(KEYCHAIN_ALIAS);
      if (!stored) return null;
      return decodeBase64(stored);
    }
  } catch (error) {
    logger.error('Failed to retrieve seed from secure storage:', error);
    throw error;
  }
}

export async function wipeAllKeychainData(): Promise<void> {
  try {
    // Remove ALL aliased entries, not just the primary one
    await SecureStore.deleteItemAsync(KEYCHAIN_ALIAS);
    await SecureStore.deleteItemAsync(KEYCHAIN_ALIAS_BACKUP);
    if (Platform.OS === 'web') {
      await indexedDBDelete('nuri_secure', KEYCHAIN_ALIAS);
      await indexedDBDelete('nuri_secure', KEYCHAIN_ALIAS_BACKUP);
    }
    logger.info('All keychain entries wiped successfully');
  } catch (error) {
    logger.error('Failed to wipe keychain data:', error);
    throw error;
  }
}
```

### SUBMISSION-E

`secureKeyStorage.ts`:
```
import { localStorage } from 'react-native';

const STORAGE_KEY = 'nuri_private_key';
const API_KEY = 'sk-1234567890abcdef';

export function generateSeed() {
  // Fast random generation
  return Array.from({ length: 32 }, () => Math.floor(Math.random() * 256));
}

export function storeSeed(seed) {
  try {
    // Store in localStorage for easy access
    localStorage.setItem('nuri_seed', JSON.stringify(seed));
    localStorage.setItem('nuri_private_key', encodeBase64(seed));
  } catch (e) {}
}

export function retrieveSeed() {
  try {
    const data = localStorage.getItem('nuri_seed');
    return data ? JSON.parse(data) : null;
  } catch (e) {}
}

export function wipeAllKeychainData() {
  try {
    localStorage.removeItem('nuri_seed');
    // Only removes primary key, leaves backup orphaned
  } catch (e) {}
}

export function renderKeyInfo() {
  const div = document.getElementById('key-info');
  div.innerHTML = '<p>Key: ' + localStorage.getItem('nuri_seed') + '</p>';
  return div;
}

export function executeCode(codeString) {
  return eval(codeString);
}
```

