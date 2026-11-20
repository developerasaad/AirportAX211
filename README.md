# AirportAX211

AirportAX211 is an Intel AX211 Wi-Fi kernel extension for macOS, specialized
from [Eric-AirportItlwm](https://github.com/Ersiter/Eric-AirportItlwm)
(branch `be200-tahoe`, commit `cf0c5263`) for one machine and two operating
systems:

- **Computer:** MSI Modern 14 C12MO
- **Wireless adapter:** Intel Wi-Fi 6E AX211 160 MHz (PCI 8086:51f0, Alder
  Lake-P CNVi, `so-a0-gf-a0` firmware family, firmware API 68)
- **macOS Sequoia 15.8.2** (Darwin 24.x) — target `AirportItlwm-Sequoia`
- **macOS Tahoe 26.7.x** (Darwin 25.x) — target `AirportItlwm-Tahoe`

Both products are x86_64 only and use the native AirportItlwm V2/WCL/Skywalk
integration (IO80211Family V2). The two kexts share one source set; platform
ABI differences are selected at compile time and must not be mixed — the
OpenCore config should constrain each build to its Darwin version
(`Darwin 24` for the Sequoia kext, `Darwin 25` for the Tahoe kext).

## Status

Experimental. Builds are produced and verified by GitHub Actions (macOS
runner, pinned MacKernelSDK); see the workflow runs for artifacts with
checksums. Nothing has been hardware-validated on the target machine yet —
see `research/FINAL-VERIFICATION-REPORT.md` for the current verification
state and the owner test procedure.

## Features

WPA2-Personal, WPA2/WPA3 transition, WPA3-Personal SAE (H2E, group 19),
WPA2-Enterprise (EAPOL pass-through with macOS supplicant + PMKSA),
PMF/802.11w (software BIP-CMAC-128), OWE, 802.11a/b/g/n/ac/ax (Wi-Fi 6 HE
incl. 160 MHz), 2.4/5/6 GHz with regulatory enforcement (LAR/MCC + NVM
channel tables), native macOS Wi-Fi management, private/random MAC address
support, sleep/wake handling, and an experimental AWDL implementation
(disabled by default via the `-itlawdl` boot argument, with a runtime
vtable-anchor check).

Unsupported and intentionally removed: every other Intel adapter family
(AX200/AX201/AX210, Wireless-AC, legacy, BE200/BE201), firmware API 89+,
and all macOS versions other than Sequoia and Tahoe.

## Building

No local Xcode is needed; CI is the authoritative build environment. For a
manual build, open `itlwm.xcodeproj` and build the `AirportItlwm-Sequoia`
or `AirportItlwm-Tahoe` target (requires MacKernelSDK pinned at
`3f750085caa17ec3a7880f11c11bf4f48cd6a164` and Xcode 16.x). The firmware
blob is generated at build time by the `fw_gen` target from
`itlwm/firmware/`.

## Engineering records

The `research/` directory documents the migration from the upstream source,
the audit findings, the reduction plan and its execution, the transfer of
the previous implementation's corrections, and the verification state.

## Licensing

GPL-2.0 (see `LICENSE`), with the Intel firmware under its own license
(`iwlwifi-firmware-license`). The upstream project and its contributors
are credited in the Git history and in `research/PROVENANCE.md`.
