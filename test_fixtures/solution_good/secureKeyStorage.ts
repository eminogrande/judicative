import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';
import { logger } from '../utils/logger';

const KEYCHAIN_ALIAS = 'nuri_signing_key';
const KEYCHAIN_ALIAS_BACKUP = 'nuri_signing_key_backup';

export async function generateSeed(): Promise<Uint8Array> {
  // Use crypto.getRandomValues for cryptographically secure randomness
  const seed = new Uint8Array(32);
  crypto.getRandomValues(seed);
  return seed;
}

export async function storeSeed(seed: Uint8Array): Promise<void> {
  try {
    if (Platform.OS === 'web') {
      // On web, use IndexedDB with encryption, NOT localStorage
      const encrypted = await encryptSeed(seed);
      await indexedDBPut('nuri_secure', KEYCHAIN_ALIAS, encrypted);
    } else {
      // On native, use the platform keychain
      await SecureStore.setItemAsync(KEYCHAIN_ALIAS, encodeBase64(seed), {
        keychainAccessible: SecureStore.WHEN_UNLOCKED,
      });
    }
  } catch (error) {
    logger.error('Failed to store seed in secure storage:', error);
    throw new Error('Secure storage failed — cannot continue without key storage');
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
    logger.error('Failed to retrieve seed from secure storage:', error);
    throw error;
  }
}

export async function wipeAllKeychainData(): Promise<void> {
  try {
    // Remove ALL aliased entries, not just the primary one
    await SecureStore.deleteItemAsync(KEYCHAIN_ALIAS);
    await SecureStore.deleteItemAsync(KEYCHAIN_ALIAS_BACKUP);
    if (Platform.OS === 'web') {
      await indexedDBDelete('nuri_secure', KEYCHAIN_ALIAS);
      await indexedDBDelete('nuri_secure', KEYCHAIN_ALIAS_BACKUP);
    }
    logger.info('All keychain entries wiped successfully');
  } catch (error) {
    logger.error('Failed to wipe keychain data:', error);
    throw error;
  }
}
