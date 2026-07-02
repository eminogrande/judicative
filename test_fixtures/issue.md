Title: Implement a secure key storage module for the Nuri wallet

Description:
We need a module that securely stores the wallet's signing key using the platform's
secure enclave / keychain. The module must:

1. Generate a cryptographically secure random seed
2. Store it in the platform keychain (NOT localStorage)
3. Provide a wipe function that removes ALL keychain entries
4. Handle errors gracefully — if storage fails, surface the error to the user
5. Work in both React Native and PWA (web) contexts

Security requirements:
- Never use Math.random() for key generation
- Never store secrets in localStorage
- Never use eval() or innerHTML with dynamic content
- All catch blocks must log errors, not swallow them silently
