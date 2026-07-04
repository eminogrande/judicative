# Secure Key Storage Module

A secure key storage module for the Nuri wallet that works in both React Native and PWA (web) contexts.

## Features

- **Cryptographically secure seed generation** using `crypto.getRandomValues()` (never `Math.random()`)
- **Platform keychain storage** - uses `react-native-keychain` on native, IndexedDB + AES-GCM encryption on web
- **Full wipe support** - removes all keychain entries and encryption keys
- **Graceful error handling** - all errors are logged and surfaced to the caller, never swallowed
- **Cross-platform** - single API for both React Native and PWA

## Usage

```typescript
import { generateAndStoreSeed, getStoredSeed, wipeSecureStorage } from "./secure-key-storage";

const seed = await generateAndStoreSeed();
const stored = await getStoredSeed();
await wipeSecureStorage();
```

## Security

- Never uses `Math.random()`
- Never stores secrets in `localStorage`
- Never uses `eval()` or `innerHTML`
- All catch blocks log errors to `console.error`, never swallow them silently
