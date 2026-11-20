# Previous-Fix Transfer Matrix — AirportAX211

Evaluation of every correction from the previous AirportItlwm_AX211
implementation (reference/, HEAD 46027fe) against the Eric-AirportItlwm
be200-tahoe snapshot (cf0c5263). Verdicts use the classification from the
assignment brief. Evidence and full semantics: `audit-notes/subagent-G-reference-fixes.md`
(old side) and `audit-notes/subagent-{A,B,C,E}-*.md` (Eric side).

Baseline reminder: all 13 old corrections were source-verified and
CI-verified (run 44620003926) but none were hardware-validated.

| ID | Old defect | Eric status | Verdict | Action |
|----|------------|-------------|---------|--------|
| F-01 | Per-frame TX rate XYLog in iwx_tx_fill_cmd | Present, narrower (mcast/mgmt/fixed frames only; data frames return early) | STILL DEFECTIVE | Remove log line at ItlIwx.cpp:8200 during fix pass |
| F-02 | Per-frame crypto XYLog in ieee80211_encrypt | Present (fires only on SW-crypto fallback: TKIP/WEP/BIP) | STILL DEFECTIVE | Remove log at ieee80211_crypto.c:375, keep BUG! log |
| F-03 | Scan-result rates always empty (bound read from zeroed asr_nrates) | Present at AirportItlwmSkywalkInterface.cpp:1102-1104 | STILL DEFECTIVE | Port reference fix: derive nrates from node, clamp to array, set count before bounded copy |
| F-04 | Undeclared `HalService` id in RB_NEXT call (compiles only because tree.h discards arg) | Present at AirportItlwmSkywalkInterface.cpp:1204 | STILL PRESENT (latent) | One-token fix: `fHalService` |
| F-05 | en0 link-down no-op (mask=0) and IFF_UP clobber | Present at AirportItlwmEthernetInterface.cpp:116 | STILL DEFECTIVE | Port reference fix: clear IFF_RUNNING only, preserve IFF_UP |
| F-06 | RX BA ba_buf never freed in ba_del (leak per roam/deauth) | Present and worse: node.c:2194-2222 frees timers only; roam node_copy overwrites stale ba_buf pointer | STILL DEFECTIVE | Port reference fix: free all BA window mbufs + buffer in ba_del |
| F-07 | Rate printer OOB (ant==4 / bw==5 read past arrays) | Present at ItlIwx.cpp:753, 769 | STILL DEFECTIVE | Two `>` → `>=` |
| F-08 | EAPOL totlen<sizeof(*key) unsigned wrap → OOB parse (msg1 PMKID, msg3 KDE walk, GTK memcpy) | Present at ieee80211_pae_input.c:138 (no totlen guard) | STILL DEFECTIVE (high severity, security) | Port reference guard verbatim: reject totlen < sizeof(*key) \|\| paylen > totlen - sizeof(*key) |
| F-09 | PNVM polarity trap (0 = loaded AND no-match; doorbell+2s wait on no-match; spurious fatal) | Present: no-match returns 0 with nothing loaded (ItlIwx.cpp:2484-2486), name-derive failure returns 0 (:2410-2413); load_pnvm doorbells + 2s wait + treats as fatal | STILL DEFECTIVE | Port reference-final semantics: ENOENT=no match→pnvm_free+return 0; other errno→propagate; 0→doorbell+wait. Also fix: unchecked inflate result (:2430), ENXIO path skipping pnvm_free (:2520). Do NOT reproduce the intermediate mistake (treating 0 as no-PNVM) |
| F-10 | Watchdog on separate workloop mutating MLME ungated; teardown freed HAL before cancelling timers | Partially fixed in Eric: V2 uses main workloop (V2.cpp:423-440), teardown order correct; residual: watchdogAction has no fHalService/if_watchdog guards, re-arms via member, releaseAll cancel not gate-serialized | ARCHITECTURAL DIFFERENCE (partial) | Add guards + sender-based re-arm + gated cancel in releaseAll |
| F-11 | WCL recovery link-up never posted LinkStatus(up) (menu bar stuck) | Fix absent: handleWCLLink (WCL.cpp:1360-1385) has no recovery branch | STILL DEFECTIVE | Port reference branch: post LinkStatus(up) when up && !joinPending && !wclLinkIndicated && assocNotified, re-track joinBSSID (flags identical between lineages) |
| F-12 | ni_fails double-count (watchdog + SCAN transition); choose_bss skips on ANY nonzero | Present + new twist: watchdog also feeds ni_fails as SAE attempts (ieee80211.c:959-960) burning WPA3 retry budget | STILL DEFECTIVE | Port both halves: count only in-place AUTH retry; skip threshold >= 2. Re-derive SAE attempts budget after |
| F-13 | fw-load nic_lock EBUSY bypasses fail labels → 3 DMA leaks per attempt | Present at ItlIwx.cpp:1488-1489 | STILL DEFECTIVE | `goto fail1` with err set (fail1→fail0 free all three DMAs) |

## New defects found in Eric (to fix in Phase G alongside transfers)

| ID | Finding | Label | Action |
|----|---------|-------|--------|
| D-01 | IEEE80211_C_MFP never set on AX211 path (only in BZ/MLD block at ItlIwx.cpp:5795) → WPA3-SAE/PMF/6GHz-OWE runtime-inert | Confirmed defect (feature-breaking for target) | Re-home C_MFP to legacy path during Tier 3 BE-block removal |
| B-N21 | task_set memcpy 256B from short literals (OOB read, 14 sites) | Confirmed defect (low) | strlcpy |
| B-N26 | node_set_timeouts memsets 2048B over 128B field (latent landmine) | Confirmed defect (latent) | Fix size computation |
| B-N22 | m_defrag EXT branch broken, zero callers | Dead code | Remove in Tier 4 |
| B-N04 | Unconditional XYLog in ieee80211_new_state macro (every transition prints) | Demonstrated inefficiency | Gate behind debug |
| C-1 | Start-failure paths leak fNetIf (V2.cpp:481-522) | Plausible risk | Release on failure |
| C-2 | Dead MAC-string snprintf (V2.cpp:1023-1030) | Dead code | Remove |
| E-05 | A-MSDU builder copies uninitialized ni_mld_addr (should be ic_wcl_peer_mld_addr) — MLO branch only | Confirmed defect (BE-live/AX211-latent) | Resolve during Tier 3 MLD removal (branch may vanish) |
| E-06 | IOKit getProperty on hot paths (every TX completion :7282, every RX MPDU :6628) | Demonstrated inefficiency | Cache/remove |
| E-16 | V2 late-start failure paths call releaseAll without fHalService->detach | Plausible risk | Add detach |
| B-N15 | SAE is H2E-only (HnP compiled out) | Intentional behavior (config) | Record; no change |
| B-N02 | Aborted firmware scans never post EVT_SCAN_DONE | Plausible risk (WCL has own timers) | Record; verify with C's WCL analysis |
| E-15 | No recovery trigger on plain 1s command timeouts | Plausible risk (inherited) | Record as deferred risk |

## Rejected / not-applicable transfers

- Old fork's itlwm-target-era code paths (non-Airport variant) — the itlwm
  target is removed entirely; its known watchdog defect (E-12) disappears
  with it.
- GMAC/BIGTK firmware-key advertisement (`ic_mld_gmac`) — MLD ABI absent
  from AX211 firmware; software BIP-CMAC-128 PMF is the correct AX211 path.
- Regulatory, RA-module, and ring-layout observations from the old fork —
  Eric's implementations verified equivalent or better (B-N19, B-N20, E-07/8/9).
