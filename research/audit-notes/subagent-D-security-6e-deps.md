# Subagent D — Security / Wi-Fi 6E / HE Dependency Map (Task M3-D)

Scope: `/home/z/my-project` (Eric-AirportItlwm, be200-tahoe, snapshot 84fb5d3 / HEAD e73c117), READ-ONLY.
Target: Intel AX211 (8086:51f0) on the legacy (non-MLD) iwx path, firmware `iwlwifi-so-a0-gf-a0-68.ucode` +
`iwlwifi-so-a0-gf-a0.pnvm`, `sc_device_family = IWX_DEVICE_FAMILY_AX210`, `sc_use_mld_api = false`, `sc_msix = 0`
(verified independently; matches Subagent A §1).
All `path:line` citations were read directly in this tree. Firmware ABI claims marked **[fw-parse]** were
extracted by this audit directly from the shipped blobs (TLV type 48 = `IWX_UCODE_TLV_CMD_VERSIONS`, 4-byte
entries `cmd,group,cmd_ver,notif_ver` per if_iwxreg.h:2978-2983, header 88 bytes per if_iwxreg.h:1637-1657),
not copied from another report.

Facts established by my own parse of `iwlwifi-so-a0-gf-a0-68.ucode` (176 cmd-version entries):

| Command (group, id) | so-a0-gf-a0-68 (AX211) | bz-b0-fm-c0-92 (BE200) | meaning |
|---|---|---|---|
| SCAN_REQ_UMAC (LONG 0x1, 0x0d) | **v14** | v17 | AX211 scans via `iwx_umac_scan_v14` |
| ADD_STA (LONG 0x1, 0x18) | **v12** | absent | legacy sta context |
| ADD_STA_KEY (LONG 0x1, 0x17) | **v3 advertised** (driver sends v1-shaped cmd) | absent | PTK/GTK install |
| PHY_CONTEXT_CMD (LONG 0x1, 0x08) | **v3** | absent | + RLC (DATA_PATH 0x08) **v2** |
| MAC_CONTEXT_CMD (LONG 0x1, 0x28) | **v5** | absent | |
| BINDING_CONTEXT_CMD (LONG 0x1, 0x2b) | **v2** | absent | |
| **STA_HE_CTXT_CMD (DATA_PATH 0x5, 0x07)** | **v2** | **absent** | HE activates on AX211 (code accepts v1/v2) |
| **TLC_MNG_CONFIG_CMD (DATA_PATH 0x5, 0x0f)** | **v3** | v4 | AX211 uses `iwl_tlc_config_cmd_v3` path |
| TLC_MNG_UPDATE_NOTIF (DATA_PATH 0x5, 0xf7) | notif **v3** | notif v3+ | rate notif parser |
| **MLD_SEC_KEY_CMD (DATA_PATH 0x5, 0x18)** | **ABSENT** | present | MLD keys impossible on AX211 fw |
| MLD_MAC/LINK/STA_CONFIG (MAC_CONF 0x08/0x09/0x0a) | **ABSENT** | present | MLD context impossible |

This is independent confirmation of A's §4/§7 with the additions that (i) **STA_HE_CTXT_CMD v2 is advertised**
(HE activation requires v1/v2, ItlIwx.cpp:4803-4804/14107-14109 — satisfied), (ii) TLC v3 (driver's
`cmdver < 4` branch at 14306-14331 handles it), and (iii) **the MLD ABI is entirely absent from the AX211
firmware**, so every MLD code path is dead by construction, not merely by the `sc_use_mld_api` gate.

---

## 1. Executive summary

1. **All AX211 security/6E/HE features live on the legacy (non-MLD, non-BE) code paths.** The dependency map
   below shows HE, 160 MHz, 6 GHz, SAE, PMF, OWE, WPA2/WPA3, PMKSA, and the crypto core are implemented in
   shared net80211 + the legacy iwx command paths, none of which are removal candidates except specific
   dead branches A already catalogued.
2. **CRITICAL PRE-EXISTING DEFECT D-01 (reduction-relevant):** `IEEE80211_C_MFP` is **never set on the AX211
   path**. The only set-site is inside the BZ-only block (ItlIwx.cpp:5786-5797); the attach caps list
   (ItlIwx.cpp:20108-20115) omits it and no other code sets it (grep over the whole tree: only 5795/5797
   write it). Because `ic_caps & IEEE80211_C_MFP` gates SAE usability (node.c:1770 `ieee80211_node_allow_wpa3`),
   SAE preference (node.c:1714-1716), MFP negotiation (node.c:1752-1755), MFPR-AP admission (node.c:1169-1172)
   and 6 GHz OWE (node.c:1156-1158), **as shipped, WPA3-SAE, PMF, and 6 GHz joining are inert at runtime on
   AX211** (every 6 GHz BSS is WPA2/WPA3 with MFPR). The old reference fork had the same hole
   (reference/research/ax211-audit DRV-11D-004). Eric fixed it for BE200 only.
   **Reduction action:** when deleting the BZ/MLD block, do not simply drop lines 5786-5797 — re-home the
   capability: for the AX211 legacy path set `ic->ic_caps |= IEEE80211_C_MFP` unconditionally (software
   BIP-CMAC-128 + firmware CCMP are always available; `ic_mld_gmac`/`ic_beacon_prot` stay 0 so GMAC stays
   refused and BIP-CMAC is the only negotiated mgmt cipher — exactly B's N-16 expectation).
3. **One genuine entanglement found (benign for AX211, worth knowing):** the 6 GHz **RNR directed-probe
   hints** collected by net80211 (`ieee80211_collect_scan_rnr` input.c:2283-2376, seeded by
   `ieee80211_seed_scan_rnr` from WCL.cpp:614) are consumed **only by the BE-only scan v17 builder**
   (ItlIwxApi86.cpp:194-222 short-SSID/BSSID hint arrays — a v17 probe_params feature). On AX211 (v14) the
   hints are collected but never consumed. Removing ItlIwxApi86.cpp therefore removes an AX211-inert
   consumer; 6 GHz discovery on AX211 rests on passive v14 scans (full 6 GHz list, PSC-filtered for bgscan)
   + the HE-Operation primary-channel fix (input.c:2642-2656). No action needed beyond optionally pruning the
   dead `ic_wcl_scan_rnr_*` state later.
4. **Crypto core:** 14 of the 21 compiled crypto files are REQUIRED for the AX211 feature set
   (incl. legacy WEP/WPA1/TKIP which remain supported); 7 have **zero reachable consumers** in this tree
   (cast, des set_key/ecb_enc/ecb3_enc, blf, gmac, chachapoly, poly1305, rmd160, idgen — see §13). They are
   removal candidates independent of the BE/MLD reduction (build-config work, per F).
5. All seven cross-checks (a–g) resolve **SAFE TO REMOVE** for AX211, with three edit-time hazards to
   respect: (i) D-01 C_MFP re-homing, (ii) the `!sc_use_mld_api && !sc_scan_active` guard at
   ItlIwx.cpp:17791 must be reworked when the v17-only scan state machine goes, (iii) ~60 MLD call sites in
   ItlIwx.cpp each keep a live legacy else-half that must survive the guard cleanup (missed guard = compile
   error, not silent regression).

---

## 2. Feature 1 — HE / Wi-Fi 6 (802.11ax)

**Implemented and active on AX211. Verified end-to-end.**

| Layer | Component | Evidence |
|---|---|---|
| IE parse (beacon/probe/assoc) | HE Cap/Operation/6 GHz-capa/MU-EDCA element dispatch | ieee80211_input.c:2581-2606 (`ELEMID_EXT_HE_CAPABILITY/OPERATION/HE_6GHZ_CAPA/HE_MU_EDCA`) |
| Node state update | `ieee80211_update_he_params` (setup_hecaps/setup_heop, live-association protection) | input.c:2150-2182; `setup_he_6ghz_capa` input.c:2742 |
| Local HE capabilities | `iwx_setup_he_rates` (legacy branch: STA_HE_CTXT version, NVM sku_11ax, 2×2 MCS map 0xfffa, 160 bit when `sc_nvm.vht160_supported`) | ItlIwx.cpp:4770-4905; caps at 4816-4838; EHT half (4840-4900) is BZ+MLD-only, dead |
| Negotiation | `ieee80211_he_negotiate` (width walk 20→160, MCS-160 intersection, reg_flags limits, 6 GHz HE-op width+ccfs0/1) | proto.c:956-1059 (6 GHz branch 985-1005; width-3 gate 1032-1042) |
| Basic MCS check | `ieee80211_he_supported` | proto.c:925-953 |
| RX NSS | `ieee80211_sta_set_rx_nss` HE branch (rx_mcs_80/160 by ni_chw) | proto.c:1236-1239+ |
| Firmware HE context | `iwx_config_he_sta` → `iwx_build_he_sta` (88-byte v2 ABI, bss color, pkt_ext/PPE, MU-EDCA) — sent from `iwx_run_update` and `iwx_mac_ctxt_task` legacy else-branch | ItlIwx.cpp:14097-14116, 14035-14094; calls at 14895 and 5108 (else of MLD link-config at 5091-5106) |
| Activation gate | requires `iwx_lookup_cmd_ver(DATA_PATH, STA_HE_CTXT_CMD) ∈ {1,2}` → **fw advertises v2 [fw-parse]** | ItlIwx.cpp:4803-4804, 14107-14109 |
| Rates/TLC | `iwx_rs_init` HE mode + `iwx_rs_fw_he_set_enabled_rates` (MCS 0-11 map, **MCS10/11 requires LDPC** mask, 160 column zeroed unless ni_chw==160), STBC/LDC/DCM flags `iwx_rs_fw_get_config_flags`; TLC_MNG_CONFIG **v3** cmd path | ItlIwx.cpp:14157-14335 (HE branch 14185-14187; rates 13933-13955; MCS11 map 13903-13918; v3 struct 14306-14331) |
| Rate feedback | `iwx_rs_update` (TLC_MNG_UPDATE_NOTIF **v3** → new rate format, fills `ni_he_txrate_kbps`/`ni_he_tx_nss` via `iwx_he_rate_kbps`) — this answers B's open question 6 | ItlIwx.cpp:14478-14554, `iwx_he_rate_kbps` 14420-14443; `iwx_mld_rate_node` is identity for non-MLD (14123-14124) |
| BA | HE nodes get RX BA winsize 256 | input.c:4414-4418 (B N-18) |

**Shared with BE/EHT:** `iwx_setup_he_rates` (EHT half is BZ+MLD-only), `iwx_rs_init` (EHT branches dead:
EHT requires `sc_use_mld_api && ic_eht_cap_valid`, 14178-14184 — `ic_eht_cap_valid` only set in the BZ branch
4840-4880), `ieee80211_eht_negotiate`/EHT parse (inert for AX211: `ic_eht_cap_valid` 0, node.c:2681 per B).
TLC v6 path (14269-14301) and EHT v4/v6 rate helpers (13957-14023) are MLD/BZ-only.
**Reduction entanglement:** none of the AX211-needed pieces sits in ItlIwxApi86.cpp / ItlIwxMld.cpp /
iwx_be_config.h. The MLD half-branches (5091-5106, 14204-14216, 14269-14301) must be deleted **with** their
guards so the legacy halves remain.

## 3. Feature 2 — 160 MHz

**Implemented.** Chain: NVM channel profile → `data->vht160_supported` (ItlIwx.cpp:4453-4456; set from
IWX_NVM_CHANNEL_160MHZ bit) → HE cap `CHANNEL_WIDTH_SET_160MHZ_IN_5G` + rx/tx_mcs_160 (4834-4838) →
VHT/HE negotiation `ni_chw` = CHAN_WIDTH_160 (proto.c:780-915 vht_negotiate incl. 80+80 handling at
848-866; HE width-3 at 1032-1042) → fw PHY context width `IWX_PHY_VHT_CHANNEL_MODE160`
(`iwx_phy_context_width` → `iwx_get_channel_width` from `ic_bss->ni_chw`, ItlIwx.cpp:7473-7495, 7522-7542)
via **PHY_CONTEXT_CMD v3** (7572-7645) → ADD_STA `IWX_STA_FLG_FAT_EN_160MHZ` (9078-9091) → TLC
`max_ch_width` = `iwx_rs_fw_bw_from_sta_bw(ni->ni_chw)` (14118 region: 13800-13811 mapping) and the
160-column rate mask (13940-13944). HE MCS-160 negotiation table at proto.c:1236-1239. Channel-center
fields: `ic_center_freq1` set by negotiate (proto.c:1054); ctrl_pos from center (ItlIwx.cpp:7497-7513).
AWDL 160-group logic at ItlIwx.cpp:12591-12623 is on the legacy (kept) listener path.
**Shared with BE:** width plumbing is shared; the only BE-only extra is 320 MHz
(`IEEE80211_CHAN_WIDTH_320` / `IWX_PHY_VHT_CHANNEL_MODE320`, EHT 320 gated BZ — dead for AX211).
`IEEE80211_CHAN_NO_320MHZ` reg flag set for all non-6GHz channels (ItlIwx.cpp:4448) — keep.
**Entanglement: none.**

## 4. Feature 3 — 6 GHz

**Implemented on the legacy path.** Components:

- **Channel table**: `iwx_nvm_channels_uhb` (ItlIwx.cpp:637-649, 59 entries incl. ch 1-233) selected when
  `sc_uhb_supported` (cfg `iwlax211_2ax_cfg_so_gf_a0.uhb_supported=1`, 18618/20060) **and** API bits
  `BAND_IN_RX_DATA` + `SCAN_EXT_CHAN_VER` (4412-4416) — both advertised by so-a0-gf-a0-68 (A §4 capa list).
  6 GHz channels map to indices 181+ (4438-4439), get `IEEE80211_CHAN_6GHZ|OFDM|HT20` (+HT40U/D when NVM
  40 MHz allows, 4488-4489) so `ieee80211_setmode` keeps them active (4477-4486 comment).
- **Regulatory/flags**: NVM v4 channel profile (API 48) via `iwx_nvm_get` v4 response (ItlIwx.cpp:5474-5565,
  v4 at 5495/5554-5556); PASSIVE when `!IWX_NVM_CHANNEL_ACTIVE` (4474-4475); DFS bit (4514-4516);
  LAR/MCC enforcement (capa 1) with `iwx_mcc_update` (10200-10220) + `mcc_task`/channel-profile resync.
- **Scan machinery (AX211 = v14)**: `iwx_umac_scan` dispatch (9758-9763) → `iwx_umac_scan_v14` (10058-10197)
  → `iwx_umac_scan_fill_channels` → `iwx_fill_chan_iter` (9260-9326): 6 GHz channels emitted with
  `chan->v2.band = IWX_PHY_BAND_6` when SCAN_EXT_CHAN_VER set (9293-9305); WCL per-band channel selection
  (`ic_wcl_scan_channels6GHz`, scanBandRestricted semantics WCL.hpp:439-447); **PSC filter for scheduled
  bgscan** (9288-9290, `AirportWCL::is6GHzPsc` WCL.hpp:449-451 — ch 5,21,37,...229); probe suppression on
  PASSIVE/DFS channels (9314-9320 `AirportWCL::probeChannel`, WCL.hpp:389-391). Scan completion for v14:
  SCAN_COMPLETE_UMAC uid 0 (17781-17782) and SCAN_ITERATION_COMPLETE_UMAC with
  `!sc_use_mld_api && !sc_scan_active` (17786-17795) → `iwx_endscan` → `ieee80211_end_scan`.
- **Discovery fixes**: 6 GHz beacon/probe channel taken from HE Operation 6 GHz info primary channel
  (input.c:2634-2656, mirrors cfg80211_get_bss_channel); `chanFromHe6` relaxes the off-channel discard
  (2667-2683).
- **RNR**: neighbor-report collection `ieee80211_collect_scan_rnr` (input.c:2283-2376; opclass 131-136,
  collocated-AP bit 0x40 required at 2330-2332, short-SSID CRC32) + `ieee80211_seed_scan_rnr` (2378-2391,
  called WCL.cpp:614). **Consumed only by ItlIwxApi86.cpp:194-222** (v17 short_ssid/bssid hint arrays).
  On AX211/v14 these hints are inert (v14 probe params have only `direct_scan[0]` SSID, 10161-10166).
- **Collocated/AFC**: no AFC (Standard-Power) machinery exists — STA-only, not needed. Collocated bit only
  used as an RNR filter (above). `IEEE80211_EXTCAP_CIR` defined but unused (ieee80211.h:1569).
- **HE on 6 GHz**: HE negotiation 6 GHz branch requires HE-op 6 GHz info present + primary match
  (proto.c:985-1005); HE 6 GHz capa parse `setup_he_6ghz_capa` (input.c:2742).
- **Security consequence**: 6 GHz BSSs are WPA2/WPA3-only with PMF required → match_bss checks
  (node.c:1134-1178) tie 6 GHz usability to C_MFP (**D-01**) and OWE-6GHz (node.c:1152-1159).

**Entanglement:** Api86 removal removes only the v17 RNR-hint consumer (AX211-inert). The shared
`iwx_fill_chan_iter` (used by v14 AND by v17's per-channel config) stays. Hidden-6GHz-scan capa 59 is
referenced only at ItlIwxApi86.cpp:308 (BE-only). 6 GHz scan does NOT depend on Api86.

## 5. Feature 4 — SAE / WPA3-Personal (H2E)

**Implemented in net80211 (host-side), pure software — no SAE firmware command exists or is needed.**

- Crypto: `ieee80211_sae.c` (749 lines): PT derivation `ieee80211_sae_password_to_pt` (sae.c:53-125,
  HMAC-SHA256 counter-mode HKDF), PWE (127-295), commit (297-459, SSWU, constant-time selects), verify
  (461-548), KCK/PMK/PMKID (628-705), confirm (707-749). Primitives: **ec_p256_m31.c + i31.c** (br_ P-256),
  **sha2.c** (SHA-256), **hmac.c** (HMAC-SHA256). md5.h/sha1.h includes at sae.c:35-36 are unused.
  Group 19 only (sae.c:491-495; `BR_EC_secp192r1` value 19 = P-256, B's cosmetic-name note stands).
- Protocol machine: `ieee80211_auth_sae` (proto.c:1648-1868): H2E required (RSNXE check via
  `ieee80211_node_allow_wpa3`, node.c:1758-1776; `IEEE80211_SAE_HNP_COMPAT` undefined → HnP compiled out,
  proto.c:1692-1717), token handling, anti-reflection, 3-attempt budget `ieee80211_auth_sae_timeout`
  (proto.c:1618-1646), PMKID into assoc (1855-1857).
- TX: SAE commit/confirm in AUTH frames via `ieee80211_send_mgmt` → mbuf sized from sae_len
  (output.c:1955-2059) → mgmt TX queue (driver `iwx_enable_mgmt_queue`, first_data_qid=1, ItlIwx.cpp:13729+).
  **SAE is 100% host-side; the firmware sees only ordinary mgmt frames.**
- Join integration: WCL classifies `PersonalSAE` (WCL.cpp:1086), sets AKM SAE + CCMP-only ciphers
  (`wclJoinWpaParams` WCL.cpp:1017-1049), derives PT in-driver (WCL.cpp:1152-1174, cached credential or
  `ieee80211_sae_password_to_pt`), sets `ic_sae_pt_valid=1`; deferred join hook
  `ic_sae_defer_join = iwx_defer_sae_join` (ItlIwx.cpp:20197; defn 15596-15620) consumed by
  `ieee80211_join_bss` (node.c:1332-1341).
- **ni_fails coupling (B's F-12)**: watchdog `ieee80211.c:956-966` — `ni_fails++` then
  `ieee80211_auth_sae_timeout(ic, bss, ni->ni_fails)`; SAE gives up at attempts>=3 (proto.c:1637-1640);
  double-count with proto.c:2091 burns the budget in ~2 timeout rounds. All seven increment sites listed by
  B (F-12). **Must-fix before/regardless of reduction; no reduction candidate touches it.**
- **Runtime gate D-01**: `allow_wpa3` requires `ic_caps & C_MFP` (node.c:1770) — currently false on AX211.

## 6. Feature 5 — PMF (802.11w)

**Implemented (software BIP on AX211).**

- Negotiation: MFPC/MFPR parsing in match_bss/choose_rsnparams (node.c:1752-1755 set NODE_MFP;
  1169-1178 MFPR/refusal; **GMAC refusal unless `ic_mld_gmac`** node.c:1161-1167 — `ic_mld_gmac` is set only
  in the BZ block ItlIwx.cpp:5791 → 0 for AX211 → BIP-CMAC-128 only, exactly as B found). Our F_MFPR
  requirement also refuses non-MFPC APs (node.c:1174-1178).
- BIP-CMAC-128: `crypto_bip.c` — set_key (69-79), encap/MMIE (99-165), decap + IPN replay (167-235),
  constant-time MIC compare; wired into TX at ieee80211_crypto.c:388-390 and RX key lookup by MMIE kid 4-7
  (crypto.c:334-359). Primitives: **cmac.c + aes.c/rijndael.c**.
- Key install (AX211 = software): `iwx_set_key` (ItlIwx.cpp:15007-15054) — BIP ciphers proceed to
  `iwx_set_key_hw` where the non-MLD path falls back to `ieee80211_set_key` SW install (15088-15091);
  IGTK kid 4/5 and BIGTK kid 6/7 from M3/group-msg1 with strict KDE framing (pae_input.c:890-969),
  TXMGMTPROT/RXMGMTPROT set on IGTK install (919-921); no firmware command carries mgmt keys on AX211
  (the only candidate, MLD_SEC_KEY_CMD, is **absent from so-a0-gf-a0-68 [fw-parse]**).
- RX enforcement: protected deauth/disassoc required (input.c:1108-1129), BIGTK beacon protection
  (input.c:1136-1142). SA Query: STA answers AP-initiated requests (input.c:4696-4723); the request/retry
  machine is STA_ONLY-compiled-out (proto.c:517-555) — known upstream gap (B N-16), unchanged by reduction.
- **Runtime gate D-01**: NODE_MFP only set when C_MFP (node.c:1753) — currently false on AX211.

## 7. Feature 6 — OWE (Enhanced Open, RFC 8110)

**Implemented.** `ieee80211_owe_prepare` (crypto.c:577-609: br_ec_p256_m31 group-19 keypair, arc4random
private key) at join (node.c:1326-1330); DH IE in assoc request (output.c:2216-2222, group 19 + pub key);
`ieee80211_owe_process_response` (crypto.c:611-674: shared-secret, HMAC-SHA256 "OWE Key Generation"
KDF → PMK, PMKID, scrubbing) on assoc response (input.c:3999); EAPOL MIC = HMAC-SHA256-128 for OWE
(crypto.c:713-719); 6 GHz OWE additionally requires MFP (node.c:1152-1159). Crypto: **ec_p256_m31.c,
i31.c, hmac.c, sha2.c**. MLO-OWE branches (pae_input.c:435-441, var.h:974-983) are net80211-shared and
require `ic_wcl_peer_is_mlo && ic_wcl_local_mlo_addrs_valid && ni_mld_valid` — only possible if WCL calls
`setMloHardwareAddresses` (V2.cpp:995-1011); inert on AX211 in practice (see open questions).

## 8. Feature 7 — WPA2/WPA3 transition + PMKSA + 4-way handshake

- **RSNE parsing branch points**: `ieee80211_parse_rsn`/choose_rsnparams (node.c:1700-1755): AKM filtering
  against `ic_rsnakms` (set by WCL join wpaparms, WCL.cpp:1017-1041); SAE preferred only when H2E+PT+C_MFP
  (1714-1717); OWE/PSK/SHA256-PSK/8021X/SHA256-8021X branches (1718-1741); cipher preference CCMP>TKIP
  (1744-1750). WPA1 parse (input.c:2100-2106). Transition-mode networks: SAE when allowed, else
  PSK/SHA256-PSK — WCL-side RSN-IE rewrite handles the Apple-side view (B's table; C's domain).
- **PMKSA seeding from WCL** (two sites): (i) join-time — WCL.cpp:1197-1208
  `ieee80211_pmksa_add(AKM_8021X / AKM_SHA256_8021X)` for a delivered 32-byte PMK; (ii) runtime enterprise
  — `installWCLKey` (WCL.cpp:955-982, wclCommand case 8 at 423) converts WCL PMK/MSK/PMKSA key ops into
  `ieee80211_pmksa_add(ni_rsnakms)`. PMKSA cache: crypto.c:857-894 (`pmksa_add` refuses SAE PMKIDs by
  design 863-865; HOSTAP-derived PMKID only in STA_ONLY-out branch 883-887). PMKID in msg1 KDE walk
  (pae_input.c:415-445) and pmksa_find in msg1 PMK selection (447-456).
- **4-way handshake (in-driver supplicant)**: msg1 (pae_input.c:382-489: PMK source selection 8021X-PMKSA
  447-456 / SAE 457-459 / OWE 460-464 / PSK 465-466), msg3 (585-998: ANonce check 625, MIC-before-parse
  636, replay monotonicity 613-617, **KRACK mitigations** — no PTK reinstall without RSN_NEW_PTK
  807-839, group-key reinstall guard `must_update_group_key` 563-570/865/908/950, WPA3-requires-IGTK
  733-736, RSNXE H2E match 738-744), group msg1/2 (1240-1448). EAPOL key-data decrypt: V1 RC4
  (crypto.c:830-839) or **AES Key Wrap** (840-848). EAPOL frames are never bridged pre-auth
  (input.c:1547-1554).
- Entanglement: none — all in net80211 + WCL, both kept.

## 9. Feature 8 — Crypto core inventory (see §13 table)

Required-for-AX211-feature-set: aes.c, rijndael.c, arc4.c, cast-less set… (full table §13). Unreachable:
cast.c (+castsb.h), set_key.c/ecb_enc.c/ecb3_enc.c (+des_locl.h/podd.h/spr.h/sk.h — DES), blf.c (blowfish),
gmac.c, chachapoly.c (+chacha_private.h), poly1305.c, rmd160.c, idgen.c. Verified by symbol-consumer grep
across the whole tree (no consumer outside crypto/ itself; `cast_setkey`, `des_set_key`, `blf_key`,
`chacha20_setkey`, `idgen32_init`, GMAC_CTX etc. appear nowhere else). Note blowfish/DES/cast/rmd160 are
inherited OpenBSD-crypto baggage; gmac/chachapoly/poly1305 would be needed only for BIP-GMAC/GCMP which are
refused (GMAC) / never negotiated (GCMP parses as unsupported) on AX211.

## 10. Feature 9 — Key installation / security state (WCL → V2 → HAL)

Flow on AX211 (STA): WCL join supplies credentials (PSK via **pbkdf2_sha1** WCL.cpp:1181 / SAE PT /
WEP nwkeys WCL.cpp:1209-1219 / enterprise PMKSA seeding) → net80211 supplicant derives keys →
`ic_set_key` (= `iwx_set_key`, ItlIwx.cpp:20215) →
- **Pairwise CCMP PTK**: `iwx_set_key_hw` → `IWX_ADD_STA_KEY` cmd (15093-15111; fw advertises v3 [fw-parse],
  driver sends the v1-shaped `iwx_add_sta_key_cmd` — accepted, matches the validated baseline), key_offset 0.
- **Group CCMP GTK**: same command with `IWX_STA_KEY_MULTICAST` + key_offset 1 (1499-15103).
- **IGTK/BIGTK (BIP)**: net80211 software (crypto_bip.c) — no fw command on AX211 (§6).
- **TKIP/WEP**: software in net80211 (crypto_tkip/wep.c) via the explicit fallback (15012-15014, 15088-15091).
- Delete: `iwx_delete_key` mirrors (15163-15207) with `IWX_STA_KEY_NOT_VALID`.
- EBUSY deferral queue for data keys only (15044-15053; mgmt keys must fail-fast 15034-15042 — comment
  documents the port-authorization hazard).
- **MLD key variants** (`iwx_mld_set_key`, ItlIwxMld.cpp:1849-1950+, MLD_SEC_KEY_CMD v1, CCMP/GCMP ciphers,
  per-link sta_mask, BIGTK beacon-prot gating): reachable only under `sc_use_mld_api`
  (15065-15066/15067-15086, 15170-15184) **and** the fw has no MLD_SEC_KEY [fw-parse] → BE-only, SAFE.
- `ic_defer_eapol_key_input` is MLD-only (5777-5780): AX211 processes EAPOL inline under the gate.

## 11. Feature 10 — Private / random MAC

**Supported.** WCL calls `setHardwareAddress` directly (AirportItlwmV2.cpp:1014-1067): BSD lladdr +
`ic_myaddr` updated; if the link is past SCAN while running, sets `ic_wcl_mac_reconfig` and
disable/enable (firmware restart) so MAC_CONTEXT_CMD/scan config pick up the new address
(uses of ic_myaddr: MAC_CONTEXT ItlIwx.cpp:10389, scan_config 9559, AWDL/listener cmds 12205-13515);
WCL-side MAC-update state machine consumes the reconfig (WCL.cpp:1100-1107, 1410-1441,
`AirportWCL::planMacUpdate`/`consumeMacReconfiguration`); scan-address rotation without restart when idle
(V2.cpp:1050-1058 comment). The deferred join covers the restart window (WCL.cpp:1105-1107).
No IOCTL/iovar beyond the V2 interface; nothing in the removal set touches it.

## 12. Feature 11 — Regulatory

Confirms B's N-20. Enforcement = (i) NVM/GEO-derived channel tables + `ic_chan_active`
(iwx_init_channel_map 4399-4530 incl. v4 channel_profile; PASSIVE 4474-4475, DFS 4514-4516, reg_flags
NO_40/80/160/320 4448-4454); (ii) scan fill consults `ic_chan_active` (Api86 227 / v14 via
iwx_fill_chan_iter input `ic_channels` walk + `sc_capa_n_scan_channels`); (iii) **probe suppression on
PASSIVE/DFS during directed scans** — ItlIwx.cpp:9314-9320 (the "9315" site, verified: the
`AirportWCL::probeChannel(n_ssids != 0, PASSIVE, DFS)` conditional selecting SSID-probe flag); (iv) beacon
hints lift PASSIVE only, never DFS, never 6 GHz (input.c:2685-2718 — verified: `channel_band !=
IEEE80211_CHAN_6GHZ` guard at 2696, DFS guard 2699/2715, 80 MHz-block vouching 2701-2717); (v) AWDL
listener channel constraints (ItlIwx.cpp:12584-12623, legacy path kept); (vi) MCC/LAR ZZ default +
CHUB updates (1790-1791, 17797-17817, mcc_task). **No removal candidate touches any of these**: Api86's
own channel logic disappears with it (BE-only), the v14 path's suppression stays in shared
iwx_fill_chan_iter, hal_iwm/hal_iwn have separate regdomain code, firmware reduction is name-keyed.
One nuance: removing `iwx_scan_task`/`sc_scan_*` requires reworking the guard at 17791 (see cross-check a).

---

## 13. Crypto reachability table (itl80211/openbsd/crypto/*.c, all 21 compiled per F §2/§3)

| File | Reachable from (AX211 feature set) | Verdict |
|---|---|---|
| aes.c | CCMP (ccmp.c), BIP (bip.c→cmac), CMAC EAPOL V3 (crypto.c:723), key wrap | **KEEP** |
| rijndael.c | aes.c backend | **KEEP** |
| cmac.c | BIP-CMAC-128 (crypto_bip.c:56-57), EAPOL MIC V3/USE_AKM non-OWE (crypto.c:722-727) | **KEEP** |
| sha2.c | SAE (sae.c:37), OWE KDF, PMKID-SHA256 (crypto.c:547), EAPOL SHA256-AKM MIC, pmkprf | **KEEP** |
| hmac.c | all HMAC_* wrappers (SAE/OWE/PMKID/EAPOL MICs) | **KEEP** |
| sha1.c | HMAC-SHA1 EAPOL V2 MIC (WPA2, crypto.c:706-712), PMKID-SHA1 (crypto.c:531) | **KEEP** |
| sha1-pbkdf2.c | PSK derivation (WCL.cpp:1181; itlwm.cpp legacy target only otherwise) | **KEEP** |
| md5.c | HMAC-MD5 EAPOL V1 MIC (WPA1, crypto.c:701-705) | **KEEP** (legacy WPA1 support is live) |
| arc4.c | WEP (crypto_wep.c:55), TKIP (crypto_tkip.c:57), EAPOL V1 key-data decrypt (crypto.c:830-839) | **KEEP** |
| michael.c | TKIP MIC (crypto_tkip.c:58) | **KEEP** (TKIP fallback still selectable, node.c:1748-1749) |
| key_wrap.c | EAPOL msg3/group-msg1 key-data unwrap (crypto.c:840-848) | **KEEP** |
| ec_p256_m31.c | SAE P-256 (sae.c:59 etc.), OWE group 19 (crypto.c:579) | **KEEP** |
| i31.c | SAE/OWE bignum (br_i31_*, sae.c:263-424, crypto.c) | **KEEP** |
| cast.c (+castsb.h) | **no consumer** (grep: zero refs outside crypto/) | REMOVE-CANDIDATE |
| set_key.c / ecb_enc.c / ecb3_enc.c (+des_locl.h, podd.h, spr.h, sk.h) | DES — **no consumer** | REMOVE-CANDIDATE |
| blf.c | blowfish — **no consumer** | REMOVE-CANDIDATE |
| rmd160.c | **no consumer** | REMOVE-CANDIDATE |
| gmac.c | **no consumer** (BIP-GMAC refused for non-MLD; even MLD path only via fw SEC_KEY) | REMOVE-CANDIDATE |
| chachapoly.c (+chacha_private.h) | **no consumer** (GCMP never negotiated) | REMOVE-CANDIDATE |
| poly1305.c | only chachapoly.c | REMOVE-CANDIDATE |
| idgen.c | **no consumer** | REMOVE-CANDIDATE |

Headers without .c counterparts (cryptodev.h etc.) follow their consumers. Removing the 7 candidates is
safe for AX211 WPA2/WPA3/PMF/OWE/legacy and is orthogonal to the BE/MLD reduction (pbxproj edits per F).
If product later drops WEP/WPA1/TKIP, arc4/michael/md5 (and the V1 EAPOL branches) become removable too —
separate decision, not part of this reduction.

---

## 14. Cross-checks against Subagent A's removal candidates

### a. ItlIwxApi86.cpp (BE scan v17) — **SAFE TO REMOVE**
- Dispatch: `iwx_umac_scan` only calls v17 when `cmd_ver(SCAN_REQ_UMAC)==17` (9696-9716); so-a0-gf-a0-68
  advertises **14** [fw-parse] → AX211 never enters. Batch continuation `iwx_scan_task` (15623-15671)
  calls v17 directly but is entered only with `sc_scan_active` set, which only the v17 dispatch sets (9700).
  Firmware proof: every API-68 blob (so/ty/Qu/QuZ/cc) advertises SCAN v14; only bz/gl (86/92) advertise v17
  (verified for bz-b0-fm-c0-92 and gl-c0-fm-c0-86 by my own parse + A's table).
- 6 GHz: v14 handles 6 GHz itself (iwx_fill_chan_iter band-6, §4). The only AX211-inert loss is the RNR
  directed-probe hint consumer (Api86:194-222) — hints were never consumed on v14 anyway.
- **Edit hazards**: (1) guard at 17791 (`!sc_use_mld_api && !sc_scan_active`) must become
  `!sc_use_mld_api` (or be dropped once MLD goes) or AX211's iteration-complete completion route breaks;
  (2) `iwx_endscan`'s `sc_scan_active`/`sc_scan_batch_pending` touches (15682-15706) and
  `iwx_scan_state_reset` need the same cleanup; (3) WCL's `ic_wcl_scan_restart_supported` flow
  (WCL.cpp:604-606) does not depend on v17 state.

### b. ItlIwxMld.cpp + ~60 `sc_use_mld_api` call sites — **SAFE TO REMOVE (with else-half preservation)**
- Enablers: `sc_use_mld_api = family >= BZ && capa(MLD_API_SUPPORT)` (5772-5773); AX211 family=AX210 →
  hard false; plus the MLD command ABI is absent from so-a0-gf-a0-68 [fw-parse] — even a hypothetical gate
  slip could not talk to the fw.
- Security/HE/6E-relevant sites audited individually (grep list of all 64 sites): keys 15065/15067/15170/
  15177 (AX211 → ADD_STA_KEY/SW-BIP else-paths), HE setup 4784/4803/4840 (legacy STA_HE_CTXT half),
  HE context 5091/5108 (else = `iwx_config_he_sta`), TLC 14204/14269 (v4/v3 path), auth/run 14606/14789/
  14723/14928 (legacy functions), scan 9497/13695 (v14 path), aux-sta/phy-ctxt init 16374/16381 (**legacy
  half is the AX211 path — must be kept when the guard is removed**), EAPOL deferral 5778 (non-MLD = NULL,
  inline processing), TTLM 20199 (dead), AWDL 10850-11907/12185/12591-12613 (legacy listener kept),
  TX 8459/8509/8519/8854 (legacy QoS/TID halves). No MLD-guarded branch gates an AX211-needed
  security/HE/6GHz function; every needed behavior is the non-MLD half.
- MLD keys/EMLSR/MLO-scan/TTLM/MLD-ROC/MLD-queue: BE-only (fw ABI absent).
- Softc fields `sc_mld_*` (if_iwxvar.h:738-772) and MLD notif case labels (17441-18157) go with it.

### c. iwx_be_config.h — **SAFE TO REMOVE (with `sc_be` member)**
Consumers verified: if_iwxvar.h:645/855 (include + `IwxBE::Selection sc_be`), ItlIwx.cpp 1671-1730 (fw
candidate loop — AX211 early-returns at 1671-1672), 2417-2418 (pnvm name — AX211 derives from ucode name),
4860-4862 (EHT 320/reduced — inside the BZ+MLD EHT block, dead), 19865 (sc_msix), 19957-19964 (BE cfg
override — AX211 keeps dev_info result), 20042-20050 (`itlwm_gl_api` boot-arg), IOPCIEDeviceWrapper.cpp:
85-95 (MSI-X configureInterrupts — BE branch). No security/HE/6E consumer. Header can go only together
with the `sc_be` member and the `IwxBE::` references listed.

### d. MSI-X removal (`iwx_intr_msix` 18389-18484 + `conf_msix_hw` BE half) — **SAFE TO REMOVE**
AX211: `sc_msix=0` (19864-19868 BE-only), MSI single-vector + ICT via `iwx_intr` (19915-19918) — key
install, EAPOL, mgmt TX and data TX all go through the command rings serviced by `iwx_notif_intr` from
either handler; `iwx_intr_msix` calls only shared helpers (notif_intr, nic_error, schedule_recovery,
check_rfkill, update_rx_desc) that the MSI path also uses. The non-BZ write-back register
`IWX_RFH_Q0_FRBDCB_WIDX_TRG` lives in `iwx_intr`/notif path (18179-18183 per A) — untouched. BZ RX-credit
code in notif_intr (18179-18235) goes with it.

### e. EHT / EMLSR / MLD keys — **SAFE TO REMOVE (BE-only)**
EHT: `ic_eht_cap_valid` set only in the BZ+MLD block (4840-4880); `iwx_rs_init` EHT requires
`sc_use_mld_api && ic_eht_cap_valid` (14178-14184); EHT parse/negotiate in net80211 are parse-and-carry
only (B's table). EMLSR: `ic_mld_emlsr_supported` only in the same block; EMLSR notifs don't exist on
so-a0-gf-a0-68. MLD keys: MLD_SEC_KEY_CMD absent [fw-parse] + `sc_use_mld_api` guards. BigTK:
`ic_beacon_prot` only set in the BZ branch (5792-5793) — BIGTK install still works host-side on AX211 via
pae_input 934-969 (needs D-01 fixed to ever negotiate).

### f. Firmware reduction to so-a0-gf-a0-68.ucode + .pnvm — **SAFE**
- AX211 (8086:51f0 incl. subsystem 0094) → dev_info generic "So with GF" (19672-19677 per A, verified
  19966-20000 loop) → `iwlax211_2ax_cfg_so_gf_a0` → `sc_fwname = "iwlwifi-so-a0-gf-a0-68.ucode"`
  (20041, cfg 18615-18621). `iwx_read_firmware`: `sc_be.family == None` → straight
  `iwx_read_firmware_file` (1671-1672) — **no candidate loop, no other name ever tried on AX211**.
- PNVM: derived by stripping the last '-…' segment → `iwlwifi-so-a0-gf-a0.pnvm` (2408-2416); BE override
  at 2417-2418 unreachable. File present in itlwm/firmware/ (verified listing).
- The "override list" A mentioned = the BE candidate loop (1673-1730, `IwxBE::candidate`), BE-only. The
  SnJ/MA/QnJ entries are dev_info cfgs referencing **missing** fw (`iwlwifi-SoSnj-*-63`, `ma-*-63`,
  `QuQnj-*-48`: ItlIwx.cpp:18659-18728, 18882-18894, 19046-19058 per A/F) — reachable only from PCI IDs
  0x2726/0x2729/0x2720/0x7E40 which must be removed from `iwx_devices`/plists together (A's open question 4);
  none of them is on the 51F0 path.
- Caveat (build, F §6): firmware trimming only takes effect when FwBinary.cpp regenerates (fw_gen.sh
  staleness quirk).

### g. hal_iwm / hal_iwn removal — **SAFE (zero security/HE dependency)**
- Separate classes (ItlIwm.hpp:36, ItlIwn.hpp:73), separate PCI IDs, own firmware (iwm-*/iwn-*).
- They **consume** net80211 (register their own `ic_set_key`: iwm mac80211.cpp:6115/3850, iwn
  ItlIwn.cpp:632/6423; use `ieee80211_set_key` SW fallback) but contribute nothing to it; no crypto/*.c or
  net80211 file is owned by them. hal_iwm/fw.cpp consumes `fwList` (F's open question 3) — after removal
  only ItlIwx.cpp references it.
- Surgery per F §10b: pbxproj (16+1 compile entries in BOTH live phases) + AirportItlwmV2.hpp:30-32
  includes + IOPCIEDeviceWrapper dispatch + plist IDs + 20 fw blobs.

---

## 15. What MUST survive the reduction (AX211 security/6E/HE checklist)

1. net80211 in full: ieee80211_sae.c, pae_input/output.c, crypto.c, crypto_bip/ccmp/tkip/wep.c,
   input.c (HE/6 GHz/RNR parse, beacon hints), node.c (RSN/PMF/OWE negotiation, ni_fails machine),
   proto.c (SAE machine, HE/VHT negotiate, SA-Query response), output.c (SAE/OWE/DH IE, RSN body).
2. Crypto: aes, rijndael, cmac, sha2, sha1, sha1-pbkdf2, hmac, md5, arc4, michael, key_wrap,
   ec_p256_m31, i31.
3. WCL.cpp + WCL.hpp (join/scan/PMKSA/MAC-update/shortSsid/chanspec) and AirportItlwmV2
   (setHardwareAddress, installWCLKey path, watchdog feed).
4. ItlIwx.cpp legacy command set: MAC_CONTEXT v5, BINDING v2, PHY_CONTEXT **v3 + RLC v2**, ADD_STA v12,
   ADD_STA_KEY (v1-shaped) for CCMP PTK/GTK, STA_HE_CTXT **v2** (`iwx_config_he_sta`),
   TLC_MNG_CONFIG **v3** (`iwx_rs_init` v3 branch), SESSION_PROT, scan **v14** + `iwx_fill_chan_iter`
   (band-6 + PSC + probe suppression), NVM v4 + channel map + MCC/LAR, PNVM, aux-sta + phy-ctxt ADD loop
   (16374-16396), legacy AWDL listener, `iwx_defer_sae_join`, MSI+ICT interrupt path.
5. The else-halves of every MLD guard listed in §14b (compile-time protected).
6. **D-01 fix**: set `IEEE80211_C_MFP` on the AX211 path (re-home from the BZ block) — without it the
   "reduction-safe" SAE/PMF/OWE/6 GHz code is runtime-dead anyway.
7. Regulatory sites: §12 list (esp. ItlIwx.cpp:9314-9320, input.c:2685-2718).

## 16. Open questions

1. **D-01 confirmation on hardware**: with C_MFP unset, an AX211 cannot join any 6 GHz / WPA3 / MFPR
   network (match_bss fails them). This contradicts any assumption that "6E works today" on Eric AX211 —
   recommend a live join test on the target machine (WPA3-Personal SSID) before/after the C_MFP re-home.
   (Static analysis is unambiguous; runtime confirmation is cheap insurance.)
2. **WCL MLO addresses on AX211** (§7): does macOS WCL ever call `setMloHardwareAddresses`
   (V2.cpp:995) against the AX211 driver? If yes, `ic_wcl_local_mlo_addrs_valid` + a Wi-Fi 7 AP's MLE could
   engage the net80211 MLO-OWE KDE paths on a non-MLD link. The mlo_downgrade logic (node.c:1322,
   input.c:4024-4034) covers the mismatch, but a runtime trace would settle it (Subagent C territory).
3. ni_fails fix (B's F-12 transfer) should land **before** the reduction branch so SAE retry behavior is
   evaluated on its own; the reduction does not touch it, but join-reliability testing conflates them.
4. BIP on AX211 is host-side; consider (post-reduction) whether firmware ADD_STA_KEY could carry IGTK on
   v3 fw — not required for correctness (SW BIP is complete), purely an offload question.
5. `IEEE80211_CHAN_NO_320MHZ` reg-flag plumbing and `IWX_TLC_MNG_CH_WIDTH_320MHZ` mapping are harmless
   dead constants for AX211 — keep or prune cosmetically, no functional risk either way.
6. HnP (compiled-out SAE fallback) decision remains B's N-15 open item; reduction-neutral.

---

## 17. Concise summary (per-feature one-liners)

| Feature | Implemented on AX211? | Core components | Reduction entanglement |
|---|---|---|---|
| HE/Wi-Fi 6 | **Yes — verified** (fw STA_HE_CTXT v2 [fw-parse]) | input.c:2581-2606/2150-2182; proto.c:956-1059; ItlIwx.cpp 4770-4905 (legacy half), 14035-14116 (HE ctxt), 14157-14335 (TLC v3), 14478-14554 (rate notif) | none — EHT/TLC-v6 halves are BZ+MLD-only, delete with guards |
| 160 MHz | **Yes** | proto.c:780-915/1032-1042; ItlIwx.cpp 4453-4456, 7473-7542 (PHY v3+RLC), 9078-9091, 13800-13811, 13940-13944 | none (320 MHz bits are BE-only) |
| 6 GHz | **Yes (v14 path)** | uhb table 637-649; channel map 4399-4530; v14 scan 10058 + chan_iter 9260-9326 (band-6/PSC/passive); HE-op channel input.c:2642-2656; RNR input.c:2283-2391 | **RNR hints consumed only by Api86 (v17)** — inert on AX211; removal safe |
| SAE/WPA3 | **Yes (host-side, H2E-only)** — but **gated off by D-01 (C_MFP unset)** | sae.c; proto.c:1618-1868; WCL.cpp:1152-1174; defer_join ItlIwx.cpp:15596/20197; crypto ec_p256_m31/i31/sha2/hmac | D-01: C_MFP set-site is BZ-gated (5786-5797) — must re-home, not delete |
| PMF | **Yes (SW BIP)** — same D-01 gate | crypto_bip.c; pae_input.c:890-969 (IGTK/BIGTK); node.c:1752-1178; input.c:1108-1142 | MLD SEC_KEY absent from fw [fw-parse]; GMAC refusal stays |
| OWE | **Yes** — 6 GHz variant also D-01-gated | crypto.c:577-674; node.c:1326-1330; output.c:2216-2222 | MLO-OWE net80211 branches shared+inert |
| WPA2/WPA3 transition + PMKSA | **Yes** | node.c:1700-1755; WCL.cpp:1197-1208 + installWCLKey 955-982; pae_input.c:382-998 (KRACK-safe) | none |
| Crypto core | 14 files required | aes/rijndael/cmac/sha2/sha1/sha1-pbkdf2/hmac/md5/arc4/michael/key_wrap/ec_p256_m31/i31 | 7 files unreachable: cast, des(set_key/ecb_enc/ecb3_enc), blf, gmac, chachapoly, poly1305, rmd160, idgen → REMOVE-CANDIDATES |
| Key install | **Yes**: ADD_STA_KEY CCMP PTK/GTK → fw; IGTK/BIGTK/TKIP/WEP → SW | ItlIwx.cpp:15007-15207 | MLD key variants BE-only, fw ABI absent |
| Random MAC | **Yes** | V2.cpp:1014-1067 + WCL MAC reconfig | none |
| Regulatory | **Yes, intact** | channel map 4399-4530; probe suppression 9314-9320; beacon hints input.c:2685-2718; MCC/LAR | no candidate touches enforcement; 17791 guard rework needed with Api86 removal |

**Cross-check verdicts:** (a) Api86 **SAFE** (v14 handles 6 GHz; RNR-hint loss is AX211-inert; fix guard
17791 + sc_scan_* cleanup) · (b) ItlIwxMld + ~60 guards **SAFE** (fw has no MLD ABI [fw-parse]; keep all
legacy else-halves) · (c) iwx_be_config.h **SAFE** (only BE selection + dead EHT-320 refs) · (d) MSI-X
**SAFE** (AX211 = MSI+ICT; shared helpers stay via iwx_intr) · (e) EHT/EMLSR/MLD-keys **SAFE** (BZ+MLD
gated, ABI absent) · (f) fw → so-a0-gf-a0-68+pnvm only **SAFE** (AX211 never enters the BE candidate loop;
SnJ/MA/QnJ names reachable only from removable PCI IDs) · (g) hal_iwm/hal_iwn **SAFE** (consume net80211,
contribute nothing to it).

**Must survive:** net80211 + WCL + V2 intact; the 14 crypto files above; ItlIwx legacy cmd set (MAC v5 /
BINDING v2 / PHY v3+RLC / ADD_STA v12 / ADD_STA_KEY / STA_HE_CTXT v2 / TLC v3 / SCAN v14 / NVM v4 / PNVM /
aux-sta+phyctxt loop / legacy AWDL listener / defer_sae_join / MSI+ICT); every MLD-guard else-half; and
the **C_MFP re-home (D-01)** — the single genuine security-critical action item the reduction surfaces.
