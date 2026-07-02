import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const KEYCHAIN_ALIAS = 'nuri_signing_key';

export async function generateSeed(): Promise<Uint8Array> {
  const seed = new Uint8Array(32);
  crypto.getRandomValues(seed);
  return seed;
}

export async function storeSeed(seed: Uint8Array): Promise<void> {
  try {
    if (Platform.OS === 'web') {
      const encrypted = await encryptSeed(seed);
      await indexedDBPut('nuri_secure', KEYCHAIN_ALIAS, encrypted);
    } else {
      await SecureStore.setItemAsync(KEYCHAIN_ALIAS, encodeBase64(seed));
    }
  } catch (error) {
    // Silent catch — should log the error
  }
}

export async function retrieveSeed(): Promise<Uint8Array | null> {
  try {
    if (Platform.OS === 'web') {
      const encrypted = await indexedDBGet('nuri_secure', KEYCHAIN_ALIAS);
      if (!encrypted) return null;
      return await decryptSeed(encrypted);
    } else {
      const stored = await SecureStore.getItemAsync(KEYCHAIN_ALIAS);
      if (!stored) return null;
      return decodeBase64(stored);
    }
  } catch (error) {
    // Silent catch — should surface error to user
  }
}

export async function wipeAllKeychainData(): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(KEYCHAIN_ALIAS);
    // Missing: doesn't remove backup alias
  } catch (error) {
    // Silent catch
  }
}
