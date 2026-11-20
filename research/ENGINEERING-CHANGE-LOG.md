# Engineering Change Log — AirportAX211

Chronological record of confirmed defects, inefficiencies, changes,
rejected hypotheses, and deferred risks. Evidence: audit-notes/ (A-G),
the independent review (M6-REVIEW), and the Git history.

## Confirmed defects fixed

| ID | Defect | Fix commit | Notes |
|---|---|---|---|
| F-08 | EAPOL key-length unsigned wrap → OOB parse of msg1 PMKID / msg3 KDE / GTK | 4f09d44 | Security; reference guard transferred verbatim |
| F-06 | RX BA reordering buffer + parked MSDUs leaked on roam/deauth (ba_del) | 4f09d44 | Covers Eric's node_copy path (cleanup precedes copy) |
| F-12 | ni_fails double-count (watchdog + SCAN transition); choose_bss skipped on any nonzero | 4f09d44 + ad5fac4 | SAE budget preserved; UAF found in first version by review, fixed |
| F-09 | PNVM 3-meaning return; doorbell + 2 s wait + spurious fatal on no-match; unchecked inflate | 4f09d44 + ad5fac4 | ENOENT contract; errno signs normalized |
| F-13 | Firmware-load nic-lock failure leaked IML/fw/prph DMAs | 4f09d44 | goto fail1 unwind |
| F-07 | Rate printers OOB (ant==4, bw==5) | 4f09d44 | `>` → `>=` |
| F-05 | en0 link-down no-op (mask 0) + IFF_UP clobber | 4f09d44 | IFF_RUNNING-only clear |
| F-03/F-04 | Scan-result rates always empty; undeclared id in RB_NEXT | 4f09d44 | Count-before-copy with clamp |
| F-11 | WCL recovery link-up never posted (menu bar stuck) | 4f09d44 | Reference branch; Tahoe Supplicant event preserved |
| F-01/F-02 | Per-frame TX-rate and SW-crypto logs | 4f09d44 | Removed |
| F-10 | Watchdog re-arm via cleared member; no teardown guard; ungated cancel; scan timer removed after HAL release | 4f09d44 | Guards + timer-param re-arm + gated cancel + ordering |
| D-01 | C_MFP never set on the AX211 path → WPA3/PMF/6GHz-OWE runtime-inert | 069c440 | Software-PMF reachability verified by review |
| E-05 | A-MSDU addr3 read never-initialized ni_mld_addr | a5d2800 (T3b) | Non-MLO source after MLD removal |
| B-N21 | task_set memcpy OOB read (256 B past literals, 14 sites) | 4f09d44 | strlcpy |
| B-N26 | node_set_timeouts memset 16x over-run | 4f09d44 | sizeof(array) |
| C-1/E-16 | Late-start failures leaked fNetIf and skipped HAL detach | 4f09d44 | stopFromStartFailure helper |
| C-2 | Dead MAC-string snprintf pair | 4f09d44 | Removed |

## Demonstrated inefficiencies addressed

- E-06 (partial): hotspot RX trace performed a registry getProperty per
  received MPDU with tracing off → cheap filters reordered first (4f09d44).
  The TX-side lookup is retained deliberately (Eric's diagnostic hook;
  documented).
- F-01/F-02 per-frame logging (above).
- Firmware embedding reduced 42 MB → 1.6 MB (Tier 3a) — build-time and
  memory footprint, not a hot path.

## Rejected / not transferred (with rationale)

- B-N04 (unconditional new_state XYLog): kept. Moderate frequency (state
  transitions, not per-frame), present in both parent lineages, diagnostic
  value; removal without runtime evidence is not justified.
- Old fork's `iwx_eht_rate_kbps`-style shared helpers: retained where they
  compile and are merely unreachable (TLC never reports EHT on the AX211).
- GMAC/BIGTK firmware-key advertisement: not applicable — MLD ABI absent.
- Deferred-EAPOL-input machinery: MLD-path only; the net80211 hook remains
  declared and NULL, exactly as before for the AX211.
- Eric's PNVM payload-length==4 success criterion: demoted to a non-fatal
  diagnostic — BE-specific, would spuriously fail every AX211 PNVM load
  (review-confirmed).
- beacon protection (BIGTK verification): left disabled, matching both
  parent lineages (documented decision in code + D-01).

## Deferred risks (recorded, not fixed)

- E-15: no recovery trigger on plain 1 s command timeouts — recovery still
  relies on SW_ERR/HW_ERR interrupts or the 15 s TX watchdog. Inherited
  from both lineages; changing it needs runtime evidence.
- B-N02: aborted firmware scans do not post EVT_SCAN_DONE; WCL relies on
  its own timers. Behavior preserved exactly (including after the v17
  batch machinery removal).
- Review note (F-10): an in-flight watchdog callback could theoretically
  re-arm after the gated cancel; disable() closes the invocation window
  and the residual race pre-exists in the parent. Not introduced by us.
- Review note (F-11): a join completing via a path that never set
  wclLinkIndicated can produce one redundant LinkStatus(up) later;
  self-limiting and idempotent for airportd.
- SAE HnP-only APs are unjoinable (H2E-only build, B-N15) — intentional
  upstream configuration, recorded.
- STA never initiates SA Query / no SA Query on unprotected deauth
  (B-N16) — upstream-faithful OpenBSD behavior, recorded.

## Regression reviews

- Independent adversarial review (M6-REVIEW) of the fix batch + tier 3b
  surgery: 8 areas, verdicts 7 SOUND / 1 DEFECT (the F-12 UAF, fixed in
  ad5fac4) + 1 CONCERN (PNVM errno signs, fixed in ad5fac4). 16 of ~70
  collapsed MLD guards sampled, all named risk sites verified.
- Structural validation after every pbxproj surgery: balanced braces,
  zero dangling references, zero orphan objects, all phase entries resolve.
- Symbol sweeps after every removal: zero code references to removed
  identifiers (comments documenting the removals excepted).
