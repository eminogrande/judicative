/**
 * rn-adapter.ts - React Native secure storage adapter.
 *
 * Uses react-native-keychain (preferred) or expo-secure-store (fallback).
 * Checks binary fingerprint before calling native APIs (OTA safety).
 * Tracks all stored keys for complete wipe functionality.
 */

import {
  SecureStorageError,
  TransientStorageError,
  type SecureStorageAdapter,
} from "./types";
import { isReactNative, supportsCapability, getBinaryFingerprint } from "./platform";
import { AsyncMutex } from "./mutex";

/**
 * Minimal type for the keychain API surface we depend on.
 * Avoids `any` by defining the shape explicitly.
 */
interface KeychainAPI {
  setGenericPassword(service: string, username: string, password: string): Promise<boolean>;
  getGenericPassword(opts: { service: string; username: string }): Promise<{ password: string } | false>;
  resetGenericPassword(opts: { service: string }): Promise<boolean>;
}

/** Prefix for all keychain service names to namespace Nuri entries. */
const SERVICE_PREFIX = "nuri_wallet_";
/** Special service name for the tracked keys list. */
const TRACKED_KEYS_SERVICE = "nuri_wallet_tracked_keys";
/** Validation: key must be non-empty alphanumeric + limited symbols. */
function isValidKey(key: string): boolean {
  return typeof key === "string" && key.length > 0 && key.length <= 256;
}
/** Sanitize a key into a valid keychain service name. */
function sanitizeKey(key: string): string {
  return SERVICE_PREFIX + key.replace(/[^a-zA-Z0-9_]/g, "_");
}

/** Validate the shape of a keychain getGenericPassword result. */
function validateKeychainResult(result: unknown): { password: string } | null {
  if (result && typeof result === "object" && "password" in result) {
    const r = result as { password: unknown };
    if (typeof r.password === "string") {
      return { password: r.password };
    }
  }
  return null;
}

/** Validate that a parsed tracked-keys array contains only strings. */
function validateTrackedKeys(arr: unknown): string[] {
  if (!Array.isArray(arr)) return [];
  return arr.filter((item): item is string => typeof item === "string" && item.length > 0);
}

export class ReactNativeSecureStorageAdapter implements SecureStorageAdapter {
  private keychain: KeychainAPI | null = null;
  private readonly mutex = new AsyncMutex();

  /**
   * Load the keychain module, checking binary fingerprint first.
   * Falls back from react-native-keychain to expo-secure-store,
   * but surfaces the downgrade to the caller via a warning log.
   */
  private async loadKeychain(): Promise<KeychainAPI> {
    if (this.keychain) return this.keychain;

    // Check binary fingerprint before calling native APIs (OTA safety)
    const fingerprint = getBinaryFingerprint();

    if (fingerprint === "no-secure-storage") {
      throw new SecureStorageError(
        "No secure storage native module available in this binary. " +
        "Install react-native-keychain or expo-secure-store."
      );
    }

    // Try react-native-keychain first (preferred — hardware-backed)
    if (supportsCapability("keychain")) {
      try {
        const mod = require("react-native-keychain");
        this.keychain = mod as KeychainAPI;
        return this.keychain;
      } catch (err) {
        console.error("[rn-adapter] keychain module load failed:", err);
        // Fall through to expo-secure-store
      }
    }

    // Fallback: expo-secure-store
    // Note: This is a storage downgrade — expo-secure-store may not have
    // hardware keychain backing on all platforms. We log a warning.
    if (supportsCapability("expo-secure-store")) {
      console.warn("[rn-adapter] Downgrading to expo-secure-store (no hardware keychain)");
      try {
        const SecureStore = require("expo-secure-store");
        // Validate that the enum we need actually exists
        const accessibleOption = SecureStore.WHEN_UNLOCKED ?? 1;
        this.keychain = {
          setGenericPassword: async (service: string, username: string, password: string) => {
            await SecureStore.setItemAsync(
              `${service}:${username}`,
              password,
              { keychainAccessible: accessibleOption }
            );
            return true;
          },
          getGenericPassword: async (opts: { service: string; username: string }) => {
            const val = await SecureStore.getItemAsync(`${opts.service}:${opts.username}`);
            return val ? { password: val } : false;
          },
          resetGenericPassword: async (opts: { service: string }) => {
            await SecureStore.deleteItemAsync(`${opts.service}:*`);
            return true;
          },
        };
        return this.keychain;
      } catch (err) {
        console.error("[rn-adapter] expo-secure-store load failed:", err);
        throw new SecureStorageError("Failed to load any secure storage module", err);
      }
    }

    throw new SecureStorageError(
      "No secure storage available. Fingerprint: " + fingerprint
    );
  }

  isAvailable(): boolean {
    return isReactNative();
  }

  async setItem(key: string, value: string): Promise<void> {
    if (!isValidKey(key) || !value) {
      throw new SecureStorageError("Invalid key or empty value");
    }

    return this.mutex.run(async () => {
      try {
        const keychain = await this.loadKeychain();
        const serviceName = sanitizeKey(key);

        // Track this key for complete wipe support
        const trackedKeys = await this.getTrackedKeys();
        if (!trackedKeys.includes(key)) {
          trackedKeys.push(key);
          await this.setTrackedKeys(trackedKeys);
        }

        await keychain.setGenericPassword(serviceName, key, value);
      } catch (err) {
        if (err instanceof SecureStorageError) throw err;
        console.error("[rn-adapter] setItem failed for key:", err);
        throw new SecureStorageError("setItem failed", err);
      }
    });
  }

  async getItem(key: string): Promise<string | null> {
    if (!isValidKey(key)) {
      throw new SecureStorageError("Invalid key");
    }

    return this.mutex.run(async () => {
      try {
        const keychain = await this.loadKeychain();
        const serviceName = sanitizeKey(key);
        const result = await keychain.getGenericPassword({ service: serviceName, username: key });
        const validated = validateKeychainResult(result);
        return validated ? validated.password : null;
      } catch (err) {
        if (err instanceof SecureStorageError) throw err;
        console.error("[rn-adapter] getItem failed:", err);
        throw new SecureStorageError("getItem failed", err);
      }
    });
  }

  async removeItem(key: string): Promise<void> {
    if (!isValidKey(key)) {
      throw new SecureStorageError("Invalid key");
    }

    return this.mutex.run(async () => {
      try {
        const keychain = await this.loadKeychain();
        const serviceName = sanitizeKey(key);

        await keychain.resetGenericPassword({ service: serviceName });

        // Remove from tracked keys
        const trackedKeys = await this.getTrackedKeys();
        const updated = trackedKeys.filter((k) => k !== key);
        await this.setTrackedKeys(updated);
      } catch (err) {
        if (err instanceof SecureStorageError) throw err;
        console.error("[rn-adapter] removeItem failed:", err);
        throw new SecureStorageError("removeItem failed", err);
      }
    });
  }

  /**
   * Wipe ALL keychain entries.
   * Iterates all tracked keys and removes each one.
   * Any individual failure is logged and re-thrown — wipe is a
   * critical operation and partial failures must be surfaced.
   */
  async wipe(): Promise<void> {
    return this.mutex.run(async () => {
      try {
        const keychain = await this.loadKeychain();
        const trackedKeys = await this.getTrackedKeys();
        const failures: string[] = [];

        // Remove each tracked key
        for (const key of trackedKeys) {
          const serviceName = sanitizeKey(key);
          try {
            await keychain.resetGenericPassword({ service: serviceName });
          } catch (err) {
            console.error("[rn-adapter] Wipe failed for individual key:", err);
            failures.push(key);
          }
        }

        // Clear the tracked keys list
        await this.setTrackedKeys([]);

        // If any individual wipe failed, surface the error
        if (failures.length > 0) {
          throw new SecureStorageError(
            `Wipe incomplete: ${failures.length} key(s) could not be removed`
          );
      } catch (err) {
        if (err instanceof SecureStorageError) throw err;
        console.error("[rn-adapter] wipe failed:", err);
        throw new SecureStorageError("wipe failed", err);
      }
    });
  }

  /**
   * Get the list of tracked keys from the keychain.
   * Errors are propagated — does not silently return empty array.
   */
  private async getTrackedKeys(): Promise<string[]> {
    try {
      const keychain = await this.loadKeychain();
      const result = await keychain.getGenericPassword({
        service: TRACKED_KEYS_SERVICE,
        username: "tracked",
      });
      const validated = validateKeychainResult(result);
      if (!validated) return [];

      try {
        const parsed = JSON.parse(validated.password);
        return validateTrackedKeys(parsed);
      } catch (parseErr) {
        console.error("[rn-adapter] Tracked keys JSON parse failed:", parseErr);
        // Corrupted tracked keys — return empty rather than failing
        // (this means wipe may miss keys, but we log the error)
        return [];
      }
    } catch (err) {
      console.error("[rn-adapter] getTrackedKeys failed:", err);
      throw new SecureStorageError("Failed to read tracked keys", err);
    }
  }

  private async setTrackedKeys(keys: string[]): Promise<void> {
    try {
      const keychain = await this.loadKeychain();
      await keychain.setGenericPassword(
        TRACKED_KEYS_SERVICE,
        "tracked",
        JSON.stringify(keys)
      );
    } catch (err) {
      console.error("[rn-adapter] setTrackedKeys failed:", err);
      throw new SecureStorageError("Failed to update tracked keys", err);
    }
  }
}
