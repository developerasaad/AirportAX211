# Feature Preservation Matrix — AirportAX211

Legend — Sequoia/Tahoe compile: Y = compiled into both targets (they share
one 51-unit compile set). Runtime: how the feature activates on the AX211.
Physical: hardware validation status on the MSI Modern 14 C12MO (nothing
has been physically tested yet; all rows are NOT TESTED and the column is
omitted — see FINAL-VERIFICATION-REPORT.md).

| Feature | Required components (evidence) | Firmware/HW dependency | Sequoia | Tahoe | Runtime notes |
|---|---|---|---|---|---|
| WPA2-Personal (CCMP) | ieee80211_pae_{in,out}put.c, crypto_ccmp.c, iwx ADD_STA_KEY | fw key API v1 | Y | Y | SW KRACK mitigations verified by audit (B-N13) |
| WPA2-Enterprise | EAPOL pass-through, WCL-seeded PMKSA (WCL.cpp:1197-1208, installWCLKey) | none (host) | Y | Y | macOS supplicant owns EAP |
| WPA2/WPA3 transition | node.c transition AKM branches (1700-1755) | none | Y | Y | requires C_MFP (enabled, D-01) |
| WPA3-Personal SAE (H2E) | ieee80211_sae.c, ec_p256_m31.c, i31.c, sha2/hmac; iwx_defer_sae_join | host-side only; mgmt-frame TX | Y | Y | H2E only (HnP compiled out — B-N15, intentional); needs C_MFP — was runtime-inert in upstream, now enabled |
| PMF / 802.11w | crypto_bip.c (CMAC), pae_input IGTK/BIGTK KDEs, SA Query (proto.c:518-553) | host-side only | Y | Y | software BIP-CMAC-128; beacon protection (BIGTK verify) intentionally off; GMAC refused (no MLD ABI) |
| OWE / Enhanced Open | crypto.c OWE KDF (577-674), output.c DH IE | host-side only | Y | Y | group 19; 6 GHz OWE gated on C_MFP (now enabled) |
| 802.11n/ac (HT/VHT) | net80211 HT/VHT parsing, rate tables | fw TLC | Y | Y | |
| Wi-Fi 6 / HE incl. 160 MHz | HE parse (input.c), iwx_setup_he_rates (4770-4905 legacy half), STA_HE_CTXT_CMD v2, PHY v3 MODE160, ADD_STA FAT_EN_160, TLC v3 | fw STA_HE_CTXT v2 (verified in shipped so-a0-gf-a0-68 TLVs) | Y | Y | EHT/320 MHz removed (BE-only) |
| 2.4 / 5 GHz | channel tables, scan v14 | NVM channel profile | Y | Y | |
| 6 GHz discovery + scan | v14 scan band-6 flags, PSC bgscan, HE-Operation primary fix (input.c:2642), RNR collection | fw scan v14 | Y | Y | RNR directed-probe hints were v17-only (Api86) — behavior-neutral on v14 (audit D) |
| Regulatory enforcement | NVM channel tables (ItlIwx.cpp:4399-4530), probe suppression (9315), beacon hints (input.c:2696), LAR/MCC | NVM + fw LAR | Y | Y | untouched by the reduction (verified, audit B-N20/D) |
| Scan management | iwx_umac_scan v14, WCL scan events, scan abort | fw SCAN_REQ_UMAC v14 | Y | Y | aborted-scan completion behavior preserved (B-N02, WCL timers) |
| Auth/assoc state machine | ieee80211_proto.c newstate, retry accounting (F-12 fixed) | none | Y | Y | |
| Reconnection/recovery | watchdog, node eviction, iwx recovery (nic_error → init_task), WCL recovery link event (F-11 fixed) | fw restart | Y | Y | |
| Private / random MAC | setHardwareAddress + ic_wcl_mac_reconfig restart (V2.cpp) | none | Y | Y | |
| Native macOS Wi-Fi management | V2 + WCL + Skywalk interfaces, IO80211InfraProtocol virtuals via wclCommand | none | Y | Y | en0 carrier truthfulness fixed (F-05) |
| Sleep/wake | PM thread_call + command-gate PM (V2.cpp:1556-1673) | fw D3 handling | Y | Y | no WoW offload (magic-packet flag only) |
| A-MPDU / BA | net80211 BA, iwx TVQM queues, BA leak fixed (F-06) | fw TVQM | Y | Y | |
| AWDL/AirDrop (experimental) | AirportItlwmAWDLInterface.cpp (3462 lines), AirportAWDL hooks, legacy listener + aux-ROC + P2P in HAL | ic_awdl_listen (9260+, AX211 has it) | Y | Y | disabled by default (`-itlawdl`), runtime vtable-anchor check; preserved intact per assignment |
| Experimental functionality | boot args: itlwm_he, -novht, -noht40, -itlawdl, -itlawdlllw, -itlawdlbaaccept | varies | Y | Y | preserved |

## Removed (with evidence — NOT AX211 features)

- Other Intel families: hal_iwn (legacy), hal_iwm (7260-9560), iwx ty/gl/bz
  (AX210/BE200/BE201) paths — cannot host the AX211; audit D cross-checks.
- MLD/MLO/EMLSR/TTLM/EHT, scan v17, MSI-X: absent from the AX211 firmware
  ABI (verified by parsing the shipped TLVs; audit D).
- Firmware families other than so-a0-gf-a0 (API 68): unreachable after the
  device-table reduction.
- GMAC/BIGTK firmware-key advertisement: MLD-only; software BIP is the
  correct AX211 PMF path.
- Crypto: CAST/DES/Blowfish/GMAC/ChaCha20-Poly1305/RIPEMD-160/idgen — zero
  consumers (audit D reachability).
- macOS targets other than Sequoia/Tahoe.
