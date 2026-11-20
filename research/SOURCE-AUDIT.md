# Source Audit Summary — AirportAX211

Full evidence lives in research/audit-notes/ (seven subagent reports, each
claim with file:line). This file summarizes the audit structure and the
reconciled conclusions that drove the reduction and fix phases.

## Audit organization (Phase B, read-only, upstream snapshot cf0c5263)

| Subagent | Scope | Key outputs |
|---|---|---|
| A — hardware/firmware | hal_iwx (20k+ lines partitioned by function), PCI tables, firmware pipeline, PNVM/NVM, interrupt modes | AX211 execution path map (probe→attach→fw load→PNVM→NVM→PHY/aux-sta→queues→MSI+ICT alive); family classification; Api86/MLD/BE-only determination; firmware-to-device mapping |
| B — net80211/protocol | scan/node/auth/assoc/EAPOL/SAE/PMF/OWE/regulatory | Old-fix counterpart verdicts (all 13 STILL DEFECTIVE except F-10 partial); feature inventory; 27 findings (N-series) |
| C — macOS integration | V2/WCL/Skywalk/AWDL, Sequoia-vs-Tahoe ABI | Request-path traces (scan, join); link publication model; Sequoia/Tahoe divergence table; AWDL architecture + gating; old-fix verdicts |
| D — security/6E deps | HE/160/6GHz/SAE/PMF/OWE dependency graph, crypto reachability, removal cross-checks a–g | Cross-checks all SAFE TO REMOVE; crypto KEEP (14) / REMOVE (11) tables; D-01 (C_MFP never set on AX211) |
| E — data path/concurrency | TX/RX/DMA/command/workloop/timers/teardown | Concurrency model (one gate + IO80211WorkQueue); teardown-order verdict; old-fix verdicts; AWDL low-latency analysis (dead on AX211) |
| F — build engineering | pbxproj (full parse), schemes, scripts, plists | Target/phase/buildfile maps; Sequoia/Tahoe compile-set equality; reduction hazard map (shared phase objects, reused BuildFile IDs) |
| G — reference comparison | reference/ repo + ENGINEERING-REPORT.md | Authoritative record of the 13 old fixes (F-01..F-13) with final semantics, incl. the PNVM intermediate-mistake history |

## Reconciled architecture model (Phase C)

macOS (airportd) → IO80211InfraProtocol virtuals → WCL command gate
(wclCommand, single serialized action) → AirportItlwmV2/HAL service →
ItlIwx (gate-held) → firmware commands (ring DMA, TVQM queues) → MSI
interrupt → ICT → iwx_rx under the gate → net80211 state machine →
EthernetInterface (en0) + WCL events (link status, scan results, LQM) →
macOS. Power via PM thread_call + gate. Recovery: SW_ERR/HW_ERR →
nic_error dump → init_task (rate-limited, one retry). The AX211 uses the
legacy (pre-BZ) command ABI throughout: MAC ctxt v5, PHY v3+RLC, ADD_STA
v12, SCAN v14, NVM v4, PNVM doorbell, software PMF.

## Call graphs recorded

- Scan: WCL join/scan request → wclCommand → ieee80211_new_state(SCAN) →
  iwx_umac_scan (v14 builder) → fw → SCAN_ITERATION_COMPLETE/COMPLETE_UMAC
  notifications → iwx_endscan → ieee80211_end_scan → scan results via
  getSCAN_RESULT (SkywalkInterface) → WCL.
- Join: WCL join → wclCommand → joinTask (SAE deferred via
  iwx_defer_sae_join) → new_state(AUTH) → mgmt TX → ASSOC → RUN →
  first-beacon → finishWCLJoin → LinkStatus + assocNotified.
- PNVM: alive → iwx_load_pnvm → read_pnvm (TLV walk, SKU match) →
  doorbell + 2 s wait (fixed polarity, F-09).
- Firmware load: read_firmware (TLV) → start_fw → ctxt_info_gen3_init
  (IML) → CPU_INIT_RUN → ALIVE (fixed leak, F-13).

## State ownership summary

- Single workloop + command gate owns all HAL/net80211 state (verified by
  audit E; the V2 watchdog now runs under the same workloop).
- Node table (RB tree) owned by net80211 under the gate; free_node is
  unconditional in this port (no refcounts) — callers must not hold nodes
  across state transitions (the F-12 UAF was exactly this class).
- DMA rings owned by the HAL; freed only via iwx_stop_device ordering
  (mask → bus-master-off → ring reset → reclaim).
- WCL session state owned by the driver (joinBSSID, wclLinkIndicated,
  assocNotified flags); airportd owns profile storage.

## Security and hardware capability requirements (from D)

Software PMF (BIP-CMAC-128 + host IGTK/BIGTK) requires no firmware
capability — the basis of the D-01 enablement. SAE is host-side. HE
requires STA_HE_CTXT_CMD v2 (present in the shipped firmware TLVs).
6 GHz requires NVM channel profile + v14 scan band flags (present).
Regulatory is NVM + LAR enforced; nothing in the reduction touches it.
