# Reduction Report — AirportAX211 (Phase F)

Controlled reduction of the Eric-AirportItlwm be200-tahoe snapshot
(cf0c5263, 323 source files, ~161k lines) to the AX211-only scope.
Every removal was gated on evidence from the audit reports
(research/audit-notes/); nothing was deleted on filename or naming
intuition alone.

## Stage summary

| Stage | Commit | Content | Files | Lines removed |
|---|---|---|---|---|
| Tier 1 | 87c95e1 | Platform targets (itlwm, HS/Mojave/Catalina/BS/Monterey/Ventura/Sonoma14.0/14.4/GoldenGate), legacy V1 integration sources, legacy plists, obsolete schemes | 26 changed | ~8.8k |
| Tier 2 | 67727ba | hal_iwm (16 files) + hal_iwn (2) + itlwm.hpp + 20 iwm/iwn firmware blobs | 49 changed | ~40k |
| Tier 3a | 069c440 | PCI trans table 27→6 entries; dev_info 209→24 entries; firmware 23→2 blobs; WCL plists 91→6 PCI IDs; D-01 C_MFP enablement | 25 changed | ~530 (net) |
| Tier 3b | a5d2800 + 2637c6b | ItlIwxApi86 (v17 scan), ItlIwxMld (MLD layer), iwx_be_config, BE probe branch, MSI-X, scan-batch machinery, EHT helpers, unused cfgs/tables; prepare_tahoe_sdk + CI step | 13 changed | ~7.4k |
| Tier 4+5 | 9b4bcc1 | 11 unused crypto implementations + 3 orphan headers, dead m_defrag, BE200 website/docs/Assets, README rewrite | 43 changed | ~6.8k |

## Removed hardware support

- Legacy iwn family (1000-6050): entire hal_iwn backend.
- iwm family (7260/3160-9560): entire hal_iwm backend.
- iwx paths for Qu/QuZ (AX200/AX201), ty (AX210), SnJ/MA/QnJ, cc (9560),
  gl/bz (BE200/BE201): trans cfgs, dev_info entries, cfg structs, boot
  workarounds, and (with Tier 3b) their code paths.
- MSI-X interrupt mode (BE attach path only; the AX211 uses single-vector
  MSI + ICT).
- MLD/MLO/EMLSR/TTLM/EHT: the AX211 firmware (API 68) does not contain the
  MLD command ABI (verified in the shipped TLVs — audit D).

## Removed firmware

41 of the original 43 payloads (all iwm-*, iwn-*, and every iwlwifi-*
family except so-a0-gf-a0). Retained: iwlwifi-so-a0-gf-a0-68.ucode +
iwlwifi-so-a0-gf-a0.pnvm — the exact pair the AX211 dev_info walk resolves
to (audit D cross-check f). Embedded payload size: ~42 MB → ~1.6 MB.

## Removed targets / schemes

Native targets 13 → 2 (AirportItlwm-Sequoia, AirportItlwm-Tahoe) + fw_gen.
Schemes 5 → 2 (Sequoia, Tahoe); the kept schemes' ProfileAction references
were repaired (they pointed at the deleted Big Sur target).

## Retained shared dependencies (explicitly verified)

- The complete net80211 port + its 14-consumer crypto set
- The V2/WCL/Skywalk integration and both platform header sets
  (include/Airport/macOS15 + macOS26) — never merged
- The legacy iwx command ABI: MAC ctxt v5, binding v2, PHY v3+RLC,
  ADD_STA v12, ADD_STA_KEY, STA_HE_CTXT v2, TLC v3, SCAN v14, NVM v4,
  PNVM, aux-sta/phy-ctxt loop, legacy AWDL listener/aux-ROC/P2P,
  defer_sae_join, software PMF (BIP-CMAC-128)
- Regulatory enforcement (NVM channel tables, LAR/MCC, passive/DFS,
  beacon hints)
- Recovery and diagnostics infrastructure

## Build results per stage (GitHub Actions, macos-15-intel, Xcode 16.4)

| Stage | Run | Sequoia | Tahoe |
|---|---|---|---|
| Baseline (untouched upstream) e73c117 | 44750197829 | pass | pass |
| Tier 1 87c95e1 | 44760253105 | pass | pass |
| Tier 2 67727ba | 44760565786 | fail (IWM_MIN_DBM) → fixed a827dec | — |
| Tier 3a a827dec | 44762035734 | fail (LE_READ_6) → fixed 2151742 | — |
| Tier 3b a5d2800 | 44767010613 | fail (4 errors) → fixed 2637c6b | — |
| Tier 3 complete 2637c6b | 44767478977 | pass | pass |
| Fix batch 4f09d44 | 44768950788 | pass | pass |
| Review fixes ad5fac4 + Tier 4/5 9b4bcc1 | (see FINAL-VERIFICATION-REPORT.md) | | |

Each build failure was diagnosed from the compiler logs (all three were
cross-file symbol dependencies the hal/platform removal severed:
IWM_MIN_DBM, LE_READ_6, and four MLD leftovers) and fixed at the root
cause; no functionality was disabled to work around a failure.

## Size changes

- Source tree: 323 → 244 tracked source files; ~161k → ~101k lines.
- Compile units per target: 114 (upstream all-target union) → 80
  (Sequoia/Tahoe in upstream) → 51 (final).
- Firmware embedded in the binary: ~42 MB → ~1.6 MB; expected kext binary
  size ~7 MB → ~3 MB (CI artifacts record the exact sizes).
- PCI match: 91 IDs → 6 AX211-family IDs; device tables 27/209 → 6/24
  entries.
