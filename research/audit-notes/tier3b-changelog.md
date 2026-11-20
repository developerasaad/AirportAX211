# Tier 3b Changelog — MLD / scan-v17 / BE / MSI-X removal

Evidence base: audit D cross-checks (a)–(g) — the AX211 firmware (API 68)
contains no MLD ABI and advertises SCAN_REQ_UMAC v14; no BE/gl/bz device
can match the reduced PCI tables; MSI-X was enabled only on the BE attach
path. Performed by subagent M5-T3b with coordinator verification; see
git history for the exact diff.

## Files deleted

- itlwm/hal_iwx/ItlIwxApi86.cpp (408 lines) — BE scan v17 implementation
- itlwm/hal_iwx/if_iwxapi86.h (112 lines) — its command structures
- itlwm/hal_iwx/ItlIwxMld.cpp (2595 lines) — MLD (BE firmware) command layer
- itlwm/hal_iwx/if_iwxmld.h (526 lines) — MLD structures (shared struct
  definitions moved to their users before deletion where still needed)
- itlwm/hal_iwx/iwx_be_config.h (124 lines) — BE200/BE201 PCI selection
- scripts/prepare_tahoe_sdk.py — exposed IOPCIDevice::configureInterrupts
  (Tahoe MSI-X API) in MacKernelSDK; the only consumer was the BE probe
  branch, removed below. Zero references remain, so the SDK patch step
  was dropped from CI as well.

## ItlIwx.cpp transformations

- iwx_umac_scan_size: removed the scan_ver == 17 branch
  (sizeof(iwx_api86_scan_req)); v12/v14/legacy size paths retained.
- iwx_umac_scan: removed the v17 fast-path block (sc_scan_active /
  sc_scan_next_channel / sc_scan_batch* state and the iwx_umac_scan_v17
  call); the legacy v14 builder path including the AIRPORT_WCL
  scan-restart preamble is unchanged.
- Scan-batch machinery removed after reachability analysis:
  iwx_scan_task, sc_scan_active, sc_scan_batch, sc_scan_batch_sent,
  sc_scan_batch_pending, sc_scan_next_channel, sc_scan_wcl_owned,
  sc_scan_wcl_join, iwx_scan_state_reset — every setter was inside the
  removed v17 path (grep-verified). iwx_endscan was simplified to the
  v14 semantics: clear flags, wake the gate, and call ieee80211_end_scan
  unless the scan was aborting — the aborting path intentionally does
  not call ieee80211_end_scan, exactly as before (WCL uses its own
  timers; audit B-N02 behavior preserved).
- All ~70 sc_use_mld_api guards transformed to the legacy else-half;
  ternaries collapsed. MLD-only functions removed from ItlIwx.cpp:
  iwx_mld_p2p_mac_cmd, iwx_mld_aux_sta_add, iwx_mld_listener_link,
  iwx_mld_listener_setup, iwx_mld_p2p_setup, iwx_mld_roc_cmd,
  iwx_mld_roc_notif, iwx_mld_queue_cmd call sites, iwx_mld_rate_node.
- iwx_run_init_mvm_ucode: the MLD capability block collapsed —
  sc_use_mld_api field deleted; ic_awdl_rx_ba / ic_awdl_peer_cache now
  follow iwx_awdl_legacy_ba_enabled() only; ic_awdl_llw_qos (MLD-only)
  removed; the AIRPORT_VTD deferred-EAPOL block removed
  (iwx_defer_eapol_key_input / iwx_process_deferred_eapol /
  iwx_deferred_eapol_task were MLD-path machinery, never active for
  AX211 — the net80211 hook ic_defer_eapol_key_input stays declared and
  NULL, as before); the BZ ENOTSUP guard and the BZ GMAC/BIGTK block
  removed; the D-01 C_MFP enablement is now the unconditional path with
  its rationale comment.
- E-05 resolved: the A-MSDU addr3 builder no longer reads the never-
  initialized ni_mld_addr; all peers are non-MLO on this hardware and
  addr3 uses the standard non-MLO source. The macOS-facing WCL fields
  (ic_wcl_peer_is_mlo, ni_mld_addr, ic_wcl_peer_mld_addr in the join
  bookkeeping) remain in the shared WCL/net80211 interface layer — they
  are part of the airportd contract — but no longer feed the firmware
  data path.
- EHT rate helpers removed (iwx_eht_peer_mcs_nss, iwx_eht_local_mcs_nss,
  iwx_rs_fw_eht_set_enabled_rates, iwx_mld_rate_node) — reachable only
  via MLD guards / family >= BZ.
- AWDL: the MLD listener/ROC/P2P/TX variants removed (iwx_awdl_tx used
  iwx_mld_queue_cmd for the AWDL peer station; iwx_awdl_ba_apply drove
  MLD RX_BAID_CONFIG sessions). The legacy AWDL implementation is
  intact: iwx_awdl_rx_ba, iwx_awdl_peer_cache, iwx_awdl_tx_frame,
  legacy listener setup, aux-ROC, vendor-action handling, defer_sae_join.
- MSI-X removal: iwx_intr_msix deleted; iwx_conf_msix_hw reduced to the
  exact body of the original !sc->sc_msix path (UREG_CHICK MSI_ENABLE
  under nic_lock when not stopped — verified against the pre-edit
  source); the interrupt attach is single-vector MSI
  (kIOInterruptTypePCIMessaged, IOFilterInterruptEventSource with
  intrFilter); sc_msix field deleted; the BE attach block (sc_msix = 1)
  removed.
- BZ-family branches in apm/sw-reset/boot/RX-credits/error-bases
  removed, keeping the pre-BZ (AX211) halves. All
  `>= IWX_DEVICE_FAMILY_AX210` comparisons were left untouched (the
  AX211 is family AX210).
- Unused config/table data removed after zero-reference verification:
  trans cfgs (qu/qu_medium/qu_long/ax200/so/snj/qnj/ma/gl/bz), iwl_cfg
  structs (AX200/AX201/AX210-ty/AX411-gf4/9560/Qu/cc/SnJ/sosnj/BE),
  their marketing name strings, iwl_be_gl_cfg / iwl_be_bz_cfg, and the
  post-walk SnJ workaround block.

## IOPCIEDeviceWrapper.cpp

- probe(): the AIRPORT_WCL BE branch (IwxBE::pciFamily check +
  configureInterrupts(kIOInterruptTypePCIMessagedX) allocation) removed.
  The legacy MSI path (find MSI-X cap and disable it, then enable MSI)
  now runs unconditionally for both WCL and non-WCL builds.

## if_iwxvar.h

- Removed sc_use_mld_api, sc_msix, sc_mld_active_sta_mask and the other
  MLD-only softc members; removed the sc_be BE selection state and the
  iwx_be_config.h include; kept everything referenced by the legacy path.

## itlwm.xcodeproj + CI

- The five deleted files removed from both kept Sources phases
  (61 compile units per target) and the file tree; pbxproj validated
  (balanced, zero dangling references, zero orphans).
- Workflow: the "Expose public Tahoe MSI-X API" step removed.

## Validation

- Brace balance preserved (the -2 naive paren delta in ItlIwx.cpp equals
  the pre-existing one, from parens inside log string literals).
- Zero code references remain for: sc_use_mld_api, iwx_mld_*, iwx_api86,
  iwx_umac_scan_v17, IwxBE, sc_msix, iwx_intr_msix, if_iwxmld.h,
  if_iwxapi86.h, iwx_be_config.h, sc_scan_active, sc_scan_batch*,
  sc_mld_active_sta_mask (comments documenting the removals remain).
- D-01 C_MFP enablement verified present and unconditional.
- Legacy AWDL/SAE-defer/PNVM/NVM/recovery/regulatory code verified intact.
