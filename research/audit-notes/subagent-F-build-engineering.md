# Subagent F — Build-Engineering & Source-Reduction Audit (M3-F)

Scope: `itlwm.xcodeproj/project.pbxproj` (4677 lines, objectVersion 48), 5 shared schemes,
`scripts/*`, `.github/workflows/main.yml`, all Info.plists, `include/FwData.h`,
`.clangd`/`compile_flags.txt`/`.gitattributes`, firmware pipeline. READ-ONLY audit.
All `file:line` references are to `itlwm.xcodeproj/project.pbxproj` unless another file is named.

Live targets for this project: **AirportItlwm-Sequoia** (macOS 15, Darwin 24) and
**AirportItlwm-Tahoe** (macOS 26, Darwin 25), x86_64, Intel AX211 (8086:51f0).

---

## 1. Target inventory

`PBXProject.targets` list: pbxproj:2611–2625 (13 entries, 12 native + 1 aggregate).

| Target | ID (pbxproj object) | Type / product | Config list | Sources phase | Deps | Scheme(s) referencing |
|---|---|---|---|---|---|---|
| itlwm | `024A07AB23FCBC3C009FBA6C` (:2327) | kernel-extension → `itlwm.kext` (:2343) | `024A07B6` (:4557) | `024A07A8` (:2725) | `5066D63E` → fw_gen (:2339) | `itlwm.xcscheme` (Blueprint 024A07AB…) |
| AirportItlwm-High Sierra | `35CBE72A251CB8CA00435CBC` (:2384) | kext → AirportItlwm.kext | `35CBE78C` (:4584) | `35CBE745` (:2978) | `5066D640` → fw_gen (:2396) | "AirportItlwm (all)" |
| AirportItlwm-Mojave | `35CBE6BF251CB8BF00435CBC` (:2365) | kext | `35CBE721` (:4575) | `35CBE6DA` (:2893) | `5066D642` → fw_gen (:2377) | "AirportItlwm (all)" |
| AirportItlwm-Catalina | `F89B6BB825021C9C000F77FF` (:2422) | kext | `F89B6BC0` (:4611) | `F89B6BB5` (:3149) | `5066D644` → fw_gen (:2434) | "AirportItlwm (all)" |
| AirportItlwm-Big Sur | `35CBE655251CB89700435CBC` (:2346) | kext | `35CBE6B7` (:4566) | `35CBE670` (:2808) | `5066D646` → fw_gen (:2358) | "AirportItlwm (all)"; **ProfileAction MacroExpansion of the Sequoia, Tahoe, GoldenGate and "(all)" schemes** (stale) |
| AirportItlwm-Monterey | `F897ECB6266EFF93005EE8F7` (:2403) | kext | `F897ED15` (:4602) | `F897ECCA` (:3063) | `F897ECB7` → fw_gen (:2415) | "AirportItlwm (all)" |
| AirportItlwm-Ventura | `F8AE64F5285471560085B4CF` (:2441) | kext | `F8AE6555` (:4620) | `F8AE6509` (:3234) | `F8AE64F6` → fw_gen (:2453) | "AirportItlwm (all)" |
| AirportItlwm-Sonoma14.0 | `F8B210A72A2EC2680043ECBD` (:2460) | kext | `F8B21107` (:4629) | `F8B210BB` (:3320) | `F8B210A8` → fw_gen (:2472) | "AirportItlwm (all)" |
| AirportItlwm-Sonoma14.4 | `F8D94C802B9ABFE20081A3C4` (:2479) | kext | `F8D94CF2` (:4638) | `F8D94CA5` (:3405) **shared** | `F8D94C81` → fw_gen (:2491) **shared** | "AirportItlwm (all)" |
| **AirportItlwm-Tahoe** | `A6465A40B44EE5DC353B726B` (:2498) | kext → `AirportItlwm.kext` (:2514) | `1DF97670B7FC55991F338AA4` (:4647) | `F8D94CA5` (:2503) **same object as Sonoma14.4** | `F8D94C81` (:2510) **same object** | `AirportItlwm-Tahoe.xcscheme`, "AirportItlwm (all)" |
| AirportItlwm-GoldenGate | `B4971F289F589AF39F00A715` (:2517) | kext | `E269A2FD523105737C8438A1` (:4656) | `F8D94CA5` (:2522) **same object** | `F8D94C81` (:2529) **same object** | `AirportItlwm-GoldenGate.xcscheme` only |
| fw_gen (aggregate) | `5066D63825287F7900EE6F38` (:10) | no product; 1 shell phase "Generate Firmware" `5066D63C` (:14, body :2703–2721) | `5066D63B` (:4593, empty settings) | n/a | none | (built implicitly as dependency) |
| **AirportItlwm-Sequoia** | `C2631DEBF2864F9B8272D88C` (:2536) | kext → `AirportItlwm.kext` (:2552) | `C9DEB043F00A4DCFAC3294DD` (:4665) | `AFFBDFD057C2402C908ECB89` (:2541, body :3493–3580) | `F8D94C81` (:2548) **same dependency object as Sonoma14.4/Tahoe/GoldenGate** | `AirportItlwm-Sequoia.xcscheme`, "AirportItlwm (all)" |

Key structural facts:

* **Every kext target depends on `fw_gen`** (all 9 `PBXTargetDependency` objects at :3584–3628 point to
  `5066D638` with their own `PBXContainerItemProxy` at :1049–1111). fw_gen has **no** dependencies.
* **Tahoe, GoldenGate and Sonoma14.4 share the exact same four build-phase objects** (Headers
  `F8D94C83` :2502/2521/2483, Sources `F8D94CA5` :2503/2522/2484, Frameworks `F8D94CEF`
  :2504/2523/2485, Resources `F8D94CF1` :2505/2524/2486) and the same dependency object
  `F8D94C81`. They differ **only** in build configuration lists. Sequoia has its own phase objects
  but **reuses Sonoma14.4's PBXBuildFile IDs** and its dependency object.
* `PBXProject.TargetAttributes` (:2563–2597) has entries for itlwm, Big Sur, Mojave, High Sierra,
  fw_gen, Monterey, Catalina, Ventura, Sonoma14.0, Sonoma14.4 — **not** for Tahoe/GoldenGate/Sequoia
  (hand-added targets). Harmless.
* All Resources phases are empty (e.g. :2630–2699). Frameworks phases link only
  `MacKernelSDK/Library/x86_64/libkmod.a` (fileRef :1205; e.g. Sequoia phase `1A48D424` :1493–1500
  uses build file `F8D94CF0` defined :978 — shared with Sonoma14.4/Tahoe/GoldenGate).

### Schemes (`itlwm.xcodeproj/xcshareddata/xcschemes/`)

* `AirportItlwm-Sequoia.xcscheme` — builds `C2631DEB…` (Sequoia). **ProfileAction MacroExpansion
  points at `35CBE655…` "AirportItlwm-Big Sur"** (scheme lines 57–65) — stale; breaks if Big Sur is deleted.
* `AirportItlwm-Tahoe.xcscheme` — builds `A6465A40…` (Tahoe). Same stale Big Sur MacroExpansion (lines 50–58).
* `AirportItlwm (all).xcscheme` — builds 10 targets: Big Sur, Catalina, High Sierra, Mojave, Monterey,
  Ventura, Sonoma14.0, Sonoma14.4, Tahoe, Sequoia (lines 15–148). **GoldenGate and itlwm are NOT in it.**
  ProfileAction → Big Sur (lines 176–184).
* `AirportItlwm-GoldenGate.xcscheme` — builds `B4971F28…`. ProfileAction → Big Sur (lines 50–58).
* `itlwm.xcscheme` — builds itlwm target.

---

## 2. AirportItlwm-Sequoia — complete compile list (Sources phase `AFFBDFD057C2402C908ECB89`, pbxproj:3493–3580)

80 real source files + 1 dead `(null)` entry (:3542). Order as in the file:

| # | Source file (tree-relative) | BuildFile ID | phase line |
|---|---|---|---|
| 1 | AirportItlwm/AirportItlwmAWDLInterface.cpp | `7C41E0B35A2D4F8E9B6A1D03` (def :625) | 3497 |
| 2 | itl80211/openbsd/crypto/ec_p256_m31.c | `E6B00D0FB5D540779710EAF1` (def :1025) | 3498 |
| 3 | itl80211/openbsd/crypto/i31.c | `B31CA34654BF4976A305CCE7` (def :1035) | 3499 |
| 4 | itl80211/openbsd/net80211/ieee80211_sae.c | `1113DC0822F6441DB271CD90` (def :1045) | 3500 |
| 5 | itl80211/ItlDma.cpp | `A7D000012026100700000001` (def :1015) | 3501 |
| 6 | itlwm/hal_iwm/rs.cpp | `F8D94CA62B9ABFE20081A3C4` | 3502 |
| 7 | itl80211/openbsd/sys/_mbuf.cpp | `F8D94CA72B9ABFE20081A3C4` | 3503 |
| 8 | itl80211/openbsd/net80211/ieee80211_ra.c | `F8D94CA82B9ABFE20081A3C4` | 3504 |
| 9 | itl80211/openbsd/sys/_task.cpp | `F8D94CA92B9ABFE20081A3C4` | 3505 |
| 10 | include/FwBinary.cpp (generated) | `F8D94CAA2B9ABFE20081A3C4` (def :907) | 3506 |
| 11 | itl80211/openbsd/net80211/ieee80211_proto.c | `F8D94CAB…` | 3507 |
| 12 | itl80211/openbsd/net80211/_string.c | `F8D94CAC…` | 3508 |
| 13 | itl80211/openbsd/net80211/ieee80211_ioctl.c | `F8D94CAD…` | 3509 |
| 14 | itl80211/openbsd/net80211/ieee80211.c | `F8D94CAE…` | 3510 |
| 15 | itl80211/openbsd/net80211/ieee80211_rssadapt.c | `F8D94CAF…` | 3511 |
| 16 | itl80211/openbsd/net80211/ieee80211_input.c | `F8D94CB0…` | 3512 |
| 17 | itl80211/openbsd/net80211/timeout.c | `F8D94CB1…` | 3513 |
| 18 | itl80211/openbsd/net80211/ieee80211_mira.c | `F8D94CB2…` | 3514 |
| 19 | itl80211/openbsd/net80211/ieee80211_crypto_bip.c | `F8D94CB3…` | 3515 |
| 20 | itl80211/openbsd/net80211/ieee80211_crypto_tkip.c | `F8D94CB4…` | 3516 |
| 21 | itl80211/openbsd/net80211/ieee80211_crypto_ccmp.c | `F8D94CB5…` | 3517 |
| 22 | itl80211/openbsd/net80211/ieee80211_crypto_wep.c | `F8D94CB6…` | 3518 |
| 23 | itl80211/openbsd/net80211/ieee80211_pae_input.c | `F8D94CB7…` | 3519 |
| 24 | itl80211/openbsd/net80211/ieee80211_amrr.c | `F8D94CB8…` | 3520 |
| 25 | itl80211/openbsd/net80211/ieee80211_output.c | `F8D94CB9…` | 3521 |
| 26 | itl80211/openbsd/net80211/ieee80211_crypto.c | `F8D94CBA…` | 3522 |
| 27 | itl80211/openbsd/net80211/CTimeout.cpp | `F8D94CBB…` | 3523 |
| 28 | itl80211/openbsd/net80211/ieee80211_regdomain.c | `F8D94CBC…` | 3524 |
| 29 | itl80211/openbsd/net80211/ieee80211_node.c | `F8D94CBD…` | 3525 |
| 30 | itl80211/openbsd/net80211/ieee80211_pae_output.c | `F8D94CBE…` | 3526 |
| 31 | itl80211/openbsd/crypto/sha1-pbkdf2.c | `F8D94CBF…` | 3527 |
| 32 | itl80211/openbsd/crypto/aes.c | `F8D94CC0…` | 3528 |
| 33 | itl80211/openbsd/crypto/hmac.c | `F8D94CC1…` | 3529 |
| 34 | itl80211/openbsd/crypto/sha2.c | `F8D94CC2…` | 3530 |
| 35 | itl80211/openbsd/crypto/rijndael.c | `F8D94CC3…` | 3531 |
| 36 | itl80211/openbsd/crypto/ecb3_enc.c | `F8D94CC4…` | 3532 |
| 37 | itl80211/openbsd/crypto/set_key.c | `F8D94CC5…` | 3533 |
| 38 | itl80211/openbsd/crypto/cast.c | `F8D94CC6…` | 3534 |
| 39 | itl80211/openbsd/crypto/michael.c | `F8D94CC7…` | 3535 |
| 40 | itl80211/openbsd/sys/arp.c | `F8D94CC8…` | 3536 |
| 41 | itl80211/openbsd/crypto/sha1.c | `F8D94CC9…` | 3537 |
| 42 | itl80211/openbsd/crypto/cmac.c | `F8D94CCA…` | 3538 |
| 43 | itl80211/openbsd/crypto/ecb_enc.c | `F8D94CCB…` | 3539 |
| 44 | itl80211/openbsd/crypto/chachapoly.c | `F8D94CCC…` | 3540 |
| 45 | AirportItlwm/AirportItlwmV2.cpp | `F8D94CCD…` (def :942) | 3541 |
| 46 | *(null — dead entry)* | `F8D94CCE…` (def :943) | 3542 |
| 47 | itl80211/openbsd/crypto/md5.c | `F8D94CCF…` (def :944) | 3543 |
| 48 | itl80211/openbsd/crypto/arc4.c | `F8D94CD0…` (def :945) | 3544 |
| 49 | AirportItlwm/AirportItlwmEthernetInterface.cpp | `F8D94CD1…` (def :946) | 3545 |
| 50 | AirportItlwm/AirportItlwmSkywalkInterface.cpp | `F8D94CD2…` (def :947) | 3546 |
| 51 | AirportItlwm/WCL/WCL.cpp | `A112F5371BD949CD8CA19D88` (def :24; fileRef :1115) | 3547 |
| 52 | itl80211/openbsd/crypto/blf.c | `F8D94CD3…` | 3548 |
| 53 | itl80211/openbsd/sys/_ifq.cpp | `F8D94CD4…` | 3549 |
| 54 | itl80211/openbsd/crypto/poly1305.c | `F8D94CD5…` | 3550 |
| 55 | itl80211/openbsd/crypto/key_wrap.c | `F8D94CD6…` | 3551 |
| 56 | itl80211/openbsd/crypto/gmac.c | `F8D94CD7…` | 3552 |
| 57 | itl80211/openbsd/crypto/rmd160.c | `F8D94CD8…` | 3553 |
| 58 | itl80211/openbsd/crypto/idgen.c | `F8D94CD9…` | 3554 |
| 59 | itl80211/compat.cpp | `F8D94CDA…` (def :955) | 3555 |
| 60 | itl80211/zutil.c | `F8D94CDB…` (def :956) | 3556 |
| 61 | include/HAL/ItlHalService.cpp | `F8D94CDC…` (def :957) | 3557 |
| 62 | itlwm/hal_iwx/ItlIwx.cpp | `F8D94CDD…` (def :958) | 3558 |
| 63 | itlwm/hal_iwx/ItlIwxMld.cpp | `14BA3EB9CA00385AEA097AC1` (def :960) | 3559 |
| 64 | itlwm/hal_iwx/ItlIwxApi86.cpp | `05CE876E5DD1273BACA2257F` (def :959) | 3560 |
| 65 | itlwm/hal_iwm/utils.cpp | `F8D94CDE…` (def :961) | 3561 |
| 66 | itlwm/hal_iwm/fw.cpp | `F8D94CDF…` (def :962) | 3562 |
| 67 | itlwm/hal_iwm/io.cpp | `F8D94CE0…` (def :963) | 3563 |
| 68 | itlwm/hal_iwm/rx.cpp | `F8D94CE1…` (def :964) | 3564 |
| 69 | itlwm/hal_iwm/coex.cpp | `F8D94CE2…` (def :965) | 3565 |
| 70 | itlwm/hal_iwm/tx.cpp | `F8D94CE3…` (def :966) | 3566 |
| 71 | itlwm/hal_iwm/hw.cpp | `F8D94CE4…` (def :967) | 3567 |
| 72 | itlwm/hal_iwn/ItlIwn.cpp | `F8D94CE5…` (def :968) | 3568 |
| 73 | itlwm/hal_iwm/phy.cpp | `F8D94CE6…` (def :969) | 3569 |
| 74 | itlwm/hal_iwm/mac80211.cpp | `F8D94CE7…` (def :970) | 3570 |
| 75 | itlwm/hal_iwm/nvm.cpp | `F8D94CE8…` (def :971) | 3571 |
| 76 | itlwm/hal_iwm/ctxt.cpp | `F8D94CE9…` (def :972) | 3572 |
| 77 | itlwm/hal_iwm/led.cpp | `F8D94CEA…` (def :973) | 3573 |
| 78 | itlwm/hal_iwm/power.cpp | `F8D94CEB…` (def :974) | 3574 |
| 79 | itlwm/hal_iwm/scan.cpp | `F8D94CEC…` (def :975) | 3575 |
| 80 | AirportItlwm/IOPCIEDeviceWrapper.cpp | `F8D94CED…` (def :976) | 3576 |
| 81 | itlwm/hal_iwm/ItlIwm.cpp | `F8D94CEE…` (def :977) | 3577 |

Breakdown: 23 openbsd net80211 C files, 21 openbsd crypto C files, 3 openbsd sys C/C++ files
(_mbuf.cpp, _task.cpp, arp.c, _ifq.cpp = 4 counting _ifq), itl80211 top-level 4
(compat.cpp, zutil.c, ItlDma.cpp + ItlHalService.cpp under include/HAL), hal_iwx 3, hal_iwm 16,
hal_iwn 1, FwBinary.cpp 1, AirportItlwm/*.cpp 6 (AWDLInterface, V2, EthernetInterface,
SkywalkInterface, WCL, IOPCIEDeviceWrapper).

---

## 3. AirportItlwm-Tahoe — complete compile list (Sources phase `F8D94CA52B9ABFE20081A3C4`, pbxproj:3405–3492)

**Identical file set to Sequoia — same 80 files + the same dead `(null)` entry** (at :3454).
Only the first four entries use different BuildFile IDs (identical fileRefs):

| # | Source file | BuildFile ID | phase line |
|---|---|---|---|
| 1 | itl80211/openbsd/crypto/ec_p256_m31.c | `F252137DD8A94D81A6C0F630` (def :1024) | 3409 |
| 2 | itl80211/openbsd/crypto/i31.c | `9A14DCCA5C8645CB961EFC29` (def :1034) | 3410 |
| 3 | itl80211/openbsd/net80211/ieee80211_sae.c | `D46644B68CFC4A469AF7F14D` (def :1044) | 3411 |
| 4 | AirportItlwm/AirportItlwmAWDLInterface.cpp | `1EE81010096D5892BA04A0E1` (def :624) | 3412 |
| 5 | itl80211/ItlDma.cpp | `A7D000012026100700000001` | 3413 |

Entries 6–81 (lines 3414–3489) use **the same `F8D94CA6…`–`F8D94CEE…` BuildFile IDs as the Sequoia
phase** (shared PBXBuildFile objects across two phases): rs.cpp :3414, _mbuf.cpp :3415,
ieee80211_ra.c :3416, _task.cpp :3417, FwBinary.cpp :3418, ieee80211_proto.c :3419, _string.c :3420,
ieee80211_ioctl.c :3421, ieee80211.c :3422, ieee80211_rssadapt.c :3423, ieee80211_input.c :3424,
timeout.c :3425, ieee80211_mira.c :3426, ieee80211_crypto_bip.c :3427, ieee80211_crypto_tkip.c :3428,
ieee80211_crypto_ccmp.c :3429, ieee80211_crypto_wep.c :3430, ieee80211_pae_input.c :3431,
ieee80211_amrr.c :3432, ieee80211_output.c :3433, ieee80211_crypto.c :3434, CTimeout.cpp :3435,
ieee80211_regdomain.c :3436, ieee80211_node.c :3437, ieee80211_pae_output.c :3438,
sha1-pbkdf2.c :3439, aes.c :3440, hmac.c :3441, sha2.c :3442, rijndael.c :3443, ecb3_enc.c :3444,
set_key.c :3445, cast.c :3446, michael.c :3447, arp.c :3448, sha1.c :3449, cmac.c :3450,
ecb_enc.c :3451, chachapoly.c :3452, AirportItlwmV2.cpp :3453, **(null)** :3454, md5.c :3455,
arc4.c :3456, AirportItlwmEthernetInterface.cpp :3457, AirportItlwmSkywalkInterface.cpp :3458,
**WCL.cpp :3459**, blf.c :3460, _ifq.cpp :3461, poly1305.c :3462, key_wrap.c :3463, gmac.c :3464,
rmd160.c :3465, idgen.c :3466, compat.cpp :3467, zutil.c :3468, ItlHalService.cpp :3469,
ItlIwx.cpp :3470, ItlIwxMld.cpp :3471, ItlIwxApi86.cpp :3472, utils.cpp :3473, fw.cpp :3474,
io.cpp :3475, rx.cpp :3476, coex.cpp :3477, tx.cpp :3478, hw.cpp :3479, ItlIwn.cpp :3480,
phy.cpp :3481, mac80211.cpp :3482, nvm.cpp :3483, ctxt.cpp :3484, led.cpp :3485, power.cpp :3486,
scan.cpp :3487, IOPCIEDeviceWrapper.cpp :3488, ItlIwm.cpp :3489.

**Sequoia vs Tahoe delta: NONE in source content.** The two targets compile byte-identical source
sets (only entry ordering and 4 BuildFile IDs differ). Sequoia/Tahoe vs everything else is where the
differences are (see §4).

Headers phases (no compile impact, but part of the project graph): Sequoia `3B64F623…` (:2284–2323)
and Sonoma14.4/Tahoe/GoldenGate `F8D94C83…` (:2244–2283) contain the same 31 headers + 2 `(null)`
entries (incl. `AirportItlwm.hpp`, `AirportItlwmV2.hpp`, `IOPCIEDeviceWrapper.hpp`,
`AirportItlwmSkywalkInterface.hpp`, `AirportItlwmEthernetInterface.hpp`, Airport SDK headers) and
share the same BuildFile IDs `F8D94C84…`–`F8D94CA4…` (defs :870–898).

---

## 4. Other native targets — what they compile; itlwm-target-only files

Membership matrix (from full parse of all 10 Sources phases; counts: itlwm 76, HS/Mojave/Catalina/BigSur
78, Monterey 79, Ventura 79, Sonoma14.0 78, Sonoma14.4/Tahoe/GG 81, Sequoia 81 — each incl. dead `(null)`):

* **Common core (73 files) compiled by ALL 10 kext targets** (itlwm + 6 legacy + Sonoma14.0 + S14.4/Tahoe/GG + Sequoia):
  * itl80211/openbsd/net80211: ieee80211.c, ieee80211_amrr.c, ieee80211_crypto.c, ieee80211_crypto_bip.c,
    ieee80211_crypto_ccmp.c, ieee80211_crypto_tkip.c, ieee80211_crypto_wep.c, ieee80211_input.c,
    ieee80211_ioctl.c, ieee80211_mira.c, ieee80211_node.c, ieee80211_output.c, ieee80211_pae_input.c,
    ieee80211_pae_output.c, ieee80211_proto.c, ieee80211_ra.c, ieee80211_regdomain.c,
    ieee80211_rssadapt.c, ieee80211_sae.c, timeout.c, CTimeout.cpp, _string.c
  * itl80211/openbsd/crypto: aes.c arc4.c blf.c cast.c chachapoly.c cmac.c ecb3_enc.c ecb_enc.c
    ec_p256_m31.c gmac.c hmac.c i31.c idgen.c key_wrap.c md5.c michael.c poly1305.c rijndael.c
    rmd160.c sha1.c sha1-pbkdf2.c sha2.c
  * itl80211/openbsd/sys: _mbuf.cpp, _task.cpp, _ifq.cpp, arp.c
  * itl80211 top: compat.cpp, zutil.c; include/HAL/ItlHalService.cpp; include/FwBinary.cpp
  * itlwm/hal_iwm (16): ItlIwm.cpp coex.cpp ctxt.cpp fw.cpp hw.cpp io.cpp led.cpp mac80211.cpp
    nvm.cpp phy.cpp power.cpp rs.cpp rx.cpp scan.cpp tx.cpp utils.cpp
  * itlwm/hal_iwn (1): ItlIwn.cpp
  * itlwm/hal_iwx (3): ItlIwx.cpp, ItlIwxApi86.cpp, ItlIwxMld.cpp
* **itlwm target only (3 files, phase `024A07A8` :2725–2807):**
  * `itlwm/itlwm.cpp` — BuildFile `024A07B223FCBC3C009FBA6C` (def :26), phase line :2764
  * `itlwm/ItlNetworkUserClient.cpp` — `F8E49A14249B923500BE6868` (def :979), phase line :2785
  * `itlwm/pm.cpp` — `F8D76362244F21BB00DEA040` (def :869), phase line :2796
  (itlwm also does **not** compile any `AirportItlwm/*.cpp` file.)
* **Legacy Airport targets only (Big Sur :2808, Mojave :2893, High Sierra :2978, Monterey :3063,
  Catalina :3149, Ventura :3234 — all compile the same set):** the 73 core +
  `AirportItlwm/AirportItlwm.cpp` (e.g. :2887), `AirportItlwm/AirportItlwmInterface.cpp` (:2821),
  `AirportItlwm/AirportSTAIOCTL.cpp` (:2886), `AirportItlwm/AirportVirtualIOCTL.cpp` (:2888),
  `AirportItlwm/AirportAWDL.cpp` (:2889). Monterey (:3109) and Ventura (:3280) phases each have one
  extra dead `(null)` entry.
* **Sonoma14.0 (phase `F8B210BB` :3320–3404):** 73 core + `AirportItlwmV2.cpp` (:3366),
  `AirportItlwmEthernetInterface.cpp` (:3370), `AirportItlwmSkywalkInterface.cpp` (:3371),
  `IOPCIEDeviceWrapper.cpp` (:3400) + dead `(null)` (:3367). **No WCL.cpp, no AirportItlwmAWDLInterface.cpp,
  no ItlDma.cpp.**
* **Sonoma14.4 / Tahoe / GoldenGate (phase `F8D94CA5`):** = Sequoia set (see §3).
* Therefore **files compiled ONLY into targets slated for deletion**:
  * From the itlwm target: `itlwm/itlwm.cpp`, `itlwm/ItlNetworkUserClient.cpp`, `itlwm/pm.cpp`
  * From the 6 legacy Airport targets: `AirportItlwm/AirportItlwm.cpp`, `AirportItlwm/AirportItlwmInterface.cpp`,
    `AirportItlwm/AirportSTAIOCTL.cpp`, `AirportItlwm/AirportVirtualIOCTL.cpp`, `AirportItlwm/AirportAWDL.cpp`
  * Nothing else: every other compiled file is also in Sequoia/Tahoe.
  * Headers only used by deleted targets (Headers phases are inert for kexts, but for completeness):
    e.g. `itlwm.hpp`, `ItlNetworkUserClient.hpp` (itlwm Headers phase :1917–1990), legacy Airport
    header sets in the 28-entry phases.

---

## 5. Build settings: Sequoia vs Tahoe (quoted)

Project-level settings inherited by both (Debug `024A07B4` :3632–3702, Release `024A07B5` :3703–3774):

```
ARCHS = x86_64;                                        (:3636)
GCC_INPUT_FILETYPE = sourcecode.cpp.cpp;               (:3672)
GCC_PREPROCESSOR_DEFINITIONS = ( DEBUG=1 /*Debug only*/, "$(inherited)",
    "ITLWM_VERSION=\"${MODULE_VERSION}\"", "GIT_COMMIT=\"${GIT_COMMIT}\"",
    IEEE80211_STA_ONLY );                              (:3675–3681 / :3747–3751)
GIT_COMMIT = "_FIX31_20261109";                        (:3688 — overridden by CI)
KERNEL_EXTENSION_HEADER_SEARCH_PATHS = "$(PROJECT_DIR)/MacKernelSDK/Headers";   (:3689)
KERNEL_FRAMEWORK_HEADERS = "$(PROJECT_DIR)/MacKernelSDK/Headers";               (:3690)
MACOSX_DEPLOYMENT_TARGET = 10.12;   (project default)  (:3691)
MODULE_VERSION = 2.4.0;                                (:3692)
SDKROOT = macosx;  CLANG_CXX_LIBRARY = "libc++";  CLANG_CXX_LANGUAGE_STANDARD = "gnu++14";
GCC_C_LANGUAGE_STANDARD = c11;  CODE_SIGN_IDENTITY = "";  CODE_SIGN_STYLE = Manual;
OTHER_CPLUSPLUSFLAGS = ("-Wno-deprecated-register", "$(OTHER_CFLAGS)");
```

**AirportItlwm-Sequoia** — Debug `2B4AD1BBF0014C848E6A7F18` (:4373–4405), Release
`E71DD1C8720A4A5E8D09A1CD` (:4511–4543):

```
CONFIGURATION_BUILD_DIR = "$(SYMROOT)/$(CONFIGURATION)/Sequoia";                  (:4376)
GCC_PRECOMPILE_PREFIX_HEADER = YES;  GCC_PREFIX_HEADER = itlwm/PrivateSPI.pch;     (:4378–4379)
GCC_PREPROCESSOR_DEFINITIONS = (
    AIRPORT_WCL,
    AIRPORT_VTD,
    "$(inherited)",
    AIRPORT,
    "__IO80211_TARGET=__MAC_15_2",
    __PRIVATE_SPI__,
    IO80211FAMILY_V2,
);                                                                                 (:4380–4388)
INFOPLIST_FILE = "AirportItlwm/WCL/Sequoia-Info.plist";                            (:4389)
LIBRARY_SEARCH_PATHS = ( "$(PROJECT_DIR)/itl80211", "$(inherited)",
    "$(PROJECT_DIR)/itl80211/openbsd", "$(PROJECT_DIR)/itl80211/linux",
    "$(PROJECT_DIR)/MacKernelSDK/Library/x86_64" );                                (:4390–4396)
MACOSX_DEPLOYMENT_TARGET = 15.2;                                                   (:4397)
MODULE_NAME = com.zxystd.AirportItlwm;
PRODUCT_BUNDLE_IDENTIFIER = com.zxystd.AirportItlwm;
PRODUCT_MODULE_NAME = AirportItlwm;  PRODUCT_NAME = AirportItlwm;                  (:4398–4401)
SYSTEM_HEADER_SEARCH_PATHS = "itl80211/openbsd itl80211 include";                  (:4402)
WRAPPER_EXTENSION = kext;                                                          (:4403)
```

**AirportItlwm-Tahoe** — Debug `7D5753727745775F75788913` (:4339–4371), Release
`D92AB006FB4B2B6A6032F9C7` (:4407–4439): **identical except four values:**

```
CONFIGURATION_BUILD_DIR = "$(SYMROOT)/$(CONFIGURATION)/Tahoe";                     (:4342)
"__IO80211_TARGET=__MAC_26_0",                                                     (:4351)
INFOPLIST_FILE = "AirportItlwm/WCL/Info.plist";                                    (:4355)
MACOSX_DEPLOYMENT_TARGET = 10.15;                                                  (:4363 — upstream quirk; kept low)
```

So the **entire Sequoia↔Tahoe delta** is: `CONFIGURATION_BUILD_DIR` suffix, `__IO80211_TARGET`
(`__MAC_15_2` vs `__MAC_26_0`), `INFOPLIST_FILE` (WCL/Sequoia-Info.plist vs WCL/Info.plist — the two
plists are content-identical, see §7), and `MACOSX_DEPLOYMENT_TARGET` (15.2 vs 10.15).

For reference, GoldenGate (`DA37A85619F71149F3AE205F` :4441–4474 Debug, `6170BC8AD74887C5A427532F`
:4476–4509 Release) = Tahoe settings **plus** `ITL_MACOS27` define (:4450, :4485) — a macOS 27
development variant. Sonoma14.4 (`F8D94CF3/F4` :4275–4337) defines only
`AIRPORT, "__IO80211_TARGET=__MAC_14_4", __PRIVATE_SPI__, IO80211FAMILY_V2` (no `AIRPORT_WCL`,
no `AIRPORT_VTD`) and uses `AirportItlwm/AirportItlwm-Sonoma-Info.plist`.

Notes:
* There is **no `HEADER_SEARCH_PATHS` pointing at `include/Airport/macOS15` or `macOS26`** — platform
  header selection is purely preprocessor-driven (see §9). The header search path for all targets is
  `SYSTEM_HEADER_SEARCH_PATHS = "itl80211/openbsd itl80211 include"` (e.g. :4402, :4368).
* No per-file compiler flags anywhere (no `settings = {…}`/`ATTRIBUTES` blocks exist in the file).
* `itlwm` target settings (:3775–3828): `INFOPLIST_FILE = itlwm/Info.plist`,
  `PRODUCT_BUNDLE_IDENTIFIER = com.zxystd.itlwm`, `MACOSX_DEPLOYMENT_TARGET = 10.9`, same prefix header
  and search paths — no `AIRPORT*` defines (plain itlwm variant).

---

## 6. Firmware generation pipeline

Flow (verified end-to-end):

1. **Every kext target depends on `fw_gen`** (aggregate target `5066D638`, pbxproj:10–20) via a
   `PBXTargetDependency` + `PBXContainerItemProxy` pair (:3584–3628, :1049–1111).
2. fw_gen's single build phase is the shell script phase **"Generate Firmware"** `5066D63C`
   (:2703–2721):
   * `outputPaths = ("$(PROJECT_DIR)/include/FwBinary.cpp")` (:2716)
   * `shellScript = "scripts/fw_gen.sh -P \"${PROJECT_DIR}/itlwm/firmware/\"\n"` (:2720)
3. **`scripts/fw_gen.sh`** (25 lines): target `${PROJECT_DIR}/include/FwBinary.cpp`; parses `-P
   <dir>`; **incremental skip**: if `FwBinary.cpp` exists and no firmware file, the python script, or
   fw_gen.sh itself is newer, exits 0 (fw_gen.sh:21–23); otherwise runs
   `python3 scripts/zlib_compress_fw.py <target> <fwdir>` (fw_gen.sh:24).
   * Hazard: the freshness check only triggers on *newer* files — deleting/renaming a firmware file
     does **not** regenerate FwBinary.cpp locally (CI always regenerates; the file is not committed).
4. **`scripts/zlib_compress_fw.py`**: `os.walk`s the whole firmware directory and for **every file**
   emits `const unsigned char <name>[] = {…zlib-compressed bytes…};` plus `<name>_size`, then writes
   `const struct FwDesc fwList[] = { IWL_FW("file", var, var_size), … };` and `const int fwNumber = N;`
   (zlib_compress_fw.py:66–95). Header: `#include "FwData.h"` (zlib_compress_fw.py:13–18).
   * Latent bug: `fwList`/`fwNumber` are written inside the `for root, dirs, files` loop — if the
     firmware dir ever gains a subdirectory, duplicate `fwList[]` definitions would be emitted
     (compile error). Currently the directory is flat, so it works.
5. **`include/FwData.h`** declares `struct FwDesc`, `IWL_FW` macro, `extern const struct FwDesc
   fwList[]`, `fwNumber`, and helpers `getFWDescByName()` (linear search by firmware file name) and
   `uncompressFirmware()` using kernel zlib via `zutil.h` (FwData.h:23–70). `itl80211/zutil.c`
   provides the zcalloc/zcfree glue.
6. `include/FwBinary.cpp` is a **generated file, not present in a fresh checkout** (verified: missing
   on disk; fileRef `5076FA7F24CC71E40011B2BB` :1201, group child of `include` :1801). It is compiled
   into **all 10 kext targets** — Sources entries: itlwm :2733 (`F8294FE4`, def :355), Big Sur :2818,
   Mojave/HS/Monterey/Catalina/Ventura/Sonoma14.0 (their `FwBinary.cpp in Sources` entries, e.g.
   :3331), Sonoma14.4/Tahoe/GoldenGate :3418 and Sequoia :3506 (`F8D94CAA`, def :907).
7. **Every target embeds ALL firmware files** — there are no per-target firmware subsets. 43 payload
   files / ~42 MB in `itlwm/firmware/` (8× `iwm-*`, 12× `iwn-*`, 23× `iwlwifi-*` incl. `.pnvm`).
   Selection happens at runtime purely by name (`getFWDescByName`) — for AX211 the iwx config
   `iwlax211_2ax_cfg_so_gf_a0` uses `"iwlwifi-so-a0-gf-a0-68.ucode"` (ItlIwx.cpp:18615–18621) +
   `iwlwifi-so-a0-gf-a0.pnvm`; BE200/BE201 (bz) devices reference `iwlwifi-gl-c0-fm-c0` at api 92
   (iwx_be_config.h:105).
8. The firmware payloads are **not** referenced by any build phase — only by the `firmware`
   PBXGroup `0250B31C23FD768400FF8CEA` (:1620–1661) with 35 PBXFileReference children
   (:1186–1197 iwn-*, :1206–1209 iwm-*, :1217/1261 pnvm, :1312–1315 iwm-*, :1337 pnvm,
   :1347–1358 iwlwifi-*.ucode). Removing a firmware file therefore requires: delete the file, delete
   its PBXFileReference line, delete its line in the group children list — no phase edits.

---

## 7. Info.plist map

| Target(s) | INFOPLIST_FILE (pbxproj) | Content notes |
|---|---|---|
| itlwm | `itlwm/Info.plist` (:3785, :3812) | bundle id `com.zxystd.itlwm`; V1 ethernet kext; `IOPCIPrimaryMatch = 0x00008086&0x0000ffff` (itlwm/Info.plist:32); `IOUserClientClass ItlNetworkUserClient` (:38); contains **hardcoded sample WiFi SSIDs/passwords** (:39–69); OSBundleLibraries: IONetworkingFamily/IOPCIFamily/bsd/iokit/libkern/mach only (:74–88) |
| High Sierra, Mojave, Catalina, Big Sur | `AirportItlwm/Info.plist` (:3843, :3904, :3964, :4099, :4132) | legacy Airport V1; `com.apple.iokit.IO80211Family = 1200.12.2b1`; no IOSkywalk |
| Monterey, Ventura | `AirportItlwm/AirportItlwm-Monterey-Info.plist` (:4037, :4068, :4165, :4196) | `com.apple.iokit.IO80211FamilyLegacy = 600.0`; no IOSkywalk |
| Sonoma14.0, Sonoma14.4 | `AirportItlwm/AirportItlwm-Sonoma-Info.plist` (:4227, :4258, :4289, :4321) | V2 two-personality structure (`NetworkController` → AirportItlwm + `itlwm` → IOPCIEDeviceWrapper, IOProbeScore 70000); OSBundleLibraries: corecapture 1.0.0, **IO80211Family 1.5.0**, IONetworkingFamily 3.2, IOPCIFamily 2.9, **IOSkywalkFamily 1.0**, bsd/iokit/libkern/mach 16.7 |
| **Tahoe**, GoldenGate | `AirportItlwm/WCL/Info.plist` (:4355, :4423, :4458, :4493) | identical structure to Sonoma plist; OSBundleLibraries identical incl. IOSkywalkFamily + corecapture; IOPCIMatch includes `0x51F08086` and `0x51F18086` (WCL/Info.plist:47) |
| **Sequoia** | `AirportItlwm/WCL/Sequoia-Info.plist` (:4389, :4527) | **content-identical to WCL/Info.plist** — `diff` shows only the laobamac XML comment header differs; same IOPCIMatch (line 54) incl. AX211 IDs, same OSBundleLibraries (lines 63–83) |

* `AirportItlwm/WCL/Info.plist` and `AirportItlwm/WCL/Sequoia-Info.plist` have **no
  PBXFileReference** — they exist only as INFOPLIST_FILE strings (invisible in Xcode's navigator).
  `AirportItlwm-Monterey-Info.plist` does have a fileRef (F883EC1F, :1230) and is a group child
  (:1736); `AirportItlwm-Sonoma-Info.plist` has none.
* `itl80211/Info.plist` (fileRef F8D6CD54 :1326, group child :1898) is **used by no target** — orphan.
* CI verify step requires exactly the WCL/Sonoma-style OSBundleLibraries set
  (IO80211Family, libkern, iokit, IOSkywalkFamily, corecapture — .github/workflows/main.yml:118–122)
  and bundle id `com.zxystd.AirportItlwm` (:115).

---

## 8. WCL sub-directory analysis

* Files: `AirportItlwm/WCL/WCL.cpp` (1850 lines), `WCL.hpp` (727 lines), `Info.plist`,
  `Sequoia-Info.plist`.
* **Compiled into: Sequoia (:3547), Sonoma14.4 (:3459), Tahoe and GoldenGate (same phase object
  `F8D94CA5` as Sonoma14.4). NOT compiled into Sonoma14.0 or any older target, nor itlwm.**
  Single PBXBuildFile `A112F5371BD949CD8CA19D88` (def :24) → fileRef `A112F5371BD949CD8CA19D89`
  (:1115) which is `sourceTree = SOURCE_ROOT; path = AirportItlwm/WCL/WCL.cpp` and is **not a member
  of any PBXGroup** (invisible in the Xcode navigator — cosmetic only).
* **Role**: WCL is *not* a library or separate bundle — it is compiled straight into the kext binary.
  `WCL.cpp` is wrapped entirely in `#ifdef AIRPORT_WCL` (WCL.cpp:9), so in Sonoma14.4 it compiles to
  nothing (that target lacks the define) and only contributes code to Sequoia/Tahoe/GoldenGate.
  It implements the macOS 15.2+/26 "WCL" (post-IO80211Family Apple wireless framework) interface
  glue used by the V2 driver: D11AC chanspec encoding/decoding for 2.4/5/6 GHz (WCL.hpp:18–55),
  MAC-address update state machine (WCL.hpp:57–74), SAE/WPA3 state resets, and interface plumbing
  on top of `AirportItlwmV2.hpp`/`AirportItlwmSkywalkInterface.hpp` (WCL.cpp:10–11). The
  `AIRPORT_WCL` define additionally switches the shared `include/Airport/*.h` dispatcher headers to
  the `macOS15`/`macOS26` header sets (§9) and gates code inside `ItlIwxMld.cpp`
  (12 `#ifdef AIRPORT_WCL` blocks) and `AirportItlwmV2.hpp` (:13–19).
* The WCL/ directory also hosts the kext Info.plists for the Sequoia/Tahoe/GoldenGate targets (§7).

---

## 9. Platform header selection mechanism (include/Airport vs macOS15 vs macOS26)

There is **no per-target HEADER_SEARCH_PATHS switch**. Mechanism:

1. All targets compile with `SYSTEM_HEADER_SEARCH_PATHS = "itl80211/openbsd itl80211 include"`
   (e.g. Sequoia :4402, Tahoe :4368) — so `#include <Airport/...>` and `#include "..."` resolve
   against `include/`.
2. The shared headers in `include/Airport/` are **dispatchers**. Example
   `include/Airport/IO80211SkywalkInterface.h:9–14`:

   ```c
   #ifdef AIRPORT_WCL
   #if __IO80211_TARGET == __MAC_15_2
   #include "macOS15/IO80211SkywalkInterface.h"
   #else
   #include "macOS26/IO80211SkywalkInterface.h"
   #endif
   #else
   … legacy inline class definitions (pre-WCL path, used by Sonoma14.4 and older) …
   #endif
   ```

   Same pattern in `IOSkywalkInterface.h`, `IO80211ControllerV2.h`, `IOSkywalkNetworkInterface.h`,
   `IOSkywalkEthernetInterface.h`, `IO80211WorkQueue.h`, `IO80211InfraInterface.h`,
   `IO80211InfraProtocol.h` (each :11–14-ish). `AirportItlwmV2.hpp:13–19` does the same for
   `<Airport/macOS15/FaultReporter.h>` vs `<Airport/macOS26/FaultReporter.h>`, and
   `AirportItlwmAWDLInterface.hpp:17–22` for the AWDL headers (macOS15 also pulls
   `IO80211ManagementBuffer.h`, which has no macOS26 counterpart).
3. So: **`AIRPORT_WCL` (defined only by Sequoia/Tahoe/GoldenGate) selects the WCL header family;
   `__IO80211_TARGET` (`__MAC_15_2` for Sequoia, anything else → macOS26 for Tahoe/`__MAC_26_0`)
   selects the macOS15 vs macOS26 variant.** Sonoma14.0/14.4 and older targets fall back to the
   legacy inline definitions in `include/Airport/*.h` themselves.
4. Consequence for reduction: `include/Airport/macOS15/*` and `include/Airport/macOS26/*` (12+13
   headers) are BOTH live for our two targets; the root `include/Airport/*.h` files stay as
   dispatchers (their legacy `#else` bodies become dead code once old targets are removed).

---

## 10. Reduction hazard map (exact pbxproj objects to touch per removal class)

### (a) Remove the `itlwm` native target + its unique sources

* **PBXNativeTarget** `024A07AB23FCBC3C009FBA6C` (:2327–2345).
* **Its phases**: Headers `024A07A7` (:1917–1990, 67 entries), Sources `024A07A8` (:2725–2807),
  Frameworks `024A07A9` (**defined twice**: :1410–1417 and duplicate block :1421–1428 — delete both),
  Resources `024A07AA` (:2630–2636).
* **Configs**: list `024A07B6` (:4557–4565); XCBuildConfiguration `024A07B7` (:3775–3801) and
  `024A07B8` (:3802–3828).
* **Dependency objects**: `PBXTargetDependency 5066D63E` (:3584–3588) + `PBXContainerItemProxy
  5066D63D` (:1049–1055).
* **Project bookkeeping**: `targets` list entry (:2612), `TargetAttributes` block (:2564–2567).
* **Product**: fileRef `024A07AC` (itlwm.kext, :1116) + Products-group child line (:1524).
* **Build files unique to this target** (defs to delete): `024A07B2` itlwm.cpp (:26),
  `F8E49A14` ItlNetworkUserClient.cpp (:979), `F8D76362` pm.cpp (:869), `F8294FE4` FwBinary.cpp
  (:355), `F8A43073` zutil.c, `F8C77292` compat.cpp, `F8ED1344` ItlIwx.cpp (:981),
  `D572A771` ItlIwxMld.cpp (:983), `C26F731C` ItlIwxApi86.cpp (:982), `628B5C92` ec_p256_m31.c
  (:1016), `BC136DD1` i31.c (:1026), `8610D2E0` ieee80211_sae.c (:1036), plus the whole
  `F8C2EC5x…` header/source build-file series used only by phases `024A07A7/024A07A8`.
* **File refs / group children** (`itlwm` group `024A07AE` :1537–1553 — keep the group, it hosts
  hal_* dirs): itlwm.hpp `024A07AF` (:1117), itlwm.cpp `024A07B1` (:1118), itlwm/Info.plist
  `024A07B3` (:1119), pm.cpp `F8D76361` (:1335), ItlNetworkUserClient.cpp/.hpp `F8E49A12/13`
  (:1338–1339 — note these two IDs are **duplicated** at :1371–1372), ItlNetworkUserClient.hpp
  headers build file `F8E49A15` (:980).
* **Scheme**: delete `itlwm.xcscheme`.
* **Also affected**: `scripts/load.sh`, `scripts/unload.sh` (reference `com.zxystd.itlwm` /
  itlwm.kext — dev-only, deletable); CI does not build itlwm.
* **Code-level**: `itlwm/PrivateSPI.pch` is shared by ALL targets (prefix header, e.g. :4379) — keep.
  `itlwm/itlwm.hpp` is included by hal_* headers → keep or refactor (it is only *compiled* nowhere else).

### (b) Remove `hal_iwm` and `hal_iwn` directories (other-chip families)

⚠️ **hal_iwm/hal_iwn files are compiled into Sequoia and Tahoe too** (16 + 1 entries per phase,
§2/§3). Removing them requires editing BOTH live Sources phases:
`F8D94CA5` (Tahoe/Sonoma14.4/GG — entries :3414, :3473–3489) and `AFFBDFD0` (Sequoia — :3502,
:3561–3577), plus all 8 legacy/itlwm phases, plus:

* **PBXGroup** `hal_iwm` `F8AF3A2E24F9F25E008911C1` (:1766–1793, 20 children) and
  `hal_iwn` `17FD7F0B255E496000611406` (:1662–1672, 4 children); their child references in the
  `itlwm` group (:1541–1542).
* **PBXFileReference** lines for all 24 files (hal_iwm: :1166–1181, :1212–1213 rs.cpp/rs.h, :1216
  coex.cpp, :1263–1264 ItlIwm.cpp/.hpp; hal_iwn: :1182–1185).
* **PBXBuildFile defs**: hal_iwm per-target series — `024A08xx` (:73–85), `35CBE6A3…`–`35CBE6B0…`
  (:152–165 + :228–240 + :304–317), `F8B210F0…` (:3385–3401), `F8D94CDE…`–`F8D94CEE…` (:961–977,
  **shared by Sequoia+S14.4 phases — must go with the phase entries**), `F8AF3A31` (:2752),
  `A5DD1115…` rs.cpp (:335–340), `F837C91D…` coex.cpp (:356–361), `F8F84F68` rs.cpp (:1008).
  hal_iwn: `17FD7F10/63/6A/71/78` ItlIwn.cpp (:86, :88–91), `F8B210F7` (:3392), `F8D94CE5` (:968),
  and the ItlIwn header build files `17FD7F11/7F/86` (:87, :92–93).
* **Headers phases**: hal_iwm/hal_iwn header build files in the itlwm Headers phase
  (`024A088B/8C` :71–72) and headers build files `35CBE65x`… in legacy phases.
* **Code-level dependencies (biggest risk, outside pbxproj)**: `AirportItlwm/AirportItlwmV2.hpp`
  includes `ItlIwm.hpp`, `ItlIwx.hpp`, `ItlIwn.hpp` (AirportItlwmV2.hpp:30–32); `itlwm/hal_iwm/fw.cpp`
  is a firmware consumer of `fwList`; `include/HAL/*` reference all three HALs. Removing hal_iwm/
  hal_iwn is a source-tree surgery job, not just a pbxproj edit. The firmware payloads for those
  families (`iwm-*`, `iwn-*` = 20 files ≈ 25 MB) can only be dropped together with this removal.
* Sequoia/Tahoe also compile `itlwm/hal_iwx/*` (AX211 driver) — that stays.

### (c) Remove old-OS targets (HS, Mojave, Catalina, Big Sur, Monterey, Ventura, Sonoma14.0,
### Sonoma14.4, optionally GoldenGate) and schemes

Per target delete: **PBXNativeTarget** block (HS :2384–2402, Mojave :2365–2383, Catalina
:2422–2440, Big Sur :2346–2364, Monterey :2403–2421, Ventura :2441–2459, Sonoma14.0 :2460–2478,
Sonoma14.4 :2479–2497, GoldenGate :2517–2535), its **4 phase objects**, its **XCConfigurationList**
(:4566–4646 etc.) and its 2 **XCBuildConfiguration** blocks, its **PBXTargetDependency** +
**PBXContainerItemProxy** pair, its `targets`-list line (:2613–2624), `TargetAttributes` entry
(:2568–2596), and its product fileRef + Products-group line (:1522–1533).

**CRITICAL — shared objects that must NOT be deleted with Sonoma14.4:**
* Sources phase `F8D94CA52B9ABFE20081A3C4` (:3405–3492), Headers `F8D94C83` (:2244–2283),
  Frameworks `F8D94CEF` (:1485–1492), Resources `F8D94CF1` (:2686–2692) — these four objects are
  **also referenced by Tahoe (:2502–2505) and GoldenGate (:2521–2524)**. When removing Sonoma14.4,
  delete only the target object `F8D94C802B9ABFE20081A3C4` + its config list `F8D94CF2`
  (:4638–4646) + configs `F8D94CF3/F4` (:4275–4337) — keep the phases.
* PBXTargetDependency `F8D94C812B9ABFE20081A3C4` (:3624–3628) + proxy `F8D94C82` (:1105–1111) —
  shared by Sonoma14.4, **Tahoe (:2510), GoldenGate (:2529), Sequoia (:2548)**. Keep.
* Build files `F8D94CA6…`–`F8D94CEE…` (defs :907–977) are used by BOTH the S14.4/Tahoe phase and
  the Sequoia phase — keep. Same for headers build files `F8D94C84…`–`F8D94CA4…` (:870–898).
* Build files unique to legacy targets (safe to delete with them): the `35CBE6xx/35CBE7xx` blocks
  (:101–321), `F897ED…`, `F8AE65…`, `F8B210B…`–`F8B210F…` series, `5088ECBD…C1` libkmod.a
  (:322–326), `F897ED13`, `F8AE6553`, `F8B21105`, plus legacy-only fileRef product entries
  (`35CBE6BA/724/78F`, `F897ED18`, `F89B6BB9`, `F8AE6558`, `F8B2110A`, `F8D94CF5`).
* The **5 legacy Airport .cpp files** (AirportItlwm.cpp, AirportItlwmInterface.cpp,
  AirportSTAIOCTL.cpp, AirportVirtualIOCTL.cpp, AirportAWDL.cpp) become source-orphans — deletable
  from disk + their fileRefs (:1238, :1319–1320, :1244–1246) + AirportItlwm group children
  (:1729–1732) + build-file defs (:166–169, :242–245, :318–321 etc.).
* **Plists**: `AirportItlwm/Info.plist` and `AirportItlwm-Monterey-Info.plist` become unused
  (delete file + fileRef F89B6BBF :1239 / F883EC1F :1230 + group children :1735/:1736);
  `AirportItlwm-Sonoma-Info.plist` becomes unused after Sonoma14.0+14.4 removal (no fileRef to
  clean, just delete the file).
* **Schemes to delete**: `AirportItlwm (all).xcscheme` (references 10 old targets),
  `AirportItlwm-GoldenGate.xcscheme` (if GoldenGate goes), `itlwm.xcscheme` (with itlwm).
  **Fix**: Sequoia/Tahoe schemes' ProfileAction MacroExpansion reference Big Sur
  `35CBE655251CB89700435CBC` (Sequoia scheme lines 57–65, Tahoe scheme lines 50–58) — retarget to
  their own BlueprintIdentifier or drop the MacroExpansion block, else Xcode shows a broken
  reference after Big Sur deletion.

### (d) Remove unused firmware files

* Firmware files are referenced **only** via the `firmware` PBXGroup `0250B31C` (:1620–1661) and
  their PBXFileReference lines — never in any build phase. Per file: delete the file from
  `itlwm/firmware/`, delete the fileRef line, delete the group-child line.
* Keep for AX211: `iwlwifi-so-a0-gf-a0-68.ucode` + `iwlwifi-so-a0-gf-a0.pnvm`
  (config `iwlax211_2ax_cfg_so_gf_a0`, ItlIwx.cpp:18615–18621; 0x51F0 device rows :19148–19149,
  :19277–19278). Everything else is removable *only if* the corresponding device families are
  dropped from the iwx device tables (a source decision, not build-system) — the iwlwifi-* set
  supports AX200/AX210/AX411/BE200/BE201 today; `iwm-*`/`iwn-*` go with hal_iwm/hal_iwn (see (b)).
* After trimming, the next build regenerates FwBinary.cpp (CI) — but note the fw_gen.sh staleness
  quirk (§6.3) for local builds.
* `iwlwifi-firmware-license` (fileRef :1204, root group child :1509) must stay (CI copies it into
  artifacts, main.yml:142).

---

## 11. Scripts inventory (build-required vs dev convenience)

| Script | Purpose | Status |
|---|---|---|
| `scripts/fw_gen.sh` | Runs zlib_compress_fw.py to generate include/FwBinary.cpp; invoked by the "Generate Firmware" phase of fw_gen (pbxproj:2720) | **BUILD-REQUIRED** (all targets) |
| `scripts/zlib_compress_fw.py` | zlib-compresses every file in itlwm/firmware/ into FwBinary.cpp (fwList/fwNumber) | **BUILD-REQUIRED** |
| `scripts/prepare_tahoe_sdk.py` | Verifies (sha256-pinned) and patches `MacKernelSDK/Headers/IOKit/pci/IOPCIDevice.h`: exposes `IOPCIDevice::configureInterrupts` at reserved slot 3 + adds `kIOInterruptTypePCIMessagedX` (prepare_tahoe_sdk.py:14–26). Refuses to run on unexpected SDK | **BUILD-REQUIRED for the Tahoe target** (CI runs it before building, main.yml:64–65) |
| `scripts/load.sh` | `kextunload com.zxystd.itlwm` + `kextutil` of the **plain itlwm.kext** debug build | dev convenience only; tied to the itlwm target (deletable with it) |
| `scripts/unload.sh` | unloads itlwm.kext | dev convenience only |
| `scripts/Collect-EricWirelessDiagnostics.command` | End-user support tool: collects Wi-Fi/AirDrop/BT diagnostics (log stream, ioreg, wdutil, panic reports) into a zip ≤24 MB | user/support tooling; not part of the build (only file with a `.gitattributes` rule) |
| `scripts/site/build.py` | Generates the GitHub-Pages `docs/` site from strings.py (per-language HTML; build commands shown: clone MacKernelSDK at pinned SHA + prepare_tahoe_sdk.py + xcodebuild Tahoe/Sequoia schemes, build.py:242–246) | docs tooling; not build-required |
| `scripts/site/strings.py` | Site copy/translations for build.py | docs tooling |

`.github/workflows/main.yml` (adapted): triggers on itlwm/**, itl80211/**, AirportItlwm/**, include/**,
itlwm.xcodeproj/**, scripts/** (:17–34); macos-15-intel runner (:54); checks out pinned MacKernelSDK
`3f750085caa17ec3a7880f11c11bf4f48cd6a164` (:58–63); runs prepare_tahoe_sdk.py (:64–65); builds
`-target AirportItlwm-Sequoia` and `-target AirportItlwm-Tahoe` with `ARCHS=x86_64
ONLY_ACTIVE_ARCH=NO SYMROOT=$PWD/build/products OBJROOT=$PWD/build/obj CODE_SIGNING_ALLOWED=NO
GIT_COMMIT=_<short-sha>` (:78–92); verifies x86_64-only, bundle id, OSBundleLibraries
(IO80211Family/libkern/iokit/IOSkywalkFamily/corecapture), records embedded firmware names and
IOPCIMatch, zips per-platform artifacts (:93–143). Expected product path
`build/products/$CONFIGURATION/{Sequoia,Tahoe}/AirportItlwm.kext` matches
`CONFIGURATION_BUILD_DIR` (§5). MODULE_VERSION is scraped from the pbxproj via awk (:76).

---

## 12. Broken / orphan references & pbxproj anomalies

1. **12 dead `(null)` PBXBuildFile objects** (no fileRef): defs at :503, :684, :775, :888, :898, :943
   (Sources) and `F897ECC2/C7`, `F8AE6501/06`, `F8B210B3/B8` (Headers). Referenced from phases at
   :3109 (Monterey), :3280 (Ventura), :3367 (Sonoma14.0), :3454 (S14.4/Tahoe/GG), :3542 (Sequoia)
   and the corresponding Headers phases (:2266, :2276, :2306, :2316). They compile nothing; safe to
   delete together with the old targets — **but :3454/:3542 live in the two phases we keep**, so
   those two entries should be scrubbed when touching the live phases.
2. **Duplicated PBXFileReference definitions**: lines :1370–1399 re-declare the same IDs as
   :1337–1366 (iwlwifi-*.ucode, ItlNetworkUserClient.*, FwData.h, IO80211*.h, linux/*.h, _task.*,
   zutil.*). Identical content, plist last-wins — harmless but a trap for text edits (an edit to one
   copy silently persists via the other).
3. **Malformed/duplicated section markers + object**: "Begin PBXFrameworksBuildPhase" at :1409 is
   closed by "End PBXFileReference section" at :1418, then a second "Begin PBXFrameworksBuildPhase"
   at :1420 re-defines the same object `024A07A923FCBC3C009FBA6C` (itlwm's Frameworks phase,
   :1410–1417 and :1421–1428).
4. **Cross-target sharing of build phases**: Tahoe (:2502–2505), GoldenGate (:2521–2524) and
   Sonoma14.4 (:2483–2486) point at the SAME four phase objects; Sequoia reuses Sonoma14.4's
   BuildFile IDs and dependency object. Deleting "Sonoma14.4's phases" naively kills Tahoe and
   GoldenGate builds. (Also: `AirportItlwm-GoldenGate` is missing from the "(all)" scheme.)
5. **WCL.cpp fileRef not in any group** (:1115) — compiles fine (SOURCE_ROOT path), invisible in
   Xcode navigator. Tahoe's product fileRef `3FCE22CDA614FF2D176FAC46` (:1367) likewise is not in
   the Products group (referenced directly at :2514).
6. **Missing-from-disk references**: `include/FwBinary.cpp` (generated — expected);
   `MacKernelSDK/Library/x86_64/libkmod.a` (fileRef :1205; CI clones MacKernelSDK, main.yml:58–63 —
   expected); `Products/*.kext` refs are BUILT_PRODUCTS_DIR (expected).
7. **Orphan plist**: `itl80211/Info.plist` — fileRef :1326 + group child :1898, used by no target.
8. **Firmware names referenced in code but not shipped**: `iwlwifi-QuQnj-b0-hr-b0-48.ucode` and
   `iwlwifi-QuQnj-b0-jf-b0-48.ucode` (ItlIwx.cpp:18883, :19047) have no corresponding file in
   `itlwm/firmware/` — those device IDs would fail `getFWDescByName`. Irrelevant for AX211 but worth
   knowing before any firmware-table pruning.
9. **Stale scheme cross-references**: ProfileAction of the Sequoia, Tahoe, GoldenGate and "(all)"
   schemes points at the Big Sur target (see §1/§10c).
10. `.clangd` (clangd LSP: disable unused/missing-include diagnostics + clang-tidy, background
    index) and `compile_flags.txt` (clangd fallback flags: `-DAIRPORT_WCL -DIEEE80211_STA_ONLY
    -DDEBUG=1 -Iitl80211/openbsd -Iitl80211 -Iinclude -Iitlwm/hal_iwx`) are local-dev-only; the
    flags mirror the WCL build flavor, not exactly Sequoia/Tahoe settings (no `__IO80211_TARGET`).
    `.gitattributes` only pins LF for the diagnostics `.command`.

---

## 13. Findings (summary)

1. Sequoia and Tahoe compile an **identical 80-file source set**; they differ only via 4 build
   settings (`CONFIGURATION_BUILD_DIR`, `__IO80211_TARGET`, `INFOPLIST_FILE`,
   `MACOSX_DEPLOYMENT_TARGET`) and two Info.plists that are themselves content-identical.
2. The pbxproj is **hand-mutated** around the Tahoe/GoldenGate/Sequoia targets: shared phase
   objects, shared dependency objects, reused BuildFile IDs, `(null)` placeholders, duplicated
   fileRef definitions, and duplicated Frameworks-phase object. Any mechanical "delete target"
   script must special-case Sonoma14.4's shared objects.
3. WCL (`AirportItlwm/WCL/WCL.cpp`, gated by `AIRPORT_WCL`) is the macOS 15.2+/26 driver interface
   implementation compiled into the kext for Sequoia/Tahoe/GoldenGate only; the same macro flips the
   `include/Airport/*.h` dispatcher headers onto `macOS15/` (when `__IO80211_TARGET == __MAC_15_2`)
   or `macOS26/`.
4. Firmware: all 43 payloads (~42 MB) are zlib-embedded into every kext via the generated
   `include/FwBinary.cpp`; there is no per-target firmware subsetting. AX211 needs only
   `iwlwifi-so-a0-gf-a0-68.ucode` + `iwlwifi-so-a0-gf-a0.pnvm` at runtime.
5. Safe-to-delete-when-targets-go source files: `itlwm/{itlwm.cpp, ItlNetworkUserClient.cpp,
   pm.cpp}` and `AirportItlwm/{AirportItlwm.cpp, AirportItlwmInterface.cpp, AirportSTAIOCTL.cpp,
   AirportVirtualIOCTL.cpp, AirportAWDL.cpp}` — nothing else is exclusive to doomed targets.
6. `hal_iwm` (16 cpp) and `hal_iwn` (1 cpp) are currently **live for Sequoia/Tahoe**; removing them
   is a combined pbxproj + source surgery (AirportItlwmV2.hpp includes all three HAL headers).
7. Build-required scripts: fw_gen.sh, zlib_compress_fw.py, prepare_tahoe_sdk.py. Everything else
   under scripts/ is dev/docs/support tooling.
8. The CI workflow already matches the two-target plan exactly (pinned MacKernelSDK + SDK patch +
   `-target` builds + verification of bundle id/OSBundleLibraries/arch).

## 14. Open questions

1. Should GoldenGate (macOS 27 dev variant, `ITL_MACOS27` define) be kept as a forward-compat
   target or deleted? It shares the Tahoe phase objects; deleting it is trivial (target object +
   config list + scheme), keeping it costs nothing.
2. Are the 6 GHz/BE200 `iwlwifi-bz-*`/`gl-c0-fm-c0-*` firmware files to be kept (BE200 support in
   the same binary) or dropped with the AX211 specialization? This is a product decision that
   bounds the firmware trim (23 iwlwifi-* files → potentially 2).
3. After removing hal_iwm/hal_iwn, `itlwm/hal_iwm/fw.cpp` disappears — confirm nothing else
   references `fwList`/`getFWDescByName` except hal_iwx (ItlIwx.cpp) before deleting FwData plumbing.
4. Confirm whether `MACOSX_DEPLOYMENT_TARGET = 10.15` on Tahoe (vs 15.2 on Sequoia) is intentional
   upstream behavior (kexts are not deployment-target-gated the way user processes are, and CI does
   not assert it) — flagging in case a later phase wants to normalize it.
5. `itlwm/PrivateSPI.pch` stays required by Sequoia/Tahoe (GCC_PREFIX_HEADER, :4379/:4345); confirm
   no other prefix header replaces it if the `itlwm/` directory layout is restructured during
   reduction.
