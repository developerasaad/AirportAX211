# Subagent B — net80211 / wireless-protocol audit (Eric-AirportItlwm)

Task ID: M3-B. READ-ONLY audit. Date: 2026-11.
Tree: `/home/z/my-project` = Eric-AirportItlwm snapshot, branch be200-tahoe, commit `84fb5d3`
("Import Eric-AirportItlwm be200-tahoe source snapshot", plus `e73c117` CI workflow; working tree
= import state). Build flavor audited: `AIRPORT_WCL` + `IEEE80211_STA_ONLY` + `DEBUG=1`
(compile_flags.txt; itlwm.xcodeproj/project.pbxproj:4347 etc. define only `AIRPORT_WCL` and
`IEEE80211_STA_ONLY` — **`IEEE80211_SAE_HNP_COMPAT` is NOT defined** anywhere in the project).

All `path:line` citations are relative to `/home/z/my-project` and were read directly in this tree.
"Old fix" references: `/home/z/my-project/research/audit-notes/subagent-G-reference-fixes.md` (F-01..F-13).

Verdict vocabulary for Part 1: ALREADY FIXED / STILL DEFECTIVE / BETTER IMPLEMENTATION /
ARCHITECTURAL DIFFERENCE / NOT APPLICABLE.

---

## Part 1 — Old-fix counterpart evaluation (Eric side)

### F-02 — per-frame SW-crypto TX log in `ieee80211_encrypt`

**Eric current code** — `itl80211/openbsd/net80211/ieee80211_crypto.c:365-396`:
```c
mbuf_t
ieee80211_encrypt(struct ieee80211com *ic, mbuf_t m0, struct ieee80211_key *k)
{
    if ((k->k_flags & IEEE80211_KEY_SWCRYPTO) == 0) {
                XYLog("%s: BUG! key unset for sw crypto. k_id: %d ...", ...);   // :370
        mbuf_freem(m0);
        return NULL;
    }

    XYLog("%s kid=%d cipher=%d\n", __FUNCTION__, k->k_id, k->k_cipher);          // :375  ← defect
    switch (k->k_cipher) { ... }
```
**Verdict: STILL DEFECTIVE — identical defect, same shape as the old baseline.**
Line 375 is byte-for-byte the old F-02 site (old baseline crypto.c:283). It fires for **every
software-encrypted TX frame**. Mitigating context in Eric: `ic_set_key` is overridden by the driver
(`ItlIwx.cpp:20215 ic->ic_set_key = iwx_set_key`), so the net80211 software path and its
`IEEE80211_KEY_SWCRYPTO` flag (crypto.c:224-225) are used only when firmware key install fails /
for SW-crypto fallbacks (TKIP/WEP/BIP) — the log is not on the CCMP fast path. It is still an
unconditional kprintf on a per-frame path that runs under the command gate.
**Transfer:** replace :375 with a comment exactly as the old fix did (old final tree
`reference/itl80211/openbsd/net80211/ieee80211_crypto.c:283-284`); **preserve** the BUG! error log
at :370 and the error-path `XYLogE` in `ieee80211_set_key` (crypto.c:227 — control-plane, key
install only; acceptable, not per-frame). Trivial, no behavioral risk.

### F-03 — scan-result rate array always empty (bzero-then-bound)

**Eric current code** — `AirportItlwm/AirportItlwmSkywalkInterface.cpp:1091-1127`
(`convertNodeToScanResult`):
```c
bzero(result, sizeof(*result));                                   // :1093
...
for (int i = 0; i < result->asr_nrates; i++ )                     // :1102  bound = just-zeroed field
    result->asr_rates[i] = fNextNodeToSend->ni_rates.rs_rates[i];
result->asr_nrates = fNextNodeToSend->ni_rates.rs_nrates;         // :1104  assigned AFTER the loop
```
**Verdict: STILL DEFECTIVE — identical defect.** `asr_nrates` is zeroed at :1093, so the copy loop
runs 0 iterations and `asr_rates` is always delivered empty while `asr_nrates` is set nonzero.
Consumers: `getSCAN_RESULT` (:1177-1209) and `getCURRENT_NETWORK` (:1159-1166).
**Node-side data source (my scope) is sound:** `ni_rates` is populated from the beacon/probe
Supported+Extended Rates IEs by `ieee80211_setup_rates` (input.c:3054 → node.c:3245-3270), with the
caller-side length guard `rates == NULL || rates[1] > IEEE80211_RATE_MAXSIZE` (input.c:2613;
RATE_MAXSIZE = 15, ieee80211.h:731) — the data is there, only the macOS-side copy is broken.
**Transfer:** port the old fix verbatim (old final tree `AirportItlwmSkywalkInterface.cpp:990-998`):
read `nrates` from the node, clamp to `sizeof(result->asr_rates)/sizeof(result->asr_rates[0])`
(`asr_rates` is `u_int32_t[APPLE80211_MAX_RATES]`, include/Airport/apple80211_var.h:483-485), store
the clamped count **before** the loop. u8→u32 element copy as in the in-tree V1 precedent.

### F-04 — undeclared `HalService` identifier in `RB_NEXT` call

**Eric current code** — `AirportItlwm/AirportItlwmSkywalkInterface.cpp:1204` (in `getSCAN_RESULT`):
```c
fNextNodeToSend = RB_NEXT(ieee80211_tree, &HalService->get80211Controller()->ic_tree, fNextNodeToSend);
```
`HalService` appears exactly once in the file (grep: only :1204); the member is `fHalService`
(correctly used at :1196). It compiles only because `RB_NEXT` discards its 2nd argument
(`itl80211/openbsd/sys/tree.h:725 #define RB_NEXT(name, x, y) name##_RB_NEXT(y)`).
**Verdict: STILL PRESENT (latent landmine, no runtime effect today).**
**Transfer:** change `HalService` → `fHalService` (one token), matching :1196.

### F-06 — RX BA reordering buffer never freed in `ba_del` (roam/deauth leak)

**Eric current code** — `itl80211/openbsd/net80211/ieee80211_node.c:2194-2222`:
```c
void
ieee80211_ba_del(struct ieee80211_node *ni)
{
    for (tid = 0; tid < nitems(ni->ni_rx_ba); tid++) {
        struct ieee80211_rx_ba *ba = &ni->ni_rx_ba[tid];
        if (ba->ba_state != IEEE80211_BA_INIT) {
            if (timeout_pending(&ba->ba_to))     timeout_del(&ba->ba_to);
            if (timeout_pending(&ba->ba_gap_to)) timeout_del(&ba->ba_gap_to);
            ba->ba_state = IEEE80211_BA_INIT;
        }                                    /* ← ba->ba_buf NOT freed, NOT NULLed */
    }
    ... same for ni_tx_ba; timeout_del(&ni->ni_addba_req_to[...]) x4
}
```
Allocation: `ba->ba_buf = malloc(IEEE80211_RX_BA_MAX_WINSZ * sizeof(struct ieee80211_ba_buf), 0, 0)`
at `ieee80211_input.c:4428` (ADDBA request; compat malloc is always zeroing —
`openbsd/sys/_malloc.h:27-38` — so the buffer starts clean).
Free sites that DO exist in Eric:
- DELBA received: input.c:4663-4670 (mbuf_freem all slots + free buffer + NULL).
- MLME-DELBA.request (Recipient): `ieee80211_proto.c:1423-1430` — reached from the RX-BA
  inactivity timeout `ieee80211_rx_ba_timeout` (proto.c:1315-1332).
- ADDBA refuse rollback: input.c:4480-4481 (buffer still empty, no mbufs parked yet — correct).
- HOSTAP-only `ieee80211_node_leave_ht`: node.c:3594-3604 (calls ba_del+ba_free **and** frees
  ba_buf) — but `ieee80211_node_leave` panics unless HOSTAP (node.c:3705-3706), so unreachable in
  the shipped STA-only build.
Free sites that DO NOT free ba_buf (the leak paths):
- `ieee80211_node_cleanup` (node.c:1803-1833, calls ba_del at :1822) — invoked on
  `ic_bss` at scan begin (node.c:897) and `ieee80211_free_allnodes(..., 1)` (node.c:2322).
- `ieee80211_node_free`/`ieee80211_free_node` (node.c:1836-1840, 2245-2276 → cleanup) — final free.
- `ieee80211_node_copy(ic, ic_bss, selbs)` at join (node.c:1294 → node_cleanup on dst at :1846):
  after cleanup fails to free ba_buf, `*dst = *src` at :1847 **overwrites the stale `ba_buf`
  pointers** with the fresh scan node's (NULL) values — the old buffer and any parked MSDUs become
  unreachable. This is the primary roam leak (RUN → bgscan → `node_switch_bss` → `join_bss`).
- `iwx_newstate` RUN→SCAN fast-path also calls `ieee80211_ba_del(ni)` directly
  (`itlwm/hal_iwx/ItlIwx.cpp:15411`), again without a buffer free.
**Verdict: STILL DEFECTIVE — same leak as the old baseline, in a structurally identical function.**
**Transfer:** port the old fix into `ieee80211_ba_del` (old final tree node.c:2031-2071): after
resetting state to INIT, free all parked mbufs + the buffer + NULL the pointer, per TID, mirroring
proto.c:1423-1430. **Caller-context invariant re-verified for Eric's timer model:** all
`timeout_*` operations execute through the driver's single command gate
(`openbsd/net80211/timeout.c:41-75` — `_fCommandGate->runAction(...)`), and CTimeout callbacks are
IOTimerEventSources on the same workloop (`openbsd/net80211/CTimeout.cpp:25-62`), so
cancel-then-free cannot race an in-flight callback on another thread — the F-06 transfer is safe
here. (One caveat outside net80211: the watchdog thread calls `new_state(SCAN)` without the main
gate — see Finding N-15 — that concurrency predates this fix and is owned by the V2/HAL audit.)

### F-08 — EAPOL key-length unsigned-wrap (OOB key-data parse)

**Eric current code** — `itl80211/openbsd/net80211/ieee80211_pae_input.c:130-139`:
```c
    /* check packet body length */
    bodylen = BE_READ_2(key->len);
    totlen = 4 + bodylen;
    if (mbuf_pkthdr_len(m) < totlen || totlen > MCLBYTES)
        goto done;

    /* check key data length */
    paylen = BE_READ_2(key->paylen);
    if (paylen > totlen - sizeof(*key))          // :138  ← unsigned wrap
        goto done;
```
`totlen`/`paylen` are `int` (pae_input.c:100) but `sizeof(*key)` is `size_t`; `totlen - sizeof(*key)`
promotes to unsigned 64-bit. The earlier guards (:111-117) check the **mbuf** length ≥
`sizeof(struct ieee80211_eapol_key)` (99 packed), not `totlen`; a 4-way M3 with `bodylen` small
(e.g. 0 → totlen = 4) passes :133 and then `paylen > (4 - 99)UL` is false for **any** paylen up to
65535 → `efrm = frm + BE_READ_2(key->paylen)` (pae_input.c:652-653) and the KDE walk
(:661-708) read past the pullup'd mbuf (pulled up to `totlen` at :168-171); the GTK/IGTK/BIGTK
`memcpy(k->k_key, &gtk[8], k->k_len)` (pae_input.c:876, 915, 957) then copies from OOB pointers —
kernel OOB read/write before MIC verification (MIC is checked first at :636 — good — but msg1's
PMKID parse at :412-433 runs **before** any MIC exists, on attacker-chosen `paylen`).
**Verdict: STILL DEFECTIVE — high-value security fix, port verbatim.**
**Transfer:** old final-tree semantics (`reference/.../ieee80211_pae_input.c:135-140`):
`if (totlen < sizeof(*key) || paylen > totlen - sizeof(*key)) goto done;` with the wrap comment.
Conformant frames always have totlen ≥ 99. Also check Eric's SAE/OWE-era additions for the same
pattern — I verified the SAE paths use explicit `sae_len >= CONSTANT` guards instead (proto.c:1677,
1723, 1790, 1804, 1839) — no wrap pattern there.

### F-12 — `ni_fails` double-count + over-strict candidate skip

**Eric current code — watchdog** `itl80211/openbsd/net80211/ieee80211.c:941-976`:
```c
ieee80211_watchdog(struct _ifnet *ifp)
{
    if (ic->ic_mgt_timer && --ic->ic_mgt_timer == 0) {
        if (ic->ic_opmode == IEEE80211_M_STA &&
            (ic->ic_state == IEEE80211_S_AUTH || ic->ic_state == IEEE80211_S_ASSOC)) {
            ...
            ni = ieee80211_find_node(ic, ic->ic_bss->ni_macaddr);
            if (ni)
                ni->ni_fails++;                                   // :958  unconditional (AUTH and ASSOC)
            if (ic->ic_state == IEEE80211_S_AUTH && ni &&
                ieee80211_auth_sae_timeout(ic, ic->ic_bss, ni->ni_fails))   // :959-960 SAE retry/fail
                goto done;
            if (ic->ic_state == IEEE80211_S_AUTH && ni && ni->ni_fails < 3) {
                ieee80211_node_join_bss(ic, ni);                  // :963-964 in-place retry
                goto done;
            }
            if (ISSET(ic->ic_flags, IEEE80211_F_AUTO_JOIN))
                ieee80211_deselect_ess(ic);
        }
        ieee80211_new_state(ic, IEEE80211_S_SCAN, -1);            // :970 give-up → SCAN
    }
```
**Eric current code — newstate SCAN entry** `ieee80211_proto.c:2086-2093`:
```c
        case IEEE80211_S_AUTH:
        case IEEE80211_S_ASSOC:
                /* timeout restart scan */
                ni = ieee80211_find_node(ic, ic->ic_bss->ni_macaddr);
                if (ni != NULL)
                        ni->ni_fails++;                           // :2091 second count
                ieee80211_begin_scan(ifp);
```
**Eric current code — candidate skip** `ieee80211_node.c:1441-1453` (`choose_bss`):
```c
        if (ni->ni_fails) {                       // :1443 skip on ANY nonzero fails
            if (ni->ni_fails++ > 2)
                ieee80211_free_node(ic, ni);      // :1449-1450 eviction at fails>2
            continue;
        }
```
**Verdict: STILL DEFECTIVE — both halves, in Eric's own shape:**
1. **Double count:** the watchdog increments at ieee80211.c:958 *before* deciding; the give-up path
   then transitions SCAN and proto.c:2091 increments the same node again → one transient
   AUTH/ASSOC timeout counts 2 (the old baseline's exact defect; the old fix counted only on the
   retry path). The in-place retry path (:963) counts once (acceptable), but the SAE continuation
   path (:959-960, `goto done`) also counts once per attempt.
2. **Over-strict selection:** `choose_bss` skips any candidate with `ni_fails != 0`
   (node.c:1443) instead of the upstream/old-fix `>= 2` — one transient failure makes the AP
   unselectable and it is evicted on the following sweep (`ni_fails++ > 2` → free at :1449-1450).
3. **Eric-specific twist (new):** the watchdog passes `ni->ni_fails` into
   `ieee80211_auth_sae_timeout(..., attempts)` (ieee80211.c:959-960) and SAE gives up at
   `attempts >= 3` (proto.c:1637-1640). Because `ni_fails` is double-counted and never reset
   between ESS retries until RUN (proto.c:2236-2239), a WPA3-SAE join can burn its 3-attempt budget
   in ~2 timeout rounds. Transfer must fix the accounting *before* touching SAE thresholds.
**Complete list of ni_fails increment sites in Eric** (for the fix work): ieee80211.c:958
(watchdog, AUTH|ASSOC timeout); ieee80211_input.c:3908 (assoc-resp failure, tree node ≠ bss);
ieee80211_node.c:1449 (choose_bss eviction post-increment); ieee80211_proto.c:1462
(try_another_bss, AP steering — intentional, keep); proto.c:1584 (open-auth status≠0, tree node);
proto.c:1611 (SAE auth failure, tree node); proto.c:2091 (newstate SCAN entry). Resets:
proto.c:2236-2239 (RUN entry); ioctl.c:203 (user SIOCS80211NODE copy-in).
**Transfer:** old-final semantics — watchdog increments only when it will retry in place (move the
`ni_fails++` inside the `ic_state == S_AUTH && ni && ni_fails < 3` branch, or keep :958 and delete
the proto.c:2091 increment for the give-up path — choose ONE site; note proto.c:2091 also fires for
non-timeout AUTH/ASSOC→SCAN transitions, so the old fix's choice — watchdog counts retries, SCAN
entry counts the give-up exactly once — requires removing the watchdog's unconditional increment);
`choose_bss` skip threshold `ni->ni_fails >= 2`. Preserve: eviction `> 2` semantics, RUN clears,
retry budget 3, `try_another_bss` increment (deliberate steering penalty).

### F-01 (out-of-scope cross-reference, HAL) — per-frame TX rate log

`itlwm/hal_iwx/ItlIwx.cpp:8200`: `XYLog("%s hwrate: %d ridx: %d rate: %d minrate: %d\n", ...)`
inside `iwx_tx_fill_cmd` — still present. Narrower than the old baseline: HT-data and legacy-data
frames return early at :8174/:8181, so the log now fires only for multicast/mgmt/fixed-rate
frames — still an unconditional per-mgmt-frame kprintf plus two function calls
(`iwx_ridx2rate`, `ieee80211_min_basic_rate`) in the arguments. Belongs to Subagent D/E (HAL);
recorded here because it is the F-01/F-02 family.

---

## Part 2 — Independent Eric-specific audit findings

Labels: **[Confirmed defect]** / **[Demonstrated inefficiency]** / **[Plausible risk]** /
**[Unverified hypothesis]** / **[Intentional behavior]**.

### Scanning

**N-01 [Architectural difference, healthy] Scan machine is firmware-driven and WCL-owned.**
`SIOCS80211SCAN` is disabled (ioctl.c:877-879, "Disabled. SIOCG80211ALLNODES is enough."). Scans
are started by the WCL layer (join scans pinned to the channel WCL selected — WCL.cpp:1112-1132
sets `ic_wcl_scan_channels`/`...6GHz` bitmaps) and executed by firmware
(`iwx_fill_chan_iter` ItlIwx.cpp:9273-9326). net80211's per-channel `ieee80211_next_scan`
(node.c:919-948) is mostly vestigial bookkeeping; `ieee80211_end_scan` (node.c:1507-1682) runs on
firmware completion via `iwx_endscan` (ItlIwx.cpp:15773-15723). Results are published three ways:
(i) into the node table (`ieee80211_recv_probe_resp_bss`, input.c:2735-2739 find-or-alloc),
(ii) live to WCL via `IEEE80211_EVT_BEACON` → `publishWCLBeacon` (input.c:3058-3071;
WCL.cpp:1479-1528, gated on scanPending/joinPending/SCAN so the associated AP's ~10 Hz beacons do
not flood the result ring — comment at WCL.cpp:1520-1526), and (iii) by ioctl walking `ic_tree`
(`getSCAN_RESULT`, SkywalkInterface.cpp:1177-1209 — steps over channel-less nodes, :1192-1195).

**N-02 [Plausible risk, cross-boundary] Aborted scans never post EVT_SCAN_DONE.**
`iwx_endscan` (ItlIwx.cpp:15700-15715): when `scan_aborting` (firmware reported
non-COMPLETED status, or `IWX_FLAG_SCAN_ABORTING`), it clears F_BGSCAN and returns **without**
calling `ieee80211_end_scan` → no `IEEE80211_EVT_SCAN_DONE` (only end_scan posts it,
node.c:1517-1518). WCL's handler (WCL.cpp:1548-1555) only completes `scanPending` on that event.
If WCL cancels a scan (abort path), WCL-side completion presumably relies on its own timers
(`fakeScanDone` V2.cpp:130-142, `scanSource`). Needs WCL-side verification (Subagent C); from the
net80211 side the asymmetry is real: successful scans post the event, aborted ones do not.

**N-03 [Intentional behavior] "Not found" scan loop.**
`ieee80211_end_scan` → `notfound` (node.c:1563-1591): with `IEEE80211_C_SCANALLBAND` (true for
iwx), an empty scan increments `ic_scan_count` and immediately rescans — "This will loop forever
until an access point is found" (comment :1580-1582). Same as upstream; be aware when reasoning
about idle CPU/dwell in an RF-silent room.

**N-04 [Confirmed defect — minor] Unconditional XYLog on every MLME state transition.**
`ieee80211_new_state` is a macro with an embedded `XYLog("%s %d nstate=%d\n", ...)`
(ieee80211_proto.h:128-132). Every transition (including per-beacon-loss rescans and TTLM churn)
prints. Control-plane frequency, but unconditional in a DEBUG=1 production kernel. Recommend
gating behind `ieee80211_debug`/DPRINTF during the engineering pass (same treatment as F-02).

**N-05 [Intentional behavior] Beacon "regulatory hint".**
input.c:2685-2718: a beacon received on its own channel sets `ic_beacon_hint` for that channel
(and the AP's whole 80 MHz block for the two Apple-AWDL blocks), lifting PASSIVE — never DFS
(:2699, :2715), never 6 GHz. Consumers: AWDL listener picks (ItlIwx.cpp:12584-12623). Matches
Linux `reg_process_beacons` semantics; documented in BE200.md:101. Do not weaken.

### Node management

**N-06 [Confirmed structure] Node table invariants.**
RB tree keyed by MAC (`ieee80211_node_cmp`, node.c:3900-3905; RB_GENERATE :3920). Insert under
`splnet()` (no-op in this port, timeout.c:32-39) at setup_node :1933-1936; capacity
`ic_max_nnodes = ieee80211_cache_size` (node.c:744; ieee80211.c:88, IEEE80211_CACHE_SIZE) with
`clean_nodes` eviction on overflow (alloc_node_helper :777-787). Refcount: `ni_refcnt`,
`ieee80211_ref_node`/`release_node` (decref → unref_cb → free if COLLECT, node.c:2278-2298).
`node_newstate` is a plain field-write macro (node.h:190-193). `ic_bss` holds one permanent ref
(lateattach :799); `free_node` panics if asked to free it (:2249-2250). All consistent with
upstream; no defect found in the invariants themselves.

**N-07 [Confirmed defect — leak, = F-06 family] Node-final free path drops ba_buf.**
`ieee80211_free_node` → `ic_node_free` → `node_cleanup` → `ba_del`+`ba_free`
(node.c:2262-2274, 1836-1840, 1822-1823): timers freed (`timeout_free`, node.c:2224-2243) but
`ba_buf` and parked MSDUs are not — a scan-evicted or inactivity-evicted node with a live RX BA
session leaks ~2 KB/TID + mbufs. Fixed by the F-06 transfer (free inside ba_del).

**N-08 [Confirmed OK] `ni_unref_arg` (roam hand-off) lifecycle.**
`end_scan` allocates `switch_bss_arg`, stashes it on `ic_bss->ni_unref_arg` with callback
`ieee80211_node_switch_bss` (node.c:1642-1675). The callback frees the arg (node.c:1242-1261);
`release_node` NULLs `ni_unref_arg` after the callback returns (node.c:2287-2292);
`node_cleanup` frees it only if the callback never ran (:1824-1828). No double free; the
bgscan roam sequence (stop A-MPDU TX → DEAUTH → unref → switch → join) is upstream-faithful.

**N-09 [Intentional behavior] DESBSSID latched per association / WCL owns AP choice.**
`choose_bss` returns the WCL-chosen node immediately when F_DESBSSID is set (node.c:1464-1468);
`match_bss` fails everything unless `ic_wcl_join_requested` (node.c:1075-1078). Driver-side
autonomous roaming is thus disabled by design in the WCL flavor (same policy family as the old
fork's "roaming disabled by design"); bgscan roamscan still exists
(`roamscan` in end_scan/join_bss, node.c:1514-1515) but only runs when WCL allows
(`IEEE80211_F_DISABLE_BG_AUTO_CONNECT`).

### Authentication/association state machine

**N-10 [Confirmed] Who drives transitions.**
`ieee80211_new_state` macro → `ic_newstate` = `iwx_newstate` (ItlIwx.cpp:15386-15425) which
dedups same-state transitions (:15400-15402), stops A-MPDU TX + `ieee80211_ba_del` on RUN→SCAN
(:15404-15417) and defers the net80211 `ieee80211_newstate` body to `newstate_task` on `sc_nswq`
(:15419-15422; task registered ItlIwx.cpp:20183). Timers: `ic_mgt_timer` (AUTH/ASSOC timeout) is
decremented by `ieee80211_watchdog` (ieee80211.c:941-976) driven by the V2 1 s watchdog
(AirportItlwmV2.cpp:122-128, 432-440); `ic_bgscan_timeout`, BA timers etc. are CTimeouts
(command-gate serialized). Failure paths converge on `new_state(SCAN)`; cancel semantics =
iwx task removal + generation counters (HAL scope).

**N-11 [Confirmed — see F-12] ni_fails accounting** (all seven increment sites listed in Part 1).

**N-12 [Plausible risk — cross-boundary] Watchdog thread is not gate-serialized against MLME.**
`watchdogAction` (V2.cpp:122-128) runs on the separate `fWatchdogWorkLoop` (created and armed at
V2.cpp:432-440) and calls `if_watchdog` (= `ieee80211_watchdog`) directly — which mutates the node
tree (`find_node`, `join_bss`→`node_copy`→`node_cleanup`, `new_state`) while RX/newstate processing
runs under the main command gate on the main workloop. `splnet()` is a no-op (timeout.c:32-35) and
there are no KASSERTs. This is the F-10-class defect the old fork fixed by moving the watchdog
onto the main workloop (old fix §9). It is AirportItlwm-integration scope (Subagent C) but its
blast radius is entirely net80211 state; flagged here with evidence. The old tree's invariant to
port: watchdog on the single workloop/gate, cancel-through-gate at teardown, re-arm via sender.

### EAPOL / 802.1X

**N-13 [Confirmed] In-driver supplicant, full 4-way + group key handshake.**
RX: `ieee80211_eapol_key_input` (pae_input.c:92-208) → msg1 :382-489 (PMK source selection:
PMKSA for 802.1X :447-456, SAE PMK :457-459, OWE :460-464, PSK :465-466; SNonce random; RSN_NEW_PTK
flag set), msg3 :585-998 (ANonce match :625, MIC before parse :636, replay monotonicity :613-617,
KRACK mitigations — no PTK reinstall without RSN_NEW_PTK :807-839, no GTK/IGTK reinstall via
`must_update_group_key` :563-570/865/908/950, WPA3 requires IGTK :733-736, RSNXE snapshot match
for H2E :738-744, second-RSN-IE pairwise cipher handling :766-781), RSN/WPA group msg1
:1240-1342 / :1348-1448. TX: `ieee80211_send_eapol_key` (pae_output.c:75-155) routes frames
through the normal ifq/if_start (EAPOL is NOT bridged, enqueue_data input.c:1547-1554 drops
non-EAPOL before port_valid — anti-auth-bypass). The only structural gap is F-08 (:138).
802.1X enterprise: the upper EAP runs on macOS; the driver gets the derived PMK seeded into the
PMKSA cache by WCL (WCL.cpp:1197-1208, `ieee80211_pmksa_add` for 8021X/SHA256_8021X AKMs;
pmksa_add refuses SAE PMKIDs by design, crypto.c:863-865) and performs the 4-way handshake
in-driver. EAPOL RX is deferred to a task with node ref + generation guard
(`iwx_defer_eapol_key_input`, ItlIwx.cpp:202-225).

### WPA3-SAE

**N-14 [Confirmed — good] SAE implementation is a modern, carefully-bounded port.**
`ieee80211_sae.c` (749 lines; OpenBSD stsp@ 2026 lineage) implements: PT derivation
`ieee80211_sae_password_to_pt` (:53-125, HKDF counters 1..2, SSWU map, muladd; password ≤ 63,
SSID ≤ 32 enforced :67-69), PWE derivation (:220-295), commit element derivation with
bounded retries and full `explicit_bzero` scrubbing (:297-459), commit verification with
reflection rejection, scalar range and on-curve checks, constant-time compares (:461-548),
shared-secret + identity check (:550-626), KCK/PMK/PMKID derivation (:628-705), confirm
verification (:707-749). Protocol machine `ieee80211_auth_sae` (proto.c:1648-1868): state-gated,
token-request handling with strict framing (`sae_len`/element-length/`IEEE80211_SAE_H2E_TOKEN_MAX_LEN`
= 254 and `sae_token[255]` bounds, proto.c:1745-1783; constants ieee80211.h:1353-1358, node.h:231),
anti-reflection discard (proto.c:1786-1798), anti-clogging retry via `ieee80211_auth_sae_timeout`
(proto.c:1618-1646, 3 attempts), PMKID propagation into assoc (:1855-1857). TX side sizes the
mbuf exactly from `sae_len` including token + MLE overhead (output.c:1955-2059) — no overflow.
Secrets are bzeroed on every exit path.

Two observations:
- **[Cosmetic defect]** `BR_EC_secp192r1` is defined as **19** with a "secp192r1" comment
  (`openbsd/crypto/ec_p256_m31.h:119-120`) — 19 is IANA group 19 = **P-256** (secp256r1), which is
  what `ec_p256_m31.c` actually implements and what SAE requires. The name/comment is wrong; the
  value and all uses are correct. Rename to avoid future confusion (value must stay 19).
- **[Intentional limitation]** Only group 19 is accepted (`fc_group != curve` →
  `IEEE80211_STATUS_BAD_FC_GROUP`, sae.c:491-495). Groups 20/21 unsupported — acceptable (19 is
  mandatory-to-implement); record for the feature matrix.

**N-15 [Architectural difference — config] SAE is H2E-only in this build.**
`IEEE80211_SAE_HNP_COMPAT` is not defined (compile_flags.txt; pbxproj defines only
AIRPORT_WCL/IEEE80211_STA_ONLY/DEBUG). Consequently `ieee80211_sae_hnp_compat_allowed()` always
returns 0 (ieee80211.h:838-848), so `ieee80211_node_allow_wpa3` (node.c:1758-1776) requires the
AP's RSNXE to advertise H2E **and** a valid PT (`ic_sae_pt_valid`), and `choose_rsnparams`
(node.c:1704-1717) only prefers SAE under the same condition. The WCL join derives the PT in-driver
from the password (`ieee80211_sae_password_to_pt`, WCL.cpp:1155) or uses a cached credential
(:1153-1154, 1162-1165); a deferred-join hook lets WCL supply it asynchronously
(`ic_sae_defer_join` = `iwx_defer_sae_join`, ItlIwx.cpp:20197; join_bss node.c:1332-1341).
Effect: **WPA3-Personal works only against H2E-capable APs** (all 6 GHz APs, virtually all modern
5/2.4 GHz WPA3 APs). HnP-only APs fall back to PSK in transition mode, and WPA3-only HnP APs
cannot be joined. This is a deliberate, documented choice (HnP code kept behind the ifdef,
proto.c:1692-1717) — record it; do not silently "fix" it, and do not enable HNP without a
security review of the HnP loop (sae.c:127-201) on the target.

### PMF / 802.11w

**N-16 [Confirmed — good, with one gap] PMF enforcement.**
- Negotiation: `choose_rsnparams` sets NODE_MFP when both support MFPC (node.c:1752-1755);
  MFPR APs are refused if we lack C_MFP, and our F_MFPR requirement refuses non-MFPC APs
  (match_bss node.c:1169-1178). GMAC management ciphers are refused unless `ic_mld_gmac`
  (BE/MLD-only; node.c:1161-1167) → AX211 accepts only BIP-CMAC-128, which is implemented
  (crypto_bip.c: set_key :68-79, encap :99-165, decap :167-235 with IPN replay check :189-195 and
  constant-time MIC compare :218).
- Keys: IGTK (kid 4/5) and BIGTK (kid 6/7) install from M3/group-msg1 with strict KDE framing
  (pae_input.c:890-969, 1240-1314); TX/RX mgmt protection flags set on install (:919-921).
- RX enforcement: unicast deauth/disassoc/action must be protected when RXMGMTPROT
  (input.c:1108-1129); beacons must be BIGTK-protected when negotiated (input.c:1136-1142).
- TX: BIP encap is wired into the output crypto path (crypto.c:388-390).
- **Gap [Intentional/CONFIG]:** the STA never *initiates* SA Query. The request/retry/timeout
  machine (`ieee80211_sa_query_request`/`_timeout`, proto.c:517-555) and the response handler
  (input.c:4732-4761) are inside `#ifndef IEEE80211_STA_ONLY` (the `#endif` at proto.c:555 and
  input.c:4761), and the node timers are only `timeout_set` in the same guard (node.c:1897-1900).
  The STA **does** answer AP-initiated SA Query Requests (input.c:4696-4723, unguarded — saves
  TRID, replies). Missing: the 11w STA behavior of starting SA Query after an *unprotected*
  disassoc/deauth while associated — `ieee80211_recv_deauth`/`recv_disassoc` (input.c:4188-4307)
  just transition state regardless of protection. Matches upstream OpenBSD STA semantics; note as
  a known 802.11w-compliance gap rather than a regression, and note the timer never being set is
  harmless because `timeout_add_msec` on a NULL CTimeout returns an error safely
  (CTimeout.cpp:47-49).

### Crypto / key installation

**N-17 [Confirmed] Key install path.**
Driver overrides `ic_set_key`/`ic_delete_key` (ItlIwx.cpp:20215-20216) → firmware key install;
net80211's software fallback (crypto.c:199-230) marks keys SWCRYPTO. `reset_key_slot`
(pae_input.c:572-579) deletes-before-overwrite on every rekey. Group keys are cleared on
AUTH/SCAN entry (`ieee80211_crypto_clear_groupkeys`, proto.c:2050-2051, 2101-2102; MLD variant
crypto.c:115-128 is dormant for AX211). Per-frame logging: only the F-02 site (see Part 1);
decrypt path has no per-frame logs. `ieee80211_crypto_detach` purges PMKSA + zeroes PSK
(crypto.c:89-113). No other per-frame inefficiencies found in the crypto TX/RX path beyond F-02.

### RX Block Ack lifecycle

**N-18 [Confirmed] Reorder semantics + the F-06 leak.**
ADDBA: state machine input.c:4319-4452 (winsize clamp; **HE nodes get
IEEE80211_RX_BA_MAX_WINSZ (256) vs 64 for HT** — input.c:4414-4418); buffer alloc :4428 (zeroed
by the compat malloc); driver callback EBUSY defers accept/refuse (:4435-4444). Reorder:
`ieee80211_input_ba` (input.c:1300-1383) — inactivity timer re-arm, window
below/above/slide/jump logic (winmiss 8, gap timeout 300 ms), flush/seq/move-window
(:1389-1533) all upstream-faithful with `mbuf_list` batching into `if_input` (gate-serialized,
_mbuf.cpp:34-63). Timeout: `ieee80211_rx_ba_timeout` → `delba_request(Recipient)` → frees buffer
(proto.c:1315-1332, 1423-1430). DELBA RX frees (input.c:4663-4670). Teardown (roam/deauth/
node-free) leaks — **F-06, see Part 1**. TX BA: addba_request (proto.c:1337-1383),
tx_ba_timeout (:1290-1312), stop_ampdu_tx (proto.c:1892-...) + ba_del resets.
`ieee80211_mld_primary_node` indirections (input.c:4458, proto.c:1392) are identity for AX211
(node.c:2636-2648).

### Rate adaptation

**N-19 [Confirmed] No net80211 RA module is active; firmware TLC owns data-frame rates.**
`ieee80211_ra.c` (954 lines), `ieee80211_mira.c`, `ieee80211_rssadapt.c`, `ieee80211_amrr.c` are
compiled but never attached for the iwx HAL (no `ra`/`mira`/`rssadapt`/`amrr` hook references in
itlwm/hal_iwx — only header includes at if_iwxvar.h:107-108). `iwx_tx_fill_cmd` leaves data frames
without `IWX_TX_FLAGS_CMD_RATE` (firmware picks the rate; mcast/mgmt/fixed use the lowest/fixed
rate, ItlIwx.cpp:8160-8182); `ni_txmcs` is used for HT mgmt/legacy paths (:8172-8174) and set at
association (assoc-time MCS selection :14551 region). HE: capabilities parsed per node
(`ieee80211_update_he_params`, input.c:2150+; ni_he_* fields node.h:486-496), HE MCS/NSS
negotiated incl. the 160 MHz table (proto.c:1238-1239 rx_mcs_160 vs rx_mcs_80), HE BA winsize 256
(input.c:4414). `ni_he_txrate_kbps` records the last firmware HE SU rate (node.h:494). So: RA
correctness on the AX211 path is a firmware+HAL concern (Subagent D/E); net80211-side HE data is
parse-and-carry only. ra.c's 160 MHz table (ra.c:203/236/942) is dead code here.

### Regulatory

**N-20 [Confirmed — nothing bypasses regulatory at this layer]**
`ieee80211_regdomain.c` is only a name↔code table (regdomain.c:59-197). Enforcement lives in:
(i) firmware-derived channel tables (ItlIwx.cpp:4515 sets CHAN_DFS from NVM/GEO), (ii) the
active-channel bitmaps consulted by match_bss (node.c:1080-1085) and scan fill, (iii) probe
suppression on PASSIVE/DFS channels during directed scans (ItlIwx.cpp:9314-9320), (iv) the beacon
hint (input.c:2685-2718, non-DFS only, N-05), and (v) AWDL listener constraints
(ItlIwx.cpp:12584-12623: skips DFS/NOADHOC/passive-unless-hint). No net80211 code path transmits
outside `ic_chan_active` or lifts DFS. **Preserve as-is; anything that widens this must be
rejected.**

### mbuf / ifq / task plumbing

**N-21 [Confirmed defect — low severity] `task_set` over-reads its `name` argument.**
`struct task.name` is `char name[256]` (_task.h:35) and `task_set` does
`memcpy(t->name, name, sizeof(t->name))` (_task.cpp:272) — always 256 bytes from a short string
literal (all 14 call sites pass literals ≤ ~20 chars, ItlIwx.cpp:218, 20173-20194). Benign in
practice (rodata over-read; destination is a 256-byte field), but it is an OOB read by
construction and would trip `_FORTIFY_SOURCE`. Fix: `strlcpy(t->name, name, sizeof(t->name))`
(or cap the struct field). Inherited from upstream itlwm.

**N-22 [Latent defect — dead code] `m_defrag` EXT branch is broken.**
`_mbuf.h:337-386`: when the copied chain needs a cluster (pkthdr len > MHLEN), the MBUF_EXT
branch (:370-374) is commented out, yet `mbuf_pkthdr_setlen/mbuf_setlen(m, mbuf_len(m0))` at
:379-380 still set m's length to the full cluster length without relocating m's data — an OOB
tx if it were live. **No caller anywhere in the tree** (grep: only the definition) → dead code.
Either fix the EXT branch or delete the function during the engineering pass to remove the trap.

**N-23 [Demonstrated inefficiency — minor] Taskq sleeps 1 ms between every task.**
`taskq_thread` does `IOSleep(1)` after each task (_task.cpp:112). Applies to systq/nswq task
drain (newstate, setkey, ba, scan-continuation tasks). Inherited from upstream itlwm; known
throughput quirk; not a correctness bug. Note for the HAL audit when measuring join latency.

**N-24 [Confirmed — semantics notes] ifq / mq / malloc wrappers.**
- `ifq_enqueue` uses `lockEnqueueWithDrop` and always returns 0 (_ifq.cpp:69-73), so
  `if_enqueue`'s ENOSPC path (_mbuf.h:444-451) is dead and EAPOL/mgmt enqueue cannot fail
  silently — dropped packets are freed inside the queue (IOPacketQueue drop semantics).
- `mq_*` (mbuf_queue) are IORecursiveLock-guarded with maxlen drop+free (_mbuf.h:209-300) —
  ownership clear, no double free; `mq_init` does not zero `mq_drops` but all users live in
  zeroed allocations.
- compat `malloc` is always zeroing and stores a length prefix; `free(NULL)` is safe
  (_malloc.h:27-49) — relevant to F-06 (ba_buf starts zeroed; parked-mbuf slots are NULL).
- `if_input` runs the whole ml drain under the command gate (_mbuf.cpp:34-63) — RX batching is
  gate-serialized; large batches lengthen gate hold times (HAL concurrency scope).

**N-25 [Plausible risk] ~2–4 KB stack arrays per management frame.**
`uint8_t mle_data[MCLBYTES]` on the stack in `ieee80211_recv_probe_resp_bss`
(input.c:2431) and in the (Re)Assoc-Response handler (input.c:3865), plus
`profile_data[MCLBYTES]` in `ieee80211_mld_assoc_response_links` (input.c:286) — each ~2 KB
(MCLBYTES on macOS) of XNU kernel stack (16 KB) per beacon/probe/assoc frame, nested for the
MBSSID path. Bounded copies (`ieee80211_mle_copy(..., sizeof(mle_data))`, :2751) so no overflow,
but stack pressure on deep call chains (bpf + decap + event handler) is real. Consider heap or a
single per-ic scratch buffer in the engineering pass.

**N-26 [Latent defect — currently benign] `node_set_timeouts` memset size is 16× too large.**
`memset(ni->ni_addba_req_to, 0, sizeof(ni->ni_addba_req_to) * nitems(ni->ni_addba_req_to))`
(node.c:1896): `ni_addba_req_to` is `CTimeout*[16]` (node.h:514; NUM_TID=16, ieee80211.h:1014) →
`sizeof` 128 × nitems 16 = **2048 bytes zeroed** starting at a 128-byte field, running through
`ni_addba_req_intval`, `ni_tx_ba[]`, `ni_rx_ba[]` and beyond. Currently harmless because
`node_set_timeouts` is only called from `ieee80211_setup_node` (node.c:1931) on freshly
malloc'd-and-zeroed nodes — but it is a landmine if the function is ever called on a live node.
Fix: `memset(ni->ni_addba_req_to, 0, sizeof(ni->ni_addba_req_to));`

**N-27 [Confirmed OK] ItlDma arena ownership/queue semantics (concurrency itself = Subagent E).**
`ItlDmaArena::allocate` zeroes on grant and validates on release (panic on mismatched run —
ItlDma.cpp:146-167); deferred recycling (`deferRecycling`/`reclaim`) only returns pages once bus
master is off (:169-196), preventing use-after-free of in-flight DMA buffers; `destroy` quiesces
bus-master first (:198-225). Buffer records are by-value and bzeroed on release — no stale
handles. No leak/double-free pattern found at this layer.

---

## Part 3 — Feature inventory (net80211 layer, Eric tree)

| Feature | Status in Eric | Evidence | HW/firmware dependency visible at this layer |
|---|---|---|---|
| WPA2-Personal (PSK) | **Implemented** — in-driver supplicant, 4-way + group handshake | pae_input.c:585-998; PSK via WCL pbkdf2 (WCL.cpp:1175-1196); choose_rsnparams PSK branch node.c:1720-1728 | none (firmware does CCMP with installed keys) |
| WPA2-Enterprise (802.1X) | **Implemented** (EAPOL pass-through + PMKSA seeding; upper EAP on macOS) | PMKSA add for 8021X/SHA256_8021X (WCL.cpp:1197-1208, crypto.c:857-894); PMKID in assoc (node.c:1734-1740); EAPOL not bridged (input.c:1547-1554) | firmware RSN CCM; PMK delivery from WCL |
| WPA2/WPA3 transition mode | **Implemented** — prefers SAE when PT valid, falls back to PSK/SHA256-PSK | node.c:1708-1728; RSN-IE rewrite on scan messages only = old-fork behavior (WCL layer) | SAE needs PT (H2E) |
| WPA3-Personal SAE (H2E) | **Implemented** — full commit/confirm, token, PMKID, retry | sae.c entire; proto.c:1648-1868; join PT via WCL (WCL.cpp:1152-1174); deferred join ItlIwx.cpp:20197 | requires AP RSNXE H2E (N-15) |
| SAE H2E | **Yes** — PT path, H2E status codes, RSNXE | `ieee80211_sae_password_to_pt` sae.c:53; sae_h2e flag node.c:1374-1375; USE_AKM desc pae_input.c:145-149 | group 19 (P-256) only (sae.c:491-495) |
| SAE HnP (hunting-and-pecking) | **Compiled OUT** (`IEEE80211_SAE_HNP_COMPAT` undefined) | ieee80211.h:838-848; pbxproj defines | — (N-15: config decision) |
| PMF (802.11w) | **Implemented** — MFPC/MFPR negotiation, IGTK/BIGTK, BIP-CMAC-128, RX+TX mgmt protection | node.c:1752-1755, 1169-1178; pae_input.c:890-969; crypto_bip.c; input.c:1108-1142 | BIP-GMAC-128/256 refused for non-MLD (node.c:1161-1167) → AX211 = CMAC only; STA never initiates SA Query (N-16) |
| OWE (Enhanced Open) | **Implemented** — DH group 19, RFC 8110 KDF, PMKID | crypto.c:577-674 (owe_prepare/process_response); match_bss node.c:1152-1159; choose_rsnparams :1718-1719; USE_AKM desc pae_input.c:145-149; join path node.c:1326-1330 | 6 GHz OWE additionally requires MFP (node.c:1156-1158) |
| 802.11n (HT) | **Implemented** | htcaps/htop parse (input.c:2758-2761), ht_negotiate (proto.c:558+), add_ht_ie output.c:1273+ | firmware TLC |
| 802.11ac (VHT) | **Implemented** | vhtcap/vhtop (input.c:2763-2766), vht negotiate (proto.c:780-880), ni_vht_chanwidth | 160/80+80 caps checked node.c:2900-2903 |
| 802.11ax (HE) | **Implemented** (STA) | HE cap/op/6GHz-cap parse (input.c:2578-2590, 2742, update_he_params :2150); HE MCS/NSS incl. 160 MHz table (proto.c:1238-1239); HE BA winsz 256 (input.c:4414); MODE_11AX (ieee80211.c:934-936) | AX211 = 2×2 HE; firmware TLC owns rates (N-19) |
| EHT (Wi-Fi 7) | **Parsed/negotiated but inert on AX211** (no EHT radio) | ehtcap/ehtop parse (input.c:2601-2606), update_eht_params :2768, ni_eht_* node.h:498-511 | requires BE hardware (`ic_eht_cap_valid`, node.c:2681) |
| 2.4/5 GHz channels | **Implemented** | band handling in recv_probe_resp_bss (input.c:2478-2490); choose_bss band preference node.c:1470-1498 | NVM/GEO tables |
| 6 GHz channels | **Implemented** — 6 GHz beacons via HE-op primary channel, RNR-seeded discovery, PSC bgscan | input.c:2642-2656; `ieee80211_seed_scan_rnr`/collect_scan_rnr (input.c:2378-2391, 2911-2918); PSC filter ItlIwx.cpp:9288-9290; opclass mapping :3088-3098; requires SCAN_EXT_CHAN_VER TLV (:9293-9295) | API-68 fw advertises it; 6 GHz implies WPA3/PMF/OWE |
| 160 MHz channels | **Implemented** | vht negotiate CHAN_WIDTH_160 (proto.c:853-879); HT 40 negotiation proto.c:568+; 160 MCS table proto.c:1238-1239; VHTCAP_SUPP_CHAN_WIDTH checks node.c:2900-2903; awdl 160-group logic ItlIwx.cpp:12568-12583 | AX211 SKU "160MHz"; center-freq fields on channel |
| WEP / WPA1 (legacy) | **Implemented** (WEP keys via WCL join; WPA1 IE parse) | crypto_wep.c; parse_wpa input.c:2100-2106; WCL legacy auth WCL.cpp:1209+; WPA group msg1 pae_input.c:1348-1448 | — |
| A-MPDU TX/RX, BA | **Implemented** (see N-18); open-network A-MPDU prohibition preserved | output.c:496-514; input.c:4319-4700 | 256-TFD agg cap = HAL |
| MLO / EMLSR (Wi-Fi 7 MLD) | **Implemented but dormant for AX211** (`sc_use_mld_api` false — see Subagent A) | MLD links node.c:2544-2698; MLO SAE/OWE + MLE checks pae_input.c:596-599, proto.c:1669-1672; TTLM proto.c:2800-2910 | BE200-family firmware only |
| MBSSID (multiple BSSID) | **Implemented** | ieee80211_mbssid.h; profile parse in beacons (input.c:3043-3051) | — |

---

## Open questions (for other subagents / next actions)

1. **WCL scan-abort completion (N-02):** does the WCL layer always run its own completion timer
   (`fakeScanDone` V2.cpp:130-142 / `scanSource`) so an aborted firmware scan still completes the
   WCL state machine? → Subagent C (WCL/AirportItlwm integration).
2. **Watchdog serialization (N-12 / F-10 class):** `fWatchdogWorkLoop` + ungated
   `ieee80211_watchdog` mutating MLME state concurrently with the gate-held RX path — confirm
   against Eric's V2 lifecycle and port the old invariant (single workloop/gate; cancel-through-gate
   at teardown; re-arm via sender). → Subagent C/E.
3. **F-12 + SAE interplay:** after fixing the ni_fails accounting, re-derive the effective WPA3
   join retry budget (`attempts >= 3` at proto.c:1637) — with H2E-only SAE and WCL rejoin loops,
   the practical "join fails, retry connects" symptom from the old fork (S3) may reproduce here.
4. **HnP (N-15):** product decision needed — accept H2E-only WPA3, or fund a review of the
   compiled-out HnP path (sae.c:127-201) before enabling `IEEE80211_SAE_HNP_COMPAT`.
5. **BIP-GMAC refusal for AX211 (node.c:1161-1167):** confirm no AX211-reachable AP profile
   advertises GMAC-only management ciphers (would be unjoinable); low likelihood, worth one
   scan-capture sanity check on the target.
6. **`ni_he_txrate_kbp`s** provenance (which firmware notification fills it) — HAL scope
   (Subagent D) to confirm for the AX211 TLC path.

## Transfer-priority shortlist (net80211 scope)

1. **F-08** EAPOL totlen guard — security, verbatim port (pae_input.c:135-140 pattern).
2. **F-06** ba_buf free in `ieee80211_ba_del` — leak on every roam/deauth; timer model verified
   safe for the transfer (gate-serialized CTimeouts).
3. **F-12** ni_fails single-count + `>= 2` choose_bss threshold — join reliability; mind the SAE
   attempts interplay (Open question 3).
4. **F-02** crypto per-frame log removal (keep :370 BUG! log).
5. **F-03/F-04** scan-result rates copy + `HalService` typo (SkywalkInterface.cpp:1093-1104, 1204).
6. Eric-native cleanups, low risk: N-21 (task_set strlcpy), N-26 (memset size), N-22 (delete or
   fix dead m_defrag), N-04 (gate the new_state XYLog), and the BR_EC_secp192r1 rename (N-14).
