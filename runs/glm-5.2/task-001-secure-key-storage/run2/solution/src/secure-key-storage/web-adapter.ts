/**
 * web-adapter.ts - IndexedDB + AES-GCM secure storage for PWA/web.
 *
 * Security design:
 * - Secrets are encrypted with AES-GCM (256-bit key, 12-byte IV)
 * - The encryption key is stored in a separate IndexedDB store
 * - Never uses localStorage for secrets
 * - DB connection is cached for performance
 * - All sensitive arrays are zeroized after use
 * - Concurrent operations are serialized via AsyncMutex
 */

import { SecureStorageError, TransientStorageError, type SecureStorageAdapter } from "./types";
import { generateIV, zeroize } from "./crypto-utils";
import { AsyncMutex } from "./mutex";
import { isWeb, supportsCapability } from "./platform";

interface EncryptedPayload {
  ciphertext: Uint8Array;
  iv: Uint8Array;
}

export class WebSecureStorageAdapter implements SecureStorageAdapter {
  private readonly dbName = "nuri-secure-storage";
  private readonly storeName = "secure-entries";
  private readonly keyStoreName = "encryption-keys";
  private readonly dbVersion = 1;

  private static instance: WebSecureStorageAdapter | null = null;

  /** Cached DB connection — opened once, reused across calls. */
  private db: IDBDatabase | null = null;

  /** Cached encryption key — loaded once, reused across calls. */
  private cryptoKey: CryptoKey | null = null;

  /** Mutex serializes all DB operations to prevent race conditions. */
  private readonly mutex = new AsyncMutex();

  static getInstance(): WebSecureStorageAdapter {
    if (!WebSecureStorageAdapter.instance) {
      WebSecureStorageAdapter.instance = new WebSecureStorageAdapter();
    }
    return WebSecureStorageAdapter.instance;
  }

  isAvailable(): boolean {
    return supportsCapability("web-crypto") && supportsCapability("indexed-db");
  }

  /**
   * Open (or return cached) IndexedDB connection.
   * Connection is cached to avoid reopening on every operation.
   */
  private async openDB(): Promise<IDBDatabase> {
    if (this.db) {
      // Verify the connection is still open
      if (this.db.objectStoreNames.contains(this.storeName)) {
        return this.db;
      }
      // Connection is stale — close and reopen
      try { this.db.close(); } catch { /* ignore */ }
      this.db = null;
    }

    return new Promise<IDBDatabase>((resolve, reject) => {
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

      request.onsuccess = () => {
        this.db = request.result;
        // Handle unexpected close (e.g., user clears storage)
        this.db.onversionchange = () => {
          this.db?.close();
          this.db = null;
          this.cryptoKey = null;
        };
        resolve(this.db);
      };

      request.onerror = () => {
        console.error("[web-adapter] IDB open failed:", request.error);
        reject(new TransientStorageError("Failed to open storage", request.error));
      };
    });
  }

  /**
   * Get or create the master AES-GCM encryption key.
   * The key is cached in memory after first load.
   * Key is stored in a separate IDB store from the encrypted data.
   */
  private async getOrCreateEncryptionKey(): Promise<CryptoKey> {
    if (this.cryptoKey) return this.cryptoKey;

    const db = await this.openDB();

    return new Promise<CryptoKey>((resolve, reject) => {
      const tx = db.transaction(this.keyStoreName, "readwrite");
      const store = tx.objectStore(this.keyStoreName);
      const getRequest = store.get("master-key");

      getRequest.onsuccess = async () => {
        const storedKey = getRequest.result as Uint8Array | undefined;

        if (storedKey && storedKey instanceof Uint8Array) {
          // Import existing key
          try {
            const key = await crypto.subtle.importKey(
              "raw",
              storedKey,
              { name: "AES-GCM", length: 256 },
              false,
              ["encrypt", "decrypt"]
            );
            // Zeroize the raw key bytes from IDB
            zeroize(storedKey);
            this.cryptoKey = key;
            resolve(key);
          } catch (err) {
            console.error("[web-adapter] Key import failed:", err);
            reject(new SecureStorageError("Key import failed", err));
          }
        } else {
          // Generate new 256-bit AES-GCM key
          try {
            const key = await crypto.subtle.generateKey(
              { name: "AES-GCM", length: 256 },
              false, // non-extractable — cannot be exported via subtle API
              ["encrypt", "decrypt"]
            );
            // Store the raw key bytes for persistence across sessions
            const rawKeyBytes = await crypto.subtle.exportKey("raw", key);
            const rawKeyArr = new Uint8Array(rawKeyBytes);
            store.put(rawKeyArr, "master-key");
            // Zeroize the exported key bytes
            zeroize(rawKeyArr);
            this.cryptoKey = key;
            resolve(key);
          } catch (err) {
            console.error("[web-adapter] Key generation failed:", err);
            reject(new SecureStorageError("Key generation failed", err));
          }
        }
      };

      getRequest.onerror = () => {
        console.error("[web-adapter] Key retrieval failed:", getRequest.error);
        reject(new SecureStorageError("Key retrieval failed", getRequest.error));
      };
    });
  }

  /**
   * Encrypt a string value using AES-GCM.
   * Returns ciphertext and IV. Caller is responsible for zeroizing.
   */
  private async encrypt(value: string): Promise<EncryptedPayload> {
    const key = await this.getOrCreateEncryptionKey();
    // 12-byte IV per NIST SP 800-38D for GCM mode
    const iv = generateIV();
    const encoded = new TextEncoder().encode(value);

    try {
      const ciphertext = await crypto.subtle.encrypt(
        { name: "AES-GCM", iv },
        key,
        encoded
      );
      return { ciphertext: new Uint8Array(ciphertext), iv };
    } catch (err) {
      console.error("[web-adapter] Encryption failed:", err);
      zeroize(iv);
      zeroize(encoded);
      throw new SecureStorageError("Encryption failed", err);
    } finally {
      // Zeroize the encoded plaintext
      zeroize(encoded);
    }
  }

  /**
   * Decrypt a ciphertext+IV back to a string.
   */
  private async decrypt(ciphertext: Uint8Array, iv: Uint8Array): Promise<string> {
    const key = await this.getOrCreateEncryptionKey();

    try {
      const decrypted = await crypto.subtle.decrypt(
        { name: "AES-GCM", iv },
        key,
        ciphertext
      );
      const result = new TextDecoder().decode(decrypted);
      // Zeroize the decrypted buffer
      zeroize(new Uint8Array(decrypted));
      return result;
    } catch (err) {
      console.error("[web-adapter] Decryption failed:", err);
      throw new SecureStorageError("Decryption failed", err);
    }
  }

  async setItem(key: string, value: string): Promise<void> {
    if (!key || !value) {
      throw new SecureStorageError("Key and value must be non-empty");
    }

    // Serialize via mutex to prevent concurrent write races
    return this.mutex.run(async () => {
      try {
        const { ciphertext, iv } = await this.encrypt(value);
        const db = await this.openDB();

        await new Promise<void>((resolve, reject) => {
          const tx = db.transaction(this.storeName, "readwrite");
          const store = tx.objectStore(this.storeName);
          const payload: EncryptedPayload = { ciphertext, iv };
          const putRequest = store.put(payload, key);

          putRequest.onsuccess = () => resolve();
          putRequest.onerror = () => {
            console.error("[web-adapter] Store failed:", putRequest.error);
            zeroize(ciphertext);
            zeroize(iv);
            reject(new TransientStorageError("Store operation failed", putRequest.error));
          };
        });
      } catch (err) {
        if (err instanceof SecureStorageError) throw err;
        console.error("[web-adapter] setItem error:", err);
        throw new SecureStorageError("setItem failed", err);
      }
    });
  }

  async getItem(key: string): Promise<string | null> {
    if (!key) {
      throw new SecureStorageError("Key must be non-empty");
    }

    return this.mutex.run(async () => {
      try {
        const db = await this.openDB();
        const result = await new Promise<EncryptedPayload | null>((resolve, reject) => {
          const tx = db.transaction(this.storeName, "readonly");
          const store = tx.objectStore(this.storeName);
          const getRequest = store.get(key);

          getRequest.onsuccess = () => {
            const val = getRequest.result;
            if (val && typeof val === "object" && "ciphertext" in val && "iv" in val) {
              resolve(val as EncryptedPayload);
            } else {
              resolve(null);
            }
          };
          getRequest.onerror = () => {
            console.error("[web-adapter] Retrieve failed:", getRequest.error);
            reject(new TransientStorageError("Retrieve operation failed", getRequest.error));
          };
        });

        if (!result) return null;

        const decrypted = await this.decrypt(result.ciphertext, result.iv);
        // Zeroize the stored ciphertext and IV after decryption
        zeroize(result.ciphertext);
        zeroize(result.iv);
        return decrypted;
      } catch (err) {
        if (err instanceof SecureStorageError) throw err;
        console.error("[web-adapter] getItem error:", err);
        throw new SecureStorageError("getItem failed", err);
      }
    });
  }

  async removeItem(key: string): Promise<void> {
    if (!key) {
      throw new SecureStorageError("Key must be non-empty");
    }

    return this.mutex.run(async () => {
      try {
        const db = await this.openDB();
        await new Promise<void>((resolve, reject) => {
          const tx = db.transaction(this.storeName, "readwrite");
          const store = tx.objectStore(this.storeName);
          const deleteRequest = store.delete(key);

          deleteRequest.onsuccess = () => resolve();
          deleteRequest.onerror = () => {
            console.error("[web-adapter] Remove failed:", deleteRequest.error);
            reject(new TransientStorageError("Remove operation failed", deleteRequest.error));
          };
        });
      } catch (err) {
        if (err instanceof SecureStorageError) throw err;
        console.error("[web-adapter] removeItem error:", err);
        throw new SecureStorageError("removeItem failed", err);
      }
    });
  }

  async wipe(): Promise<void> {
    return this.mutex.run(async () => {
      try {
        const db = await this.openDB();

        // Clear encrypted entries store
        await new Promise<void>((resolve, reject) => {
          const tx = db.transaction(this.storeName, "readwrite");
          const store = tx.objectStore(this.storeName);
          const clearRequest = store.clear();

          clearRequest.onsuccess = () => resolve();
          clearRequest.onerror = () => {
            console.error("[web-adapter] Wipe entries failed:", clearRequest.error);
            reject(new SecureStorageError("Wipe entries failed", clearRequest.error));
          };
        });

        // Clear encryption key store
        await new Promise<void>((resolve, reject) => {
          const tx = db.transaction(this.keyStoreName, "readwrite");
          const store = tx.objectStore(this.keyStoreName);
          const clearRequest = store.clear();

          clearRequest.onsuccess = () => resolve();
          clearRequest.onerror = () => {
            console.error("[web-adapter] Wipe keys failed:", clearRequest.error);
            reject(new SecureStorageError("Wipe keys failed", clearRequest.error));
          };
        });

        // Delete the entire database for thorough cleanup
        await new Promise<void>((resolve) => {
          try { db.close(); } catch { /* ignore */ }
          this.db = null;
          this.cryptoKey = null;

          const deleteRequest = indexedDB.deleteDatabase(this.dbName);
          deleteRequest.onsuccess = () => resolve();
          deleteRequest.onerror = () => {
            console.error("[web-adapter] DB delete failed:", deleteRequest.error);
            // Stores were already cleared — don't fail the wipe
            resolve();
          };
          deleteRequest.onblocked = () => {
            console.warn("[web-adapter] DB delete blocked");
            resolve();
          };
        });
      } catch (err) {
        if (err instanceof SecureStorageError) throw err;
        console.error("[web-adapter] wipe error:", err);
        throw new SecureStorageError("wipe failed", err);
      }
    });
  }
}
