# Judicative Report — What Went Wrong

Rubric: `2.1.0` — mode: `static+external-judge` — score model: `global-penalty-v2`

## Leaderboard

| Rank | Agent | Score | Verdict | Penalty |
|---|---|---|---|---|
| 1 | glm-5.2-run1 | 0.0/100 | FAIL | -270.32 |

## glm-5.2-run1 — 0.0/100 (FAIL)

### What you did wrong

- **[critical] SEC-003 — No Math.random for crypto** at `README.md:7`
  - Matched: `Math.random(`
  - Why it matters: Math.random() is not cryptographically secure. Use crypto.getRandomValues(). Real reviews flagged this category 97× in the source repos.
- **[critical] SEC-003 — No Math.random for crypto** at `README.md:25`
  - Matched: `Math.random(`
  - Why it matters: Math.random() is not cryptographically secure. Use crypto.getRandomValues(). Real reviews flagged this category 97× in the source repos.
- **[critical] SEC-004 — No eval or Function constructor** at `README.md:27`
  - Matched: `eval(`
  - Why it matters: eval() and new Function() execute arbitrary strings as code. Real reviews flagged this category 97× in the source repos.
- **[critical] SEC-002 — No hardcoded secrets** at `src/secure-key-storage/secureKeyStorage.ts:512`
  - Matched: `seed:", err); throw new SecureStorageError("`
  - Why it matters: Hardcoded secrets, API keys, or operator details must never be committed. Real reviews flagged this category 97× in the source repos.
- **[critical] SEC-002 — No hardcoded secrets** at `src/secure-key-storage/secureKeyStorage.ts:523`
  - Matched: `seed:", err); throw new SecureStorageError("`
  - Why it matters: Hardcoded secrets, API keys, or operator details must never be committed. Real reviews flagged this category 97× in the source repos.
- **[judge score 0.2] SEC-010 — Missing zeroization of sensitive data**
  - Judge: Critical: Uint8Array from getRandomValues, the encrypted ciphertext, IV, and TextEncoder output are never zeroed after use. The seed hex string persists in memory. No explicit memory wiping (fill(0) o
  - Why it matters: Sensitive Uint8Array (seeds, keys, nonces) must be wiped after use. Leaving them in memory increases exposure window. Real reviews flagged this category 97× in the source repos.
- **[judge score 0.3] RACE-005 — Concurrent state mutation**
  - Judge: WebSecureStorageAdapter.getOrCreateEncryptionKey (line ~120) has a race: two concurrent calls can both see no master-key and both generate+store one. The IDB readwrite transaction doesn't prevent this
  - Why it matters: Multiple async operations writing to the same state without ordering guarantees. Use mutex, queue, or atomic updates to prevent interleaving. Real reviews flagged this category 498× in the source repos.
- **[judge score 0.4] ARCH-003 — Module structure**
  - Judge: secureKeyStorage.ts has multiple responsibilities: type definitions, platform detection, crypto helpers, web adapter, RN adapter, factory, and high-level API. Should be split into types.ts, platform.t
  - Why it matters: Files should have a single responsibility. Mixing unrelated functionality in one file makes the codebase harder to navigate. Real reviews flagged this category 185× in the source repos.
- **[judge score 0.5] STALE-002 — Cached data used after async gap**
  - Judge: In openDB(), the db reference returned is used after the Promise resolves, but another concurrent operation could close or delete the database (wipe() calls db.close() then indexedDB.deleteDatabase). 
  - Why it matters: Data fetched or computed before an await is used after the await without revalidation. The data may be stale if state changed during the async gap. Real reviews flagged this category 373× in the source repos.
- **[judge score 0.3] OTA-002 — Fingerprint compatibility check**
  - Judge: No binary fingerprint or version check before calling native APIs. The code assumes react-native-keychain or expo-secure-store is available without checking the native binary version. An OTA update co
  - Why it matters: Code must check the binary fingerprint before calling native APIs that may not exist in older versions. Real reviews flagged this category 96× in the source repos.
- **[judge score 0.3] DATA-005 — Deduplicate sync requests**
  - Judge: No deduplication of concurrent operations. Two concurrent setItem('wallet-seed', value1) and setItem('wallet-seed', value2) calls will race — the last one to complete wins, with no ordering guarantee.
  - Why it matters: Repeated sync requests must be deduplicated to prevent duplicate state writes. Real reviews flagged this category 70× in the source repos.
- **[judge score 0.5] ARCH-002 — Separation of concerns**
  - Judge: The main file mixes platform detection, crypto utilities, two storage adapters, factory, and high-level API all in one ~400-line file. Adapters and crypto utils should be separate modules.
  - Why it matters: Business logic mixed with UI rendering, or crypto operations in view components. Extract into hooks or services. Real reviews flagged this category 185× in the source repos.
- **[judge score 0.4] DATA-002 — No silent storage downgrade**
  - Judge: RN adapter silently falls back from react-native-keychain to expo-secure-store. This is a storage downgrade — expo-secure-store has different security properties (e.g., no keychain hardware backing on
  - Why it matters: Storage operations must not silently downgrade from persistent to volatile. Real reviews flagged this category 70× in the source repos.
- **[judge score 0.5] OTA-001 — Native module call in OTA-shippable code**
  - Judge: RN adapter calls require('react-native-keychain') which is a native module. If an OTA update ships JS that references a native module not in the current binary, it crashes. The try/catch fallback to e
  - Why it matters: OTA updates cannot change native modules. Code that calls native modules not present in the current binary must be gated or have fallbacks. Real reviews flagged this category 96× in the source repos.
- **[judge score 0.7] SEC-008 — No nonce reuse**
  - Judge: AES-GCM IV is generated via crypto.getRandomValues (12 bytes) which is cryptographically random, but there's no explicit uniqueness check before use. If the RNG produced a duplicate IV (astronomically
  - Why it matters: Cryptographic nonces must never be reused. In MuSig2, nonce reuse leaks private keys. Real reviews flagged this category 97× in the source repos.
- **[judge score 0.3] CATCH-001 — Silent catch (LLM check for context)**
  - Judge: getTrackedKeys() catch block (line ~330) returns [] instead of propagating — this swallows storage errors. RN adapter wipe() inner catch (line ~310) logs but doesn't propagate individual key wipe fail
  - Why it matters: Empty catch blocks that swallow errors. The static check is in error_handling/ERR-001. This LLM rule catches cases where the catch block has code but still swallows errors (e.g., catch but only logs, doesn't propagate). Real reviews flagged this category 55× in the source repos.
- **[judge score 0.2] VALID-002 — Per-item validation in arrays**
  - Judge: trackedKeys from JSON.parse(result.password) is not validated per-item. If the stored JSON is corrupted or contains non-string entries, the wipe() method will iterate invalid data. No schema validatio
  - Why it matters: Arrays from external sources must have per-item validation, not just type checks on the array itself. Real reviews flagged this category 47× in the source repos.
- **[judge score 0.3] VALID-001 — Runtime validation at external boundaries**
  - Judge: No validation of data returned from external sources. keychain.getGenericPassword() result is used without checking its shape — assumes it has a .password property. The expo-secure-store wrapper assum
  - Why it matters: Data from external sources (API responses, user input, IPC) must be validated at the boundary before use. Real reviews flagged this category 47× in the source repos.
- **[judge score 0.7] ERR-003 — Non-transient failure handling**
  - Judge: No distinction between transient and non-transient failures. A failed setItem due to invalid input (non-transient) is treated the same as a transient IndexedDB lock failure. Callers cannot distinguish
  - Why it matters: Non-transient failures (e.g., invalid input, permission denied) must not be retried indefinitely. Distinguish from transient failures (network timeout). Real reviews flagged this category 94× in the source repos.
- **[judge score 0.3] PERF-001 — Don't initialize expensive resources on every call**
  - Judge: openDB() is called on every setItem, getItem, and removeItem — each call opens a new IDBDatabase connection. The database connection should be cached/reused. getOrCreateEncryptionKey() also opens DB a
  - Why it matters: Expensive initializations should be cached or lazy-loaded. Real reviews flagged this category 36× in the source repos.
- **[judge score 0.3] CLEAN-001 — Complete keychain wipe**
  - Judge: RN adapter wipe() only removes tracked keys. If keys were stored by a previous version that didn't track them, or if the tracked_keys entry is corrupted/deleted, those orphaned keychain entries surviv
  - Why it matters: wipeAllKeychainData must remove ALL aliased entries, not just the primary key. Real reviews flagged this category 12× in the source repos.
- **[judge score 0.5] DEAD-001 — No dead code or unused imports**
  - Judge: MockAdapter class in test file is declared but never used in any test case. The SecureStorageAdapter import in the test file is only used as a type for MockAdapter.
  - Why it matters: Unused imports and dead code should be removed. Real reviews flagged this category 62× in the source repos.
- **[judge score 0.4] TYPE-001 — No unsafe type casts**
  - Judge: keychain: any in ReactNativeSecureStorageAdapter is an unsafe type. getRequest.result is untyped in the web adapter. The expo-secure-store shim object is untyped. No type guards on external data.
  - Why it matters: Avoid `as any` and unsafe type casts. Use proper type guards. Real reviews flagged this category 29× in the source repos.
- **[judge score 0.5] DOC-002 — Document complex logic**
  - Judge: AES-GCM encryption/decryption lacks inline comments explaining why 12-byte IV is used (NIST recommendation for GCM mode). The key derivation/storage strategy isn't documented. The singleton pattern in
  - Why it matters: Complex logic, crypto operations, and state machines need inline comments explaining the why. Real reviews flagged this category 50× in the source repos.
- **[judge score 0.5] CLEAN-002 — Sweep all items, not just first**
  - Judge: wipe() iterates all tracked keys, but relies on the tracked keys list being complete and accurate. If setItem was called but setTrackedKeys failed, the key exists in keychain but not in the tracked li
  - Why it matters: Sweep operations must process all items, not just the first match. Real reviews flagged this category 12× in the source repos.
- **[judge score 0.7] TYPE-002 — Correct enum usage**
  - Judge: Uses SecureStore.WHEN_UNLOCKED which is a valid expo-secure-store option, but doesn't verify the enum exists at runtime. If the expo-secure-store version doesn't export WHEN_UNLOCKED, it would be unde
  - Why it matters: Enum values must match the actual library API. Example: BIOMETRIC_STRONG doesn't exist in expo-local-authentication. Real reviews flagged this category 29× in the source repos.
- **[judge score 0.9] ERR-002 — Error propagation**
  - Judge: Errors are generally propagated via throw with SecureStorageError wrappers. Minor: getTrackedKeys() swallows errors and returns [] instead of propagating.
  - Why it matters: Errors from critical operations must be propagated to the caller or surfaced to the user, not swallowed. Real reviews flagged this category 94× in the source repos.
- **[judge score 0.9] DATA-004 — Make failed critical operations fatal**
  - Judge: Critical operations throw on failure. Minor: wipe() in RN adapter continues past individual key deletion failures (line ~310) — a failed wipe of a specific key is logged but not fatal.
  - Why it matters: Critical operations like IBAN moves must be fatal on failure. Real reviews flagged this category 70× in the source repos.
- **[judge score 0.8] STATE-002 — State synchronization**
  - Judge: cachedAdapter singleton could get out of sync with platform state. If resetSecureStorageAdapter() is called but a reference to the old adapter is held, operations on the old adapter could conflict wit
  - Why it matters: Multiple state sources (local state, context, server) must be synchronized to prevent inconsistent UI. Real reviews flagged this category 41× in the source repos.
- **[judge score 0.9] STYLE-001 — ESLint compliance**
  - Judge: Code is generally ESLint-clean; minor: `any` type for keychain in RN adapter would trigger @typescript-eslint/no-explicit-any.
  - Why it matters: Code should pass eslint with the project's configured ruleset. Real reviews flagged this category 125× in the source repos.
- **[judge score 0.9] NAME-001 — Clear naming**
  - Judge: Names are generally clear. Minor: keyNameForKey is a bit redundant; sanitizeKey would be clearer. loadKeychain does more than load — it also sets up fallbacks.
  - Why it matters: Names should be descriptive and not misleading. Real reviews flagged this category 36× in the source repos.
- **[judge score 0.9] API-001 — Implement required interfaces**
  - Judge: SecureStorageAdapter interface is properly implemented by both adapters. Minor: the expo-secure-store shim doesn't fully implement the keychain API surface (resetGenericPassword throws).
  - Why it matters: WebView shims must implement all required interfaces like injectedJavaScriptObject. Missing interfaces cause runtime crashes. Real reviews flagged this category 19× in the source repos.

### Instructions for your next run

Add these to the agent's system prompt / instructions and re-run the task:

- **No Math.random for crypto**: Math.random() is not cryptographically secure. Use crypto.getRandomValues().
- **No eval or Function constructor**: eval() and new Function() execute arbitrary strings as code.
- **No hardcoded secrets**: Hardcoded secrets, API keys, or operator details must never be committed.
- **Missing zeroization of sensitive data**: Sensitive Uint8Array (seeds, keys, nonces) must be wiped after use. Leaving them in memory increases exposure window.
- **Concurrent state mutation**: Multiple async operations writing to the same state without ordering guarantees. Use mutex, queue, or atomic updates to prevent interleaving.
- **Module structure**: Files should have a single responsibility. Mixing unrelated functionality in one file makes the codebase harder to navigate.
- **Cached data used after async gap**: Data fetched or computed before an await is used after the await without revalidation. The data may be stale if state changed during the async gap.
- **Fingerprint compatibility check**: Code must check the binary fingerprint before calling native APIs that may not exist in older versions.
- **Deduplicate sync requests**: Repeated sync requests must be deduplicated to prevent duplicate state writes.
- **Separation of concerns**: Business logic mixed with UI rendering, or crypto operations in view components. Extract into hooks or services.
- **No silent storage downgrade**: Storage operations must not silently downgrade from persistent to volatile.
- **Native module call in OTA-shippable code**: OTA updates cannot change native modules. Code that calls native modules not present in the current binary must be gated or have fallbacks.
- **No nonce reuse**: Cryptographic nonces must never be reused. In MuSig2, nonce reuse leaks private keys.
- **Silent catch (LLM check for context)**: Empty catch blocks that swallow errors. The static check is in error_handling/ERR-001. This LLM rule catches cases where the catch block has code but still swallows errors (e.g., catch but only logs, doesn't propagate).
- **Per-item validation in arrays**: Arrays from external sources must have per-item validation, not just type checks on the array itself.
- **Runtime validation at external boundaries**: Data from external sources (API responses, user input, IPC) must be validated at the boundary before use.
- **Non-transient failure handling**: Non-transient failures (e.g., invalid input, permission denied) must not be retried indefinitely. Distinguish from transient failures (network timeout).
- **Don't initialize expensive resources on every call**: Expensive initializations should be cached or lazy-loaded.
- **Complete keychain wipe**: wipeAllKeychainData must remove ALL aliased entries, not just the primary key.
- **No dead code or unused imports**: Unused imports and dead code should be removed.
- **No unsafe type casts**: Avoid `as any` and unsafe type casts. Use proper type guards.
- **Document complex logic**: Complex logic, crypto operations, and state machines need inline comments explaining the why.
- **Sweep all items, not just first**: Sweep operations must process all items, not just the first match.
- **Correct enum usage**: Enum values must match the actual library API. Example: BIOMETRIC_STRONG doesn't exist in expo-local-authentication.
- **Error propagation**: Errors from critical operations must be propagated to the caller or surfaced to the user, not swallowed.
- **Make failed critical operations fatal**: Critical operations like IBAN moves must be fatal on failure.
- **State synchronization**: Multiple state sources (local state, context, server) must be synchronized to prevent inconsistent UI.
- **ESLint compliance**: Code should pass eslint with the project's configured ruleset.
- **Clear naming**: Names should be descriptive and not misleading.
- **Implement required interfaces**: WebView shims must implement all required interfaces like injectedJavaScriptObject. Missing interfaces cause runtime crashes.

## What did others do wrong (across all submissions)

| Rule | Category | Violations | Severity |
|---|---|---|---|
| SEC-003 — No Math.random for crypto | security_crypto | 2 | critical |
| SEC-002 — No hardcoded secrets | security_crypto | 2 | critical |
| RACE-005 — Concurrent state mutation | race_condition | 1 | critical |
| STALE-002 — Cached data used after async gap | stale_state | 1 | major |
| ARCH-002 — Separation of concerns | architecture | 1 | minor |
| ARCH-003 — Module structure | architecture | 1 | minor |
| SEC-004 — No eval or Function constructor | security_crypto | 1 | critical |
| SEC-010 — Missing zeroization of sensitive data | security_crypto | 1 | major |
| OTA-001 — Native module call in OTA-shippable code | ota_native_boundary | 1 | critical |
| OTA-002 — Fingerprint compatibility check | ota_native_boundary | 1 | major |
| DATA-002 — No silent storage downgrade | data_integrity | 1 | major |
| DATA-005 — Deduplicate sync requests | data_integrity | 1 | major |
| DEAD-001 — No dead code or unused imports | dead_code | 1 | minor |
| CATCH-001 — Silent catch (LLM check for context) | silent_catch | 1 | major |
| DOC-002 — Document complex logic | documentation | 1 | minor |
| VALID-001 — Runtime validation at external boundaries | missing_validation | 1 | major |
| VALID-002 — Per-item validation in arrays | missing_validation | 1 | major |
| PERF-001 — Don't initialize expensive resources on every call | performance | 1 | major |
| TYPE-001 — No unsafe type casts | type_safety | 1 | minor |
| CLEAN-001 — Complete keychain wipe | incomplete_cleanup | 1 | major |
| CLEAN-002 — Sweep all items, not just first | incomplete_cleanup | 1 | major |

## Context: what real reviewers flag in the source repos

| Category | Review comments | Share |
|---|---|---|
| race_condition | 498 | 12.5% |
| stale_state | 373 | 9.4% |
| ui_component | 187 | 4.7% |
| architecture | 185 | 4.7% |
| code_style | 125 | 3.1% |
| security_crypto | 97 | 2.4% |
| ota_native_boundary | 96 | 2.4% |
| error_handling | 94 | 2.4% |
| data_integrity | 70 | 1.8% |
| timeout_retry | 65 | 1.6% |

