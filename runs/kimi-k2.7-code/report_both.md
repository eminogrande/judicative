# Judicative Report — What Went Wrong

Rubric: `2.1.0` — mode: `static+external-judge` — score model: `global-penalty-v2`

## Leaderboard

| Rank | Agent | Score | Verdict | Penalty |
|---|---|---|---|---|
| 1 | kimi-k2.7-code-run2 | 86.41/100 | PASS | -13.59 |
| 2 | kimi-k2.7-code-run1 | 56.38/100 | FAIL | -43.62 |

## kimi-k2.7-code-run2 — 86.41/100 (PASS)

### What you did wrong

- **[judge score 0.8] SEC-010 — Missing zeroization of sensitive data**
  - Judge: zeroize() is used on Uint8Arrays, but immutable JS strings (base64) and Array.from copies cannot be zeroized; residual exposure remains.
  - Why it matters: Sensitive Uint8Array (seeds, keys, nonces) must be wiped after use. Leaving them in memory increases exposure window. Real reviews flagged this category 97× in the source repos.
- **[judge score 0.6] UV-001 — User verification on passkey operations**
  - Judge: Native path uses requireAuthentication. Web path has no UV gate because the web platform lacks one for IndexedDB; documented honestly.
  - Why it matters: Passkey signing operations must require user verification (UV). Missing UV allows signing without biometric/PIN. Real reviews flagged this category 20× in the source repos.
- **[judge score 0.9] RACE-005 — Concurrent state mutation**
  - Judge: All mutating ops run under withLock and create is deduped via dedupeOp. Residual: loadSeed does not dedupe concurrent reads with the same key, and in-flight load vs wipe can still serialize correctly 
  - Why it matters: Multiple async operations writing to the same state without ordering guarantees. Use mutex, queue, or atomic updates to prevent interleaving. Real reviews flagged this category 498× in the source repos.
- **[judge score 0.9] ARCH-002 — Separation of concerns**
  - Judge: Clean backend split; remaining coupling is the Platform.OS inline branch. Could be abstracted into a pluggable backend interface.
  - Why it matters: Business logic mixed with UI rendering, or crypto operations in view components. Extract into hooks or services. Real reviews flagged this category 185× in the source repos.
- **[judge score 0.9] ARCH-003 — Module structure**
  - Judge: Still a single file with public API, two backends, mutex, crypto, validation; acceptable but could be split into smaller modules.
  - Why it matters: Files should have a single responsibility. Mixing unrelated functionality in one file makes the codebase harder to navigate. Real reviews flagged this category 185× in the source repos.
- **[judge score 0.9] OTA-001 — Native module call in OTA-shippable code**
  - Judge: SecureStore is statically imported but every native call is gated by assertNativeAvailable(). The import still assumes the module exists in the bundle.
  - Why it matters: OTA updates cannot change native modules. Code that calls native modules not present in the current binary must be gated or have fallbacks. Real reviews flagged this category 96× in the source repos.
- **[judge score 0.9] OTA-002 — Fingerprint compatibility check**
  - Judge: isAvailableAsync() checked before every native operation; import-time assumption remains.
  - Why it matters: Code must check the binary fingerprint before calling native APIs that may not exist in older versions. Real reviews flagged this category 96× in the source repos.
- **[judge score 0.9] ERR-003 — Non-transient failure handling**
  - Judge: No retry/backoff for storage failures; arguably correct because local keychain failures are generally not transient.
  - Why it matters: Non-transient failures (e.g., invalid input, permission denied) must not be retried indefinitely. Distinguish from transient failures (network timeout). Real reviews flagged this category 94× in the source repos.
- **[judge score 0.9] DATA-005 — Deduplicate sync requests**
  - Judge: createAndStoreSeed is deduped by key; loadSeed and wipe are serialized by lock but not deduped.
  - Why it matters: Repeated sync requests must be deduplicated to prevent duplicate state writes. Real reviews flagged this category 70× in the source repos.
- **[judge score 0.9] DOC-002 — Document complex logic**
  - Judge: Security model documented in header; added inline comment explaining cleanup catch. Could add more about why web cannot provide UV.
  - Why it matters: Complex logic, crypto operations, and state machines need inline comments explaining the why. Real reviews flagged this category 50× in the source repos.
- **[judge score 0.9] TYPE-001 — No unsafe type casts**
  - Judge: Uses Partial cast after structural check; acceptable. The encryptSeed/decryptSeed helpers expose crypto surface not required by the task.
  - Why it matters: Avoid `as any` and unsafe type casts. Use proper type guards. Real reviews flagged this category 29× in the source repos.
- **[judge score 0.9] VALID-001 — Runtime validation at external boundaries**
  - Judge: Asserts seed length and validates web record shape, including ciphertext size. Slight nit: does not validate that iv values are bytes 0-255.
  - Why it matters: Data from external sources (API responses, user input, IPC) must be validated at the boundary before use. Real reviews flagged this category 47× in the source repos.
- **[judge score 0.9] PERF-001 — Don't initialize expensive resources on every call**
  - Judge: DB connection cached via dbPromise and transactions reused per operation; still opens a new transaction per call, but connection is not closed each time.
  - Why it matters: Expensive initializations should be cached or lazy-loaded. Real reviews flagged this category 36× in the source repos.

### Instructions for your next run

Add these to the agent's system prompt / instructions and re-run the task:

- **Missing zeroization of sensitive data**: Sensitive Uint8Array (seeds, keys, nonces) must be wiped after use. Leaving them in memory increases exposure window.
- **User verification on passkey operations**: Passkey signing operations must require user verification (UV). Missing UV allows signing without biometric/PIN.
- **Concurrent state mutation**: Multiple async operations writing to the same state without ordering guarantees. Use mutex, queue, or atomic updates to prevent interleaving.
- **Separation of concerns**: Business logic mixed with UI rendering, or crypto operations in view components. Extract into hooks or services.
- **Module structure**: Files should have a single responsibility. Mixing unrelated functionality in one file makes the codebase harder to navigate.
- **Native module call in OTA-shippable code**: OTA updates cannot change native modules. Code that calls native modules not present in the current binary must be gated or have fallbacks.
- **Fingerprint compatibility check**: Code must check the binary fingerprint before calling native APIs that may not exist in older versions.
- **Non-transient failure handling**: Non-transient failures (e.g., invalid input, permission denied) must not be retried indefinitely. Distinguish from transient failures (network timeout).
- **Deduplicate sync requests**: Repeated sync requests must be deduplicated to prevent duplicate state writes.
- **Document complex logic**: Complex logic, crypto operations, and state machines need inline comments explaining the why.
- **No unsafe type casts**: Avoid `as any` and unsafe type casts. Use proper type guards.
- **Runtime validation at external boundaries**: Data from external sources (API responses, user input, IPC) must be validated at the boundary before use.
- **Don't initialize expensive resources on every call**: Expensive initializations should be cached or lazy-loaded.

## kimi-k2.7-code-run1 — 56.38/100 (FAIL)

### What you did wrong

- **[major] ERR-001 — No silent catch blocks** at `lib/secureKeyStorage.ts:278`
  - Matched: `catch (_) { }`
  - Why it matters: Empty catch blocks swallow errors silently. At minimum, log the error. Real reviews flagged this category 94× in the source repos.
- **[judge score 0.6] RACE-005 — Concurrent state mutation**
  - Judge: Uses withLock and inFlightCreate dedup, but inFlightCreate is not itself guarded by the lock during assignment; two rapid calls could both see null and each create a separate Promise that the lock sti
  - Why it matters: Multiple async operations writing to the same state without ordering guarantees. Use mutex, queue, or atomic updates to prevent interleaving. Real reviews flagged this category 498× in the source repos.
- **[judge score 0.7] SEC-010 — Missing zeroization of sensitive data**
  - Judge: Provides zeroize() and clears many Uint8Arrays, but the native base64 string copy and intermediate Array.from ciphertext/iv arrays cannot be zeroized; JS strings are immutable. Residual exposure remai
  - Why it matters: Sensitive Uint8Array (seeds, keys, nonces) must be wiped after use. Leaving them in memory increases exposure window. Real reviews flagged this category 97× in the source repos.
- **[judge score 0.3] CATCH-001 — Silent catch (LLM check for context)**
  - Judge: catch (_) { // ignore nested cleanup errors } on line ~273 is a silent catch block; it swallows a real cleanup failure with only a comment. Static rule ERR-001 already caught it, and this LLM rule con
  - Why it matters: Empty catch blocks that swallow errors. The static check is in error_handling/ERR-001. This LLM rule catches cases where the catch block has code but still swallows errors (e.g., catch but only logs, doesn't propagate). Real reviews flagged this category 55× in the source repos.
- **[judge score 0.7] DATA-005 — Deduplicate sync requests**
  - Judge: inFlightCreate dedups concurrent create calls, but loadSeed, wipeAllKeychainData and other operations are not deduped; concurrent load+wipe could race.
  - Why it matters: Repeated sync requests must be deduplicated to prevent duplicate state writes. Real reviews flagged this category 70× in the source repos.
- **[judge score 0.8] ARCH-003 — Module structure**
  - Judge: Single file does many things: public API, native backend, web backend, mutex, base64 helpers, validation. Could be split into smaller modules.
  - Why it matters: Files should have a single responsibility. Mixing unrelated functionality in one file makes the codebase harder to navigate. Real reviews flagged this category 185× in the source repos.
- **[judge score 0.8] ERR-003 — Non-transient failure handling**
  - Judge: Failures are thrown to caller; no retry/backoff for transient storage failures, but arguably storage failures are not transient.
  - Why it matters: Non-transient failures (e.g., invalid input, permission denied) must not be retried indefinitely. Distinguish from transient failures (network timeout). Real reviews flagged this category 94× in the source repos.
- **[judge score 0.6] UV-001 — User verification on passkey operations**
  - Judge: Native path uses requireAuthentication: true. Web path has no user-verification gate because the web platform offers none for IndexedDB; documented honestly but still means any same-origin code can in
  - Why it matters: Passkey signing operations must require user verification (UV). Missing UV allows signing without biometric/PIN. Real reviews flagged this category 20× in the source repos.
- **[judge score 0.9] ARCH-002 — Separation of concerns**
  - Judge: Clean separation between web and native backends; only minor quibble is web/native branches are selected by Platform.OS inline rather than via a pluggable backend interface.
  - Why it matters: Business logic mixed with UI rendering, or crypto operations in view components. Extract into hooks or services. Real reviews flagged this category 185× in the source repos.
- **[judge score 0.9] OTA-001 — Native module call in OTA-shippable code**
  - Judge: SecureStore is statically imported and asserted via isAvailableAsync() before use, but the static import still assumes the module is present in the bundle. Good but not perfect for OTA boundaries.
  - Why it matters: OTA updates cannot change native modules. Code that calls native modules not present in the current binary must be gated or have fallbacks. Real reviews flagged this category 96× in the source repos.
- **[judge score 0.9] OTA-002 — Fingerprint compatibility check**
  - Judge: Calls SecureStore.isAvailableAsync() before every native operation; still relies on the module being present at import time.
  - Why it matters: Code must check the binary fingerprint before calling native APIs that may not exist in older versions. Real reviews flagged this category 96× in the source repos.
- **[judge score 0.9] ERR-002 — Error propagation**
  - Judge: Errors are wrapped and re-thrown as KeyStorageError; callers receive them. Could include structured error codes for programmatic handling.
  - Why it matters: Errors from critical operations must be propagated to the caller or surfaced to the user, not swallowed. Real reviews flagged this category 94× in the source repos.
- **[judge score 0.9] DATA-004 — Make failed critical operations fatal**
  - Judge: createAndStoreSeed throws on failure and wipes partial state, which is correct. Minor: nested cleanup error is swallowed with catch (_).
  - Why it matters: Critical operations like IBAN moves must be fatal on failure. Real reviews flagged this category 70× in the source repos.
- **[judge score 0.9] STYLE-001 — ESLint compliance**
  - Judge: Likely eslint-clean, but uses catch (_) which many linters flag.
  - Why it matters: Code should pass eslint with the project's configured ruleset. Real reviews flagged this category 125× in the source repos.
- **[judge score 0.8] DOC-002 — Document complex logic**
  - Judge: Crypto and security model are documented in the header, but the failure-path cleanup reasoning could use an inline comment at the silent catch.
  - Why it matters: Complex logic, crypto operations, and state machines need inline comments explaining the why. Real reviews flagged this category 50× in the source repos.
- **[judge score 0.9] VALID-001 — Runtime validation at external boundaries**
  - Judge: Asserts seed length on decode and validates web record shape; good. Minor: ciphertext array length check only ensures >=16, not tied to expected plaintext size.
  - Why it matters: Data from external sources (API responses, user input, IPC) must be validated at the boundary before use. Real reviews flagged this category 47× in the source repos.
- **[judge score 0.9] PERF-001 — Don't initialize expensive resources on every call**
  - Judge: IndexedDB connection is cached via dbPromise, but every operation still opens a new transaction and closes the db in finally. This re-opens/closes the connection each time despite caching.
  - Why it matters: Expensive initializations should be cached or lazy-loaded. Real reviews flagged this category 36× in the source repos.
- **[judge score 0.9] TYPE-001 — No unsafe type casts**
  - Judge: assertPlatform checks typeof Platform.OS but uses any for cause; minor. The Partial<WebSeedRecord> cast in validateWebRecord is a deliberate conservative cast after structural checks.
  - Why it matters: Avoid `as any` and unsafe type casts. Use proper type guards. Real reviews flagged this category 29× in the source repos.
- **[judge score 0.9] API-001 — Implement required interfaces**
  - Judge: Required functions (generateSeed, createAndStoreSeed, loadSeed, wipeAllKeychainData, zeroize) are exported; missing a formal interface type but matches task.
  - Why it matters: WebView shims must implement all required interfaces like injectedJavaScriptObject. Missing interfaces cause runtime crashes. Real reviews flagged this category 19× in the source repos.

### Instructions for your next run

Add these to the agent's system prompt / instructions and re-run the task:

- **No silent catch blocks**: Empty catch blocks swallow errors silently. At minimum, log the error.
- **Concurrent state mutation**: Multiple async operations writing to the same state without ordering guarantees. Use mutex, queue, or atomic updates to prevent interleaving.
- **Missing zeroization of sensitive data**: Sensitive Uint8Array (seeds, keys, nonces) must be wiped after use. Leaving them in memory increases exposure window.
- **Silent catch (LLM check for context)**: Empty catch blocks that swallow errors. The static check is in error_handling/ERR-001. This LLM rule catches cases where the catch block has code but still swallows errors (e.g., catch but only logs, doesn't propagate).
- **Deduplicate sync requests**: Repeated sync requests must be deduplicated to prevent duplicate state writes.
- **Module structure**: Files should have a single responsibility. Mixing unrelated functionality in one file makes the codebase harder to navigate.
- **Non-transient failure handling**: Non-transient failures (e.g., invalid input, permission denied) must not be retried indefinitely. Distinguish from transient failures (network timeout).
- **User verification on passkey operations**: Passkey signing operations must require user verification (UV). Missing UV allows signing without biometric/PIN.
- **Separation of concerns**: Business logic mixed with UI rendering, or crypto operations in view components. Extract into hooks or services.
- **Native module call in OTA-shippable code**: OTA updates cannot change native modules. Code that calls native modules not present in the current binary must be gated or have fallbacks.
- **Fingerprint compatibility check**: Code must check the binary fingerprint before calling native APIs that may not exist in older versions.
- **Error propagation**: Errors from critical operations must be propagated to the caller or surfaced to the user, not swallowed.
- **Make failed critical operations fatal**: Critical operations like IBAN moves must be fatal on failure.
- **ESLint compliance**: Code should pass eslint with the project's configured ruleset.
- **Document complex logic**: Complex logic, crypto operations, and state machines need inline comments explaining the why.
- **Runtime validation at external boundaries**: Data from external sources (API responses, user input, IPC) must be validated at the boundary before use.
- **Don't initialize expensive resources on every call**: Expensive initializations should be cached or lazy-loaded.
- **No unsafe type casts**: Avoid `as any` and unsafe type casts. Use proper type guards.
- **Implement required interfaces**: WebView shims must implement all required interfaces like injectedJavaScriptObject. Missing interfaces cause runtime crashes.

## What did others do wrong (across all submissions)

| Rule | Category | Violations | Severity |
|---|---|---|---|
| UV-001 — User verification on passkey operations | user_verification | 2 | major |
| RACE-005 — Concurrent state mutation | race_condition | 1 | critical |
| ERR-001 — No silent catch blocks | error_handling | 1 | major |
| CATCH-001 — Silent catch (LLM check for context) | silent_catch | 1 | major |

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

