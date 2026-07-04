# Judicative Report — What Went Wrong

Rubric: `2.1.0` — mode: `static+external-judge` — score model: `global-penalty-v2`

## Leaderboard

| Rank | Agent | Score | Verdict | Penalty |
|---|---|---|---|---|
| 1 | run2 | 89.55/100 | PASS | -10.45 |
| 2 | run1 | 46.36/100 | FAIL | -53.64 |

## run2 — 89.55/100 (PASS)

### What you did wrong

- **[judge score 0.7] SEC-010 — Missing zeroization of sensitive data**
  - Judge: IMPROVED, NOT PERFECT: zeroize() exported, failed-create path wipes the seed, caller ownership documented. Residual: the native base64 string copy cannot be zeroized (JS strings are immutable) and the
  - Why it matters: Sensitive Uint8Array (seeds, keys, nonces) must be wiped after use. Leaving them in memory increases exposure window. Real reviews flagged this category 97× in the source repos.
- **[judge score 0.6] UV-001 — User verification on passkey operations**
  - Judge: PLATFORM LIMIT: native path requires user verification; the web platform has no UV primitive for IndexedDB access. Documented honestly with CSP guidance. A WebAuthn-gated unlock flow could raise this 
  - Why it matters: Passkey signing operations must require user verification (UV). Missing UV allows signing without biometric/PIN. Real reviews flagged this category 20× in the source repos.
- **[judge score 0.9] OTA-001 — Native module call in OTA-shippable code**
  - Judge: IMPROVED: assertNativeAvailable() gates every native call and fails with a user-facing error. Residual: the static import itself assumes the JS module exists in the bundle.
  - Why it matters: OTA updates cannot change native modules. Code that calls native modules not present in the current binary must be gated or have fallbacks. Real reviews flagged this category 96× in the source repos.
- **[judge score 0.9] OTA-002 — Fingerprint compatibility check**
  - Judge: IMPROVED: isAvailableAsync() checked before every native operation.
  - Why it matters: Code must check the binary fingerprint before calling native APIs that may not exist in older versions. Real reviews flagged this category 96× in the source repos.
- **[judge score 0.8] LS-001 — No private keys in localStorage (duplicate hard gate)**
  - Judge: IMPROVED: only AES-GCM ciphertext is persisted on web; the wrapping key is non-extractable. Residual: a same-origin attacker can still invoke decryption while the page is compromised — inherent to the
  - Why it matters: Duplicate of SEC-001 — kept as LLM rule to avoid double-penalizing with the same regex. The static check is in security_crypto/SEC-001. This LLM rule catches cases the regex misses (e.g., indirect localStorage access via wrapper functions). Real reviews flagged this category 2× in the source repos.
- **[judge score 0.9] VALID-001 — Runtime validation at external boundaries**
  - Judge: IMPROVED: assertSeedShape() enforces 32 bytes on every load; malformed IDB entries throw. Residual: ciphertext field type is not deeply validated before decrypt (decrypt failure would throw anyway).
  - Why it matters: Data from external sources (API responses, user input, IPC) must be validated at the boundary before use. Real reviews flagged this category 47× in the source repos.

### Instructions for your next run

Add these to the agent's system prompt / instructions and re-run the task:

- **Missing zeroization of sensitive data**: Sensitive Uint8Array (seeds, keys, nonces) must be wiped after use. Leaving them in memory increases exposure window.
- **User verification on passkey operations**: Passkey signing operations must require user verification (UV). Missing UV allows signing without biometric/PIN.
- **Native module call in OTA-shippable code**: OTA updates cannot change native modules. Code that calls native modules not present in the current binary must be gated or have fallbacks.
- **Fingerprint compatibility check**: Code must check the binary fingerprint before calling native APIs that may not exist in older versions.
- **No private keys in localStorage (duplicate hard gate)**: Duplicate of SEC-001 — kept as LLM rule to avoid double-penalizing with the same regex. The static check is in security_crypto/SEC-001. This LLM rule catches cases the regex misses (e.g., indirect localStorage access via wrapper functions).
- **Runtime validation at external boundaries**: Data from external sources (API responses, user input, IPC) must be validated at the boundary before use.

## run1 — 46.36/100 (FAIL)

### What you did wrong

- **[judge score 0.3] SEC-010 — Missing zeroization of sensitive data**
  - Judge: REAL ISSUE: no zeroization anywhere. The seed Uint8Array is returned and never wiped; toBase64 creates additional string copies of key material that linger in memory. No zeroize() helper is offered to
  - Why it matters: Sensitive Uint8Array (seeds, keys, nonces) must be wiped after use. Leaving them in memory increases exposure window. Real reviews flagged this category 97× in the source repos.
- **[judge score 0.4] RACE-005 — Concurrent state mutation**
  - Judge: REAL ISSUE: createAndStoreSeed() has no mutex/in-flight guard. Two concurrent calls generate two different seeds; both write to the same alias and each caller believes its returned seed is the stored 
  - Why it matters: Multiple async operations writing to the same state without ordering guarantees. Use mutex, queue, or atomic updates to prevent interleaving. Real reviews flagged this category 498× in the source repos.
- **[judge score 0.5] DATA-005 — Deduplicate sync requests**
  - Judge: REAL ISSUE: no dedup of concurrent storage operations; same root cause as RACE-005. Two concurrent createAndStoreSeed calls both proceed.
  - Why it matters: Repeated sync requests must be deduplicated to prevent duplicate state writes. Real reviews flagged this category 70× in the source repos.
- **[judge score 0.7] OTA-002 — Fingerprint compatibility check**
  - Judge: No fingerprint/availability check (SecureStore.isAvailableAsync) before native calls.
  - Why it matters: Code must check the binary fingerprint before calling native APIs that may not exist in older versions. Real reviews flagged this category 96× in the source repos.
- **[judge score 0.4] VALID-001 — Runtime validation at external boundaries**
  - Judge: REAL ISSUE: loadSeed()/fromBase64() never validates that the decoded seed is exactly 32 bytes. A corrupted or tampered store entry yields a garbage seed that flows into signing.
  - Why it matters: Data from external sources (API responses, user input, IPC) must be validated at the boundary before use. Real reviews flagged this category 47× in the source repos.
- **[judge score 0.8] OTA-001 — Native module call in OTA-shippable code**
  - Judge: expo-secure-store is imported unconditionally and called without checking availability. If an OTA update ships this to a binary without the module, it crashes at call time instead of failing gracefull
  - Why it matters: OTA updates cannot change native modules. Code that calls native modules not present in the current binary must be gated or have fallbacks. Real reviews flagged this category 96× in the source repos.
- **[judge score 0.5] UV-001 — User verification on passkey operations**
  - Judge: REAL ISSUE: native path requires user verification (requireAuthentication: true) but the web path has none — any code with origin access can read the seed from IndexedDB without any user presence chec
  - Why it matters: Passkey signing operations must require user verification (UV). Missing UV allows signing without biometric/PIN. Real reviews flagged this category 20× in the source repos.
- **[judge score 0.5] LS-001 — No private keys in localStorage (duplicate hard gate)**
  - Judge: REAL CONCERN: not localStorage, but the web path persists the RAW seed (base64) in IndexedDB — plaintext at rest, extractable by any same-origin script. The spirit of this rule (web-accessible plainte
  - Why it matters: Duplicate of SEC-001 — kept as LLM rule to avoid double-penalizing with the same regex. The static check is in security_crypto/SEC-001. This LLM rule catches cases the regex misses (e.g., indirect localStorage access via wrapper functions). Real reviews flagged this category 2× in the source repos.
- **[judge score 0.6] NAME-001 — Clear naming**
  - Judge: REAL ISSUE: the module docstring claims 'IndexedDB-backed non-extractable storage on web' but the implementation stores a plain base64 seed — fully extractable. Misleading documentation of a security 
  - Why it matters: Names should be descriptive and not misleading. Real reviews flagged this category 36× in the source repos.
- **[judge score 0.7] PERF-001 — Don't initialize expensive resources on every call**
  - Judge: openDb() opens and closes the IndexedDB connection on EVERY operation instead of caching it.
  - Why it matters: Expensive initializations should be cached or lazy-loaded. Real reviews flagged this category 36× in the source repos.
- **[judge score 0.9] DOC-002 — Document complex logic**
  - Judge: Crypto and wipe semantics documented, but the web storage security model (what an XSS attacker can reach) is not documented.
  - Why it matters: Complex logic, crypto operations, and state machines need inline comments explaining the why. Real reviews flagged this category 50× in the source repos.

### Instructions for your next run

Add these to the agent's system prompt / instructions and re-run the task:

- **Missing zeroization of sensitive data**: Sensitive Uint8Array (seeds, keys, nonces) must be wiped after use. Leaving them in memory increases exposure window.
- **Concurrent state mutation**: Multiple async operations writing to the same state without ordering guarantees. Use mutex, queue, or atomic updates to prevent interleaving.
- **Deduplicate sync requests**: Repeated sync requests must be deduplicated to prevent duplicate state writes.
- **Fingerprint compatibility check**: Code must check the binary fingerprint before calling native APIs that may not exist in older versions.
- **Runtime validation at external boundaries**: Data from external sources (API responses, user input, IPC) must be validated at the boundary before use.
- **Native module call in OTA-shippable code**: OTA updates cannot change native modules. Code that calls native modules not present in the current binary must be gated or have fallbacks.
- **User verification on passkey operations**: Passkey signing operations must require user verification (UV). Missing UV allows signing without biometric/PIN.
- **No private keys in localStorage (duplicate hard gate)**: Duplicate of SEC-001 — kept as LLM rule to avoid double-penalizing with the same regex. The static check is in security_crypto/SEC-001. This LLM rule catches cases the regex misses (e.g., indirect localStorage access via wrapper functions).
- **Clear naming**: Names should be descriptive and not misleading.
- **Don't initialize expensive resources on every call**: Expensive initializations should be cached or lazy-loaded.
- **Document complex logic**: Complex logic, crypto operations, and state machines need inline comments explaining the why.

## What did others do wrong (across all submissions)

| Rule | Category | Violations | Severity |
|---|---|---|---|
| UV-001 — User verification on passkey operations | user_verification | 2 | major |
| RACE-005 — Concurrent state mutation | race_condition | 1 | critical |
| SEC-010 — Missing zeroization of sensitive data | security_crypto | 1 | major |
| DATA-005 — Deduplicate sync requests | data_integrity | 1 | major |
| VALID-001 — Runtime validation at external boundaries | missing_validation | 1 | major |
| NAME-001 — Clear naming | naming_convention | 1 | minor |
| LS-001 — No private keys in localStorage (duplicate hard gate) | localstorage_secret | 1 | critical |

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

