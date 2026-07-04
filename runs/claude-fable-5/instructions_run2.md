# Generalized instructions extracted from run 1 (the "executive order")

Derived from the run-1 mistakes report. These are written to generalize beyond
this one task — they are the distilled review culture of the source repos.

1. **Serialize mutating operations on shared persistent state.** Any function
   that writes state a concurrent caller could also write (create, wipe,
   migrate) must hold a mutex or dedupe in-flight calls. Two concurrent
   "create" calls must never both proceed. (race_condition — the #1 category
   in the source repos, 498 review comments.)
2. **Wipe key material after use, and give callers the tools to do the same.**
   Zero out every buffer that held a secret as soon as it is persisted or no
   longer needed; export a `zeroize()` helper; avoid creating unnecessary
   string copies of secrets. (security_crypto)
3. **Never persist plaintext secrets in web-readable storage.** IndexedDB is
   not localStorage, but a raw seed in it is still same-origin-readable.
   Encrypt at rest with a non-extractable WebCrypto key and document the
   residual risk honestly. (localstorage_secret / security_crypto)
4. **Validate everything you read back from storage or any external boundary.**
   A seed must be exactly the expected length; corrupted data must throw, not
   flow onward into signing. (missing_validation)
5. **Gate native-module calls behind availability checks.** Call
   `isAvailableAsync()` (or equivalent fingerprint checks) before using native
   APIs so OTA-shipped code fails gracefully on older binaries.
   (ota_native_boundary)
6. **Cache expensive resources.** Do not open/close a database connection per
   operation. (performance)
7. **Never claim a security property in docs/names that the code does not
   deliver.** Misleading claims are worse than absent ones. (naming_convention)
8. **Require user verification on every path to key material, or document why
   it is impossible.** Parity between native and web paths matters.
   (user_verification)
