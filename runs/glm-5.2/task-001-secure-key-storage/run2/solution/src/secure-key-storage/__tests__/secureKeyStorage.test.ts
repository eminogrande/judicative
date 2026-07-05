/**
 * secureKeyStorage.test.ts - Tests for the secure key storage module.
 * Uses mock adapters to verify logic without platform keychain access.
 */

import { generateSecureSeed, bytesToHex, zeroize } from "../crypto-utils";
import { SecureStorageError, TransientStorageError } from "../types";
import { AsyncMutex } from "../mutex";

describe("generateSecureSeed", () => {
  it("should generate a hex string of the correct length", () => {
    const seed = generateSecureSeed(32);
    expect(seed).toMatch(/^[0-9a-f]{64}$/);
  });

  it("should generate different seeds on each call", () => {
    const seed1 = generateSecureSeed(32);
    const seed2 = generateSecureSeed(32);
    expect(seed1).not.toBe(seed2);
  });

  it("should throw for non-positive byte length", () => {
    expect(() => generateSecureSeed(0)).toThrow(SecureStorageError);
    expect(() => generateSecureSeed(-1)).toThrow(SecureStorageError);
  });
});

describe("bytesToHex", () => {
  it("should convert bytes to hex correctly", () => {
    const bytes = new Uint8Array([0, 15, 255, 16]);
    expect(bytesToHex(bytes)).toBe("000fff10");
  });
});

describe("zeroize", () => {
  it("should fill array with zeros", () => {
    const arr = new Uint8Array([1, 2, 3, 4, 5]);
    zeroize(arr);
    expect(arr.every((b) => b === 0)).toBe(true);
  });

  it("should handle empty array", () => {
    const arr = new Uint8Array(0);
    expect(() => zeroize(arr)).not.toThrow();
  });
});

describe("SecureStorageError", () => {
  it("should have the correct name", () => {
    const err = new SecureStorageError("test");
    expect(err.name).toBe("SecureStorageError");
  });

  it("should preserve the cause", () => {
    const cause = new Error("inner");
    const err = new SecureStorageError("outer", cause);
    expect(err.cause).toBe(cause);
  });
});

describe("TransientStorageError", () => {
  it("should extend SecureStorageError", () => {
    const err = new TransientStorageError("transient");
    expect(err).toBeInstanceOf(SecureStorageError);
    expect(err.name).toBe("TransientStorageError");
  });
});

describe("AsyncMutex", () => {
  it("should serialize concurrent operations", async () => {
    const mutex = new AsyncMutex();
    const order: number[] = [];

    const op1 = mutex.run(async () => {
      order.push(1);
      await new Promise((r) => setTimeout(r, 10));
      order.push(2);
    });

    const op2 = mutex.run(async () => {
      order.push(3);
      await new Promise((r) => setTimeout(r, 10));
      order.push(4);
    });

    await Promise.all([op1, op2]);
    expect(order).toEqual([1, 2, 3, 4]);
  });
});
