/**
 * factory.ts - Adapter factory and high-level convenience API.
 */

import { SecureStorageError } from "./types";
import { generateSecureSeed } from "./crypto-utils";
import { isReactNative, isWeb } from "./platform";
import type { SecureStorageAdapter } from "./types";

// Lazy imports to avoid circular dependencies
let cachedAdapter: SecureStorageAdapter | null = null;

/**
 * Get the platform-appropriate secure storage adapter (singleton).
 * The same instance is reused across all calls within the app lifecycle.
 *
 * @throws SecureStorageError if the platform is unsupported or the
 *   adapter is not available.
 */
export async function getSecureStorageAdapter(): Promise<SecureStorageAdapter> {
  if (cachedAdapter) return cachedAdapter;

  if (isReactNative()) {
    const { ReactNativeSecureStorageAdapter } = await import("./rn-adapter");
    cachedAdapter = new ReactNativeSecureStorageAdapter();
  } else if (isWeb()) {
    const { WebSecureStorageAdapter } = await import("./web-adapter");
    cachedAdapter = WebSecureStorageAdapter.getInstance();
  } else {
    throw new SecureStorageError("Unsupported platform");
  }

  return cachedAdapter;
}

/** Reset the cached adapter (useful for testing). */
export function resetSecureStorageAdapter(): void {
  cachedAdapter = null;
}

/**
 * Generate a cryptographically secure seed and store it.
 * @param byteLength - Number of random bytes (default: 32 = 256 bits)
 * @param storageKey - Key name for storage (default: "wallet-seed")
 * @returns The hex-encoded seed string
 */
export async function generateAndStoreSeed(
  byteLength: number = 32,
  storageKey: string = "wallet-seed"
): Promise<string> {
  try {
    const seed = generateSecureSeed(byteLength);
    const adapter = await getSecureStorageAdapter();
    await adapter.setItem(storageKey, seed);
    return seed;
  } catch (err) {
    if (err instanceof SecureStorageError) throw err;
    console.error("[factory] generateAndStoreSeed failed:", err);
    throw new SecureStorageError("Failed to generate and store seed", err);
  }
}

/** Retrieve the stored wallet seed. Returns null if not stored. */
export async function getStoredSeed(storageKey: string = "wallet-seed"): Promise<string | null> {
  try {
    const adapter = await getSecureStorageAdapter();
    return await adapter.getItem(storageKey);
  } catch (err) {
    if (err instanceof SecureStorageError) throw err;
    console.error("[factory] getStoredSeed failed:", err);
    throw new SecureStorageError("Failed to retrieve stored seed", err);
  }
}

/** Wipe ALL secure storage entries. */
export async function wipeSecureStorage(): Promise<void> {
  try {
    const adapter = await getSecureStorageAdapter();
    await adapter.wipe();
  } catch (err) {
    if (err instanceof SecureStorageError) throw err;
    console.error("[factory] wipeSecureStorage failed:", err);
    throw new SecureStorageError("Failed to wipe secure storage", err);
  }
}

/** Remove a specific key from secure storage. */
export async function removeSecureKey(key: string): Promise<void> {
  try {
    const adapter = await getSecureStorageAdapter();
    await adapter.removeItem(key);
  } catch (err) {
    if (err instanceof SecureStorageError) throw err;
    console.error("[factory] removeSecureKey failed:", err);
    throw new SecureStorageError("Failed to remove key", err);
  }
}
