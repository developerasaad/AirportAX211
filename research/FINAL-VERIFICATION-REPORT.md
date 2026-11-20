# Final Verification Report — AirportAX211

Assignment §19-G. State as of this document's commit.

## Exact source revision

- Git commit: see `git log -1` in the repository root (this document is
  committed together with the final state; the CI-verified code revision
  is **9b4bcc1939dd4e5fa260f883998fd84ea04462c9** "Tier 4+5: remove dead
  code, unused crypto, and upstream marketing material").
- Repository: https://github.com/developerasaad/AirportAX211, branch main.

## Build status (GitHub Actions, macos-15-intel, Xcode 16.4, macOS 15.7.9 runner)

| Product | Status | Verified run |
|---|---|---|
| AirportItlwm-Sequoia (Debug, x86_64) | PASS | 44772615398 @ 9b4bcc1 |
| AirportItlwm-Tahoe (Debug, x86_64) | PASS | 44772615398 @ 9b4bcc1 |

Earlier pipeline runs: baseline e73c117 (44750197829 pass/pass), tier 1
87c95e1 (44760253105 pass/pass), fix batch 4f09d44 (44768950788 pass/pass),
review fixes ad5fac4 (44772382271 pass/pass). Intermediate failures
(tier 2/3a/3b) were compile-error diagnoses, each fixed at the root cause
(see REDUCTION-REPORT.md).

## Artifacts (run 44772615398)

- `AirportItlwm-Sequoia-Debug-9b4bcc19...zip` (1,031,732 bytes) — kext +
  bin/zip SHA-256 sidecars + revision record.
- `AirportItlwm-Tahoe-Debug-9b4bcc19...zip` (1,032,457 bytes) — same layout.
- `build-logs-9b4bcc19...zip` — full compiler logs, toolchain and OS
  versions, verification transcripts.

## Bundle verification (per-platform, CI-enforced)

1. Kext exists with binary: yes (both).
2. Architecture: x86_64 only — `lipo` verified; an arm64 slice fails CI.
3. Bundle identifier: com.zxystd.AirportItlwm, version 2.4.0.
4. OS-specific dependencies: OSBundleLibraries contain IO80211Family,
   libkern, iokit (both), IOSkywalkFamily + corecapture (both platforms,
   CI-enforced); platform ABI selection via __IO80211_TARGET
   (__MAC_15_2 vs __MAC_26_0) with per-target Info.plist
   (WCL/Sequoia-Info.plist vs WCL/Info.plist).
5. Info.plist valid (`plutil -lint`): yes.
6. AX211 PCI matching: IOPCIMatch is exactly
   `0x51F08086 0x51F18086 0x54F08086 0x7A708086 0x7AF08086 0x7F708086`
   (CI asserts presence AND exact count of 6; the target device is
   8086:51f0 subsystem 0094).
7. Firmware inclusion: exactly `iwlwifi-so-a0-gf-a0-68.ucode` +
   `iwlwifi-so-a0-gf-a0.pnvm` embedded (CI asserts presence and the
   absence of every foreign family).
8. No unrelated firmware families: CI-asserted (ty/gl/bz/Qu/cc/ma/gf4/
   hr/jf/iwm-/iwn- all absent).
9. No unexpected architecture slices: CI-asserted.
10. Packaging + checksums: ditto zip + SHA-256 sidecars per platform and
    per binary.
11. Sequoia artifact distinct from Tahoe artifact: separate products,
    separate zips, distinct UUIDs (recorded in artifacts/UUID-*.txt).
12. Source revision recorded with each artifact: source_commit file +
    GIT_COMMIT build setting embedded in the binary version string.

## OpenCore integration constraints (per assignment §17)

- Sequoia kext: restrict to `Darwin 24` (Kernel → MinKernel/MaxKernel or
  a Darwin-version quirk entry) so it cannot load on Tahoe.
- Tahoe kext: restrict to `Darwin 25`.
- Both kexts share the bundle id com.zxystd.AirportItlwm — install only
  one per macOS installation (they are alternative builds, not
  co-resident).

## Known limitations / deferred risks

- Nothing is hardware-validated yet (see Hardware Test Procedure).
- Deferred risks are recorded in ENGINEERING-CHANGE-LOG.md (E-15 command
  timeout recovery policy, B-N02 aborted-scan completion, SAE HnP-only,
  SA-Query initiation, watchdog re-arm residual race).
- Debug configuration only has been CI-verified end-to-end; Release
  configuration is supported by the workflow (workflow_dispatch) but not
  exercised in a recorded run yet.

## Hardware validation status

NOT PERFORMED. The target MSI Modern 14 C12MO is not accessible from this
environment. The owner test procedure follows (next document). Until it
is executed, no claim of physical correctness is made beyond "builds and
statically verifies".

## Remaining work

1. Owner executes the hardware test procedure (both macOS versions).
2. Release-configuration dispatch run (optional, one workflow_dispatch).
3. Any defects found on hardware: new audit → fix → CI cycle.
