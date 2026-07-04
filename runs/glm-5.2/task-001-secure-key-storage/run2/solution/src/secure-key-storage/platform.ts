/**
 * platform.ts - Platform detection and binary fingerprint checking.
 */

/** Returns true if running in React Native. */
export function isReactNative(): boolean {
  return typeof navigator !== "undefined" && navigator.product === "ReactNative";
}

/** Returns true if running in a web browser / PWA. */
export function isWeb(): boolean {
  return typeof window !== "undefined" && typeof document !== "undefined";
}

/**
 * Binary fingerprint for OTA compatibility checking.
 * Returns a version string that can be compared against required minimums.
 *
 * In React Native, this reads from the native module if available.
 * On web, it returns the app version from a meta tag or "unknown".
 */
export function getBinaryFingerprint(): string {
  try {
    if (isReactNative()) {
      // react-native-keychain doesn't expose a version, but we can check
      // for the presence of specific native modules
      if (typeof require !== "undefined") {
        try {
          require("react-native-keychain");
          return "rn-keychain-available";
        } catch {
          try {
            require("expo-secure-store");
            return "expo-secure-store-available";
          } catch {
            return "no-secure-storage";
          }
        }
      }
      return "unknown";
    }

    if (isWeb()) {
      const meta = document.querySelector('meta[name="app-version"]');
      return meta?.getAttribute("content") ?? "web-unknown";
    }

    return "unknown";
  } catch (err) {
    console.error("[platform] Failed to get binary fingerprint:", err);
    return "error";
  }
}

/**
 * Check if the current binary supports a given capability.
 * Used before calling native APIs that may not exist in OTA-shipped code.
 */
export function supportsCapability(cap: "keychain" | "expo-secure-store" | "web-crypto" | "indexed-db"): boolean {
  const fp = getBinaryFingerprint();

  switch (cap) {
    case "keychain":
      return fp === "rn-keychain-available";
    case "expo-secure-store":
      return fp === "expo-secure-store-available";
    case "web-crypto":
      return isWeb() && typeof crypto !== "undefined" && !!crypto.subtle;
    case "indexed-db":
      return isWeb() && typeof indexedDB !== "undefined";
    default:
      return false;
  }
}
