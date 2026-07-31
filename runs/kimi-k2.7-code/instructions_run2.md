# Instructions for run 2

Extracted from the mistakes report for `kimi-k2.7-code-run1`. These instructions are generalized, not task-specific:

- **No silent catch blocks**: Empty catch blocks swallow errors silently. At minimum, log the error. If the catch is intentionally ignoring a secondary cleanup failure, add an inline comment and log it so the failure is visible.
- **Concurrent state mutation**: Guard assignment of in-flight promises; otherwise two callers can both see `null` and start duplicate operations. Use a keyed dedupe map plus a mutex for all mutating storage operations.
- **Deduplicate sync requests**: Apply deduplication not only to creation but to any concurrent operation that touches the same alias / state, and clean up the in-flight entry exactly once.
- **Native module call in OTA-shippable code**: Runtime availability checks (`isAvailableAsync`) are necessary but not sufficient; document the import-time assumption and fail gracefully if the module is missing.
- **Fingerprint compatibility check**: Call availability APIs before every native operation; pair with error codes so callers know the platform is unsupported.
- **Missing zeroization of sensitive data**: Wipe every Uint8Array after use. Do not rely on zeroizing immutable types (strings, base64, Array.from copies); document that residual exposure.
- **User verification on passkey operations**: Require `requireAuthentication` on native keychain reads/writes. State honestly when the web platform cannot provide a user-verification gate for storage.
- **Runtime validation at external boundaries**: Validate decoded seed length and persisted record shape at every load boundary; reject corrupted data instead of passing it downstream.
- **Don't initialize expensive resources on every call**: Cache the IndexedDB connection across transactions; do not open/close the database on every operation.
- **Module structure / separation of concerns**: Keep backend implementations isolated from the public API; use a pluggable backend interface instead of inline `Platform.OS` branches where feasible.
- **Document complex logic**: Explain why the cleanup catch logs rather than throws, and why web storage cannot offer user verification.
