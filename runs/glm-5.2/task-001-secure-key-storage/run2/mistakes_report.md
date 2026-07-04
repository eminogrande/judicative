# Judicative Report — What Went Wrong

Rubric: `2.1.0` — mode: `static+external-judge` — score model: `global-penalty-v2`

## Leaderboard

| Rank | Agent | Score | Verdict | Penalty |
|---|---|---|---|---|
| 1 | glm-5.2-run2 | 76.4/100 | PASS | -23.6 |

## glm-5.2-run2 — 76.4/100 (PASS)

### What you did wrong

- **[judge score 0.8] SEC-010 — Missing zeroization of sensitive data**
  - Judge: zeroize() is now called on sensitive arrays: raw seed bytes after hex conversion, encoded plaintext after encrypt, decrypted buffer after decode, IV after encrypt failure, raw key bytes after storing.
  - Why it matters: Sensitive Uint8Array (seeds, keys, nonces) must be wiped after use. Leaving them in memory increases exposure window. Real reviews flagged this category 97× in the source repos.
- **[judge score 0.8] DATA-002 — No silent storage downgrade**
  - Judge: Storage downgrade from react-native-keychain to expo-secure-store is now logged via console.warn (visible to developer). The caller can detect this via getBinaryFingerprint(). Minor: the downgrade is 
  - Why it matters: Storage operations must not silently downgrade from persistent to volatile. Real reviews flagged this category 70× in the source repos.
- **[judge score 0.9] STALE-002 — Cached data used after async gap**
  - Judge: DB connection is now cached and checked for staleness. onversionchange handler closes and nullifies the connection. The mutex ensures no stale db reference is used concurrently. Minor: the cached cryp
  - Why it matters: Data fetched or computed before an await is used after the await without revalidation. The data may be stale if state changed during the async gap. Real reviews flagged this category 373× in the source repos.
- **[judge score 0.9] SEC-008 — No nonce reuse**
  - Judge: IV is generated fresh for each encrypt call via generateIV() using crypto.getRandomValues. 12-byte IV per NIST SP 800-38D. No reuse possible since each encryption generates a new random IV. Minor: no 
  - Why it matters: Cryptographic nonces must never be reused. In MuSig2, nonce reuse leaks private keys. Real reviews flagged this category 97× in the source repos.
- **[judge score 0.8] OTA-001 — Native module call in OTA-shippable code**
  - Judge: Binary fingerprint check added via getBinaryFingerprint() and supportsCapability(). Native module calls are gated behind these checks. The try/catch fallback still exists but is now guarded. Minor: th
  - Why it matters: OTA updates cannot change native modules. Code that calls native modules not present in the current binary must be gated or have fallbacks. Real reviews flagged this category 96× in the source repos.
- **[judge score 0.8] OTA-002 — Fingerprint compatibility check**
  - Judge: getBinaryFingerprint() probes for native module availability before use. supportsCapability() is used to check before loading keychain. Minor: fingerprint is a string comparison, not a semantic versio
  - Why it matters: Code must check the binary fingerprint before calling native APIs that may not exist in older versions. Real reviews flagged this category 96× in the source repos.
- **[judge score 0.8] ERR-003 — Non-transient failure handling**
  - Judge: TransientStorageError class added for transient failures (IndexedDB lock contention). Callers can check `instanceof TransientStorageError` to decide retry. Non-transient errors use SecureStorageError.
  - Why it matters: Non-transient failures (e.g., invalid input, permission denied) must not be retried indefinitely. Distinguish from transient failures (network timeout). Real reviews flagged this category 94× in the source repos.
- **[judge score 0.9] ARCH-002 — Separation of concerns**
  - Judge: Good separation: types, platform detection, crypto utils, mutex, web adapter, RN adapter, factory, and index are all separate files. Each has a single responsibility. Minor: factory.ts still contains 
  - Why it matters: Business logic mixed with UI rendering, or crypto operations in view components. Extract into hooks or services. Real reviews flagged this category 185× in the source repos.
- **[judge score 0.9] ARCH-003 — Module structure**
  - Judge: Files now have single responsibilities: types.ts (types), crypto-utils.ts (crypto), platform.ts (detection), mutex.ts (concurrency), web-adapter.ts (web storage), rn-adapter.ts (RN storage), factory.t
  - Why it matters: Files should have a single responsibility. Mixing unrelated functionality in one file makes the codebase harder to navigate. Real reviews flagged this category 185× in the source repos.
- **[judge score 0.8] CATCH-001 — Silent catch (LLM check for context)**
  - Judge: getTrackedKeys now throws on keychain errors instead of returning []. The JSON.parse catch still returns [] for corrupted data (soft failure, logged). RN wipe inner catch logs and collects failures fo
  - Why it matters: Empty catch blocks that swallow errors. The static check is in error_handling/ERR-001. This LLM rule catches cases where the catch block has code but still swallows errors (e.g., catch but only logs, doesn't propagate). Real reviews flagged this category 55× in the source repos.
- **[judge score 0.9] DATA-005 — Deduplicate sync requests**
  - Judge: AsyncMutex serializes all operations per adapter. Concurrent setItem calls are queued and executed in order. No duplicate state writes. Minor: mutex is per-adapter-instance, not global — if two adapte
  - Why it matters: Repeated sync requests must be deduplicated to prevent duplicate state writes. Real reviews flagged this category 70× in the source repos.
- **[judge score 0.9] RACE-005 — Concurrent state mutation**
  - Judge: AsyncMutex now serializes all operations per adapter. Web adapter mutex serializes setItem/getItem/removeItem/wipe. RN adapter has its own mutex. Minor: if both adapters were used simultaneously (shou
  - Why it matters: Multiple async operations writing to the same state without ordering guarantees. Use mutex, queue, or atomic updates to prevent interleaving. Real reviews flagged this category 498× in the source repos.
- **[judge score 0.8] CLEAN-001 — Complete keychain wipe**
  - Judge: RN wipe iterates all tracked keys. If tracked keys list is intact, all entries are removed. Failures are collected and re-thrown. Minor: orphaned keys from a previous version (before tracking was adde
  - Why it matters: wipeAllKeychainData must remove ALL aliased entries, not just the primary key. Real reviews flagged this category 12× in the source repos.
- **[judge score 0.8] VALID-001 — Runtime validation at external boundaries**
  - Judge: validateKeychainResult() checks the shape of keychain results. validateTrackedKeys() validates parsed JSON. isValidKey() validates input keys. getItem result is checked before use. Minor: IndexedDB ge
  - Why it matters: Data from external sources (API responses, user input, IPC) must be validated at the boundary before use. Real reviews flagged this category 47× in the source repos.
- **[judge score 0.8] VALID-002 — Per-item validation in arrays**
  - Judge: validateTrackedKeys() filters parsed array to only string items with length > 0. Each item is individually validated. Minor: no maximum length check on individual key strings.
  - Why it matters: Arrays from external sources must have per-item validation, not just type checks on the array itself. Real reviews flagged this category 47× in the source repos.
- **[judge score 0.8] DOC-002 — Document complex logic**
  - Judge: Inline comments added: NIST SP 800-38D IV explanation, zeroization rationale, key storage strategy, mutex purpose. File-level JSDoc on all modules. Minor: factory.ts high-level functions could use mor
  - Why it matters: Complex logic, crypto operations, and state machines need inline comments explaining the why. Real reviews flagged this category 50× in the source repos.
- **[judge score 0.8] TYPE-001 — No unsafe type casts**
  - Judge: No `any` types. KeychainAPI interface replaces the previous `any`. Type assertions are guarded by runtime checks (validateKeychainResult, validateTrackedKeys). Minor: `as` casts in validation function
  - Why it matters: Avoid `as any` and unsafe type casts. Use proper type guards. Real reviews flagged this category 29× in the source repos.
- **[judge score 0.8] CLEAN-002 — Sweep all items, not just first**
  - Judge: Wipe processes all tracked keys, not just the first. If setTrackedKeys fails after setItem succeeds, the key exists but isn't tracked — it survives wipe. However, setItem is wrapped in mutex and setTr
  - Why it matters: Sweep operations must process all items, not just the first match. Real reviews flagged this category 12× in the source repos.
- **[judge score 0.9] ERR-002 — Error propagation**
  - Judge: All errors propagated via throw. getTrackedKeys now throws SecureStorageError instead of returning []. Wipe failures in RN adapter are collected and re-thrown. Minor: JSON.parse failure in getTrackedK
  - Why it matters: Errors from critical operations must be propagated to the caller or surfaced to the user, not swallowed. Real reviews flagged this category 94× in the source repos.
- **[judge score 0.9] DATA-004 — Make failed critical operations fatal**
  - Judge: Wipe is now critical: RN adapter collects failures and throws if any key couldn't be removed. Web adapter clears both stores and deletes the database. Minor: web adapter resolves (not rejects) on DB d
  - Why it matters: Critical operations like IBAN moves must be fatal on failure. Real reviews flagged this category 70× in the source repos.
- **[judge score 0.9] STATE-002 — State synchronization**
  - Judge: cachedAdapter singleton with resetSecureStorageAdapter for clean reset. DB connection cached with onversionchange handler. CryptoKey cached. Mutex ensures consistent state. Minor: if reset is called w
  - Why it matters: Multiple state sources (local state, context, server) must be synchronized to prevent inconsistent UI. Real reviews flagged this category 41× in the source repos.
- **[judge score 0.9] STYLE-001 — ESLint compliance**
  - Judge: No `any` types — KeychainAPI interface replaces `any`. All types are explicit. Minor: the `as` casts in validateKeychainResult are type assertions, but they're guarded by runtime checks.
  - Why it matters: Code should pass eslint with the project's configured ruleset. Real reviews flagged this category 125× in the source repos.
- **[judge score 0.9] PERF-001 — Don't initialize expensive resources on every call**
  - Judge: DB connection is now cached in this.db. CryptoKey is cached in this.cryptoKey. openDB() only opens once. Keychain module is cached in this.keychain. Minor: first call still pays the initialization cos
  - Why it matters: Expensive initializations should be cached or lazy-loaded. Real reviews flagged this category 36× in the source repos.
- **[judge score 0.9] TYPE-002 — Correct enum usage**
  - Judge: SecureStore.WHEN_UNLOCKED is now checked with `?? 1` fallback in case the enum doesn't exist in the installed version. Fallback value 1 is the standard iOS keychain accessible constant.
  - Why it matters: Enum values must match the actual library API. Example: BIOMETRIC_STRONG doesn't exist in expo-local-authentication. Real reviews flagged this category 29× in the source repos.
- **[judge score 0.9] NAME-001 — Clear naming**
  - Judge: Clear names: zeroize, generateSecureSeed, generateIV, sanitizeKey, validateKeychainResult, validateTrackedKeys, supportsCapability. All descriptive and accurate.
  - Why it matters: Names should be descriptive and not misleading. Real reviews flagged this category 36× in the source repos.
- **[judge score 0.9] API-001 — Implement required interfaces**
  - Judge: SecureStorageAdapter interface fully implemented by both adapters. KeychainAPI interface properly defined. expo-secure-store shim now implements all three methods. Minor: expo shim's resetGenericPassw
  - Why it matters: WebView shims must implement all required interfaces like injectedJavaScriptObject. Missing interfaces cause runtime crashes. Real reviews flagged this category 19× in the source repos.

### Instructions for your next run

Add these to the agent's system prompt / instructions and re-run the task:

- **Missing zeroization of sensitive data**: Sensitive Uint8Array (seeds, keys, nonces) must be wiped after use. Leaving them in memory increases exposure window.
- **No silent storage downgrade**: Storage operations must not silently downgrade from persistent to volatile.
- **Cached data used after async gap**: Data fetched or computed before an await is used after the await without revalidation. The data may be stale if state changed during the async gap.
- **No nonce reuse**: Cryptographic nonces must never be reused. In MuSig2, nonce reuse leaks private keys.
- **Native module call in OTA-shippable code**: OTA updates cannot change native modules. Code that calls native modules not present in the current binary must be gated or have fallbacks.
- **Fingerprint compatibility check**: Code must check the binary fingerprint before calling native APIs that may not exist in older versions.
- **Non-transient failure handling**: Non-transient failures (e.g., invalid input, permission denied) must not be retried indefinitely. Distinguish from transient failures (network timeout).
- **Separation of concerns**: Business logic mixed with UI rendering, or crypto operations in view components. Extract into hooks or services.
- **Module structure**: Files should have a single responsibility. Mixing unrelated functionality in one file makes the codebase harder to navigate.
- **Silent catch (LLM check for context)**: Empty catch blocks that swallow errors. The static check is in error_handling/ERR-001. This LLM rule catches cases where the catch block has code but still swallows errors (e.g., catch but only logs, doesn't propagate).
- **Deduplicate sync requests**: Repeated sync requests must be deduplicated to prevent duplicate state writes.
- **Concurrent state mutation**: Multiple async operations writing to the same state without ordering guarantees. Use mutex, queue, or atomic updates to prevent interleaving.
- **Complete keychain wipe**: wipeAllKeychainData must remove ALL aliased entries, not just the primary key.
- **Runtime validation at external boundaries**: Data from external sources (API responses, user input, IPC) must be validated at the boundary before use.
- **Per-item validation in arrays**: Arrays from external sources must have per-item validation, not just type checks on the array itself.
- **Document complex logic**: Complex logic, crypto operations, and state machines need inline comments explaining the why.
- **No unsafe type casts**: Avoid `as any` and unsafe type casts. Use proper type guards.
- **Sweep all items, not just first**: Sweep operations must process all items, not just the first match.
- **Error propagation**: Errors from critical operations must be propagated to the caller or surfaced to the user, not swallowed.
- **Make failed critical operations fatal**: Critical operations like IBAN moves must be fatal on failure.
- **State synchronization**: Multiple state sources (local state, context, server) must be synchronized to prevent inconsistent UI.
- **ESLint compliance**: Code should pass eslint with the project's configured ruleset.
- **Don't initialize expensive resources on every call**: Expensive initializations should be cached or lazy-loaded.
- **Correct enum usage**: Enum values must match the actual library API. Example: BIOMETRIC_STRONG doesn't exist in expo-local-authentication.
- **Clear naming**: Names should be descriptive and not misleading.
- **Implement required interfaces**: WebView shims must implement all required interfaces like injectedJavaScriptObject. Missing interfaces cause runtime crashes.

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

