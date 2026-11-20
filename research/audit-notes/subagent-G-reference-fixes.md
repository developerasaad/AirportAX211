# Subagent G — Reference (OLD) Fix Audit: AirportItlwm_AX211 Engineering Pass

Task ID: M3-G. Date: 2026-11 (audit of reference tree).
Reference repo: `/home/z/my-project/reference/` — `AirportItlwm_AX211`, HEAD = `46027fe`
("Record verified CI build of the engineering pass (run 44620003926)").

Sources used (all read-only):
- `reference/research/eng-2026-11/ENGINEERING-REPORT.md` (300 lines, read in full — authoritative for intent)
- `reference/research/eng-2026-11/inventory.json` (232-file inventory)
- `reference/research/ax211-audit/` (the earlier 152-finding dossier; the eng-2026-11 report explicitly
  supersedes/corrects it — several prior-audit claims were REFUTED, see §15)
- Git history: 8 commits. Import baseline `0159121`; fixes in `68eb060`, `22c7cdf`, `31fbdab`,
  review corrections `2ada74b`; README records `6039eb6` (first CI build, run 44591987929) and
  `46027fe` (final CI build, run 44620003926).
- Final source state verified directly at HEAD; every file:line below was re-read in the final tree.

Findings register: F-01 … F-13 (13 defects), implemented as change sets CS1 … CS10 (CS4 covers
F-06 + F-13). Full diff `0159121..HEAD` touches exactly 9 source files (+ README + research docs):

```
AirportItlwm/AirportItlwmEthernetInterface.cpp  |    7 +-
AirportItlwm/AirportItlwmSkywalkInterface.cpp   |   12 +-
AirportItlwm/AirportItlwmV2.cpp                 |   79 +-
AirportItlwm/AirportItlwmV2.hpp                 |    1 -
AirportItlwm/WCL/WCL.cpp                        |   24 +
itl80211/openbsd/net80211/ieee80211.c           |    8 +-
itl80211/openbsd/net80211/ieee80211_crypto.c    |    3 +-
itl80211/openbsd/net80211/ieee80211_node.c      |   16 +-
itl80211/openbsd/net80211/ieee80211_pae_input.c |    5 +-
itlwm/hal_iwx/ItlIwx.cpp                        |   48 +-
```

Line-number convention: the report's findings register cites **baseline-tree** line numbers
(state at investigation time); each section below gives BOTH the baseline citation (as in the
report) and the **final-tree (HEAD 46027fe) line numbers**, which I verified by direct read.
No report-vs-code disagreement was found (see §14).

---

## 1. Per-frame TX logging removed (F-01, F-02 — CS1)

**Old defect.** Two unconditional per-frame `XYLog` (kprintf) sites on the TX hot path, which
runs under the single command gate:
- F-01: `iwx_tx_fill_cmd` — baseline `ItlIwx.cpp:6913`:
  `XYLog("%s hwrate: %d ridx: %d rate: %d minrate: %d\n", __FUNCTION__, hwrate, ridx, iwx_ridx2rate(rs, ridx) & IEEE80211_RATE_VAL, ieee80211_min_basic_rate(ic));`
  — two function calls evaluated in the format arguments for every transmitted frame
  (called from `iwx_tx` per frame).
- F-02: `ieee80211_encrypt` — baseline `ieee80211_crypto.c:283`:
  `XYLog("%s kid=%d cipher=%d\n", ...)` — fires for every software-encrypted TX frame (TKIP/WEP).
- Consequence: unconditional driver-wide overhead (symptom S4).

**Final implementation.**
- `reference/itlwm/hal_iwx/ItlIwx.cpp:6939-6941` — the XYLog replaced by a comment
  ("Per-frame logging removed…"). Control flow unchanged: `*rate_n_flags = htole32(rate_flags | hwrate)`
  at :6942, `return rinfo` at :6944. Function spans :6886-6945; call site `iwx_tx` at :7072.
- `reference/itl80211/openbsd/net80211/ieee80211_crypto.c:283-284` — comment replaces the log;
  cipher `switch` follows at :286. The genuine BUG! error log at :278 (key unset for SW crypto)
  is preserved, as are all error-path/DPRINTF logs.

**Subsystem:** hal_iwx (F-01) + net80211 crypto (F-02).
**Verification:** source-verified (edits re-read; REVIEW-1 verdict SOUND — variables still used,
no -Werror risk) + build-verified (CI run 44620003926). NOT hardware-validated.
**Transfer notes:** trivially portable; preserve the adjacent error-path logs. The report's
C.2 notes `IWX_DEBUG`/`iwx_debug=1` DPRINTFs were deliberately KEPT (control-plane frequency,
primary bring-up diagnostic) — do not strip those in the new tree.

## 2. Scan-result rate information (F-03, F-04 — CS2)

**Old defect.** `convertNodeToScanResult` (baseline `AirportItlwmSkywalkInterface.cpp:981, 990-992`):
the struct is `bzero()`ed at :981, then the copy loop bound was read from `result->asr_nrates`
(just zeroed) → loop ran 0 iterations; `result->asr_nrates = node->ni_rates.rs_nrates` was
assigned only AFTER the loop → `asr_rates` always delivered EMPTY while `asr_nrates` stayed
nonzero. Degraded CURRENT_NETWORK/SCAN_RESULT data (symptom S2).
Additionally F-04: baseline `AirportItlwmSkywalkInterface.cpp:1042` used undeclared identifier
`HalService` in live `getSCAN_RESULT`'s `RB_NEXT(ieee80211_tree, &HalService->…, …)` — compiled
only because `RB_NEXT` discards its 2nd argument (`tree.h:725`: `#define RB_NEXT(name, x, y)
name##_RB_NEXT(y)`); latent landmine.

**Final implementation.** `reference/AirportItlwm/AirportItlwmSkywalkInterface.cpp:990-998`:
```c
uint8_t nrates = fNextNodeToSend->ni_rates.rs_nrates;
if (nrates > sizeof(result->asr_rates) / sizeof(result->asr_rates[0]))
    nrates = sizeof(result->asr_rates) / sizeof(result->asr_rates[0]);
result->asr_nrates = nrates;
for (int i = 0; i < nrates; i++)
    result->asr_rates[i] = fNextNodeToSend->ni_rates.rs_rates[i];
```
— bound taken from the NODE, clamped to the destination array size, count stored BEFORE the
copy, copy bounded by the clamped count. Struct layout and RB-tree iteration semantics
preserved. F-04 fixed at :1048 (`&fHalService->get80211Controller()->ic_tree`).
Consumers: `getSCAN_RESULT` (:1031-1053, wrapping logic untouched) and `getCURRENT_NETWORK`
(:1013-1020, requires `ic_state == IEEE80211_S_RUN && ic_bss != NULL`).

**Subsystem:** AirportItlwm integration (Skywalk interface apple80211 ioctl conversion path).
**Verification:** source-verified (REVIEW-2: matches the in-tree V1 precedent — raw u8→u32
element copy) + build-verified. NOT hardware-validated. Report's stated runtime check
("rates non-empty in getCURRENT_NETWORK path") could not be run (no hardware).
**Transfer notes:** check whether the new (Eric) tree has the same bzero-then-bound pattern
in its scan-result conversion; the clamp to `sizeof(asr_rates)/sizeof(elem)` is the safety net.

## 3. en0 link truthfulness on link-down (F-05 — CS3)

**Old defect.** `setLinkState` (baseline `AirportItlwmEthernetInterface.cpp:126`):
`ifnet_set_flags(getIfnet(), flags & ~(IFF_UP | IFF_RUNNING), 0)` — the mask argument (3rd
param) is 0, so NO flag bits are ever changed: the call is a no-op. en0 kept IFF_RUNNING
forever after link loss → configd/System Settings stale "connected" (symptom S2).

**Final implementation.** `reference/AirportItlwm/AirportItlwmEthernetInterface.cpp:120-134`:
- Up path unchanged (:123-124): sets `IFF_UP | IFF_RUNNING`.
- Down path :131: `ifnet_set_flags(getIfnet(), ifnet_flags(getIfnet()) & ~IFF_RUNNING, IFF_RUNNING);`
  — clears the CARRIER flag (IFF_RUNNING) only; IFF_UP (administrative state) intentionally
  preserved, matching native macOS behavior. Comment at :126-130 documents the old no-op.

**Subsystem:** AirportItlwm integration (BSD ifnet mirror of the Skywalk link state).
**Verification:** source-verified (REVIEW-2: en0 RUNNING drops only on real disassociation —
bgscan never calls new_state; LQM -2 behavior is the designed semantic) + build-verified.
NOT hardware-validated.
**Transfer notes:** semantics to preserve exactly: clear carrier on down, NEVER clear admin UP.

## 4. RX BA (block-ack) resource cleanup (F-06 — CS4)

**Old defect.** `ieee80211_ba_del` (baseline `ieee80211_node.c:2029-2057`) cancelled the
`ba_to`/`ba_gap_to` timers and reset `ba_state` to INIT but NEVER freed `ba->ba_buf` — the RX
reordering buffer (~2 KB struct array + any parked MSDUs) leaked on every roam/deauth
transition and was simply overwritten by the next ADDBA. Correct free pattern already existed
in the DELBA path (`ieee80211_proto.c:1189-1196`).

**Final implementation.** `reference/itl80211/openbsd/net80211/ieee80211_node.c:2031-2071`:
per TID, if `ba_state != IEEE80211_BA_INIT`: cancel `ba_to` (:2039-2040) and `ba_gap_to`
(:2041-2042) if pending, set state INIT (:2043), then (:2044-2054):
```c
if (ba->ba_buf != NULL) {
    int i;
    for (i = 0; i < IEEE80211_BA_MAX_WINSZ; i++)
        mbuf_freem(ba->ba_buf[i].m);
    free(ba->ba_buf);
    ba->ba_buf = NULL;
}
```
— identical to the DELBA-path free (`ieee80211_proto.c:1189-1196`). TX BA loop (:2058-2065)
and the four `ni_addba_req_to` timeout_del calls (:2067-2070) unchanged.

**Subsystem:** net80211.
**Verification:** source-verified + build-verified. NOT hardware-validated. REVIEW-1's R7
concern (ba_del free vs in-flight CTimeout callback) was analyzed SOUND: every ba_del caller
is on the workloop thread or holds the workloop gate without sleeping (`iwx_newstate_task`
re-enters the gate; IOKit timer callbacks hold the gate; ba_del never sleeps) — and fix #8
below removed the one previously-ungated caller (the watchdog).
**Transfer notes:** safe only if the caller-context invariant above holds in the new tree —
re-verify there before porting (the new tree's workloop/gate structure differs).

## 5. Rate-array bounds checking in rate pretty-printers (F-07 — CS5)

**Old defect.** Off-by-one guards in the TLC-notification rate printers
(baseline `ItlIwx.cpp:527-528, 543-544`): `if (ant > ARRAY_SIZE(ant_name))` /
`if (bw > ARRAY_SIZE(pretty_bw))` let `ant == 4` and `bw == 5` through, reading one entry past
the static tables. `ant_name[]` has 4 entries (NONE/A/B/AB), `pretty_bw[]` has 5 (20..320 MHz);
`IWX_ANT_C == 1<<2 == 4` (`if_iwxreg.h:5777`) was the reachable OOB antenna value; `bw == 5`
is reachable from every TLC notification. OOB read (memory safety).

**Final implementation.** `reference/itlwm/hal_iwx/ItlIwx.cpp:527` and `:543`:
`>` → `>=` (`if (ant >= ARRAY_SIZE(ant_name))`, `if (bw >= ARRAY_SIZE(pretty_bw))`);
out-of-range returns "UNKNOWN". Table definitions at :520-525 and :535-541.

**Subsystem:** hal_iwx.
**Verification:** source-verified (REVIEW-1: "arrays are 4/5 entries; IWX_ANT_C was the old
OOB value") + build-verified. NOT hardware-validated.
**Transfer notes:** one-character semantic change; verify the new tree's printers (if any)
use `>=`.

## 6. EAPOL key-length validation (F-08 — CS6)

**Old defect.** `ieee80211_eapol_key_input` (baseline `ieee80211_pae_input.c:129-137`):
`paylen = BE_READ_2(key->paylen); if (paylen > totlen - sizeof(*key))` — `totlen` is
unsigned; when `totlen < sizeof(*key)` (99 bytes packed, struct at `ieee80211.h:1181`) the
subtraction wraps to a huge value, so ANY `paylen` passed, driving an out-of-bounds key-data
parse (up to 64 KB) before MIC verification. The earlier guard at :109 checks the MBUF
length, not `totlen` (a short EAPOL body inside a longer mbuf slips through). Kernel memory
safety.

**Final implementation.** `reference/itl80211/openbsd/net80211/ieee80211_pae_input.c:135-140`:
```c
paylen = BE_READ_2(key->paylen);
/* totlen - sizeof(*key) would wrap to a huge unsigned value when
 * totlen < sizeof(*key) (short body inside a longer frame), letting
 * any paylen pass and driving an out-of-bounds parse below. */
if (totlen < sizeof(*key) || paylen > totlen - sizeof(*key))
    goto done;
```
Conformant frames always have `totlen >= 99` (REVIEW-1), so no legitimate traffic is rejected.
The `totlen` computation itself (`bodylen = BE_READ_2(key->len); totlen = 4 + bodylen;` with
`mbuf_pkthdr_len(m) < totlen || totlen > MCLBYTES` rejection) is unchanged at :128-132.

**Subsystem:** net80211 (in-driver supplicant — the 4-way handshake runs in-driver under WCL).
**Verification:** source-verified + build-verified. NOT hardware-validated.
**Transfer notes:** high-value security fix; port verbatim. Check the new tree's SAE/WPA3
key-input paths for the same wrap pattern.

## 7. PNVM failure handling (F-09 — CS7) — see SPECIAL WARNING §8

**Old defect (baseline `ItlIwx.cpp:2164-2177`).** `iwx_load_pnvm` contained:
`if (!iwx_read_pnvm(sc)) { goto out; };` followed immediately by `out:` — a DEAD goto (both
paths fall through), so on EVERY return from `iwx_read_pnvm` (success, no-SKU-match, or hard
error) the code: (a) kicked the PNVM doorbell (`IWX_UREG_DOORBELL_TO_ISR6` /
`IWX_UREG_DOORBELL_TO_ISR6_PNVM`), then (b) blocked in `iwx_wait_notification(...,
IWX_PNVM_COMPLETE, 2000)` — a 2-second gate-held wait. Without a loaded PNVM section the
firmware never sends PNVM_INIT_COMPLETE_NTFY, so the wait always burned the full 2 s and then
propagated a spurious timeout failure into the init retry loop. Root ambiguity: baseline
`iwx_read_pnvm` returned 0 (== "success") BOTH when a SKU-matching section was loaded AND
when the TLV walk completed with no match (`err` stayed 0) — the two outcomes were
indistinguishable to the caller.

**Final implementation** (after review correction; commit `2ada74b`):
- `reference/itlwm/hal_iwx/ItlIwx.cpp:2058-2167` `iwx_read_pnvm`: adds `int loaded = 0`
  (:2061); sets `loaded = 1` only when a SKU-matching section was successfully handled
  (:2140-2143); after the walk (:2155-2161): `if (!loaded && err == 0) err = ENOENT;` —
  no-match is now distinguishable from both success and hard errors (EINVAL/-EINVAL from TLV
  parse or resource-load failure keep their errno and take the early `goto out` paths).
- `reference/itlwm/hal_iwx/ItlIwx.cpp:2169-2210` `iwx_load_pnvm`, final control flow:
  1. Empty SKU_ID → `return 0` (:2175-2177; nothing to do).
  2. `err = iwx_read_pnvm(sc)` (:2179).
  3. `err == ENOENT` → nothing loaded: `iwx_pnvm_free(&sc->sc_fw); return 0;` (:2180-2190) —
     NO doorbell, NO wait; firmware built-in defaults apply; the rawdata buffer that
     read_pnvm speculatively malloc'ed (:2096) is freed.
  4. `err` any other nonzero → `return err` (:2191-2192) — hard errors propagate.
  5. `err == 0` (section loaded into pnvm_dram): clear `IWX_PNVM_COMPLETE` (:2196); ring the
     doorbell under `iwx_nic_lock` (:2197-2201); wait up to 2000 ms for the notification
     (:2203); ENXIO returns immediately (:2204-2205); otherwise `iwx_pnvm_free` and return
     (:2207-2209). This loaded path is byte-identical to the validated baseline on target.

**Subsystem:** hal_iwx (firmware/PNVM load).
**Verification:** source-verified + build-verified (CI run 44620003926). NOT hardware-validated
as a tree; the loaded-path doorbell+wait is byte-identical to the upstream laobamac baseline
that WAS hardware-validated on the MSI (see §12 for that distinction).

## 8. ⚠ SPECIAL WARNING — PNVM intermediate mistake and its repair

The FIRST implementation of CS7 (commit `68eb060`) was WRONG and was repaired in `2ada74b`.
Never reproduce this error class.

**The mistake.** The intermediate code read:
```c
if (!iwx_read_pnvm(sc)) {
    /* "No usable PNVM section for this SKU" ... */
    return 0;
}
```
It interpreted `iwx_read_pnvm() == 0` as "no usable PNVM section" — but **0 is the SUCCESS
return**, including the SKU-matched, data-loaded path. Because the intermediate change kept
read_pnvm's 0-on-no-match behavior, the polarity was doubly wrong: on the actual AX211
target (8086:51f0, matching `iwlwifi-so-a0-gf-a0.pnvm` embedded) read_pnvm returns 0 WITH the
section loaded, so this early return would have **skipped the PNVM doorbell on the real
target and silently never applied regulatory data** — while also (harmlessly-but-wrongly)
skipping it on the no-match path. Caught by adversarial REVIEW-1 ("one CRITICAL defect in my
initial PNVM change").

**The repair (final semantics).** Disambiguate the return value instead of guessing polarity:
- read_pnvm: track `loaded`; report `ENOENT` for walked-but-nothing-loaded; keep 0 for
  loaded; keep errno for hard errors.
- load_pnvm: `ENOENT` → free + return 0 (no doorbell, no wait); other errno → propagate;
  `0` → doorbell + 2 s wait exactly as the validated baseline.

**Rule for the transfer phase:** when porting any "skip work on failure" optimization, first
make the callee's return value unambiguous (distinct sentinel per outcome), and never assume
polarity from a boolean test of an int that has three possible meanings. The report's
correction ledger (§H) records this as the canonical caught-by-review defect.

## 9. Watchdog serialization and teardown order (F-10 — CS8 + review follow-up)

**Old defect.** Baseline `AirportItlwmV2.cpp`: the 1 s watchdog (`kWatchDogTimerPeriod 1000`)
ran on a SEPARATE workloop (`fWatchdogWorkLoop`, created at baseline :345-361) with zero gate
serialization, mutating MLME state (`ieee80211_watchdog` → `ieee80211_node_join_bss` /
`ieee80211_new_state`, baseline `ieee80211.c:906-929`) concurrently with the gate-serialized
RX/newstate paths; `splnet()` is a no-op in this port and KASSERT compiles away.
`watchdogAction` (baseline :116-122) dereferenced `fHalService` unconditionally, called
`ifp->if_watchdog` unconditionally, and re-armed via the `watchdogTimer` MEMBER pointer.
`releaseAll` freed `fHalService` FIRST (baseline :54-57) and cancelled watchdog/scan only
later (:72-79) — an in-flight callback window against freed memory.

**Final implementation.**
- **start()** — `reference/AirportItlwm/AirportItlwmV2.cpp:374-392`: `watchdogTimer` created
  and added to the MAIN `_fWorkloop` (the `fWatchdogWorkLoop` member was removed entirely —
  `AirportItlwmV2.hpp` diff in `31fbdab`). Failure path: release timer, `fHalService->detach`,
  `super::stop`, `releaseAll`, return false.
- **watchdogAction()** — `reference/AirportItlwm/AirportItlwmV2.cpp:135-151`:
  guard `if (!fHalService) return;` (:144-145); null-check `if (ifp->if_watchdog)` before the
  call (:147-148); re-arm via the SENDER argument `timer->setTimeoutMS(kWatchDogTimerPeriod)`
  (:150) — the canonical IOKit pattern, immune to a cleared member. Period preserved at
  1000 ms (`AirportItlwmV2.hpp:37`).
- **releaseAll()** — `reference/AirportItlwm/AirportItlwmV2.cpp:54-101`, strict order:
  1. Watchdog cancelled FIRST, and through the COMMAND GATE when available (review follow-up,
     :59-79): `_fCommandGate->runAction(lambda { timer->cancelTimeout(); timer->disable(); })`
     — an in-flight callback (which re-arms itself) completes its re-arm before teardown;
     direct cancel fallback if no gate (:72-75). Then `removeEventSource` + `release` + NULL.
  2. `scanSource` same cancel/disable/remove/release (:80-86).
  3. Only THEN `fHalService->release()` (:88-91).
  4. Then command gate removal/release and workloop release (:92-101), then `unregistPM()`.
- Rationale recorded: the same re-entrancy model already used by `if_input`'s gated runAction
  from interrupt context; REVIEW-2 confirmed the watchdog path contains no blocking calls
  (task_add is enqueue-only; the entire join_bss→new_state chain already runs on the main
  workloop from RX context — "decisive proof of tolerance"). PM ack deadlines preserved.

**Subsystem:** AirportItlwm integration (concurrency/lifecycle); interacts with net80211 MLME.
**Verification:** source-verified + build-verified. NOT hardware-validated.
**Transfer notes:** this is the old tree's answer to "watchdog must share the single
workloop/gate". The new (Eric) tree likely has a different V2/workloop layout — port the
INVARIANT (serialize watchdog with MLME; cancel timers before freeing what they dereference;
re-arm via sender; gate-serialize the cancel), not the line-level patch.

## 10. WCL link-up notifications on out-of-join recovery (F-11 — CS9)

**Old defect.** `handleWCLLink` (baseline `WCL.cpp:624-640`): the DOWN branch posted
`LinkStatus{up=0}`; the UP branch only finished a PENDING WCL join (`finishWCLJoin`); the
`LinkStatus{up=1}` message existed only in the join path (FirstBeacon handling, baseline
:747-759). A link recovery OUTSIDE a WCL join — in-driver re-authentication after AP
deauth/disassoc — never informed WCL: menu bar stayed "disconnected" while the driver was
associated and traffic flowed (symptom **S2**).

**Final implementation.** `reference/AirportItlwm/WCL/WCL.cpp:624-664`:
- Down branch unchanged (:629-636): posts `LinkStatus` with `joinBSSID`, reason 255, clears
  `wclLinkIndicated`/`wclBssValid`.
- Pending-join completion unchanged (:637-638).
- NEW recovery branch (:639-662): `else if (up && !joinPending && !wclLinkIndicated &&
  assocNotified)` — builds `AirportWCL::LinkStatusEvent`: BSSID from `ic->ic_bss` when
  non-NULL (else the latched `joinBSSID`); RE-TRACKS `joinBSSID` to the current BSSID if it
  changed (`IEEE80211_ADDR_EQ` compare + memcpy); `event.up = 1; event.reason = 255;
  wclLinkIndicated = true;` and posts `AirportWCL::LinkStatus` — field-for-field mirror of
  the join-path event (join path at :778-783: same bssid/up=1/reason=255/wclLinkIndicated
  sequence). Comment (extended in `2ada74b`, :646-648) documents the open-network edge case:
  a leftover `des_essid` can produce an autonomous re-join after a failed WCL join — posting
  the real state is the truthful report either way.
- Preconditions validated by REVIEW-2: `assocNotified` is set only by a WCL join and reset by
  the next one; link-up implies port_valid (4-way handshake completed).
- `updateWCLLinkQuality(true)` still runs at the end (:663).

**Subsystem:** WCL (macOS Wi-Fi control layer integration).
**Verification:** source-verified + build-verified. NOT hardware-validated.
**Transfer notes:** the new tree's WCL state machine is more extensive (SAE/PMF/WPA3/6GHz);
re-derive the equivalent "recovery outside join" condition against ITS flags.

## 11. Authentication/association retry accounting (F-12 — CS10)

**Old defect.** Double-count + over-strict selection:
- Baseline `ieee80211.c:917-928`: the watchdog incremented `ni_fails` unconditionally on
  auth/assoc timeout; on give-up, `ieee80211_new_state(SCAN)` transitioned, and the newstate
  path (`ieee80211_proto.c:1575-1581`, unchanged region) incremented `ni_fails` AGAIN — a
  single transient timeout counted 2.
- Baseline `ieee80211_node.c:1334-1346`: `choose_bss` skipped a candidate on ANY
  `ni->ni_fails` (nonzero), while upstream OpenBSD tolerates `< 2`. Combined with the double
  count: one transient assoc timeout made the target AP unselectable and evicted within 2
  sweeps; the join then idled until the 30 s WCL joinTimer — symptoms **S3** (first join
  fails, retry connects) and S1 (slow switching). Also punished user-initiated leaves
  (RUN→SCAN falls through the same poisoning in proto.c).

**Final implementation.**
- `reference/itl80211/openbsd/net80211/ieee80211.c:901-938` (`ieee80211_watchdog`):
  `ni_fails++` ONLY on the in-place retry path (:919-924: `ic_state == IEEE80211_S_AUTH &&
  ni && ni->ni_fails < 3` → count this attempt, `ieee80211_node_join_bss`, `goto done`);
  comment :925-928 records that the SCAN transition counts the give-up exactly once
  (proto.c:1575-1581). `ieee80211_deselect_ess` under `IEEE80211_F_AUTO_JOIN` (:929-930) and
  `ieee80211_new_state(ic, IEEE80211_S_SCAN, -1)` (:932) preserved.
- `reference/itl80211/openbsd/net80211/ieee80211_node.c:1336` (`choose_bss`): skip at
  `ni->ni_fails >= 2` (one transient failure stays selectable/retried); eviction semantics
  preserved at :1345-1346 (`if (ni->ni_fails++ > 2) ieee80211_free_node(ic, ni);` — a node
  that reaches fails==3 is freed on the following sweep). Preserved per contract/REVIEW-1:
  free-at->2 sweep eviction, RUN clears fails, retry budget 3 AUTH attempts,
  `ieee80211_match_bss` has no fails check of its own.

**Subsystem:** net80211 MLME.
**Verification:** source-verified (REVIEW-1: "budget identical: 3 AUTH retries; give-up
counts once via the SCAN transition; task-drop only via iwx_stop which frees the table
anyway"; "`>= 2` selection threshold: match_bss has no fails check of its own; eviction still
terminates; RUN clears fails") + build-verified. NOT hardware-validated.
**Transfer notes:** this is the real mechanism behind the misdiagnosed "30 s dead-BSSID
lockout" from the earlier dossier (no such constant exists in net80211) — port the accounting
fix, not the myth.

## 11b. Firmware-load error-path DMA leak (F-13 — CS4b)

**Old defect.** `iwx_ctxt_info_gen3_init` (baseline `ItlIwx.cpp:1255-1267`): after the gen3
context DMA allocations (iml/prph_info/prph_scratch), `if (!iwx_nic_lock(sc)) return EBUSY;`
returned EARLY, bypassing the `fail1`/`fail0` cleanup labels — leaking all three DMA
allocations per failed init attempt; the init retry loop compounds the leak and the next
attempt clobbers the live pointers.

**Final implementation.** `reference/itlwm/hal_iwx/ItlIwx.cpp:1255-1271`:
`if (!iwx_nic_lock(sc)) goto fail1;` (:1259-1260) with explanatory comment (:1255-1258);
on nic-lock success: `iwx_write_umac_prph(IWX_UREG_CPU_INIT_RUN, 1)` then unlock, return 0
(:1261-1264). `fail1:` frees `sc->iml_dma` (:1266-1267); falls through to `fail0:` which
frees `prph_info_dma` + `prph_scratch_dma` (:1268-1270); `return ENOMEM` (:1271). (The IML
allocation's own failure already used `goto fail1` at :1232-1237.) REVIEW-1: "fail1 falls
through to fail0 — all three DMAs freed."

**Subsystem:** hal_iwx (gen3 firmware load path).
**Verification:** source-verified + build-verified. NOT hardware-validated.

---

## 12. Verification-status matrix (preserve these distinctions exactly)

| Fix | Finding/CS | Source-verified | CI build-verified | Hardware-validated |
|---|---|---|---|---|
| TX rate log removal | F-01/CS1 | yes (+REVIEW-1 SOUND) | run 44620003926 | **NO** |
| SW-crypto TX log removal | F-02/CS1 | yes (+REVIEW-1) | run 44620003926 | **NO** |
| Scan-result rates + HalService | F-03,F-04/CS2 | yes (+REVIEW-2) | run 44620003926 | **NO** |
| en0 IFF_RUNNING on link-down | F-05/CS3 | yes (+REVIEW-2) | run 44620003926 | **NO** |
| RX BA buffer free | F-06/CS4 | yes (+REVIEW-1 R7 analysis) | run 44620003926 | **NO** |
| Rate printer `>=` guards | F-07/CS5 | yes (+REVIEW-1) | run 44620003926 | **NO** |
| EAPOL totlen guard | F-08/CS6 | yes (+REVIEW-1) | run 44620003926 | **NO** |
| PNVM ENOENT semantics | F-09/CS7 | yes (after REVIEW-1 CRITICAL fix) | run 44620003926 | **NO** (loaded path byte-identical to hw-validated baseline) |
| Watchdog on main workloop + teardown | F-10/CS8 | yes (+REVIEW-2 SHIP + follow-ups) | run 44620003926 | **NO** |
| WCL link-recovery LinkStatus | F-11/CS9 | yes (+REVIEW-2) | run 44620003926 | **NO** |
| ni_fails single-count + >=2 threshold | F-12/CS10 | yes (+REVIEW-1) | run 44620003926 | **NO** |
| fw-load goto fail1 | F-13/CS4b | yes (+REVIEW-1) | run 44620003926 | **NO** |

**ALL 13 corrections are NOT hardware-validated.** Report §F: "Runtime/hardware: NOT available
in this environment. All behavioral fixes are source-verified + build-verified only; hardware
verification on the MSI target remains pending." README (final): "Hardware verification status
is unchanged: **NOT yet hardware-verified** on the MSI target. A passing CI build confirms
compilation and bundle integrity only, not hardware functionality."
Distinction that matters: the clean upstream laobamac baseline build WAS hardware-validated on
the MSI (README Status, tag `ax211-baseline-validated`, commit `aa19316` in the predecessor
repo) — the reduced tree and the engineering pass were never hardware-run. Only code paths
byte-identical to that baseline (e.g. the PNVM loaded-path doorbell+wait) inherit
validated-on-target status by identity.

CI build identity (final): run 44620003926 on commit `2ada74b`; runner macos-15-intel, Xcode
16.4, MacOSX15.5 SDK, x86_64, Sequoia/Debug; binary 7,624,328 B, SHA-256
`472d042c57f2e851189a994cdda344b74587a94be36a3400586cffe36b70fe2c`; artifact SHA-256
`7c7050f60ff032f3df06088761845aa17537751353647bd3dde5c41ec8775e5f`. First import build:
run 44591987929 on `0159121`, binary SHA-256 `059dcea854948ee2786f9de894e6638ce000721226e07a664cc78bcd5989e589`.

## 13. Old PCI matching and firmware inventory

**PCI matching.** Key is `IOPCIMatch` (NOT `IOPCIPrimaryMatch` — naming correction). Three
plists carry the identical 19-ID list (all iwx device IDs after the Tier-1 reduction pruned
~80 iwm/iwn IDs):
- `reference/AirportItlwm/Info.plist:31-32` — personality `itlwm`, IOClass `AirportItlwm`,
  IOProbeScore 2000, provider IOPCIDevice.
- `reference/AirportItlwm/WCL/Info.plist:46-47` and
  `reference/AirportItlwm/WCL/Sequoia-Info.plist:53-54` — personality `itlwm`, IOClass
  `IOPCIEDeviceWrapper`, IOProbeScore 70000, provider IOPCIDevice (wrapper then publishes
  the `NetworkController` personality: IOClass `AirportItlwm`, provider IOPCIEDeviceWrapper,
  IOResourceMatch IOBSD — WCL/Info.plist:23-39).
- The 19 IDs: `0x02F08086 0x06F08086 0x34F08086 0x3DF08086 0x4DF08086 0x43F08086 0xA0F08086
  0x27208086 0x27238086 0x27258086 0x27268086 0x27298086 0x7A708086 0x7AF08086 0x51F08086
  0x51F18086 0x54F08086 0x7E408086 0x7F708086`. CI gates on the 5 AX211-family IDs
  `0x51F08086 0x51F18086 0x54F08086 0x7E408086 0x7F708086` (main.yml:97-100).
- Target: 8086:51f0 (subsystem 0094, MSI) → `iwl_so_long_latency_trans_cfg`
  (ItlIwx.cpp:12426) and, via the dev_info-table walk (ItlIwx.cpp:13588-13614), the
  `iwlax211_2ax_cfg_so_gf_a0` config (ItlIwx.cpp:12271-12277, name "Intel(R) Wi-Fi 6 AX211
  160MHz", `.fwname = "iwlwifi-so-a0-gf-a0-68.ucode"`) — the report records this as verified
  via the dev_info table walk.

**Firmware inventory.** 15 blobs in `reference/itlwm/firmware/` (12 API-68 ucode + 3 pnvm),
zlib-compressed into the generated `include/FwBinary.cpp` at build time
(`scripts/fw_gen.sh` → `scripts/zlib_compress_fw.py`; lookup via `getFWDescByName`,
`include/FwData.h:36-44`):
- ucode: iwlwifi-Qu-b0-hr-b0-68, Qu-b0-jf-b0-68, Qu-c0-hr-b0-68, Qu-c0-jf-b0-68,
  QuZ-a0-hr-b0-68, QuZ-a0-jf-b0-68, cc-a0-68, **so-a0-gf-a0-68** (AX211 target),
  so-a0-gf4-a0-68, so-a0-hr-b0-68, so-a0-jf-b0-68, ty-a0-gf-a0-68.
- pnvm: iwlwifi-so-a0-gf-a0.pnvm (AX211 target), so-a0-gf4-a0.pnvm, ty-a0-gf-a0.pnvm.
- CI string-verifies 5 families embedded in the Mach-O: `iwlwifi-so-a0-gf-a0-68,
  iwlwifi-ty-a0-gf-a0-68, iwlwifi-so-a0-gf4-a0-68, iwlwifi-so-a0-hr-b0-68,
  iwlwifi-so-a0-jf-b0-68` (main.yml:92-95) + binary-size floor 4 MB (actual ~7.27 MB after
  the 20 iwm/iwn firmware files were removed in the Tier-1 reduction).

## 14. Old build/version conventions

- `MODULE_VERSION = 2.4.0` (`itlwm.xcodeproj/project.pbxproj:1807, 1875`);
  `CURRENT_PROJECT_VERSION = $(MODULE_VERSION)`.
- Preprocessor defines: `ITLWM_VERSION=\"${MODULE_VERSION}\"` and `GIT_COMMIT=\"${GIT_COMMIT}\"`
  (pbxproj:1793-1794, 1861-1862); project-level default `GIT_COMMIT = ""`.
- The workflow passes `GIT_COMMIT="_$(git rev-parse --short HEAD)"` to xcodebuild
  (`.github/workflows/main.yml:45`) — i.e. an underscore-prefixed short SHA — so the reported
  driver version becomes e.g. `itlwm: 2.4.0_2ada74b fw: <fwver>` via `getDRIVER_VERSION`
  (`AirportItlwm/AirportItlwmV2.cpp:1073-1083`, snprintf `"itlwm: %s%s fw: %s"` with
  ITLWM_VERSION, GIT_COMMIT, firmware version). (Same pattern in the inactive V1
  `AirportSTAIOCTL.cpp:1250`.)
- Packaging: version re-extracted from pbxproj via awk (main.yml:115); artifact named
  `AirportItlwm-v${version}-AX211-Sequoia-Debug-${short_sha}.zip` with sha256 sidecars;
  kext bundle id gated to `com.zxystd.AirportItlwm`; x86_64-only lipo enforced; IOSkywalkFamily
  + corecapture linkage enforced.
- Build config: single target `AirportItlwm-Sequoia`, Debug only, defines
  `AIRPORT_WCL AIRPORT_VTD AIRPORT __IO80211_TARGET=__MAC_15_2 __PRIVATE_SPI__
  IO80211FAMILY_V2 IEEE80211_STA_ONLY` (+`DEBUG=1`), SDK MacOSX15.5, MacKernelSDK pinned at
  `3f750085caa17ec3a7880f11c11bf4f48cd6a164`. `AIRPORT_VTD` compiles in the ItlDmaArena
  bounce-buffer layer (full TX copy + RX copy/zero — architectural, kept intentionally).

## 15. Discrepancies, refuted claims, and preserved behaviors (for the transfer phase)

**Report-vs-code:** no substantive disagreement found. All 13 findings verified present and
correct in the final tree at the locations documented above. The findings-register line
numbers are baseline-tree numbers; final-tree equivalents are given per section (they shifted
by a few lines where fixes added code above them, e.g. F-01's site moved 6913 → 6939-6941).

**Corrections ledger (report §H), beyond the PNVM polarity fix:**
- An intermediate edit pass introduced tab→space churn in five files; caught by diff review
  and repaired to byte-precise edits BEFORE committing (verified: no whitespace noise in the
  four fix commits).
- The proposed mgmt-queue-before-qfullmsk reorder was REJECTED after verifying mgmt and data
  share ONE TX ring (`iwx_tx` — mgmt `IWX_MGMT_TID` and data alike on `first_data_qid`);
  the reorder would DROP frames instead of deferring. Documented as deferred D-6.

**Deferred (documented, NOT fixed — do not port as fixes):** D-1 ScanResult throttling;
D-2 RX zero-fill elision (the zero-fill is documented intentional: stale recycled-mbuf bytes
must never be parsed as packets); D-3 idle-scan backoff; D-4 TVQM queue return (needs
firmware-spec verification; wrong command risks fw crash); D-5 cmd-slot recycling; D-6
EAPOL/mgmt second queue; D-7 softc ring array downsizing; D-8 scan-completion epoch
restructure; D-9 ADDBA backoff in HW-setup mode; D-10 disassoc event surfacing.

**Prior-audit claims REFUTED for the live build (do NOT port):** DRV-AP-006 as stated
(live `setPOWER` ON path checks IFF_RUNNING only; the quoted OR-expression is in dead
non-WCL code; init-failure path clears IFF_UP — V2.cpp:1129-1144 vs ItlIwx.cpp:13850-13859);
DRV-AP-011 as stated (both paths on one workloop; the real window was the one-deep skip
flag); "30 s dead-BSSID lockout" (no such constant; actual mechanism is F-12); ScanDone
overtake on 5 GHz specifically.

**Intentional behaviors verified and preserved (do NOT "fix"):** DESBSSID latched per
association (roaming disabled by design in this single-AP fork); open-network A-MPDU
prohibition (anti-injection, output.c:490-507); 256-TFD agg-ring cap (author-documented
macOS freeze workaround); provider-identity spoof + deferred BSD attach (load-bearing
Skywalk workaround); WPA2/WPA3-transition RSN-IE rewrite on scan messages only; RX
zero-fill; EAPOL consumed by the in-driver supplicant under WCL.

**Independent review record (report §G):** REVIEW-1 (HAL + net80211) — all verdicts SOUND
after the PNVM CRITICAL correction; REVIEW-2 (macOS integration) — verdict SHIP, with two
follow-ups applied (gate-serialized watchdog cancel; open-network autonomous-rejoin comment)
and the note that CI was re-run on the final tree (run 44620003926) because the earlier
stored artifact predated the fix commits.
