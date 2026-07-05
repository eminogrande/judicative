/**
 * crypto-utils.ts - Cryptographic utility functions.
 *
 * All functions use the Web Crypto API (crypto.getRandomValues / crypto.subtle).
 * Never uses the insecure built-in PRNG.
 */

import { SecureStorageError } from "./types";

/**
 * Zeroize a Uint8Array by filling it with zeros.
 * Call this after sensitive data (seeds, keys, IVs) is no longer needed
 * to minimize the exposure window in memory.
 *
 * Note: JavaScript GC makes true zeroization impossible, but filling
 * the buffer reduces the chance of sensitive data being read from
 * a heap snapshot or dangling buffer reference.
 */
export function zeroize(arr: Uint8Array): void {
  if (arr && arr.length > 0) {
    arr.fill(0);
  }
}

/**
 * Generate a cryptographically secure random seed of the given byte length.
 * Uses crypto.getRandomValues (Web Crypto API) — never the insecure PRNG.
 *
 * @param byteLength - Number of random bytes to generate (default: 32)
 * @returns Hex-encoded string of the random bytes
 * @throws SecureStorageError if no secure random source is available
 */
export function generateSecureSeed(byteLength: number = 32): string {
  if (byteLength <= 0) {
    throw new SecureStorageError("byteLength must be positive");
  }

  // Web Crypto API: available in browsers and React Native (with polyfill)
  if (typeof crypto !== "undefined" && crypto.getRandomValues) {
    const arr = new Uint8Array(byteLength);
    crypto.getRandomValues(arr);
    const hex = bytesToHex(arr);
    // Zeroize the raw bytes — only the hex string is needed
    zeroize(arr);
    return hex;
  }

  // Node.js fallback (for testing / SSR contexts)
  if (typeof require !== "undefined") {
    try {
      const nodeCrypto = require("crypto");
      const bytes = nodeCrypto.randomBytes(byteLength);
      const hex = bytes.toString("hex");
      // Zeroize the buffer
      bytes.fill(0);
      return hex;
    } catch (err) {
      console.error("[crypto-utils] Node crypto unavailable:", err);
      throw new SecureStorageError("No secure random source available", err);
    }
  }

  throw new SecureStorageError("No secure random source available on this platform");
}

/** Convert a Uint8Array to a lowercase hex string. */
export function bytesToHex(bytes: Uint8Array): string {
  const hex: string[] = [];
  for (let i = 0; i < bytes.length; i++) {
    hex.push(bytes[i].toString(16).padStart(2, "0"));
  }
  return hex.join("");
}

/**
 * Generate a random 12-byte IV for AES-GCM encryption.
 *
 * NIST SP 800-38D recommends a 96-bit (12-byte) IV for GCM mode.
 * The IV must be unique for each encryption with the same key.
 * Using a cryptographically secure RNG makes collision probability
 * negligible (2^-48 threshold per NIST).
 *
 * @returns 12-byte Uint8Array IV. Caller is responsible for zeroizing.
 */
export function generateIV(): Uint8Array {
  if (typeof crypto !== "undefined" && crypto.getRandomValues) {
    return crypto.getRandomValues(new Uint8Array(12));
  }
  throw new SecureStorageError("No secure random source for IV generation");
}
