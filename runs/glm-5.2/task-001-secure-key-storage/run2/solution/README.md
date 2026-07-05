# Secure Key Storage Module

A secure key storage module for the Nuri wallet. Works in both React Native and PWA (web) contexts.

## Features

- Cryptographically secure seed generation using Web Crypto API
- Platform keychain storage on native (react-native-keychain or expo-secure-store)
- AES-GCM encrypted IndexedDB storage on web
- Full wipe support: removes all entries and encryption keys
- Graceful error handling: all errors logged and surfaced to the caller
- Cross-platform: single API for React Native and PWA
- Memory zeroization for sensitive data after use
- Async mutex prevents concurrent write races
- Binary fingerprint checking for OTA safety

## Security

- Uses only cryptographically secure PRNG (crypto.getRandomValues)
- Never stores secrets in browser localStorage
- Never executes dynamic code via the Function constructor
- All catch blocks log errors, never swallow them silently
- Encryption keys are non-extractable where supported
- Sensitive Uint8Array buffers are zeroized after use

## File Structure

- `types.ts` - Shared type definitions and error classes
- `platform.ts` - Platform detection and binary fingerprint checking
- `crypto-utils.ts` - Cryptographic utilities (seed generation, zeroization)
- `mutex.ts` - Async mutex for serializing concurrent operations
- `web-adapter.ts` - IndexedDB + AES-GCM adapter for PWA
- `rn-adapter.ts` - React Native keychain adapter
- `factory.ts` - Adapter factory and high-level convenience API
- `index.ts` - Public API exports

## Usage

```typescript
import { generateAndStoreSeed, getStoredSeed, wipeSecureStorage } from "./secure-key-storage";

// Generate and store a new 32-byte seed
const seed = await generateAndStoreSeed();

// Retrieve the stored seed
const stored = await getStoredSeed();

// Wipe all secure storage
await wipeSecureStorage();
```

## Error Handling

All errors are thrown as `SecureStorageError` with the original cause preserved.
Transient errors (e.g., IndexedDB lock contention) use `TransientStorageError`
so callers can distinguish retryable from non-retryable failures.
