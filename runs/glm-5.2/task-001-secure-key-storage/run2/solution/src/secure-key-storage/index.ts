/**
 * index.ts - Public API for the secure key storage module.
 *
 * This module provides cross-platform (React Native + PWA) secure storage
 * for the Nuri wallet's signing keys, using platform keychain on native
 * and IndexedDB + AES-GCM encryption on web.
 */

export { generateSecureSeed, bytesToHex, generateIV, zeroize } from "./crypto-utils";
export { getSecureStorageAdapter, resetSecureStorageAdapter,
         generateAndStoreSeed, getStoredSeed, wipeSecureStorage, removeSecureKey } from "./factory";
export type { SecureStorageAdapter } from "./types";
export { SecureStorageError, TransientStorageError } from "./types";
export { isReactNative, isWeb, getBinaryFingerprint, supportsCapability } from "./platform";
export { WebSecureStorageAdapter } from "./web-adapter";
export { ReactNativeSecureStorageAdapter } from "./rn-adapter";
export { AsyncMutex } from "./mutex";
