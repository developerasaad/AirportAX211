# AX211 Reduction Plan (Phase F) — AirportAX211

Controlled reduction of the Eric-AirportItlwm snapshot to the AX211-only
scope for MSI Modern 14 C12MO (Intel AX211, PCI 8086:51f0) on macOS
Sequoia 15.8.2 + Tahoe 26.7.x (x86_64). Evidence base:
`audit-notes/subagent-{A,B,C,D,E,F,G}-*.md`.

Principles: remove only what is proven unreachable for the AX211 on both
targets; keep every shared dependency; never merge the Sequoia/Tahoe ABI
surfaces; never touch regulatory enforcement, security validation, error
handling, or recovery.

## Tier 1 — remove unrelated platform support

Keep ONLY AirportItlwm-Sequoia and AirportItlwm-Tahoe native targets
(+ fw_gen aggregate they depend on).

Remove:
- Native targets: itlwm, AirportItlwm-High Sierra, -Mojave, -Catalina,
  -Big Sur, -Monterey, -Ventura, -Sonoma14.0, -Sonoma14.4, -GoldenGate
- Schemes: AirportItlwm (all), AirportItlwm-GoldenGate, itlwm; fix
  ProfileAction refs in kept schemes (they point at Big Sur target)
- Sources compiled only into removed targets: itlwm/itlwm.cpp,
  itlwm/ItlNetworkUserClient.cpp, itlwm/pm.cpp,
  AirportItlwm/AirportItlwm.cpp, AirportItlwmInterface.cpp,
  AirportItlwmSTAIOCTL.cpp, AirportItlwmVirtualIOCTL.cpp,
  AirportAWDL.cpp (legacy V1 files — NOT the V2 set)
- AirportItlwm-Monterey-Info.plist, AirportItlwm-Sonoma-Info.plist,
  itlwm/Info.plist (verify no kept target references them first)
- pbxproj housekeeping: dead (null) PBXBuildFile entries, duplicated
  fileRefs, broken Frameworks section objects

Hazards (from F): shared Sources phase F8D94CA5 (S14.4/Tahoe/GoldenGate)
must survive GoldenGate+Sonoma removal — edit only target objects and
their buildConfigurationList/dependency edges, not shared phases; Sequoia
phase AFFBDFD0 reuses BuildFile IDs F8D94CA6-F8D94CEE — keep both phases
consistent.

Verification: xcodebuild -target AirportItlwm-Sequoia and -Tahoe build
clean in CI; grep pbxproj for removed target names.

## Tier 2 — remove unrelated Intel hardware families

Remove:
- itlwm/hal_iwm/ (16 files) and itlwm/hal_iwn/ (2 files) — separate
  drivers for 7260-9560 and legacy cards; zero consumers of net80211
  security/HE features (D cross-check g)
- Their compile-phase entries (17 entries per live Sources phase)
- hal family dispatch in the kept entry point (AirportItlwmV2 /
  IOPCIEDeviceWrapper construct only ItlIwx after reduction; keep the
  HAL service interface)
- Firmware: all iwm-*/iwn-* files (22 files)
- AirportItlwmV2.hpp:30-32 includes ItlIwm/ItlIwn headers — remove

Note: keep include/HAL/ItlHalService structure intact (itlwm.hpp class
hierarchy) — verify what the V2 driver actually instantiates.

Verification: CI builds both targets; no unresolved ItlIwm/ItlIwn symbols.

## Tier 3 — specialize Intel IWX for AX211

Remove (all proven BE-only / AX211-dead, D cross-checks a-e):
- itlwm/hal_iwx/ItlIwxApi86.cpp + if_iwxapi86.h (BE scan v17; AX211 fw
  advertises v14; RNR hints consumed only there — behavior-neutral)
- itlwm/hal_iwx/ItlIwxMld.cpp + if_iwxmld.h (MLD ABI absent from AX211
  firmware; keep every legacy else-half; ~64 sc_use_mld_api guards to
  clean)
- itlwm/hal_iwx/iwx_be_config.h (BE selection tables)
- MSI-X paths: iwx_intr_msix, BE half of conf_msix_hw, BE attach block,
  BE fw-candidate loop, gen2 ctxt_info_init (AX211 is gen3 IML), BZ
  branches in apm/sw_reset/boot/RX-credits/error-bases, EHT rate helpers,
  SnJ/MA/QnJ device cfgs, MLD AWDL listener/ROC variants, EMLSR/MLO/TTLM
- IOPCIEDeviceWrapper BE branch calling configureInterrupts (Tahoe MSI-X
  API) — then evaluate whether scripts/prepare_tahoe_sdk.py is still
  needed at all (it only patches the SDK header that this branch uses)
- Device tables: reduce PCI table to AX211-family entries; keep
  so-a0-gf-a0 (51f0) + so-a0-gf4-a0 (51f1? verify) + so-a0-hr-b0/jf-b0 +
  ty-a0-gf-a0 ONLY IF they are the same physical AX211 SKU family used
  by the target — DECISION: keep the so-a0-gf-a0 entry (target device)
  plus entries sharing its firmware (so-a0-gf4-a0); drop ty (AX210,
  different card), Qu/QuZ (AX200/201), cc (9560), gl/bz (BE200/201),
  ma/SnJ/QnJ (missing fw). Rationale: PCI personality should match only
  the target NIC family so the kext never binds other hardware.
- Firmware: keep ONLY iwlwifi-so-a0-gf-a0-68.ucode + iwlwifi-so-a0-gf-a0.pnvm
  (D cross-check f: AX211 dev_info resolves to exactly this fw)
- Info.plist IOPCIMatch: reduce to the AX211 family IDs kept above;
  align WCL plists
- D-01 (required by feature preservation): set IEEE80211_C_MFP on the
  legacy (non-BZ) path so WPA3-SAE/PMF/6GHz-OWE activate for AX211
  (software PMF: BIP-CMAC-128 + host IGTK/BIGTK). Evaluate ic_beacon_prot
  separately — record decision.
- E-05: resolve ni_mld_addr copy (branch disappears with MLD removal;
  verify the A-MSDU addr3 path uses the right source for non-MLO peers)

Verification: CI builds both targets; embedded firmware strings show only
so-a0-gf-a0; IOPCIMatch lists AX211 IDs only; C_MFP present in capability
initialization; grep for sc_use_mld_api/sc_scan_active returns nothing.

## Tier 4 — simplify unreachable logic

- Remove m_defrag broken EXT branch (zero callers) — B-N22
- Remove legacy setSCAN_REQ WCL vestige IF confirmed unreachable (C)
- Remove dead snprintf (V2.cpp:1023-1030) — C-2 (may fold into fix pass)
- Remove now-unused iwlwifi firmware references in code (QuQnj names die
  with their PCI entries in Tier 3)
- Grep-driven dead symbol sweep limited to symbols orphaned by Tiers 1-3
  (cross-checked against call graph; conservative — keep anything with
  indirect callers/callback registration)

## Tier 5 — clean the build and documentation

- README.md: rewrite for AirportAX211 (target hardware, build, install,
  status); keep README.zh-CN.md and docs/ site? DECISION: remove docs/
  site + translations + BE200.md + Assets (upstream marketing materials
  for BE200); keep LICENSE, iwlwifi-firmware-license
- scripts/: keep fw_gen.sh, zlib_compress_fw.py; remove load.sh/unload.sh/
  Collect-EricWirelessDiagnostics.command/site/ (dev conveniences, not
  build-required); prepare_tahoe_sdk.py per Tier 3 decision
- .clangd/compile_flags.txt: keep if harmless
- Verify no broken references to removed files remain (grep)

## Per-tier discipline

After each tier: commit (small, reviewable), push, CI both targets,
verify relevant capabilities remain (firmware strings, PCI match, arch,
bundle). No tier combination into single commits.

## Explicitly NOT removed (feature preservation)

net80211 core + SAE/PMF/OWE (incl. D-01 enablement), 14 crypto files
(aes, rijndael, cmac, sha2, sha1, sha1-pbkdf2, hmac, md5, arc4, michael,
key_wrap, ec_p256_m31, i31 — per D), HE/160MHz/6GHz machinery (v14 scan,
HE-op + RNR, PSC), AWDL implementation (boot-arg gated, vtable-anchor
checked — preserved intact), regulatory enforcement, recovery/diagnostics,
legacy AWDL listener/aux-ROC (macOS WCL contract), both platform header
sets (macOS15/macOS26), WCL + V2 integration, private MAC support,
PMKSA/WCL supplicant path.
