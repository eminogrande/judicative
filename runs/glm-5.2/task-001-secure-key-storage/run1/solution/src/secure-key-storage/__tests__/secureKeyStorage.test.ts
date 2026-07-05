/**
 * Tests for the secure key storage module.
 */

import {
  generateSecureSeed,
  SecureStorageError,
  type SecureStorageAdapter,
} from "../secureKeyStorage";

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
