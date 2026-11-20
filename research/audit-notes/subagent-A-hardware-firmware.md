# Subagent A — AX211 Hardware & Firmware Audit (Task M3-A)

Scope: `/home/z/my-project` (Eric-AirportItlwm, branch be200-tahoe, cf0c5263), read-only.
Target machine: MSI Modern 14 C12MO — Intel Wi-Fi 6E AX211 160 MHz, PCI 8086:51f0 subsystem 0094, CNVi Alder Lake-P, firmware family `so-a0-gf-a0` (API 68).
All `path:line` citations are relative to `/home/z/my-project` unless stated.

---

## 1. Executive summary

1. **The AX211 is fully supported on the "legacy" (non-MLD) IWX path** with firmware `iwlwifi-so-a0-gf-a0-68.ucode` + `iwlwifi-so-a0-gf-a0.pnvm`. Device family classification is `IWX_DEVICE_FAMILY_AX210` (gen3), trans cfg `iwl_so_long_latency_trans_cfg` (ItlIwx.cpp:18750-18755, 18776).
2. **`sc_use_mld_api` is false for AX211 by construction**: `sc_use_mld_api = sc->sc_device_family >= IWX_DEVICE_FAMILY_BZ && isset(capa, MLD_API_SUPPORT)` (ItlIwx.cpp:5772-5773). BZ = BE200/BE201 only. Therefore **all of ItlIwxMld.cpp and all ~60 `sc_use_mld_api` branches in ItlIwx.cpp are dead for AX211**.
3. **ItlIwxApi86.cpp is BE-only.** It implements SCAN_REQ_UMAC v17 (ItlIwxApi86.cpp:90). Firmware parsing (done for this audit directly on the shipped `.ucode` blobs) proves every API-68 firmware (so/ty/Qu/QuZ/cc) advertises `SCAN_REQ_UMAC cmd_ver=14`, while only bz/gl (API 86/92, i.e. BE200/BE201) advertise v17. AX211 scans through `iwx_umac_scan_v14` (ItlIwx.cpp:10058, dispatched at 9758-9763).
4. **Interrupts: AX211 uses single-vector MSI + ICT, not MSI-X.** `sc_msix` is set only for the BE families (ItlIwx.cpp:19864-19868). The Tahoe `IOPCIDevice::configureInterrupts(kIOInterruptTypePCIMessagedX,…)` API (scripts/prepare_tahoe_sdk.py:16-19) is called only inside the `IwxBE::pciFamily != None` branch (AirportItlwm/IOPCIEDeviceWrapper.cpp:85-95). AX211 falls into the legacy branch: MSI-X disabled, MSI enabled in config space.
5. **Surprise — 0x7E40 (an "AX211-family" PCI candidate) is effectively broken in this build**: it maps to `iwl_cfg_ma_a0_gf_a0` → `iwlwifi-ma-a0-gf-a0-63.ucode` (ItlIwx.cpp:18696-18701), which is **not shipped** in `itlwm/firmware/` (12 referenced fw names are missing, all SnJ/MA/QnJ, API 63/48 — see §10). PCI match succeeds; firmware load then fails. Only 0x51F0 / 0x51F1 / 0x54F0 / 0x7A70 / 0x7AF0 / 0x7F70 (all "So + GF" → so-a0-gf-a0-68) are usable AX211-class paths.
6. **Surprise — the BE200 (BZ) path pervades shared files via small inline `>= IWX_DEVICE_FAMILY_BZ` branches** (apm init/stop, sw reset, boot flow, RX credit return, error-table base, MSI-X). Removing "BE-only" code means editing ~15 guarded branches inside shared functions, not deleting whole functions — moderate regression risk.
7. Clean removal candidates for an AX211-only build: `ItlIwxApi86.cpp/.h`, `ItlIwxMld.cpp` (+careful call-site cleanup), `iwx_be_config.h`, `hal_iwm/`, `hal_iwn/`, 41 of 43 firmware blobs, and all non-AX211 PCI IDs in the plists and `iwx_devices`/`iwl_dev_info_table`.

---

## 2. PCI identity & matching

### 2.1 Personality plists

| Plist | Key | AX211 IDs present | Notes |
|---|---|---|---|
| AirportItlwm/Info.plist:31-32 | `IOPCIMatch` | 0x51F08086 0x54F08086 0x51F18086 0x7E408086 0x7F708086 0x7A708086 0x7AF08086 | Non-WCL Airport personality; IOClass `AirportItlwm`; **no** BE IDs (0x272b/a840/7740/4d40) |
| AirportItlwm/WCL/Info.plist:46-47 | `IOPCIMatch` | same set + 0x272b8086 0xa8408086 0x77408086 0x4d408086 | WCL personality; two personalities (IOPCIEDeviceWrapper → AirportItlwm chain), IOProbeScore 70000 |
| AirportItlwm/WCL/Sequoia-Info.plist:53-54 | `IOPCIMatch` | same as WCL | |
| AirportItlwm/AirportItlwm-Sonoma-Info.plist:47 / -Monterey-Info.plist:32 | `IOPCIMatch` | same as main | No BE IDs |
| itlwm/Info.plist:31 | `IOPCIPrimaryMatch` | mask `0x00008086&0x0000ffff` (all Intel) | Non-Airport itlwm variant |

Note: the task brief said `IOPCIPrimaryMatch`; the Airport personalities actually use **`IOPCIMatch`** (only the legacy itlwm kext uses `IOPCIPrimaryMatch`, with a vendor mask). This matters when trimming: the AirportItlwm list is the operative one for this project's WCL builds.

### 2.2 HAL selection

`IOPCIEDeviceWrapper::probe` (AirportItlwm/IOPCIEDeviceWrapper.cpp:60-114) — identical dispatch in AirportItlwm/AirportItlwm.cpp:64-101 and itlwm/itlwm.cpp:66-106:
1. `ItlIwx::iwx_match(device)` → `new ItlIwx` (IOPCIEDeviceWrapper.cpp:71-74)
2. else `ItlIwm::iwm_match` → `new ItlIwm` (:75-78)
3. else `ItlIwn::iwn_match` → `new ItlIwn` (:79-82)

`iwx_match` (ItlIwx.cpp:19719-19725) = `pci_matchbyid(vendor 0x8086, devId, iwx_devices[])`.

### 2.3 AX211 candidates verified against `iwx_devices` (ItlIwx.cpp:18749-18784)

| PCI ID | trans cfg (iwx_devices) | dev_info final cfg | fwname | Verdict |
|---|---|---|---|---|
| 0x51F0 | `iwl_so_long_latency_trans_cfg` (18776) | subdevice 0094 → "So with GF" (19673-19677) → `iwlax211_2ax_cfg_so_gf_a0` (18615-18621) | `iwlwifi-so-a0-gf-a0-68.ucode` | **The target machine. WORKS.** |
| 0x51F1 | `iwl_so_long_latency_trans_cfg` (18777) | subdev 1671/1672→gf (19279); 1692→gf4 (19150) | so-a0-gf-a0-68 / so-a0-gf4-a0-68 | AX211/AX411 variant; works |
| 0x54F0 | `iwl_so_long_latency_trans_cfg` (18778) | subdev 1671/1672→gf; 1691/1692→gf4 (19151-19152, 19280-19281) | so-a0-gf-a0-68 | works |
| 0x7F70 | `iwl_so_trans_cfg` (18779) | subdev 1671/1672→gf; 1691/1692→gf4 (19270-19271, 19286-19287) | so-a0-gf-a0-68 | works (RPL-S CNVi) |
| 0x7E40 | `iwl_ma_trans_cfg` (18783) | subdev 1671/1672→`iwl_cfg_ma_a0_gf_a0` (19290-19291); MAC MA+GF (19566-19570) | `iwlwifi-ma-a0-gf-a0-63.ucode` — **file absent** | **PCI matches, fw load fails** (EINVAL at ItlIwx.cpp:1773-1777) |
| 0x7A70 / 0x7AF0 | so long-lat / so (18774-18775) | subdev 0090/0098→`…_long`; 1671/1672→gf (19246-19257, 19282-19285) | so-a0-gf-a0-68 | works |

For 8086:51f0 subsystem 0094: no subdevice-specific dev_info entry matches, so the loop at ItlIwx.cpp:19966-20000 falls through to the generic **MAC_TYPE_SO(0x37)+RF_TYPE_GF(0x10D)** entry at 19672-19677 (`iwlax211_2ax_cfg_so_gf_a0`). Because the loop keeps the *last* match, this generic entry wins over earlier partial matches — correct behavior for the MSI's subsystem.

---

## 3. Device table map

`iwx_devices[]` (ItlIwx.cpp:18749-18784) — trans-level matching:

| IDs | trans cfg | family | comment |
|---|---|---|---|
| 0x272b, 0xa840, 0x7740, 0x4d40 | iwl_gl_trans_cfg (18563), iwl_bz_trans_cfg (18578) | BZ | BE200/BE201, `#ifdef AIRPORT_WCL` (18750-18755); fwname "auto" via `IwxBE::Selection` |
| 0x02F0, 0x06F0 | iwl_qu_trans_cfg (18513) | 22000 | AX201-class (Qu) |
| 0x34F0, 0x3DF0, 0x4DF0 | iwl_qu_medium_latency_trans_cfg (18520) | 22000 | |
| 0x43F0, 0xA0F0 | iwl_qu_long_latency_trans_cfg (18527) | 22000 | |
| 0x2720 | iwl_qnj_trans_cfg (18535) | 22000 | QnJ — cfgs reference missing QuQnj-48 fw |
| 0x2723 | iwl_ax200_trans_cfg (18596) | 22000 | AX200, cc-a0-68 |
| 0x2725 | iwl_so_trans_cfg (18543) | AX210 | AX210 (ty)/AX211 (so) on discrete CNVi |
| 0x2726 | iwl_snj_trans_cfg (18539) | AX210 | SnJ — all cfgs reference missing SoSnj-63 fw |
| 0x7A70, 0x7AF0, 0x51F0, 0x51F1, 0x54F0 | iwl_so / iwl_so_long_latency | AX210 | **AX211 family** |
| 0x2729, 0x7E40 | iwl_ma_trans_cfg (18557) | AX210 | MA — all cfgs reference missing ma-63 fw |

`iwl_dev_info_table[]` (19143-19717) — refines cfg by (device, subdevice, mac_type, mac_step, rf_type, rf_id, no_160, cores, cdb). AX211-relevant entries:
- IWL_DEV_INFO(0x51F0/0x51F1/0x54F0/0x7A70/0x7AF0/0x7F70, 0x1671/0x1672, iwlax211_2ax_cfg_so_gf_a0, Killer 1675 names) — 19275-19287.
- Generic "So with GF" (MAC_TYPE_SO + RF_TYPE_GF → iwlax211_2ax_cfg_so_gf_a0) 19672-19677; "So-F with Gf" 19626-19636.
- MA+GF entry 19566-19570 (iwl_cfg_ma_a0_gf_a0) — the broken 0x7E40 path.

Note: per-device `iwl_cfg.trans` overrides (e.g. `iwlax211_2ax_cfg_so_gf_a0_long` at 18623-18631) are **never read** — only `sc_cfg_params` from `iwx_devices` feeds `sc_integrated/sc_ltr_delay/sc_low_latency_xtal/sc_xtal_latency` (ItlIwx.cpp:20055-20058). For 0x51F0: integrated=1, xtal_latency=12000, ltr_delay=2500, low_latency_xtal=0 (ItlIwx.cpp:18550-18555).

`sc_device_family` after attach = `IWX_DEVICE_FAMILY_AX210` (2) for AX211 (ItlIwx.cpp:20054, from iwlax211_2ax_cfg_so_gf_a0.device_family at 18619). All `>= IWX_DEVICE_FAMILY_AX210` gen3 branches are live for AX211; all `>= IWX_DEVICE_FAMILY_BZ` (3) branches are dead for AX211.

---

## 4. Firmware selection & API version analysis

Selection chain (AX211):
1. `iwx_attach`: `sc->sc_fwname = sc->sc_cfg->fwname` = `"iwlwifi-so-a0-gf-a0-68.ucode"` (ItlIwx.cpp:20041, cfg at 18617).
2. `iwx_read_firmware` (1669): `if (sc->sc_be.family == IwxBE::None) return iwx_read_firmware_file(sc);` (1671-1672) — AX211 takes the plain-file path; the API-86/92 candidate loop (1673-1730) is BE-only.
3. `iwx_read_firmware_file` (1734): `getFWDescByName(sc->sc_fwname)` (1773) → zlib-inflated (FwData.h:46-70) → TLV parse. API version from `IWX_UCODE_TLV_FW_VERSION` → `sc->sc_fw_api` (2000).
4. Embedded blobs come from `itlwm/firmware/*` compressed at build time by scripts/fw_gen.sh → scripts/zlib_compress_fw.py → `include/FwBinary.cpp` `fwList[]` (FwData.h:33-44).

**Firmware-parse evidence (extracted directly from the shipped blobs for this audit):**

| firmware | FW_VERSION | SCAN_REQ_UMAC ver | ADD_STA ver | PHY_CONTEXT ver |
|---|---|---|---|---|
| iwlwifi-so-a0-gf-a0-68.ucode (AX211) | api=68 build 0x1d30b0c | **14** | 12 | 3 |
| iwlwifi-ty-a0-gf-a0-68 (AX210) | 68 | 14 | 12 | 3 |
| iwlwifi-so-a0-gf4-a0-68 (AX411) | 68 | 14 | 12 | 3 |
| Qu/QuZ/cc/so-hr/so-jf -68 | 68 | 14 | 12 | 3 |
| iwlwifi-bz-b0-fm-c0-92 (BE200) | 92 | **17** | — (MLD) | — |
| iwlwifi-gl-c0-fm-c0-86 / -92 (BE201) | 86 / 92 | **17** | — | — |

AX211-relevant API/capa bits of so-a0-gf-a0-68: API 32 (ADAPTIVE_DWELL), 42 (ADAPTIVE_DWELL_V2), 48 (REGULATORY_NVM_INFO → NVM v4), 56 (REDUCED_SCAN_CONFIG), 58 (SCAN_EXT_CHAN_VER); capa 1 (LAR), 2 (UMAC_SCAN), 43 (TLC_OFFLOAD), 48 (ULTRA_HB/6GHz), 50 (SET_LTR_GEN2), 54 (SESSION_PROT_CMD), 59 (HIDDEN_6GHZ_SCAN), 74 (CT_KILL_BY_FW), 100 (BIGTK). **Not set**: capa 12 (DQA_SUPPORT — so `iwx_send_dqa_cmd` is skipped, ItlIwx.cpp:16367-16371), capa 32 (FRAGMENTED_PNVM_IMG — PNVM is a single blob, ItlIwx.cpp:2379-2380), capa 40 (CDB).

Where API matters in code:
- Scan dispatch: `iwx_umac_scan` checks `iwx_lookup_cmd_ver(...IWX_SCAN_REQ_UMAC)==17` → Api86 (ItlIwx.cpp:9696-9716); `==12` → v12 (9760-9761); `==14` → **v14 = AX211** (9762-9763); else legacy v6/v7/v8 builder (9765+, unreachable with shipped fws).
- `iwx_lookup_cmd_ver`/`iwx_lookup_notif_ver` (936-949) read `sc->cmd_versions[]` filled from TLV_CMD_VERSIONS (ItlIwx.cpp:2092-2107).
- No code branches on the numeric API 68 vs 86/92 directly; all dispatch is per-command version or capa/API bits — good for stability.

---

## 5. PNVM analysis

Path (AX211):
- `iwx_load_pnvm` (ItlIwx.cpp:2495): if `sku_id[]` all zero → `return sc_device_family >= BZ ? ENOENT : 0` (2503-2504) — for AX211 an empty SKU means PNVM is *not required* (returns success).
- `sc->sku_id` comes from the ALIVE v5 response (ItlIwx.cpp:17645-17647).
- `iwx_read_pnvm` (2394): derives `.pnvm` name from the ucode name — `iwlwifi-so-a0-gf-a0-68.ucode` → strip last '-' segment → **`iwlwifi-so-a0-gf-a0.pnvm`** (2408-2416); BE override at 2417-2418. Loads blob, walks SKU sections, requires exact `sku_id` match (2468-2474) → `iwx_pnvm_handle_section`.
- `iwx_pnvm_handle_section` (2211): requires HW match `mac_type == CSR_HW_REV_TYPE(sc_hw_rev) && rf_id == CSR_HW_RFID_TYPE(sc_hw_rf_id)` (2273-2275) — for AX211: MAC SO (0x37) + RF GF (0x10D). Extracts `SEC_RT` data segments, allocates `pnvm_dram` DMA (single blob for AX211 since capa 32 unset; fragmented form at 2365-2378 is BE-style), and programs `prph_scratch.ctrl_cfg.pnvm_cfg` (2382-2385).
- Doorbell: `iwx_write_umac_prph(IWX_UREG_DOORBELL_TO_ISR6, PNVM)` + wait `IWX_PNVM_COMPLETE` 2 s (2511-2519); completion notification handler at 17759-17766.
- **Failure behavior**: any error propagates up `iwx_load_ucode_wait_alive` (5736-5738) → `iwx_run_init_mvm_ucode` fails → `iwx_preinit` fails → **attach fails**. PNVM failure is fatal when the SKU is non-empty (the normal case for AX211). If no SKU section matches, `iwx_read_pnvm` returns 0 for non-BZ (2485-2486), the doorbell is kicked and the 2-s wait must still succeed (payload len check at 2525-2526).
- Devices needing PNVM: all AX210-class (ty/so/gf/gf4) and BE; the .pnvm inventory: so-a0-gf-a0 (AX211), so-a0-gf4-a0 (AX411), ty-a0-gf-a0 (AX210), bz-b0-fm-c0, bz-b0-gf-a0, gl-c0-fm-c0(+92 variant) (BE).

---

## 6. NVM analysis

`iwx_nvm_get` (ItlIwx.cpp:5474-5565) — runtime NVM fetch from firmware (not raw EEPROM):
- Command `NVM_GET_INFO` (REGULATORY_AND_NVM group) with response (5478-5484).
- **v4 vs v3**: `v4 = isset(sc_ucode_api, API_REGULATORY_NVM_INFO(48))` (5495). so-a0-gf-a0-68 sets API 48 → **AX211 uses the v4 response** with `rsp->regulatory.channel_profile` and `IWX_NUM_CHANNELS` (5554-5556); v3 path (5557-5561) is for older fw (dead for AX211).
- Sections consumed: `general` (nvm_version, n_hw_addrs 5527-5528), `mac_sku` (11ac/11n/11ax/2.4/5.2 GHz/MIMO flags 5531-5543), `phy_sku` (valid_tx/rx_ant 5546-5547), `regulatory` (lar_enabled 5549-5552 + channel profile).
- MAC address: `iwx_set_mac_addr_from_csr` (5434-5463) reads `CSR_MAC_ADDR0/1_STRAP` then OTP fallback.
- Channel map: `iwx_init_channel_map` (4399) with UHB (6 GHz) channel list `iwx_nvm_channels_uhb` (637-649) since `uhb_supported=1`.
- Called from `iwx_run_init_mvm_ucode(readnvm=1)` during `iwx_preinit` (19762, 5832-5842).

---

## 7. Api86 / MLD analysis (who uses them)

### ItlIwxApi86.cpp (408 lines) — **BE200/BE201 only, zero AX211 relevance**
- Contains only `iwx_umac_scan_v17_fill_general` + `iwx_umac_scan_v17` (ItlIwxApi86.cpp:35, 90).
- Call sites: `iwx_umac_scan` when `cmd_ver(SCAN_REQ_UMAC)==17` (ItlIwx.cpp:9696-9710) and the batch continuation `iwx_scan_task` (15657). Both fire only for fw advertising scan v17 = bz/gl API 86/92 (proven by blob parse, §4).
- Helpers it uses (`iwx_fill_probe_req`, `iwx_send_cmd`) are shared, but the file itself is exclusively BE. **Removal candidate** (also drop `if_iwxapi86.h` and the `sc_scan_*` batch state machine: `sc_scan_active/batch/batch_pending/batch_sent` are only set in v17 paths — see grep: ItlIwx.cpp:9697-9713, Api86.cpp:94/362-363; `iwx_scan_task` 15623-15706 is v17-only continuation, and 17786-17795's iteration-complete path uses `!sc_use_mld_api && !sc_scan_active` which is AX211's actual completion route).
- `iwx_umac_scan_v12` (9930) and the legacy v6/v7/v8 builder (9765-9929) are **dead with the shipped firmware set** (no blob advertises v12 or unversioned) — v12 was for older AX210 fw generations.

### ItlIwxMld.cpp (2595 lines) — **BZ family (BE200/BE201) only**
- Architecture gate: `sc_use_mld_api` (ItlIwx.cpp:5772-5773) requires `device_family >= BZ` **and** fw capa `IWL_UCODE_TLV_CAPA_MLD_API_SUPPORT` (110, if_iwxmld.h:100). AX211 = family 2 (AX210) → hard false. BZ fw without MLD capa is rejected outright (5781-5784).
- Contents: MLD link/sta/mac config, EMLSR policy, MLO scan, TTLM, MLD ROC/P2P, MLD sec-key (per-link), MLD queue cfg (`iwx_mld_queue_cmd`), MLD RX BAID, MLD aux sta/listener.
- Call sites in ItlIwx.cpp are all guarded: e.g. `iwx_add_sta_cmd`→`iwx_mld_add_sta_cmd` (9031-9032), `iwx_auth`→`iwx_mld_auth` (14606-14607), `iwx_run`→`iwx_mld_run` (14789-14790), `iwx_deauth` (14723-14724), `iwx_run_stop` (14928-14929), `iwx_enable_txq` (3874-3886), `iwx_tvqm_enable_txq` (4068-4088), `iwx_p2p_session_cmd` (13351-13353), plus `iwx_mld_rate_node` (14119-14133 — used in TLC path but returns `ic->ic_bss` when `!sc_use_mld_api`), notification handlers referenced in `iwx_rx_pkt` dispatch (EMLSR/stats-oper/beacon-filter notifs — these notifs don't exist in so-a0-gf-a0-68) and the non-WCL no-op stubs (ItlIwxMld.cpp:1107-1114).
- **Removal candidate with care**: ~60 guarded call sites + softc fields (`sc_mld_*` ~40 fields, if_iwxvar.h:738-772). Mechanical but broad; regression risk medium (missed guard = compile error, so risk is mostly build-time, not runtime).

### iwx_be_config.h — BE only
- `IwxBE::pciFamily` (iwx_be_config.h:6-15): GL=0x272b, BZ=0xa840/0x7740/0x4d40, everything else `None`.
- Used at: IOPCIEDeviceWrapper.cpp:86 (MSI-X configureInterrupts), ItlIwx.cpp:19865-19866 (sc_msix), 19957-19964 (BE cfg override + MAC check), 1671-1730 (fw candidate/ABI check), 2417-2418 (pnvm name), 4860-4862 (320 MHz/reduced-cap), 20042-20050 (`itlwm_gl_api` boot-arg). Softc member `sc_be` (if_iwxvar.h:855) forces the header to stay unless the member is removed too.

---

## 8. AX211 execution path map (probe → firmware alive → runnable)

1. **IOPCIDeviceWrapper::probe** (AirportItlwm/IOPCIEDeviceWrapper.cpp:60-114): `iwx_match` → `new ItlIwx`; AX211 → not BE → clear MSI-X enable bit, set MSI enable (97-102).
2. **ItlIwx::attach** (ItlIwx.cpp:313-337) → **iwx_attach** (19821-20254):
   - map PCIe BAR (19857-19863); MSI intr map `pci_intr_map_msi` (19870);
   - establish `IOFilterInterruptEventSource` with `iwx_intr` (sc_msix==0) (19915-19918);
   - read `CSR_HW_REV`/`CSR_HW_RF_ID` (19930-19944); `pci_match` → `iwl_so_long_latency_trans_cfg`; dev_info loop → `iwlax211_2ax_cfg_so_gf_a0`; `sc_fwname="iwlwifi-so-a0-gf-a0-68.ucode"` (19949-20041);
   - allocate gen3 ctxt_info DMA (family>=AX210, 20063-20065), ICT (20076), tx rings (cmd q0=128 slots gen3, 20083-20090, 3028-3033), rx ring (20092); task/taskq setup (20098-20194);
   - **iwx_preinit** (19728-19801) → iwx_prepare_card_hw (3341) → **iwx_start_hw** (3626-3679): clear persistence bit (no-op ≥AX210, 1527-1528), sw_reset (3503-3512, non-BZ branch), **iwx_apm_init** (3407-3460: L1/L0s chicken bits, apm_config link speed, INIT_DONE + clock-ready poll), **iwx_init_msix_hw**→`iwx_conf_msix_hw` MSI branch writes `UREG_CHICK_MSI_ENABLE` (3533-3540), rfkill check;
   - **iwx_run_init_mvm_ucode(readnvm=1)** (5746-5844) → **iwx_load_ucode_wait_alive** (5723-5743):
     - **iwx_read_firmware** (1669) → iwx_read_firmware_file (1734): blob → TLVs (sections, capa/API bits, cmd versions, IML 2082-2090, error-table addrs 2043-2077);
     - **iwx_start_fw** (5642-5675): rfkill int, clear/enable fw-load int, **iwx_nic_init** (3828-3844: apm_init + iwx_nic_config 3776 + nic_rx_init 3816 + shadow regs) → **iwx_load_firmware** (5585-5639) → **iwx_ctxt_info_gen3_init** (1384-1506: prph scratch/info DMA, fw image DMA (`iwx_init_fw_sec` 1038), IML DMA, write `CSR_CTXT_INFO_ADDR`/`CSR_IML_DATA_ADDR`, `AUTO_FUNC_BOOT_ENA`, iwx_set_ltr 1276, non-BZ boot kick `UREG_CPU_INIT_RUN=1` 1494) → wait ALIVE int 2 s; ALIVE notif (17601-17657) captures error tables + sku_id;
     - **iwx_load_pnvm** (2495) — §5;
     - **iwx_post_alive** (4166-4177): iwx_ict_reset (3297), iwx_enable_interrupts;
   - back in run_init_mvm: `sc_use_mld_api=false`; INIT_EXTENDED_CFG(INIT_NVM) + NVM_ACCESS_COMPLETE (5804-5812); wait INIT_COMPLETE (5828); **iwx_nvm_get** (§6);
   - iwx_stop_device (19765) — preinit done (rates setup, channel/media init 19775-19798).
3. **Runtime up**: `iwx_init` (16522) → **iwx_init_hw** (16313-16493): preinit fast-path, start_hw, run_init_mvm_ucode(0), TX_ANT_CFG, BT_COEX config, SOC_CONF (xtal 12000), (DQA skipped), **iwx_add_aux_sta** (9151, legacy), **iwx_phy_ctxt_cmd ADD × IWX_NUM_PHY_CTX** (non-MLD loop 16381-16396; ver 3 → `iwx_phy_ctxt_cmd_v3` 7572 + RLC cmd), (config_ltr skipped — capa SET_LTR_GEN2), TEMP_REPORT_THS (capa 74), POWER_TABLE_CMD, LAR MCC update ZZ, **iwx_config_umac_scan** (reduced v5, 9473), disable beacon filter; then `ieee80211_begin_scan`.
4. **Scan**: iwx_scan/iwx_bgscan (10725/10797) → iwx_umac_scan → **iwx_umac_scan_v14** (10058); completion via SCAN_ITERATION_COMPLETE_UMAC/SCAN_COMPLETE_UMAC (17773-17795) → iwx_endscan (15674).
5. **Auth/assoc**: iwx_newstate (15387) → newstate_task (15242) → **iwx_auth** (14602-14718, legacy): iwx_phy_ctxt_update (14560, v3+RLC), MAC_CONTEXT_CMD ADD (v5), BINDING_CONTEXT_CMD ADD, ADD_STA (v12), **iwx_enable_mgmt_queue** (13729-13750: ADD_STA v12 ⇒ first_data_qid=1, iwx_enable_txq SCD_QUEUE_CFG), clear statistics, SESSION_PROTECTION_CMD (capa 54). → **iwx_run** (14787-14905): phy ctxt chains/MIMO, MAC CONTEXT MODIFY, SF_CFG FULL_ON, MCAST filter, power device/mac, TIME_QUOTA, ADD_STA modify, STA_HE_CTXT_CMD (**iwx_config_he_sta** 14097), **iwx_rs_init** (14157, TLC_MNG_CONFIG_CMD v4, HE mode).
6. **Data TX**: iwx_start (16730) → iwx_tx (8414): first frame per TID → **iwx_tvqm_alloc_txq/enable_txq** (3939/3974, SCD_QUEUE_CFG, fw-assigned qid, gen3 bc_tbl 4031-4033, size limited to 256 — see comment 3946-3951); TX ring per fw queue; BA via iwx_ba_task (5233).
7. **RX/IRQ**: MSI `iwx_intr` (18240-18387) with ICT; RX via iwx_notif_intr (18160) → iwx_rx_pkt (17469) → iwx_rx_mpdu_mq (6733) → net80211; hw decrypt (6036), reorder (6428).
8. **Runnable**: IFF_RUNNING set in iwx_init (16588) after init_hw success (one retry on failure, 16561-16575).

---

## 9. Family classification table

Legend: (a) required for AX211; (b) shared infra (keep); (c) exclusively other families — removal candidate.

| Region (file:lines) | Class | Evidence | Removal candidate? | Regression risk if removed |
|---|---|---|---|---|
| ItlIwx.cpp:143-311 scan-state reset, deferred EAPOL, diagnostics | a/b | used on AX211 paths; `iwx_record_diagnostic` compiled only `#ifdef AIRPORT_WCL` (228-291) | No | — |
| ItlIwx.cpp:313-611 kext attach/detach/enable, driver-info getters | a | attach→iwx_attach (331) | No | — |
| ItlIwx.cpp:628-935 channel tables, rates, channel map init | a | iwx_nvm_channels_uhb used (uhb=1) | No | — |
| ItlIwx.cpp:936-1004 cmd-ver lookup, cscheme | b | core | No | — |
| ItlIwx.cpp:1022-1506 ctxt_info gen2 (1308-1383) / gen3 (1384-1506) init | a (gen3) / c (gen2) | gen2 only for family<AX210 (5595-5598); AX211 → gen3 | gen2 init removable | Low (isolated function) |
| ItlIwx.cpp:1508-1667 fw section store/free | b | core | No | — |
| ItlIwx.cpp:1669-1731 iwx_read_firmware BE loop | c | `sc_be.family == None` early-out (1671) | Yes (keep 2-line guard) | Low |
| ItlIwx.cpp:1734-2203 fw TLV parse | a | core, AX211 fw parsed here | No | — |
| ItlIwx.cpp:2211-2529 PNVM | a | so-a0-gf-a0.pnvm | No | — |
| ItlIwx.cpp:2531-3400 prph/mem/DMA/rings/rfkill/intr/ICT/prepare | b (BZ branch at 2927? no) | `iwx_alloc_tx_ring` gen3 branch 3028; keep all | No | — |
| ItlIwx.cpp:3400-3623 apm/msix | a (MSI part) / c (MSI-X part 3519-3623) | AX211: conf_msix_hw MSI branch only (3533-3540) | MSI-X half removable with BE | Low-Med |
| ItlIwx.cpp:3626-3773 start/stop device | a | BZ branches inline (3713-3715 etc.) | BZ sub-branches only | Med (inline edits) |
| ItlIwx.cpp:3776-4177 nic cfg, txq enable, tvqm, post-alive | a | MLD branches at 3874/3942/4068 guarded | MLD sub-branches only | Med |
| ItlIwx.cpp:4187-4530 time events, channel map | a | session protection capa 54 set | No | — |
| ItlIwx.cpp:4530-4910 rates, BA rx | a | HE rates used | No | — |
| ItlIwx.cpp:4910-5434 mac ctxt tasks, BA | a | legacy net80211 ifc | No | — |
| ItlIwx.cpp:5434-5844 nvm, fw load, init mvm | a | core; `sc_use_mld_api` set false (5772); BZ checks 5781-5798 | BZ block 5786-5798 removable | Low |
| ItlIwx.cpp:5847-7376 rx path, tx cmd | a | core | No | — |
| ItlIwx.cpp:7424-7750 binding/phy ctxt cmds | a | v3 (7695-7708 dispatch; AX211 ver 3) | uhb (7648-7692) & v1 tail (7721-7742) dead for AX211 but harmless | Low |
| ItlIwx.cpp:7759-8410 cmd send, tx fill, amsdu | a | core | No | — |
| ItlIwx.cpp:8414-9028 tx, flush, power | a | core | No | — |
| ItlIwx.cpp:9029-9472 add_sta/aux/rm_sta, scan cfg + fill | a | v5 reduced scan config (9485-9515); legacy cfg (9518-9598) dead for AX211 (API 56 set) | legacy scan-config fn removable | Low |
| ItlIwx.cpp:9601-9683 scan size helpers | a(b) | v12/legacy branches dead | v12/legacy removable | Low |
| ItlIwx.cpp:9684-10199 iwx_umac_scan dispatch + v12 + v14 | a (v14); c (v12, legacy) | AX211 → v14 (9762) | v12+legacy removable | Low |
| ItlIwx.cpp:10200-10795 mcc, rates, mac ctxt, quotas, tasks, scan entry | a | core | No | — |
| ItlIwx.cpp:10831-13552 AWDL/P2P/aux-ROC/listener | a (legacy listener) / c (MLD listener 12389-12557, 13253-13332; mld p2p 13253; mld roc 13296) | legacy listener path used by AX211 (iwx_legacy_listener_setup 13133; iwx_awdl_listen_v14 13591); MLD variants guarded | MLD AWDL subset removable | Med |
| ItlIwx.cpp:13657-14110 scan abort, mgmt queue, TLC/rate scaling | a | TLC offload (capa 43); EHT helpers (13957-14033) dead for AX211 (EHT only via MLD, 14178-14184) | EHT helpers removable | Low |
| ItlIwx.cpp:14119-14559 mld_rate_node (b helper), rs update | a | rs_update notif path | mld_rate_node simplify | Low |
| ItlIwx.cpp:14560-15000 phy update, auth/deauth/run/run_stop | a | legacy assoc | MLD branches only | Med |
| ItlIwx.cpp:15007-15241 keys | a | ADD_STA_KEY path (15057+); MLD branches 15065-15067, 15170-15177 | MLD branches only | Med |
| ItlIwx.cpp:15242-15706 newstate, sae join, scan task, endscan | a | scan_task (15623) is v17-only continuation — removable | scan_task removable only with Api86 | Med |
| ItlIwx.cpp:15783-16306 sf/bt/soc/mcc/temp | a | SOC_CONF xtal 12000 (15890-15895) | No | — |
| ItlIwx.cpp:16313-16730 init_hw/init/start/stop | a | core | No | — |
| ItlIwx.cpp:16748-17094 watchdog/ioctl | a | core | No | — |
| ItlIwx.cpp:17095-17440 nic error dumps | a | recovery forensics (BZ base-address thresholds inline 17102/17287) | No | — |
| ItlIwx.cpp:17441-18157 rx pkt dispatch | a | MLD notif case labels exist but notifs never arrive on AX211 fw | MLD case labels removable | Low |
| ItlIwx.cpp:18160-18484 notif_intr, iwx_intr, iwx_intr_msix | a (iwx_intr) / c (iwx_intr_msix 18389-18484 + BZ credit branches 18179-18235) | AX211: MSI + ICT | iwx_intr_msix + BZ RX-credit code removable | Med |
| ItlIwx.cpp:18486-19717 device tables + names | b (trim) | keep so/gf rows only | 22 of 26 iwx_devices rows + ~90% of dev_info + ~150 cfg/name lines removable | Low |
| ItlIwx.cpp:19719-20443 match/preinit/attach/init_task/resume/activate | a | core; BE MSI-X attach block 19864-19868 removable | partial | Low |
| **ItlIwxApi86.cpp + if_iwxapi86.h** | **c** | scan v17 = BE only (§7) | **Yes (whole file)** | Low |
| **ItlIwxMld.cpp + if_iwxmld.h** | **c** | MLD = BZ only (§7) | **Yes (with call-site cleanup)** | Med |
| **iwx_be_config.h** | c | BE selection helpers | Yes (with `sc_be` softc member) | Low-Med |
| **hal_iwm/** (ItlIwm, 7260-9260 family) | c (for AX211 project) | separate class ItlIwm (ItlIwm.hpp:36); no shared files with hal_iwx | Yes | Low (build config) |
| **hal_iwn/** (ItlIwn, 1000-6050 legacy) | c | separate class ItlIwn (ItlIwn.hpp:73) | Yes | Low |
| itlwm.cpp / itlwm.hpp (non-Airport scheme) | c for Airport-only builds | separate IOEthernetController product | Optional | Low |
| if_iwxreg.h / if_iwxvar.h | b | shared ABI defs; MLD/BZ structs interleaved | No (partial struct pruning possible) | — |
| Firmware blobs (41 of 43) | c | §10 | Yes | Low |

**Must-keep summary for AX211**: all of the legacy IWX command machinery (send_cmd, mac/binding/phy/sta ctxt, quotas, session protection, time events), scan v14, NVM v4, PNVM, TLC/HE rate scaling, BA/TX-RX rings (TVQM), power/beacon-filter/MCC/LAR, recovery (nic_error dumps, init_task restart logic, CT kill), AWDL **legacy** listener/P2P path (macOS WCL requirement), ICT+MSI interrupt path.

---

## 10. Firmware file inventory (itlwm/firmware/, 43 files)

| Blob(s) | HAL / family | Hardware | On AX211 path? |
|---|---|---|---|
| iwlwifi-so-a0-gf-a0-68.ucode + iwlwifi-so-a0-gf-a0.pnvm | iwx AX210-class (so+GF) | **AX211 (51F0/51F1/54F0/7A70/7AF0/7F70)** | **YES — keep** |
| iwlwifi-so-a0-gf4-a0-68.ucode + .pnvm | iwx (so+GF4 CDB) | AX411 | No |
| iwlwifi-ty-a0-gf-a0-68.ucode + .pnvm | iwx (ty+GF) | AX210 | No |
| iwlwifi-so-a0-hr-b0-68.ucode; iwlwifi-so-a0-jf-b0-68.ucode | iwx (so+HR/JF) | AX203/AX101/9560-on-So | No |
| iwlwifi-Qu-b0-hr-b0-68, Qu-c0-hr-b0-68, QuZ-a0-hr-b0-68 | iwx 22000 | AX201/AX203/AX101 | No |
| iwlwifi-Qu-b0-jf-b0-68, Qu-c0-jf-b0-68, QuZ-a0-jf-b0-68 | iwx 22000 | 9560 (Qu/QuZ) | No |
| iwlwifi-cc-a0-68.ucode | iwx 22000 (iwl_ax200_cfg_cc, ItlIwx.cpp:18868) | AX200 (0x2723) | No |
| iwlwifi-gl-c0-fm-c0-86.ucode, -92.ucode, .pnvm, -92.pnvm | iwx BZ (GL) | BE201 | No (IwxBE) |
| iwlwifi-bz-b0-fm-c0-92.ucode + .pnvm | iwx BZ | BE200 | No |
| iwlwifi-bz-b0-gf-a0-92.ucode + .pnvm | iwx BZ | BE200 (GF RF SKU) | No |
| iwm-3160-17, iwm-3168-29, iwm-7260-17, iwm-7265-17, iwm-8000C-36, iwm-8265-36, iwm-9000-46, iwm-9260-46 | **iwm** | 3160..9260 | No |
| iwn-1000/105/135/2000/2030/4965/5000/5150/6000/6005/6030/6050 | **iwn** | legacy 1000-6050 | No |

**Referenced but missing** (PCI matches, fw load fails — ItlIwx.cpp:1773-1777): iwlwifi-{SoSnj-a0-gf4-a0,SoSnj-a0-gf-a0,SoSnj-a0-hr-b0,SoSnj-a0-jf-b0,SoSnj-a0-mr-a0,ma-a0-hr-b0,ma-a0-gf-a0,ma-a0-gf4-a0,ma-a0-mr-a0,ma-a0-fm-a0}-63.ucode (SnJ 0x2726, MA 0x2729/0x7E40 — cfgs at 18659-18728) and iwlwifi-QuQnj-b0-{hr,jf}-b0-48.ucode (QnJ 0x2720, cfgs 18882-18894/19046-19058).

Embedding: scripts/fw_gen.sh:24 invokes scripts/zlib_compress_fw.py which zlib-compresses **every** file in the firmware dir into `include/FwBinary.cpp` `fwList[]`; runtime lookup by exact name `getFWDescByName` (include/FwData.h:36-44).

---

## 11. Findings

### Confirmed facts
1. AX211 (8086:51f0 any subsystem, incl. 0094) → `iwlax211_2ax_cfg_so_gf_a0` → `iwlwifi-so-a0-gf-a0-68.ucode` + `iwlwifi-so-a0-gf-a0.pnvm` (ItlIwx.cpp:18776, 19673-19677, 18617, 2408-2416).
2. `sc_device_family = IWX_DEVICE_FAMILY_AX210`; `sc_use_mld_api = 0`; `sc_msix = 0` (ItlIwx.cpp:20054, 5772-5773, 19864-19868).
3. AX211 fw ABI (parsed from blob): scan v14, ADD_STA v12, PHY_CONTEXT v3 (+ separate RLC v2 — ItlIwx.cpp:7629-7644), SCAN_CFG v5, SESSION_PROT v1, HE STA ctxt, NVM v4 (API 48), reduced scan config (API 56).
4. PNVM is mandatory when ALIVE v5 reports non-zero SKU; failure aborts init (ItlIwx.cpp:2503-2528, 5736-5738).
5. TX: cmd queue 0 (128 slots gen3), mgmt queue = first_data_qid 1 (ADD_STA v12), data queues TVQM/SCD_QUEUE_CFG fw-assigned, gen3 bc_tbl (ItlIwx.cpp:3028-3033, 13734-13742, 3855/3974, 4031-4033). No BE "gen4" queue mode on AX211 (MLD SCD_QUEUE_CONFIG is MLD-only).
6. RX: MQ RX ring 512 buffers, non-BZ write-back index register `RFH_Q0_FRBDCB_WIDX_TRG` (ItlIwx.cpp:18179-18183); BZ completion-descriptor path is dead for AX211.
7. Interrupts: MSI single vector, `IOFilterInterruptEventSource` + `iwx_intr`, ICT table (ItlIwx.cpp:19915-19918, 18250-18276, 3297). MSI-X (`iwx_intr_msix`, `configureInterrupts`) is BE-only.
8. Recovery on AX211 path: SW_ERR/HW_ERR/RF_KILL in `iwx_intr` → `iwx_nic_error` (LMAC+UMAC error tables, registry mirror) → `iwx_schedule_recovery` → `init_task` (20316-20390) with HW_ERR rate-limit (≥3 restarts/min or CT-kill ⇒ fatal) → stop/init. CT_KILL notif (17680-17691). Watchdog 16907. One automatic retry in `iwx_init` (16561-16575).
9. MLD/EMLSR/MLO/TTLM/EHT: dead for AX211 (family gate + fw ABI absent).
10. DQA command never sent on AX211 (capa 12 unset in so-a0-gf-a0-68).

### Unverified / open hypotheses
- Whether the MSI's specific subsystem 0094 has any RF-ID nuance — code matches by MAC SO + RF GF regardless of subdevice, which matches Linux behavior; not independently verified against the physical OTP.
- `iwx_umac_scan_v12`/legacy builder: believed dead with the *shipped* fw set (all blobs report v14 or v17). A hypothetical future fw advertising v12 would revive them.
- The unused per-cfg `trans` fields (e.g. `_long` variants) appear to be vestigial from Linux; confirmed unread in this codebase (`sc_cfg->trans` has zero references).

---

## 12. Open questions (for other subagents / next steps)

1. WCL layer (AirportItlwm/WCL/WCL.cpp) — does anything in it assume BE/MLD presence at runtime (e.g. MLO scan plumbing reachable from AirportItlwmV2) that would need stubbing if ItlIwxMld.cpp is removed? (The no-op stubs at ItlIwxMld.cpp:1107-1114 exist precisely for non-WCL builds, suggesting WCL builds link the real ones.)
2. Does the Xcode target embed firmware for all three HALs unconditionally (fw_gen.sh takes `-P <dir>`)? Trimming the firmware dir is the lever; verify the target's `-P` argument in project.pbxproj before deleting blobs.
3. `AirportItlwmV2.cpp` (1673 lines) was only spot-checked for this audit (HAL dispatch lives in IOPCIEDeviceWrapper.cpp); confirm no direct `sc_use_mld_api`/BE reachability from the V2 controller (it talks via ItlHalService interface).
4. Decide policy for 0x7E40/0x2726/0x2729 (PCI-match-but-broken): either ship ma-a0/SoSnj firmware or drop the IDs + cfgs.
