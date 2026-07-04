/**
 * secureKeyStorage.ts
 * 
 * Secure key storage module for the Nuri wallet.
 * Works in both React Native and PWA (web) contexts.
 * 
 * Security principles:
 * - Never uses Math.random() for key generation
 * - Never stores secrets in localStorage
 * - Never uses eval() or innerHTML
 * - All catch blocks log errors, never swallow them silently
 * - Uses platform keychain / secure storage
 */

// ==================== Types ====================

export interface SecureStorageAdapter {
  setItem(key: string, value: string): Promise<void>;
  getItem(key: string): Promise<string | null>;
  removeItem(key: string): Promise<void>;
  wipe(): Promise<void>;
  isAvailable(): boolean;
}

export class SecureStorageError extends Error {
  constructor(message: string, public readonly cause?: unknown) {
    super(message);
    this.name = "SecureStorageError";
  }
}

// ==================== Platform Detection ====================

function isReactNative(): boolean {
  return typeof navigator !== "undefined" && navigator.product === "ReactNative";
}

function isWeb(): boolean {
  return typeof window !== "undefined" && typeof document !== "undefined";
}

// ==================== Web Crypto (shared) ====================

export function generateSecureSeed(byteLength: number = 32): string {
  if (byteLength <= 0) {
    throw new SecureStorageError("byteLength must be positive");
  }

  if (typeof crypto !== "undefined" && crypto.getRandomValues) {
    const arr = new Uint8Array(byteLength);
    crypto.getRandomValues(arr);
    return bytesToHex(arr);
  }

  if (typeof require !== "undefined") {
    try {
      const nodeCrypto = require("crypto");
      return nodeCrypto.randomBytes(byteLength).toString("hex");
    } catch (err) {
      console.error("[secureKeyStorage] Failed to generate secure seed via node crypto:", err);
      throw new SecureStorageError("No secure random source available", err);
    }
  }

  throw new SecureStorageError("No secure random source available on this platform");
}

function bytesToHex(bytes: Uint8Array): string {
  const hex: string[] = [];
  for (let i = 0; i < bytes.length; i++) {
    hex.push(bytes[i].toString(16).padStart(2, "0"));
  }
  return hex.join("");
}

// ==================== Web / PWA Adapter ====================

class WebSecureStorageAdapter implements SecureStorageAdapter {
  private dbName = "nuri-secure-storage";
  private storeName = "secure-entries";
  private keyStoreName = "encryption-keys";
  private dbVersion = 1;
  private static instance: WebSecureStorageAdapter | null = null;

  static getInstance(): WebSecureStorageAdapter {
    if (!WebSecureStorageAdapter.instance) {
      WebSecureStorageAdapter.instance = new WebSecureStorageAdapter();
    }
    return WebSecureStorageAdapter.instance;
  }

  isAvailable(): boolean {
    return isWeb() && typeof indexedDB !== "undefined" && typeof crypto !== "undefined" && !!crypto.subtle;
  }

  private openDB(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(this.dbName, this.dbVersion);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(this.storeName)) {
          db.createObjectStore(this.storeName);
        }
        if (!db.objectStoreNames.contains(this.keyStoreName)) {
          db.createObjectStore(this.keyStoreName);
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => {
        console.error("[secureKeyStorage] IndexedDB open failed:", request.error);
        reject(new SecureStorageError("Failed to open secure storage database", request.error));
      };
    });
  }

  private async getOrCreateEncryptionKey(): Promise<CryptoKey> {
    const db = await this.openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(this.keyStoreName, "readwrite");
      const store = tx.objectStore(this.keyStoreName);
      const getRequest = store.get("master-key");

      getRequest.onsuccess = async () => {
        if (getRequest.result) {
          try {
            const key = await crypto.subtle.importKey(
              "raw",
              getRequest.result,
              { name: "AES-GCM", length: 256 },
              false,
              ["encrypt", "decrypt"]
            );
            resolve(key);
          } catch (err) {
            console.error("[secureKeyStorage] Failed to import encryption key:", err);
            reject(new SecureStorageError("Failed to import encryption key", err));
          }
        } else {
          try {
            const key = await crypto.subtle.generateKey(
              { name: "AES-GCM", length: 256 },
              false,
              ["encrypt", "decrypt"]
            );
            const rawKey = await crypto.subtle.exportKey("raw", key);
            store.put(new Uint8Array(rawKey), "master-key");
            resolve(key);
          } catch (err) {
            console.error("[secureKeyStorage] Failed to generate encryption key:", err);
            reject(new SecureStorageError("Failed to generate encryption key", err));
          }
        }
      };

      getRequest.onerror = () => {
        console.error("[secureKeyStorage] Failed to retrieve encryption key:", getRequest.error);
        reject(new SecureStorageError("Failed to retrieve encryption key", getRequest.error));
      };
    });
  }

  private async encrypt(value: string): Promise<{ ciphertext: Uint8Array; iv: Uint8Array }> {
    const key = await this.getOrCreateEncryptionKey();
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const encoded = new TextEncoder().encode(value);

    try {
      const ciphertext = await crypto.subtle.encrypt(
        { name: "AES-GCM", iv },
        key,
        encoded
      );
      return { ciphertext: new Uint8Array(ciphertext), iv };
    } catch (err) {
      console.error("[secureKeyStorage] Encryption failed:", err);
      throw new SecureStorageError("Failed to encrypt value", err);
    }
  }

  private async decrypt(ciphertext: Uint8Array, iv: Uint8Array): Promise<string> {
    const key = await this.getOrCreateEncryptionKey();
    try {
      const decrypted = await crypto.subtle.decrypt(
        { name: "AES-GCM", iv },
        key,
        ciphertext
      );
      return new TextDecoder().decode(decrypted);
    } catch (err) {
      console.error("[secureKeyStorage] Decryption failed:", err);
      throw new SecureStorageError("Failed to decrypt value", err);
    }
  }

  async setItem(key: string, value: string): Promise<void> {
    if (!key || !value) {
      throw new SecureStorageError("Key and value must be non-empty");
    }

    try {
      const { ciphertext, iv } = await this.encrypt(value);
      const db = await this.openDB();
      await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(this.storeName, "readwrite");
        const store = tx.objectStore(this.storeName);
        const payload = { ciphertext, iv };
        const putRequest = store.put(payload, key);

        putRequest.onsuccess = () => resolve();
        putRequest.onerror = () => {
          console.error("[secureKeyStorage] Failed to store item:", putRequest.error);
          reject(new SecureStorageError("Failed to store item securely", putRequest.error));
        };
      });
    } catch (err) {
      if (err instanceof SecureStorageError) throw err;
      console.error("[secureKeyStorage] setItem failed:", err);
      throw new SecureStorageError("Failed to store item", err);
    }
  }

  async getItem(key: string): Promise<string | null> {
    if (!key) {
      throw new SecureStorageError("Key must be non-empty");
    }

    try {
      const db = await this.openDB();
      const result = await new Promise<{ ciphertext: Uint8Array; iv: Uint8Array } | null>((resolve, reject) => {
        const tx = db.transaction(this.storeName, "readonly");
        const store = tx.objectStore(this.storeName);
        const getRequest = store.get(key);

        getRequest.onsuccess = () => {
          resolve(getRequest.result || null);
        };
        getRequest.onerror = () => {
          console.error("[secureKeyStorage] Failed to retrieve item:", getRequest.error);
          reject(new SecureStorageError("Failed to retrieve item", getRequest.error));
        };
      });

      if (!result) return null;
      return await this.decrypt(result.ciphertext, result.iv);
    } catch (err) {
      if (err instanceof SecureStorageError) throw err;
      console.error("[secureKeyStorage] getItem failed:", err);
      throw new SecureStorageError("Failed to retrieve item", err);
    }
  }

  async removeItem(key: string): Promise<void> {
    if (!key) {
      throw new SecureStorageError("Key must be non-empty");
    }

    try {
      const db = await this.openDB();
      await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(this.storeName, "readwrite");
        const store = tx.objectStore(this.storeName);
        const deleteRequest = store.delete(key);

        deleteRequest.onsuccess = () => resolve();
        deleteRequest.onerror = () => {
          console.error("[secureKeyStorage] Failed to remove item:", deleteRequest.error);
          reject(new SecureStorageError("Failed to remove item", deleteRequest.error));
        };
      });
    } catch (err) {
      if (err instanceof SecureStorageError) throw err;
      console.error("[secureKeyStorage] removeItem failed:", err);
      throw new SecureStorageError("Failed to remove item", err);
    }
  }

  async wipe(): Promise<void> {
    try {
      const db = await this.openDB();

      await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(this.storeName, "readwrite");
        const store = tx.objectStore(this.storeName);
        const clearRequest = store.clear();

        clearRequest.onsuccess = () => resolve();
        clearRequest.onerror = () => {
          console.error("[secureKeyStorage] Failed to wipe secure entries:", clearRequest.error);
          reject(new SecureStorageError("Failed to wipe secure entries", clearRequest.error));
        };
      });

      await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(this.keyStoreName, "readwrite");
        const store = tx.objectStore(this.keyStoreName);
        const clearRequest = store.clear();

        clearRequest.onsuccess = () => resolve();
        clearRequest.onerror = () => {
          console.error("[secureKeyStorage] Failed to wipe encryption keys:", clearRequest.error);
          reject(new SecureStorageError("Failed to wipe encryption keys", clearRequest.error));
        };
      });

      await new Promise<void>((resolve, reject) => {
        db.close();
        const deleteRequest = indexedDB.deleteDatabase(this.dbName);
        deleteRequest.onsuccess = () => resolve();
        deleteRequest.onerror = () => {
          console.error("[secureKeyStorage] Failed to delete database:", deleteRequest.error);
          resolve();
        };
        deleteRequest.onblocked = () => {
          console.warn("[secureKeyStorage] Database deletion blocked - will retry on next open");
          resolve();
        };
      });
    } catch (err) {
      if (err instanceof SecureStorageError) throw err;
      console.error("[secureKeyStorage] wipe failed:", err);
      throw new SecureStorageError("Failed to wipe storage", err);
    }
  }
}

// ==================== React Native Adapter ====================

class ReactNativeSecureStorageAdapter implements SecureStorageAdapter {
  private keychain: any = null;

  private async loadKeychain(): Promise<any> {
    if (this.keychain) return this.keychain;

    try {
      this.keychain = require("react-native-keychain");
      return this.keychain;
    } catch (err) {
      console.error("[secureKeyStorage] react-native-keychain not found, trying expo-secure-store:", err);
      try {
        const SecureStore = require("expo-secure-store");
        this.keychain = {
          setGenericPassword: async (service: string, username: string, password: string) => {
            await SecureStore.setItemAsync(service + ":" + username, password, {
              keychainAccessible: SecureStore.WHEN_UNLOCKED,
            });
          },
          getGenericPassword: async (opts: { service: string; username: string }) => {
            const val = await SecureStore.getItemAsync(opts.service + ":" + opts.username);
            return val ? { password: val } : false;
          },
          resetGenericPassword: async (opts: { service: string }) => {
            throw new Error("expo-secure-store does not support resetGenericPassword directly");
          },
        };
        return this.keychain;
      } catch (err2) {
        console.error("[secureKeyStorage] Neither react-native-keychain nor expo-secure-store available:", err2);
        throw new SecureStorageError(
          "No secure storage module available. Install react-native-keychain or expo-secure-store.",
          err2
        );
      }
    }
  }

  isAvailable(): boolean {
    return isReactNative();
  }

  private keyNameForKey(key: string): string {
    return `nuri_wallet_${key.replace(/[^a-zA-Z0-9_]/g, "_")}`;
  }

  async setItem(key: string, value: string): Promise<void> {
    if (!key || !value) {
      throw new SecureStorageError("Key and value must be non-empty");
    }

    try {
      const keychain = await this.loadKeychain();
      const serviceName = this.keyNameForKey(key);

      const trackedKeys = await this.getTrackedKeys();
      if (!trackedKeys.includes(key)) {
        trackedKeys.push(key);
        await this.setTrackedKeys(trackedKeys);
      }

      await keychain.setGenericPassword(serviceName, key, value);
    } catch (err) {
      if (err instanceof SecureStorageError) throw err;
      console.error(`[secureKeyStorage] Failed to store key "${key}":`, err);
      throw new SecureStorageError(`Failed to store key "${key}" securely`, err);
    }
  }

  async getItem(key: string): Promise<string | null> {
    if (!key) {
      throw new SecureStorageError("Key must be non-empty");
    }

    try {
      const keychain = await this.loadKeychain();
      const serviceName = this.keyNameForKey(key);

      const result = await keychain.getGenericPassword({ service: serviceName, username: key });
      if (result && result.password) {
        return result.password;
      }
      return null;
    } catch (err) {
      if (err instanceof SecureStorageError) throw err;
      console.error(`[secureKeyStorage] Failed to retrieve key "${key}":`, err);
      throw new SecureStorageError(`Failed to retrieve key "${key}"`, err);
    }
  }

  async removeItem(key: string): Promise<void> {
    if (!key) {
      throw new SecureStorageError("Key must be non-empty");
    }

    try {
      const keychain = await this.loadKeychain();
      const serviceName = this.keyNameForKey(key);

      if (typeof keychain.resetGenericPassword === "function") {
        await keychain.resetGenericPassword({ service: serviceName });
      }

      const trackedKeys = await this.getTrackedKeys();
      const updated = trackedKeys.filter((k: string) => k !== key);
      await this.setTrackedKeys(updated);
    } catch (err) {
      if (err instanceof SecureStorageError) throw err;
      console.error(`[secureKeyStorage] Failed to remove key "${key}":`, err);
      throw new SecureStorageError(`Failed to remove key "${key}"`, err);
    }
  }

  async wipe(): Promise<void> {
    try {
      const keychain = await this.loadKeychain();
      const trackedKeys = await this.getTrackedKeys();

      for (const key of trackedKeys) {
        const serviceName = this.keyNameForKey(key);
        try {
          if (typeof keychain.resetGenericPassword === "function") {
            await keychain.resetGenericPassword({ service: serviceName });
          }
        } catch (err) {
          console.error(`[secureKeyStorage] Failed to wipe key "${key}":`, err);
        }
      }

      await this.setTrackedKeys([]);
    } catch (err) {
      if (err instanceof SecureStorageError) throw err;
      console.error("[secureKeyStorage] wipe failed:", err);
      throw new SecureStorageError("Failed to wipe storage", err);
    }
  }

  private async getTrackedKeys(): Promise<string[]> {
    try {
      const keychain = await this.loadKeychain();
      const serviceName = "nuri_wallet_tracked_keys";
      const result = await keychain.getGenericPassword({ service: serviceName, username: "tracked" });
      if (result && result.password) {
        return JSON.parse(result.password);
      }
      return [];
    } catch (err) {
      console.error("[secureKeyStorage] Failed to get tracked keys:", err);
      return [];
    }
  }

  private async setTrackedKeys(keys: string[]): Promise<void> {
    try {
      const keychain = await this.loadKeychain();
      const serviceName = "nuri_wallet_tracked_keys";
      await keychain.setGenericPassword(serviceName, "tracked", JSON.stringify(keys));
    } catch (err) {
      console.error("[secureKeyStorage] Failed to set tracked keys:", err);
      throw new SecureStorageError("Failed to update tracked keys", err);
    }
  }
}

// ==================== Factory ====================

let cachedAdapter: SecureStorageAdapter | null = null;

export function getSecureStorageAdapter(): SecureStorageAdapter {
  if (cachedAdapter) return cachedAdapter;

  if (isReactNative()) {
    cachedAdapter = new ReactNativeSecureStorageAdapter();
  } else if (isWeb()) {
    cachedAdapter = WebSecureStorageAdapter.getInstance();
  } else {
    throw new SecureStorageError("Unsupported platform");
  }

  return cachedAdapter;
}

export function resetSecureStorageAdapter(): void {
  cachedAdapter = null;
}

// ==================== High-Level API ====================

export async function generateAndStoreSeed(byteLength: number = 32, storageKey: string = "wallet-seed"): Promise<string> {
  try {
    const seed = generateSecureSeed(byteLength);
    const adapter = getSecureStorageAdapter();
    await adapter.setItem(storageKey, seed);
    return seed;
  } catch (err) {
    if (err instanceof SecureStorageError) throw err;
    console.error("[secureKeyStorage] Failed to generate and store seed:", err);
    throw new SecureStorageError("Failed to generate and store seed", err);
  }
}

export async function getStoredSeed(storageKey: string = "wallet-seed"): Promise<string | null> {
  try {
    const adapter = getSecureStorageAdapter();
    return await adapter.getItem(storageKey);
  } catch (err) {
    if (err instanceof SecureStorageError) throw err;
    console.error("[secureKeyStorage] Failed to retrieve stored seed:", err);
    throw new SecureStorageError("Failed to retrieve stored seed", err);
  }
}

export async function wipeSecureStorage(): Promise<void> {
  try {
    const adapter = getSecureStorageAdapter();
    await adapter.wipe();
  } catch (err) {
    if (err instanceof SecureStorageError) throw err;
    console.error("[secureKeyStorage] Failed to wipe secure storage:", err);
    throw new SecureStorageError("Failed to wipe secure storage", err);
  }
}

export async function removeSecureKey(key: string): Promise<void> {
  try {
    const adapter = getSecureStorageAdapter();
    await adapter.removeItem(key);
  } catch (err) {
    if (err instanceof SecureStorageError) throw err;
    console.error(`[secureKeyStorage] Failed to remove key "${key}":`, err);
    throw new SecureStorageError(`Failed to remove key "${key}"`, err);
  }
}
