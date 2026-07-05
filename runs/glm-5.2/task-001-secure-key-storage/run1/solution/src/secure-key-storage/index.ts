/**
 * Public API for the secure key storage module.
 */

export {
  generateSecureSeed,
  generateAndStoreSeed,
  getStoredSeed,
  wipeSecureStorage,
  removeSecureKey,
  getSecureStorageAdapter,
  resetSecureStorageAdapter,
} from "./secureKeyStorage";

export type { SecureStorageAdapter } from "./secureKeyStorage";
export { SecureStorageError } from "./secureKeyStorage";
