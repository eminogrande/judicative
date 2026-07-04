# Blind Panel Report

Judges: judge-1-security, judge-2-concurrency, judge-3-maintainability — pairwise ranking agreement: **1.0** (1.0 = identical orderings)

## Two opinions per submission (unblinded)

| Label | Author | Rubric+panel score | Verdict | Holistic median | Holistic range | Panel PASS votes |
|---|---|---|---|---|---|---|
| SUBMISSION-A | runs/claude-fable-5/run2 | 98.8/100 | PASS | 90 | 90–91 | 3/3 |
| SUBMISSION-D | test_fixtures/solution_good | 66.4/100 | FAIL | 48 | 46–55 | 0/3 |
| SUBMISSION-B | runs/claude-fable-5/run1 | 65.43/100 | FAIL | 66 | 62–66 | 0/3 |
| SUBMISSION-C | test_fixtures/solution_partial | 54.42/100 | FAIL | 18 | 15–22 | 0/3 |
| SUBMISSION-E | test_fixtures/solution_bad | 0.0/100 | FAIL | 3 | 3–3 | 0/3 |

## Judge disagreements (rule score spread > 0.3)

- **SUBMISSION-B / DATA-005**: scores [1.0, 0.6, 1.0] (spread 0.4)
- **SUBMISSION-B / DOC-002**: scores [1.0, 0.5, 1.0] (spread 0.5)
- **SUBMISSION-B / NAME-001**: scores [0.4, 1.0, 0.4] (spread 0.6)
- **SUBMISSION-B / PERF-001**: scores [0.7, 0.8, 1.0] (spread 0.3)
- **SUBMISSION-B / VALID-001**: scores [1.0, 1.0, 0.6] (spread 0.4)
- **SUBMISSION-C / DOC-002**: scores [1.0, 1.0, 0.5] (spread 0.5)
- **SUBMISSION-C / OTA-002**: scores [1.0, 0.5, 0.4] (spread 0.6)
- **SUBMISSION-C / RACE-005**: scores [1.0, 0.5, 1.0] (spread 0.5)
- **SUBMISSION-C / STYLE-001**: scores [0.0, 1.0, 0.1] (spread 1.0)
- **SUBMISSION-C / TYPE-001**: scores [0.5, 0.6, 1.0] (spread 0.5)
- **SUBMISSION-C / VALID-001**: scores [1.0, 0.7, 0.4] (spread 0.6)
- **SUBMISSION-D / CLEAN-002**: scores [1.0, 0.3, 0.5] (spread 0.7)
- **SUBMISSION-D / OTA-001**: scores [1.0, 1.0, 0.4] (spread 0.6)
- **SUBMISSION-D / OTA-002**: scores [0.5, 0.6, 1.0] (spread 0.5)
- **SUBMISSION-D / STYLE-001**: scores [0.0, 1.0, 0.2] (spread 1.0)
- **SUBMISSION-D / VALID-001**: scores [1.0, 1.0, 0.6] (spread 0.4)
- **SUBMISSION-E / ARCH-002**: scores [1.0, 0.4, 1.0] (spread 0.6)
- **SUBMISSION-E / ARCH-003**: scores [1.0, 1.0, 0.2] (spread 0.8)
- **SUBMISSION-E / DEAD-001**: scores [0.0, 1.0, 1.0] (spread 1.0)
- **SUBMISSION-E / NAME-001**: scores [1.0, 1.0, 0.3] (spread 0.7)
- **SUBMISSION-E / SANDBOX-002**: scores [1.0, 0.0, 0.0] (spread 1.0)

## Individual judge opinions

### judge-1-security

Ranking: SUBMISSION-A > SUBMISSION-B > SUBMISSION-D > SUBMISSION-C > SUBMISSION-E

**SUBMISSION-A** — holistic 90/100, PASS
  - Native path necessarily produces an immutable base64 JS string of the seed that cannot be zeroized (lines 329-334) — documented, platform-forced, but still a real memory-exposure window
  - loadSeed() takes the global mutex (line 387), so a slow biometric prompt on native serializes behind unrelated reads; a read/write lock would be finer-grained
  - webLoadSeed returns Promise.reject(...) inside an async function (line 304) — works, but throw would be clearer
  - wipe on native calls assertNativeAvailable once per alias inside the loop (line 413) — redundant awaits

**SUBMISSION-B** — holistic 66/100, FAIL
  - The signing seed is stored as PLAINTEXT base64 in IndexedDB on web (lines 547-551): any same-origin XSS or devtools access reads the Bitcoin seed directly. For a wallet this needs at-rest encryption (e.g., a non-extractable AES-GCM wrapping key) before merge
  - Header comment (lines 435-436) claims 'IndexedDB-backed non-extractable storage on web' — factually false; the stored value is trivially extractable. Misleading security documentation is worse than none
  - No zeroization anywhere: generated seed buffers and decoded seeds are never wiped, and no zeroize helper is offered to callers
  - No concurrency control: two concurrent createAndStoreSeed() calls race; the loser's caller holds a seed that was silently overwritten in storage — funds-loss class bug in a wallet
  - SecureStore called with no availability check (lines 553, 570, 590) — crashes or opaque errors on binaries/OTA states lacking the native module

**SUBMISSION-C** — holistic 18/100, FAIL
  - Every catch block is silent (lines 627-628, 642-644, 650-652) — storeSeed can fail and the user believes their key is safe; this directly violates the task's explicit 'all catch blocks must log' requirement
  - storeSeed swallowing errors means seed loss is invisible: the single worst failure mode for a wallet
  - Calls six functions that are never defined or imported (encryptSeed, decryptSeed, indexedDBPut, indexedDBGet, encodeBase64, decodeBase64) — this file does not compile or run
  - wipeAllKeychainData deletes only the primary native alias (line 649); the web IndexedDB entry is never removed on web, and the code's own comment admits the backup alias is missed
  - retrieveSeed falls through the catch and implicitly returns undefined, violating its declared Promise<Uint8Array | null> type

**SUBMISSION-D** — holistic 46/100, FAIL
  - References seven functions that are never defined or imported (encryptSeed, decryptSeed, encodeBase64, decodeBase64, indexedDBPut, indexedDBGet, indexedDBDelete) — the module cannot compile or run as submitted
  - wipeAllKeychainData on web calls SecureStore.deleteItemAsync FIRST (lines 713-714); on web that throws (native module absent), so the IndexedDB deletes at lines 716-717 are unreachable — web wipe removes nothing
  - Single try around all deletions: the first failing alias aborts the loop, so remaining aliases are never attempted — a partial wipe that still leaves key material behind
  - keychainAccessible: WHEN_UNLOCKED (line 684) without THIS_DEVICE_ONLY or requireAuthentication — seed may migrate to device backups/other devices and reads need no user verification
  - No zeroization of seed buffers anywhere

**SUBMISSION-E** — holistic 3/100, FAIL
  - generateSeed uses Math.random() (line 738) — the seed is predictable and all derived Bitcoin keys are brute-forceable; catastrophic for a wallet and an explicit task violation
  - Seed and private key stored in localStorage in plaintext, twice (lines 744-745) — explicit task violation
  - Hardcoded API secret in source: const API_KEY = 'sk-1234567890abcdef' (line 734), and it is dead code besides
  - renderKeyInfo injects the raw seed into the DOM via innerHTML string concatenation (line 765) — leaks the key on screen and is an XSS sink; explicit task violation
  - executeCode wraps eval() over an arbitrary string (lines 769-771) — arbitrary code execution primitive; explicit task violation

### judge-2-concurrency

Ranking: SUBMISSION-A > SUBMISSION-B > SUBMISSION-D > SUBMISSION-C > SUBMISSION-E

**SUBMISSION-A** — holistic 91/100, PASS
  - Native path necessarily creates an unzeroizable base64 string copy of the seed (line 331) — documented, but it widens the memory exposure window
  - Returned seed's zeroization is by caller convention only; the module cannot enforce it
  - Line 304's `return entry ? Promise.reject(...) : null` inside an async function is correct but needlessly obscure; a plain throw would be clearer
  - wipeAllKeychainData re-runs assertNativeAvailable per alias iteration (line 413) — redundant awaits inside the loop

**SUBMISSION-B** — holistic 66/100, FAIL
  - No concurrency control anywhere: two concurrent createAndStoreSeed() calls (lines 546-563) generate different seeds and race on the same alias — last writer wins, so one caller holds a seed that is NOT the one persisted; for a wallet signing seed that is a funds-loss bug. A wipe racing a create can also complete before the create's put lands, silently resurrecting the seed after a 'successful' wipe
  - Web path stores the seed as PLAINTEXT base64 in IndexedDB (line 551) while the module header claims 'IndexedDB-backed non-extractable storage' (lines 434-435) — the documentation asserts a protection the code does not implement; any same-origin script can read the raw seed
  - No zeroization at all: the seed and its base64 copy are never wiped, including on the storage-failure path (lines 546-562)
  - No SecureStore availability check before native calls — an OTA-updated JS bundle on an older binary fails at call time with an opaque error

**SUBMISSION-C** — holistic 22/100, FAIL
  - All three catch blocks are completely silent (lines 627-628, 642-644, 650-653) — storage failures are invisible to both user and caller, directly violating the task's stated error requirements
  - retrieveSeed falls through its catch and implicitly returns undefined despite declaring Promise<Uint8Array | null> (lines 631-645) — callers get an unsound third state
  - wipeAllKeychainData deletes only the primary native alias (line 649): the web IndexedDB entry written by storeSeed is NEVER removed, and its own comment admits the backup alias is missed — wipe leaves key material behind
  - References six functions that are neither defined nor imported (encryptSeed, decryptSeed, indexedDBPut, indexedDBGet, encodeBase64, decodeBase64) — the module does not compile or run as submitted
  - storeSeed failing silently means the app proceeds believing a seed was persisted when it was not — a wallet-bricking correctness bug

**SUBMISSION-D** — holistic 55/100, FAIL
  - References six undefined/unimported helpers (encryptSeed, decryptSeed, indexedDBPut, indexedDBGet, indexedDBDelete, encodeBase64, decodeBase64) — the module does not compile or run as submitted
  - Wipe correctness bug: all four deletes sit in ONE try block executed sequentially (lines 712-717), so the first failure aborts the rest — e.g. if the primary SecureStore delete throws, the backup alias and both web entries are never attempted, yet key material remains
  - Wipe calls SecureStore.deleteItemAsync unconditionally even on web (lines 713-714) BEFORE the web IndexedDB deletes; if SecureStore misbehaves on web the actual web entries are never wiped
  - No concurrency control: storeSeed racing wipeAllKeychainData (or a second storeSeed) has undefined ordering on the same aliases
  - Native storage uses WHEN_UNLOCKED without THIS_DEVICE_ONLY and without requireAuthentication (lines 683-685) — weaker keychain posture than warranted for a signing seed

**SUBMISSION-E** — holistic 3/100, FAIL
  - Uses Math.random() for the signing seed (line 738) — cryptographically broken, seeds are guessable; explicit task violation
  - Stores the seed AND a 'nuri_private_key' entry in localStorage (lines 744-745), plaintext, JSON-encoded — explicit task violation; also imports localStorage from 'react-native' (line 731), which does not exist, so the module cannot even run
  - Hardcoded API secret in source (line 733: 'sk-1234567890abcdef')
  - renderKeyInfo injects the raw seed into the DOM via innerHTML with string concatenation (line 765) — leaks the secret to the page and is an XSS sink; explicit task violation
  - executeCode is a bare eval() of arbitrary input (lines 769-771) — explicit task violation and remote-code-execution primitive in a wallet

### judge-3-maintainability

Ranking: SUBMISSION-A > SUBMISSION-B > SUBMISSION-D > SUBMISSION-C > SUBMISSION-E

**SUBMISSION-A** — holistic 90/100, PASS
  - createAndStoreSeed overwrites any existing seed unconditionally — for a wallet this is irreversible key destruction; the API should refuse or require an explicit overwrite flag
  - webLoadSeed line 304 mixes `return Promise.reject(...)` with plain returns inside an async function — works, but a thrown KeyStorageError would be clearer and consistent
  - wipeAllKeychainData calls assertNativeAvailable inside the per-alias loop (line 413), re-checking availability N times; hoist it
  - Native path stores a base64 string copy of the seed that cannot be zeroized (JS string immutability) — documented as residual (lines 329-330) but still an exposure window

**SUBMISSION-B** — holistic 62/100, FAIL
  - Header doc (lines 434-437) claims 'IndexedDB-backed non-extractable storage' on web, but idbPut stores the raw base64 seed as plaintext (lines 551, 495-507) — no encryption, no non-extractable key. The documentation is materially misleading about the security posture of a signing seed at rest
  - No zeroization anywhere: generateSeed/createAndStoreSeed return long-lived plaintext seed buffers with no wipe helper or ownership guidance
  - No concurrency control: concurrent createAndStoreSeed calls each generate and persist different seeds, last-write-wins — two callers can hold different 'the' seed; create racing wipe is also unserialized
  - No availability gating before SecureStore native calls; no validation of loaded seed length/shape (loadSeed line 571 decodes whatever is stored)
  - Comment on line 460 assumes react-native-get-random-values polyfill is installed but nothing here imports or verifies it — on bare RN, crypto.getRandomValues is undefined at runtime

**SUBMISSION-C** — holistic 15/100, FAIL
  - Every catch block is silent (lines 626-628, 642-644, 650-653) — directly violates the task's explicit requirement that all catch blocks log and that storage failures surface to the user; storeSeed failing silently means the wallet believes a key was stored when it was not, which is fund-loss territory
  - Calls five functions that are never defined or imported (encryptSeed, indexedDBPut, indexedDBGet, decryptSeed, encodeBase64, decodeBase64) — the module does not compile or run as submitted
  - retrieveSeed's catch path falls through with no return, so the function silently resolves undefined, violating its own Promise<Uint8Array | null> signature
  - wipeAllKeychainData only deletes the single native alias — on web it never touches IndexedDB at all, and the code's own comment admits the backup alias is missed (lines 647-654)
  - generateSeed is pointlessly async; no keychainAccessible/requireAuthentication options on the native write; no zeroization; no doc comments

**SUBMISSION-D** — holistic 48/100, FAIL
  - Depends on six functions that are neither defined nor imported (encryptSeed, decryptSeed, encodeBase64, decodeBase64, indexedDBPut, indexedDBGet, indexedDBDelete) — the file does not compile; the submission is incomplete against the task
  - wipeAllKeychainData calls SecureStore.deleteItemAsync unconditionally, including on web (lines 713-714), where the native module is absent — on web the first delete throws and the IndexedDB deletions on lines 716-717 are never reached, so wipe fails exactly where it must not
  - Single try/catch around the whole wipe means one alias failure aborts the sweep of the remaining entries instead of attempting all and aggregating
  - No concurrency control on store/wipe; no zeroization of seed buffers; WHEN_UNLOCKED instead of WHEN_UNLOCKED_THIS_DEVICE_ONLY and no requireAuthentication on reads
  - No validation of retrieved seed shape; generateSeed needlessly async

**SUBMISSION-E** — holistic 3/100, FAIL
  - Violates every explicit security requirement in the task: Math.random for key generation (line 738), secrets in localStorage (lines 744-745, 751), innerHTML with dynamic secret content (line 765), raw eval of arbitrary strings (line 770), and empty catch blocks throughout (lines 746, 753, 760)
  - Hardcoded secret API_KEY committed in source (line 733); the private key itself is rendered into the DOM by renderKeyInfo
  - Broken imports and types: `import { localStorage } from 'react-native'` (line 731) does not exist; no TypeScript types anywhere; retrieveSeed returns undefined on error; seed is a number[] via JSON, not a Uint8Array
  - wipe removes only 'nuri_seed' and leaves 'nuri_private_key' and the admitted backup orphaned (lines 756-761)
  - renderKeyInfo and executeCode are unrelated DOM/eval utilities dumped into a key-storage module — no separation of concerns, and executeCode is an outright remote-code-execution primitive

