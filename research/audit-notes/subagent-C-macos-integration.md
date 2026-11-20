# Subagent C — macOS Integration Audit (Eric-AirportItlwm, be200-tahoe @ cf0c5263)

Task ID: M3-C. READ-ONLY audit of the NEW authoritative source
`/home/z/my-project/AirportItlwm/` (+ `include/Airport`, `include/HAL`, `WCL/`), compared against
`/home/z/my-project/reference/` (old AX211 tree, fixes documented in
`research/audit-notes/subagent-G-reference-fixes.md`) and the build map in
`research/audit-notes/subagent-F-build-engineering.md`.

Scope read in full: AirportItlwmV2.cpp/.hpp, AirportItlwmEthernetInterface.cpp/.hpp,
AirportItlwmSkywalkInterface.cpp/.hpp (including WCL method bodies in WCL/WCL.cpp),
AirportItlwmAWDLInterface.cpp/.hpp, AirportItlwm.cpp/.hpp + AirportSTAIOCTL.cpp +
AirportVirtualIOCTL.cpp + AirportItlwmInterface.cpp + AirportAWDL.cpp (legacy),
IOPCIEDeviceWrapper.cpp/.hpp, Info.plist ×3, WCL/WCL.hpp + WCL/Info.plist +
WCL/Sequoia-Info.plist, include/Airport dispatchers + macOS15/ + macOS26/ (diffed),
include/HAL/*, include/ClientKit/*, and the net80211/HAL call-sites that the integration
layer depends on (ieee80211_set_link_state, ic_event_handler posts, match_bss WCL guard,
iwx_watchdog).

Every claim carries `path:line`. Labels: **[Confirmed defect]**, **[Plausible risk]**,
**[Intentional behavior]**, **[Unverified hypothesis]**.

---

## Part 1 — Old-fix counterpart evaluation (Eric side)

### F-03 (+F-04) — scan-result rate information — **[Confirmed defect, present in Eric]**

**Current Eric implementation** — `AirportItlwm/AirportItlwmSkywalkInterface.cpp:1091-1127`
(`convertNodeToScanResult`):

```c
1093:    bzero(result, sizeof(*result));
...
1102:    for (int i = 0; i < result->asr_nrates; i++ )
1103:        result->asr_rates[i] = fNextNodeToSend->ni_rates.rs_rates[i];
1104:    result->asr_nrates = fNextNodeToSend->ni_rates.rs_nrates;
```

The loop bound is read from `result->asr_nrates`, which `bzero()` at :1093 just cleared, so the
loop runs 0 iterations; the count is assigned only afterwards (:1104). Byte-for-byte the same
defect as the reference baseline (G-report §2): `asr_rates` is always delivered empty while
`asr_nrates` stays nonzero. The correct bounded pattern demonstrably exists elsewhere in the
same Eric file — `getRATE_SET` at `AirportItlwmSkywalkInterface.cpp:598-619` clamps from the
node, sets `num_rates` first, and copies `min(rs_nrates, ARRAY_SIZE(ad->rates))`.

**F-04 landmine also present**: `AirportItlwmSkywalkInterface.cpp:1204` (live `getSCAN_RESULT`):

```c
fNextNodeToSend = RB_NEXT(ieee80211_tree, &HalService->get80211Controller()->ic_tree, fNextNodeToSend);
```

`HalService` (bare identifier, no `f`) appears exactly once in the tree
(rg over AirportItlwm: only :1204). It compiles only because `RB_NEXT` discards its 2nd
argument (`itl80211/openbsd/sys/tree.h:725`: `#define RB_NEXT(name, x, y) name##_RB_NEXT(y)`),
the same latent landmine as reference F-04. Note the same function uses the member
`fHalService` at :1186 and :1196.

**Does the defect matter on the live (WCL) targets?** Yes — this path is reachable on Sequoia
and Tahoe, not just legacy: `AirportItlwm::apple80211_ioctl` routes `APPLE80211_IOC_SCAN_RESULT`
to `wcl->getSCAN_RESULT` (`AirportItlwmV2.cpp:1440-1441,1444-1445`), and
`AirportItlwmSkywalkInterface::processBSDCommand` does the same for the SIOCGA80211 form
(`AirportItlwmSkywalkInterface.cpp:1042-1050`). `getCURRENT_NETWORK`
(:1159-1166) feeds `ic_bss` through the same converter. The WCL-native scan path
(`AirportWCL::ScanResult` BeaconMetadata messages, WCL/WCL.cpp:872-932) does not carry rates,
so whenever macOS asks for the legacy `apple80211_scan_result` form it gets empty rate lists.

**Correct transfer** (Eric-internal, minimal): mirror the reference fix
(`reference/AirportItlwm/AirportItlwmSkywalkInterface.cpp:993-998`) into Eric's converter at
:1102-1104 — take `uint8_t nrates = node->ni_rates.rs_nrates`, clamp to
`sizeof(result->asr_rates)/sizeof(result->asr_rates[0])` (u32 array, APPLE80211_MAX_RATES
entries — `include/Airport/apple80211_var.h:483-485`; u8→u32 element copy is the in-tree V1
precedent), store the clamped count **before** the loop, and fix :1204 to `fHalService`.
Eric's channel-less-node guards (:1113-1119 and the skip loop :1192-1199) are an Eric
improvement over the reference and must be preserved.

### F-05 — en0 link truthfulness on link-down — **[Confirmed defect, present in Eric]**

**Current Eric implementation** — `AirportItlwm/AirportItlwmEthernetInterface.cpp:110-119`
(`AirportItlwmEthernetInterface::setLinkState`):

```c
113:    if (state == kIO80211NetworkLinkUp) {
114:        ifnet_set_flags(getIfnet(), ifnet_flags(getIfnet()) | (IFF_UP | IFF_RUNNING), (IFF_UP | IFF_RUNNING));
115:    } else {
116:        ifnet_set_flags(getIfnet(), ifnet_flags(getIfnet()) & ~(IFF_UP | IFF_RUNNING), 0);
117:    }
```

The down branch's mask argument is 0 → `ifnet_set_flags` changes **no** bits → the call is a
no-op. Identical code shape to the reference baseline (G-report §3). en0 keeps
`IFF_UP|IFF_RUNNING` forever after link loss. This is the station en0 path: the down call
arrives via `ieee80211_set_link_state()` (`itl80211/openbsd/net80211/ieee80211_proto.c:2250-2286`,
invoked on the newstate-down path :1956 and from `ieee80211.c:269`) →
`AirportItlwm::setLinkStatus` (`AirportItlwmV2.cpp:784-811`) → command gate
`setLinkStateGated` (`AirportItlwmV2.cpp:813-830`, `that->bsdInterface->setLinkState(state)`
at :820). Note `if_link_state_change()` is commented out in this port
(ieee80211_proto.c:2287-2304), so the BSD stack learns nothing there either — the
`ifnet_set_flags` call is the only en0 carrier mechanism.

Two compounding problems vs the fixed reference:

1. the mask=0 no-op (the bug);
2. even the *intended* value (`& ~(IFF_UP | IFF_RUNNING)`) would clear the administrative
   IFF_UP, which the reference fix deliberately preserves (native macOS keeps en0 UP and only
   drops the carrier).

The correct `ifnet_set_flags(value, mask)` idiom is used **correctly elsewhere in the same
tree**, which makes the base-class down-branch unambiguously an oversight:
- AWDL: `AirportItlwmAWDLInterface.cpp:2258-2259` —
  `ifnet_set_flags(ifnet, arg0 ? IFF_RUNNING : 0, IFF_RUNNING)`.
- llw0 down: `AirportItlwmAWDLInterface.cpp:176-184` (value 0, mask `IFF_RUNNING` — correct;
  its up-branch is a mask=0 no-op, apparently intentional for the hidden interface whose
  RUNNING is driven from `setAWDLLinkGated`/`performCommand`).

**Correct transfer**: apply the reference's fixed semantics verbatim
(`reference/AirportItlwm/AirportItlwmEthernetInterface.cpp:120-134`): up branch unchanged
(sets `IFF_UP|IFF_RUNNING`); down branch
`ifnet_set_flags(getIfnet(), ifnet_flags(getIfnet()) & ~IFF_RUNNING, IFF_RUNNING)` — clear
carrier only, never IFF_UP.

### F-10 — watchdog serialization & teardown order — **[Partially fixed in Eric; guards missing]**

Eric's watchdog architecture differs from the reference baseline but converges on the same
invariant, with three residual gaps.

**What Eric does (verified):**
- **Single workloop — defect NOT present.** `AirportItlwmV2.cpp:423-440`:
  `fWatchdogWorkLoop = _fWorkloop;` (an alias assignment — the member name survives from the
  old design but no second `IOWorkLoop` is ever created; rg confirms no other assignment), then
  `retain()`, `IOTimerEventSource::timerEventSource(this, watchdogAction)` and
  `fWatchdogWorkLoop->addEventSource(watchdogTimer)`. `_fWorkloop` is the global
  `IO80211WorkQueue` created once in `IOPCIEDeviceWrapper::start`
  (`IOPCIEDeviceWrapper.cpp:120`, `IO80211WorkQueue::workQueue()`; class derives from
  IOWorkLoop — `include/Airport/macOS26/IO80211WorkQueue.h:25`). All command-gate actions,
  RX/newstate work, the WCL join/scan timers and the watchdog therefore share one workloop
  gate — the core F-10 invariant (watchdog serialized with MLME) holds.
- **Teardown order — mostly correct.** `releaseAll()` (`AirportItlwmV2.cpp:27-88`) cancels the
  watchdog FIRST (:29-38), long before `fHalService->release()` (:66-69); `stop()`
  (`AirportItlwmV2.cpp:578-597`) additionally cancels it earlier still via
  `disableAdapter(bsdInterface)` at :590 (`cancelTimeout()+disable()`, V2.cpp:1484-1489) before
  `fHalService->detach(pciNub)` (:592). The reference's "free HAL first, cancel timers later"
  hazard does not exist in Eric.
- **Arming**: only in `enableAdapter` (V2.cpp:1479-1481) after the HAL reports success; armed
  with a 1000 ms period (`kWatchDogTimerPeriod`, AirportItlwmV2.hpp:43). The callback
  (`watchdogAction`) runs `(*ifp->if_watchdog)(ifp)` = `iwx_watchdog`
  (`itlwm/hal_iwx/ItlIwx.cpp:20152` sets it) → `ieee80211_watchdog`
  (`itl80211/openbsd/net80211/ieee80211.c:941-976`).

**Residual gaps vs the reference fix (reference V2.cpp:135-151 / :54-101):**
1. `watchdogAction` (`AirportItlwmV2.cpp:122-128`) dereferences `fHalService`
   **unconditionally** (:124) — no `if (!fHalService) return;` guard. In practice safe by
   ordering (watchdog always cancelled in stop()/releaseAll before `fHalService` is NULLed),
   but the reference judged the guard necessary; the member is a plain global-adjacent
   pointer, and `stop()` on a *different* thread than an in-flight callback keeps a narrow
   window open. **[Plausible risk]**.
2. No null-check of `ifp->if_watchdog` before the call (:125). `if_watchdog` is set only in
   `iwx_attach` (ItlIwx.cpp:20152); arming happens after `fHalService->attach()` succeeded
   (enableAdapter is only called after start), so NULL is not expected — same reasoning the
   reference used, but the reference still added the check. **[Plausible risk]**.
3. Re-arm uses the **member pointer** `watchdogTimer->setTimeoutMS(...)` (:127) instead of the
   `timer` sender argument — the canonical IOKit pattern immune to a cleared member. Combined
   with (1): if a callback is in flight when `releaseAll` runs `cancelTimeout()`/`removeEventSource()`
   /`release()` (:31-34) on another thread, the still-running callback re-arms through the
   member after it may have been freed. Eric's cancel is a **direct** cancel, not the
   reference's gate-serialized `_fCommandGate->runAction(...)` cancel (reference V2.cpp:59-79)
   that waits for an in-flight (gate-holding) callback to finish. **[Plausible risk — narrow
   race; the reference's gated-cancel is the stronger pattern]**.

**Correct transfer**: port the three guards (fHalService guard, if_watchdog null-check,
sender-based re-arm at V2.cpp:122-128) and consider wrapping the releaseAll cancel in
`_fCommandGate->runAction` exactly as reference V2.cpp:59-79 does. The main-workloop part of
F-10 needs no change in Eric.

### F-11 — WCL link-up notification on out-of-join recovery — **[Fix absent in Eric; reachability differs — see analysis]**

**Current Eric implementation** — `AirportItlwm/WCL/WCL.cpp:1360-1385` (`handleWCLLink`):

```c
1364:    portAuthorized = up;
1365:#if __IO80211_TARGET == __MAC_26_0     // Tahoe: Supplicant event on RSN link-up
1374:    if (!up && wclLinkIndicated) {       // DOWN: post LinkStatus{up=0, reason 255}
1382:    if (up && joinPending && firstBeaconNotified)
1383:        finishWCLJoin(0, 0, kIOReturnSuccess);
1384:    updateWCLLinkQuality(true);
```

The UP branch only finishes a pending join. The only `LinkStatus{up=1}` poster is the
first-beacon join path (`WCL/WCL.cpp:1529-1545`: requires `joinPending && assocNotified &&
!firstBeaconNotified`, posts LinkStatus + FirstBeacon at :1536-1542). There is **no**
`up && !joinPending && !wclLinkIndicated && assocNotified` recovery branch — the exact branch
the reference added as F-11/CS9 (`reference/AirportItlwm/WCL/WCL.cpp:639-662`, re-tracking
`joinBSSID` to `ic_bss` and posting a field-for-field mirror of the join-path event).
Eric carries the same state flags (`joinPending`, `wclLinkIndicated`, `assocNotified`,
`joinBSSID` — AirportItlwmSkywalkInterface.hpp:496-518), so the transfer is direct.

**Reachability analysis (differs from the reference).** Eric structurally forecloses most
autonomous re-association: `ieee80211_match_bss` refuses every candidate unless
`ic->ic_wcl_join_requested` (`itl80211/openbsd/net80211/ieee80211_node.c:1075-1078`), and the
DEAUTH handler immediately retires the session (`WCL/WCL.cpp:1575-1586`: posts Deauth(203) +
`finishWCLJoin(1, reason, kIOReturnOffline)`, whose failure branch clears
`ic_wcl_join_requested` at :1296). `startWCLJoin` also clears `IEEE80211_F_AUTO_JOIN`
(:1140). **However**, the reference has the *same* match_bss guard
(reference ieee80211_node.c:1059) and still concluded the recovery branch was needed
(G-report §10: "in-driver re-authentication after AP deauth/disassoc", open-network
autonomous re-join from a leftover `des_essid`). In Eric the leftover state is real:
`finishWCLJoin` on failure does **not** clear `ic_des_essid`/`ic_des_bssid`/`F_DESBSSID`
(only `leaveWCLNetwork` does, WCL.cpp:1347-1349), so after an assoc-failure or DEAUTH the
join target remains programmed; any path that re-arms `ic_wcl_join_requested` or races the
event ordering can re-produce RUN with `joinPending == false` — in which case en0 recovers
(bsd up-branch works) but WCL/the menu bar are never told (no LinkStatus up, no
ConnectComplete). Verdict: **[Plausible risk — semantics of the reference defect preserved in
Eric's architecture; runtime reachability unproven]**. Recommended transfer: add the reference
branch to `handleWCLLink` (adapted 1:1 — flags are identical), which is harmless if
unreachable and fixes the stuck-menu-bar symptom (S2) if reachable.

---

## Part 2 — Independent Eric-specific audit

### 2.1 Driver request path (how macOS talks to the driver)

Under `AIRPORT_WCL` (both live targets), requests arrive as **IO80211InfraProtocol virtual
calls** on `AirportItlwmSkywalkInterface` (subclass of `IO80211InfraProtocol`,
AirportItlwmSkywalkInterface.hpp:26), dispatched by the WCL/airportd side of
IO80211Family — *not* via the classic apple80211 ioctl switch. Two additional legacy funnels
remain: `AirportItlwm::apple80211_ioctl` (V2.cpp:1426-1453; under WCL only handles
SCAN_REQ/SCAN_RESULT) and `processBSDCommand` (AirportItlwmSkywalkInterface.cpp:1039-1052,
SIOCGA80211/SIOCSA80211 apple80211req form — also only SCAN_REQ/SCAN_RESULT).
`apple80211SkywalkRequest` both overloads return `kIOReturnUnsupported` (V2.cpp:1455-1467).

**Serialization**: every mutating WCL request funnels into one command-gate action —
`wclCommand` (WCL/WCL.cpp:405-475) — via
`_fCommandGate->runAction(wclCommand, this, <opcode>, <arg>)` from the individual setters:
`setWCL_SCAN_REQ` :477-480 (op 0), `setWCL_ASSOCIATE` :487-490 (op 1),
`setWCL_JOIN_ABORT` :492-499 (op 2; Sequoia signature `void*`, Tahoe
`apple80211_wcl_abort_join*` — SkywalkInterface.hpp:391-395),
`setWCL_LEAVE_NETWORK` :501-504 (op 3), `setCIPHER_KEY` (SkywalkInterface.cpp:380-381, op 8),
`getRSN_IE`/`setRSN_IE` (:733/:758, ops 10/9), `setCLEAR_PMKSA_CACHE` :950-953 (op 11),
`setWCL_SCAN_ABORT` :482-485 (op 4 → `finishWCLScan(kIOReturnAborted)`),
`getWCL_BSS_INFO`/`getWCL_EXTENDED_BSS_INFO`/`getBEACON_INFO`/`getCHANNELS_INFO`/
`getWCL_TRAFFIC_COUNTERS`/`setWCL_SET_SCAN_HOME_AWAY_TIME` (ops 5/6/7/13/14/15).

**Completion semantics** — asynchronous by design: every request returns `kIOReturnSuccess`
when accepted, and completion is posted later via `AirportItlwm::postMessage(interface,
AirportWCL::<Message>, payload, size, /*wclRoute=*/true)` (the IO80211Controller WCL postMessage,
`include/Airport/macOS15/IO80211ControllerV2.h:131`). Message IDs live in
`WCL/WCL.hpp:96-109`. Payload structs carry static_asserts for wire layout
(WCL.hpp:118-264). Cancellation: join abort/leave/scan abort each reset state and post the
matching completion (JoinAbortComplete 214 / ConnectComplete 213 / ScanDone 237) — see traces.

#### Trace A — full SCAN request (WCL route)

1. airportd/WCL → `setWCL_SCAN_REQ(apple80211ScanRequest*)` — WCL/WCL.cpp:477-480 → gate →
   `wclCommand` case 0 (:426) → `beginWCLScan(request)` :506-525.
2. `AirportWCL::decodeScan(request, 0x1550, scan)` (WCL.hpp:511-543) validates the 0x1550-byte
   native request: count ≤ 400, ssidLen ≤ 32, type 1-4, and builds 2.4/5 + 6 GHz channel
   bitmaps from the native `apple80211_channel` array. On Tahoe only, an Instant-Hotspot
   SSID is pulled from the native SSID list at +0x1318 (WCL.cpp:512-523, `#if
   __IO80211_TARGET == __MAC_26_0`).
3. `startWCLScan(scan)` WCL.cpp:527-634:
   - driver not RUNNING yet: if IFF_UP, the request is parked (`deferredScan`, `scanDeferred`,
     14 s timer WCL_SCAN_TIMEOUT_MS=14000, WCL.cpp:75) and re-issued on DRIVER_READY
     (:1466-1474); else `kIOReturnNotReady`.
   - a scan in flight is retired with `finishWCLScan(kIOReturnAborted)` (:549-557 — the
     "menu never refreshes" fix); join in flight → `kIOReturnBusy`; mid-AUTH/ASSOC → Busy.
   - maps requested channels onto `ic_chan_active` (568-586), sets the net80211 WCL scan
     state (`ic_wcl_scan_requested/_active/_ssid/_restricted/_channels[_6GHz]`, 605-613),
     seeds RNR (:614), arms the 14 s scanSource (:615), and starts either
     `ieee80211_begin_cache_bgscan` (RUN, :616-623) or `ic_newstate(SCAN)` (:625-631).
4. Execution: net80211 scans; every beacon/proberesp raises `IEEE80211_EVT_BEACON`
   (`ieee80211_input.c:3070`) → `AirportItlwm::eventHandler` (V2.cpp:90-120) →
   `handleWCLEvent` (WCL.cpp:1387-1589) case BEACON → `publishWCLBeacon` (WCL.cpp:773-870;
     only when `scanPending || joinPending || S_SCAN`, :1527) → `postWCLScanResult`
   (WCL.cpp:872-932): allocates `BeaconMetadata + IEs`, fills channel/spec/SSID/RSSI/
   interval/capability with `RSSIValid|SSIDPresent` flags, keeps a copy per (chanspec,BSSID)
   in `wclScanCopies[96]` (`keepWCLScanResult` :676-703), and posts
   `AirportWCL::ScanResult` (201) live (:929).
5. Completion: scan end → `IEEE80211_EVT_SCAN_DONE` (`ieee80211_node.c:1518`) →
   WCL.cpp:1548-1555 sets `scanCompleted` and `scanSource->setTimeoutMS(0)` →
   `AirportItlwm::fakeScanDone` (V2.cpp:130-142) → `completeWCLScan` (WCL.cpp:713-717) →
   `finishWCLScan(status)` (WCL.cpp:636-674): writes the `WCLScanLast` ioreg summary, cancels
   the timer, re-posts every kept result (:664-666, for WCL's age-limited consumption), posts
   `AirportWCL::ScanDone` (237) with the status (:668), then the **legacy**
   `APPLE80211_M_SCAN_DONE` (:671-673, "still drives airportd's result fetch on Tahoe").
   Timeout path: 14 s timer → same `fakeScanDone` → `kIOReturnTimeout` if nothing heard.
6. Abort: `setWCL_SCAN_ABORT` → op 4 → `finishWCLScan(kIOReturnAborted)` (WCL.cpp:470-472).

#### Trace B — full JOIN request (WCL route)

1. airportd → `setWCL_ASSOCIATE(apple80211AssocCandidates*)` — WCL.cpp:487-490 → gate op 1 →
   `beginWCLJoin` :1006-1014 → `AirportWCL::decodeJoin(request, 0x2cc, join)`
   (WCL.hpp:683-723: count 1-10, ssid 1-32, key ≤ 64, RSN ≤ 257, MLO address checks) →
   `startWCLJoin(join)` :1063-1258.
2. `startWCLJoin`: OWE auto-detect from the node's RSN (:1066-1074); classify auth
   (`classifyLegacyAuth`, WCL.hpp:639-681: Open/WEP/Personal/PersonalSAE/Enterprise/
   EnhancedOpen); derived-credential cache lookup (PBKDF2/SAE-PT reuse, :1076-1084);
   retires an in-flight scan (:1097-1098 — "join preempts scan" fix); defers the join while a
   private-MAC reconfig or a non-RUNNING window is open (`deferWCLJoin` :1052-1061, 30 s
   bound); validates the channel spec against `ic_chan_active` (:1112-1128); leaves any
   current network (:1133-1134); clears RSN/WEP/PSK/SAE/PMKSA (:1135-1140); programs
   `ieee80211_wpaparams` (SAE PT derivation, `pbkdf2_sha1` for passphrase, PMKSA seeds for
   enterprise, WEP nwkeys — :1143-1220); programs `ic_des_essid/des_bssid/F_DESBSSID` and the
   join channel bitmaps (:1221-1233); sets `ic_wcl_join_requested=true` (:1234), joinPending,
   `assocNotified=firstBeaconNotified=portAuthorized=false` (:1241); 30 s joinTimer (:1245);
   `ic_newstate(SCAN)` (:1246) — error path fully unwinds state (:1247-1255).
3. net80211 (guard `ic_wcl_join_requested`, ieee80211_node.c:1075-1078) matches → AUTH →
   ASSOC → RUN; the in-driver supplicant runs the 4-way handshake (EAPOL consumed by
   net80211; enterprise EAPOL from macOS is queued via `deferWCLUserEapol`
   (WCL.cpp:159-207, Tahoe-only hook `ic_wcl_defer_user_eapol` set in `initWCL`
   :279-283) and released on link authorization (:172-207, `setWCLNativeLinkReady` from
   `setWCL_LINK_STATE_UPDATE` :1636-1656).
4. Events: `IEEE80211_EVT_STA_ASSOC_DONE` (ieee80211_input.c:3897 etc.) →
   `handleWCLEvent` case ASSOC_DONE (WCL.cpp:1556-1574): posts `AssocComplete` (211) with
   status/MLO data; failure finishes the join immediately; success extends the timer to 60 s
   for enterprise (:1567-1569). Port valid → `ieee80211_set_link_state(LINK_STATE_UP)`
   (ieee80211_proto.c:2233, RSN-deferred) → `AirportItlwm::setLinkStatus(active)` →
   gate `setLinkStateGated` (V2.cpp:813-830) → en0 `setLinkState(up)` + `handleWCLLink(true)`
   (portAuthorized; Tahoe posts Supplicant 76, WCL.cpp:1365-1373). First beacon for
   `joinBSSID` (BEACON case, WCL.cpp:1529-1545): posts `LinkStatus{up=1}` (216) + FirstBeacon
   (212) → `finishWCLJoin(0,0,Success)` when portAuthorized → posts `ConnectComplete` (213)
   with `ConnectionEvent{status, reason, peers[1]{bssid, driverStatus}}` (WCL.cpp:1276-1304).
5. airportd then drives the session: `setWCL_LINK_STATE_UPDATE` — Sequoia implementation
   parses the raw bytes and calls the Skywalk `setLinkState(up/down[, debounce])`
   (WCL.cpp:1607-1618); Tahoe delegates to
   `IO80211InfraInterface::setWCL_LINK_STATE_UPDATE` and layers enterprise-EAPOL handoff +
   output-thread control on top (:1620-1659).
6. Failure/timeout/cancel: `wclJoinTimeout` (WCL.cpp:1306-1313, 30 s → finish(1,1004)+
   leave); `abortWCLJoin` :1353-1358 (leave + JoinAbortComplete 214); `leaveWCLNetwork`
   :1315-1351 (flushes queues, clears all join state incl. des_essid, `S_SCAN` if needed).

**Keys**: `setCIPHER_KEY` under WCL accepts only PMK/PMKSA/MSK for enterprise
(`installWCLKey` WCL.cpp:955-982 — feeds `ieee80211_pmksa_add`); PTK/GTK are rejected
("native WCL user-client rejects PTK/GTK"), the 4-way/GTK install runs in net80211. The
legacy `setPTK`/`setGTK` bodies (SkywalkInterface.cpp:190-282) are only reachable from the
non-WCL `setCIPHER_KEY` branch (:382-443).

### 2.2 Link/interface status publication & consistency

Three publishing layers:
1. **en0 carrier** — driver-driven: `ieee80211_set_link_state` (proto.c:2250-2286) →
   `setLinkStatus` (V2.cpp:784-811; dedup on `currentStatus` :788-790) → gate
   `setLinkStateGated` (V2.cpp:813-830) → `bsdInterface->setLinkState()` (F-05 defect on
   down) + `handleWCLLink()` + llw0 link state. Up also `startOutputThread()`, down flushes
   queues (:795-807).
2. **Skywalk/WCL session state** — airportd-driven: `setWCL_LINK_STATE_UPDATE` (WCL.cpp:1603-
   1664). `linkState()` on Tahoe defers to `IO80211InfraInterface::linkState()` ("WCL owns
   the BSD link transition", SkywalkInterface.cpp:1004-1014); on Sequoia it derives from
   `ic_state == S_RUN`.
3. **WCL messages** — the contract in §2.7.

**Path comparison**:
- *Join path*: AssocComplete → (port valid) en0 up + handleWCLLink(true) → LinkStatus(up)+
  FirstBeacon → ConnectComplete. Consistent.
- *Deauth path*: EVT_STA_DEAUTH → Deauth(203) + finishWCLJoin(1, reason, Offline) →
  ConnectComplete(fail); net80211 transitions produce link-down → en0 setLinkState(down)
  **no-op [F-05]** + handleWCLLink(false) → LinkStatus(down) if wclLinkIndicated. **en0
  inconsistent with actual association state after every disassociation** (carrier stays up).
- *Recovery path* (link returns without a new WCL join): en0 up-branch works, WCL gets
  nothing — **F-11 gap** (§Part 1).
- *Driver-reset path*: RESET_BEGIN → ResetInterface(0) (49) unless a private-MAC reconfig is
  being consumed (WCL.cpp:1406-1419); READY → ResetInterface(1) + DriverAvailable ×2 routes
  (:1447-1465) + deferred join/scan resume. Association across a reset is not re-signaled
  with LinkStatus; WCL relies on the ResetInterface pair — consistent with native behavior.
- LQM mirrors state: `updateWCLLinkQualityGated` (WCL.cpp:365-396) reports quality -2 unless
  `portAuthorized && linkState()==Up && IFF_UP|IFF_RUNNING && S_RUN && bssid==joinBSSID`.

**Finding C-1 [Confirmed defect — F-05 carrier no-op]**: after link loss en0 keeps
IFF_RUNNING (and the F-05 down-branch would also drop IFF_UP if the mask were fixed naively —
see Part 1). Symptom: configd/System Settings/menus can show a live interface while the
driver is disassociated.

**Finding C-2 [Plausible risk — F-11 gap]**: recovery link-up is invisible to WCL (Part 1).

**Finding C-3 [Intentional behavior]**: `setLinkStatus` dedup on `currentStatus`
(V2.cpp:788-790) coalesces repeated same-state posts; bgscan never produces RUN↔SCAN
transitions, so only real assoc/deassoc events move it.

### 2.3 en0 semantics (IFF_UP/IFF_RUNNING) — F-05 counterpart

Covered in Part 1 (F-05). Summary of every flag touch in the integration layer:
- Up: `AirportItlwmEthernetInterface.cpp:114` sets `IFF_UP|IFF_RUNNING` (works).
- Down: `:116` mask=0 no-op **[Confirmed defect]**.
- AWDL: `AirportItlwmAWDLInterface.cpp:2258-2259` correct value/mask idiom (IFF_RUNNING
  only, data-gated by `awDataAllowed()`); llw0: `:176-184` (down correct; up no-op by
  design — RUNNING comes from `performCommand`/`setAWDLLinkGated`).
- `setPOWER` OFF checks `IFF_UP|IFF_RUNNING` before `disableAdapter` (V2.cpp:1384-1390);
  ON checks IFF_RUNNING only (:1391-1396) — matches the reference's fixed semantics
  (G-report §15 refuted DRV-AP-006 for the equivalent code).
- `isChipInterfaceReady()` = IFF_RUNNING (SkywalkInterface.cpp:997-1002).

### 2.4 Scan result publication — F-03 counterpart

Two publication paths:
1. **WCL-native (primary on Sequoia/Tahoe)**: `publishWCLBeacon`/`postWCLScanResult`
   (WCL.cpp:773-932). Bounds and validation are thorough: IE chain validated by
   `validIEPrefix` (WCL.hpp:405-418, ≤2048, tail allowance), SSID parsed by `parseSsid`
   (WCL.hpp:478-509) with explicit Hidden/AllZero/TooLong/NoElement/Truncated states;
   nameless results are suppressed except the join target (:825-838 — the 6 GHz menu-visibility
   fix); a 16-entry SSID ring remembers names across node rebuilds (:813-824); RSSI =
   `IWM_MIN_DBM + ni_rssi` (:865, :890); dedup per (chanspec,BSSID) in
   `keepWCLScanResult` (:676-703, 96 slots); allocation failure counted and dropped
   (:878-882). The result is posted live (:929) and re-posted at ScanDone (:664-666).
   **[Intentional behavior — double posting]**: results are delivered twice (live + batch) —
   documented as required because "WCL applies result-age limits when it consumes ScanDone"
   (WCL.cpp:662).
2. **Legacy apple80211_scan_result (secondary)**: `getSCAN_RESULT` RB-tree cursor
   (SkywalkInterface.cpp:1177-1209) + `convertNodeToScanResult` (:1091-1127) — **F-03
   confirmed defect** (Part 1), plus the Eric-added channel-less node skip (:1192-1199) and
   channel guard in the converter (:1113-1119) which are improvements over the reference.
   Iteration safety: the cursor `fNextNodeToSend` + `fScanResultWrapping` walk the RB tree
   across separate ioctl calls without a lock — same model as the reference (single-threaded
   airportd fetch under the family's own serialization); `setSCANCACHE_CLEAR` refuses while
   BGSCAN/ASCAN active (:948-956).
3. Legacy `setSCAN_REQ` (SkywalkInterface.cpp:1054-1087) on WCL builds: starts a bgscan and
   arms scanSource(100 ms) → `fakeScanDone` → `completeWCLScan` → `finishWCLScan` — which
   **early-returns unless scanPending** (WCL.cpp:638-639). A legacy-route scan that did not
   go through `startWCLScan` therefore never posts APPLE80211_M_SCAN_DONE. **[Plausible
   risk — vestigial path; harmless if airportd only uses the WCL route (all evidence says it
   does), broken for any legacy consumer]**

### 2.5 Power management

- **IOKit PM**: `registerWithPolicyMaker` (V2.cpp:1628-1645) allocates power on/off thread
  calls; `setPowerState` (:1556-1584) defers to them with a 5,000,000 µs ack; the thread
  calls re-enter through the command gate (`handleSetPowerStateOff/On` :1592-1626) — clean
  gated pattern. `setPowerStateOff` (:1647-1653) = `disableAdapter` (watchdog cancel + HAL
  disable) + ack; `setPowerStateOn` (:1655-1673) re-enables the adapter when `!IFF_UP`,
  with a documented fix for "does not reconnect after sleep" (comment :1659-1668; enabling
  is idempotent in ItlIwx::enable).
- **airportd-driven**: `setPOWER` (V2.cpp:1374-1424, WCL branch) — OFF:
  `changePowerStateToPriv(kPowerStateOff)` + `disableAdapter` if IFF_UP|IFF_RUNNING +
  `net80211_ifstats`; ON: `changePowerStateToPriv(kPowerStateOn)` + `enableAdapter` if
  !IFF_RUNNING.
- **PCI PM**: `initPCIPowerManagment` (V2.cpp:1513-1536) — enables BusMaster/MemWrInvalidate,
  disables I/O space, finds PMC, sets PME enable (0x8000), `magicPacketSupported` from
  D3cold PME support; `getPacketFilters` advertises wake-on-magic-packet when supported
  (:1089-1099); `setWakeOnMagicPacket` stores the flag (:1586-1590). Real WoW ioctls
  (get/setWOW_PARAMETERS, getWOW_ENABLED, setWOW_LOW_POWER_MODE,
  getSYSTEM_SLEEP_CONFIG) all return `kIOReturnUnsupported`
  (SkywalkInterface.hpp:36, 63, 156-157, 305-306). **[Intentional behavior — no WoW
  offload; magic-packet flag only]**.
- **Suspend/resume ordering vs teardown**: sleep → policy maker → thread call → gate →
  `disableAdapter` (watchdog cancelled BEFORE HAL disable — good); wake → gate →
  `enableAdapter`. Driver unload (`stop()`): destroyAWDL → stopWCL → super::stop →
  disableAdapter → setLinkStatus(valid) → `fHalService->detach` → ether_ifdetach →
  detachInterface(fNetIf) → release fNetIf → releaseAll (watchdog already cancelled;
  cancels again first, then WCL/fault-reporters/pipes, then HAL release, then command gate,
  scanSource, workloop, `unregistPM` — V2.cpp:27-88). The only ordering nit: in `stop()`
  `disableAdapter` runs *after* `super::stop(provider)` (:589-590) — inherited from upstream,
  no evidence of harm. `unregistPM` frees thread calls last (:87, :1544-1554).
- **Sequoia vs Tahoe**: zero divergence — no `__IO80211_TARGET` branch exists in any PM
  function (grep list in §2.8).

### 2.6 Watchdog/monitor timer — F-10 counterpart

Analyzed in Part 1 (F-10). Additional facts: the timer is created only after
`fHalService->attach()` succeeds (creation at V2.cpp:432-440, attach at :405), armed only in
`enableAdapter` (:1479-1481), cancelled in `disableAdapter` (:1486-1487) and `releaseAll`
(:29-38). It runs on the main IO80211WorkQueue (single gate) and touches, via
`iwx_watchdog` (ItlIwx.cpp:~16920-16955): TX-ring health (schedules firmware recovery on
stuck rings), `ifp->if_timer`, and `ieee80211_watchdog` (MLME auth/assoc retry — see the
F-12 note below). Everything it touches is gate-serialized **except** the teardown race
documented in Part 1.

**Adjacent finding C-4 [Confirmed defect — F-12 not ported; net80211, flagged for Subagent
B]**: Eric's `ieee80211_watchdog` still has the F-12 double-count:
`itl80211/openbsd/net80211/ieee80211.c:956-970` increments `ni_fails` unconditionally on
timeout (:958) *and* the SCAN give-up transition increments again
(`ieee80211_proto.c:1584,1611`), while `choose_bss` skips a candidate on ANY `ni_fails`
(`ieee80211_node.c:1443`) instead of the reference's `>= 2` threshold
(reference ieee80211_node.c:1336; the reference watchdog counts only on the in-place retry
path, reference ieee80211.c:919-923). Eric adds an SAE-timeout hook
(`ieee80211_auth_sae_timeout`, ieee80211.c:959-961) inside the same block. The F-12 fix
(single-count + `>=2` selection threshold, symptom "first join fails, retry connects")
should be transferred by the net80211 owner.

### 2.7 WCL event contract (enumerated)

Message IDs (`WCL/WCL.hpp:96-109`); all payloads static_asserted. Posting contexts verified:

| # | Message (ID) | Posted at (WCL.cpp) | Payload | Context | Sequencing notes |
|---|---|---|---|---|---|
| 1 | LqmUpdate (39) | :1505 (Sequoia `SequoiaLqmUpdate` 0x150) / :1512 (Tahoe `LqmBeaconUpdate` 0x1dc) | RSSI / beacon deltas | workloop (BEACON event), every 8th associated beacon, portAuthorized only | Two different wire formats per OS (`#if` at :1499); Tahoe resets `wclLqmReportedBeacons` after post (:1514) |
| 2 | ResetInterface (49) | :1418 (begin, payload 0) / :1449 (complete, payload 1) | uint32 | gate (DRIVER_* re-gated at :1393-1397) | begin posted only when not consuming a private-MAC reconfig (:1410-1416) |
| 3 | DriverAvailable (55) | :1455 (WCL route) **and** :1465 (interface route) | `DriverAvailability` 0xf8, version 3, reason 0xe0821803/04 | gate | Dual posting documented as load-bearing (:1456-1464 — the second route reaches IO80211ControllerMonitor::setDriverAvailable) |
| 4 | Supplicant (76) | :1370 | `SupplicantEvent` 0x28 | gate (setLinkStateGated), Tahoe only | Posted on link-up with RSNON; clears WCL's handshake deadline / IO80211RSNDone |
| 5 | ScanResult (201) | :929 (live) / :665 (batch) | `BeaconMetadata`+IEs (0x40/0x44 header + ≤0x800) | workloop | See §2.4; metadata layout differs Sequoia/Tahoe (`WCL.hpp:182-186, 251-257`) |
| 6 | Deauth (203) | :1583 | `DeauthEvent` 0x14 | workloop (DEAUTH event) | Followed by finishWCLJoin(1,...) → ConnectComplete(fail) |
| 7 | AssocComplete (211) | :1570 | `AssociationEvent` 0x1c (+MLO) | workloop | Only while joinPending && !assocNotified; assocNotified = !status |
| 8 | FirstBeacon (212) | :1542 | `FirstBeaconEvent` 0x14 | workloop | Requires wclBssValid; preceded by LinkStatus(up) at :1541 |
| 9 | ConnectComplete (213) | :1289 | `ConnectionEvent` 0xa4 | gate/workloop | posted by finishWCLJoin (join retired) |
| 10 | JoinAbortComplete (214) | :1356 | none | gate (op 2) | always after leaveWCLNetwork |
| 11 | LinkStatus (216) | :1380 (down) / :1541 (up, join path only) | `LinkStatusEvent` 16B | gate (setLinkStateGated) | **F-11 gap**: no up-poster outside the join path |
| 12 | ScanDone (237) | :668 | IOReturn status | workloop (timer) | Followed by legacy APPLE80211_M_SCAN_DONE :672 |
| 13 | legacy APPLE80211_M_SCAN_DONE / COUNTRY_CODE_CHANGED / CHANNEL_SPEC_QUERY_COMPLETED | :672 / :273 / :271 | — | country: thread_call + gate (wclCountryUpdateGated :255-275, deliberately NOT on the workloop thread :261) | country flow refreshes WCL's copy via CHANNEL_SPEC_QUERY_COMPLETED first |

Contract checks: payload population is field-complete per the static_asserted structs (grep
verified all fills); every posting site runs either on the workloop (RX-event origin) or
under the command gate (`setLinkStateGated`, `wclCommand`, country thread); the
`instance->postMessage(..., true/false)` route split (WCL PostOffice vs interface route) is
applied deliberately at each site (the only dual-post is DriverAvailable). Two contract
observations: (a) `getWCL_BSS_INFO` (wclCommand case 5, WCL.cpp:436-468) copies
`sizeof(wclBssInfo)` (= `sizeof(BeaconMetadata)+0x800` → 0x840 on Sequoia / 0x844 on Tahoe)
into the caller's opaque `apple80211_beacon_msg*` — **[Unverified hypothesis]** that the
native struct is ≥ that size on both OSes (it is reverse-engineered, not declared; case 7
uses the separate 0x808 `wclBeaconInfo`); (b) case 5 also strips EHT IEs from the metadata
copy when the association is not EHT (:447-467) — WCL derives active PHY from the BSS IEs.

### 2.8 Sequoia vs Tahoe ABI differences and every target branch

**Build-level**: identical 80-file source set; delta is `__IO80211_TARGET`
(`__MAC_15_2` vs `__MAC_26_0`), `INFOPLIST_FILE` (WCL/Sequoia-Info.plist vs WCL/Info.plist —
**content-identical**, differ only by an XML comment header — verified by diff), build dir,
deployment target (15.2 vs 10.15) [Subagent F].

**Header-level (include/Airport/macOS15 vs macOS26, diffed file-by-file)**:

| Header | Sequoia (15.8.2 / 24H232) | Tahoe (25G229/332/342) | Behavioral consequence |
|---|---|---|---|
| IO80211InfraInterface.h | size 0x120; `setLinkState(4 args)`; `createLinkQualityMonitor(IO80211Peer*, IOService*)`; **no** `setWCL_LINK_STATE_UPDATE` (it lives in InfraProtocol); no `setMacAddress(mloAddrArray&)` | size **0x130**; `setLinkState(5 args, +code)`; `setLinkStateInternal(5 args)`; `createLinkQualityMonitor(IO80211Peer*, bool)`; adds `setWCL_LINK_STATE_UPDATE`; pure-virtual `setMacAddress(mloAddrArray&) = 0`; `_abi_0c30` slot trick for setRxDataStallStats; ITL_MACOS27 extras | Eric code branches on the arg-count/MAC-array differences (see branch list); `_layout` padding absorbs the 16-byte growth |
| IO80211InfraProtocol.h | size 0x120; `setWCL_JOIN_ABORT(void*)`; has `setWCL_LINK_STATE_UPDATE`, `set6G_MODE`, `get/setWIFI_BT_5G_POLICY` | size **0x130**; `setWCL_JOIN_ABORT(apple80211_wcl_abort_join*)`; drops `setWCL_LINK_STATE_UPDATE` (moved to InfraInterface), `set6G_MODE`, WIFI_BT_5G_POLICY; adds 7 getters (SMARTCCA, LQM_STATISTICS, HE_CAPABILITY, DEVICE_ORIENTATION, ACCESSORY_STATE, P2P_DEVICE_CAPABILITY, POWERTABLE_VERSION) and 6 setters (BTCOEX_EXT_PROFILE, DEVICE_ORIENTATION, ACCESSORY_STATE, OS_ELIGIBILITY, TX_MODE_CONFIG, MITIGATE_INTERFERENCE); ITL_MACOS27 tail slot 677 | Explains the `#if != __MAC_15_2` stub block at SkywalkInterface.hpp:37-44 and the differing setWCL_JOIN_ABORT signature |
| IO80211SkywalkInterface.h | size 0x118; `setMacAddress(ether_addr&) = 0` at end | size **0x128**; `_abi_0e60` syncDPSStats slot; `createLinkQualityMonitor(IO80211Peer*, bool)`; `setMacAddress` moved/changed; ITL_MACOS27 postMessageOutOfOrder/postPeerPresenceDone/getTotalRxUnicastFrames | Driver must override the right setMacAddress per OS (it does, SkywalkInterface.cpp:1221-1231) |
| IO80211VirtualInterface.h | 500-slot IO80211VirtualInterface / 563-slot IO80211AWDLProtocol tables, `#pragma once`, opaque slots documented ("must not be called") | generated from the Tahoe kernel collection; same slot discipline | AWDL anchor table differs (see §2.9) |
| IOSkywalkNetworkInterface.h | 0x110 Ethernet class | adds `willTerminate`, `_abi_0928` setRxFlowSteering slot, mloAddrArray fwd; ITL_MACOS27 IPsec offload virtuals ("five IOSkywalkNetworkInterface virtuals at slot 323" — V2.cpp:289-290 comment) | macOS 27 guard exists because the table grows again |
| IOSkywalkEthernetInterface.h | 0x110; mExpansionData2 @0x108 | **0x120**; mExpansionData2 @0x118 | RegistrationInfo buffer sizes differ per OS (used by AWDL create) |
| IOSkywalkInterface.h / IO80211WorkQueue.h / FaultReporter.h | override-style decls | plain virtuals (same slots) + ITL_MACOS27 extras | FaultReporter content-identical |
| IO80211ControllerV2.h | postMessage(5-arg) at :131 (macOS15 header) | same signature | — |
| IO80211ManagementBuffer.h | present (macOS15 only) | **absent** | AWDL mgmt-frame pool on 15 comes from the controller header; on 26 via exported vtable symbols (AWDLInterface.hpp:31-42) |

**Wire-format differences inside shared code (WCL.hpp)**: `BeaconMetadata` 0x40 vs 0x44
(`#if !defined(__IO80211_TARGET) || __IO80211_TARGET != __MAC_15_2` extra `reserved2`,
WCL.hpp:182-186 + static_asserts :251-257); `copyWCLExtendedBss` zeroes 0x1e0 vs 0x214 and
places RSN at +0xdd vs +0x113 (WCL.cpp:1688-1721).

**Every `__IO80211_TARGET` / `ITL_MACOS27` branch in the live .cpp/.hpp (grep-complete):**
- `AirportItlwmV2.hpp:14-18` — FaultReporter header choice.
- `AirportItlwmV2.cpp:291-317` — **Darwin version gate in start()** (Sequoia: Darwin 24.2+;
  26: Darwin 25; 27: Darwin 27; 14.4/14.0 legacy branches) — the "unmatched kernel would
  dispatch to the wrong methods" guard (comment :289-290).
- `AirportItlwmV2.cpp:1185-1187` — capability byte 9 bit 1 (cap 73) **Tahoe-only**
  (directed-scan type-86 workaround; comment :1179-1184).
- `AirportItlwmSkywalkInterface.hpp:37-44` (Tahoe-only getter stubs), `:97-108`
  (setMacAddress/getP2P…/getWCL families), `:112` setWCL_ASSOCIATE arg type, `:391-395`
  (setWCL_JOIN_ABORT Sequoia variant), `:557-561` (LowLatency setMacAddress per OS).
- `AirportItlwmSkywalkInterface.cpp:1007-1014` — `linkState()` Tahoe defers to the native
  InfraInterface (WCL owns the BSD link transition); Sequoia derives from S_RUN.
- `AirportItlwmSkywalkInterface.cpp:1221-1231` — setMacAddress(ether_addr&) on 15 vs
  setMacAddress(mloAddrArray&)→setMloHardwareAddresses on 26.
- `WCL/WCL.hpp:182-186, 251-257` — BeaconMetadata layout; `WCL/WCL.cpp:279-283`
  (`initWCL`: enterprise EAPOL defer hook installed on **non-15.2 only** — `ic_wcl_defer_user_eapol`),
  `:492-499` (setWCL_JOIN_ABORT signature), `:512-523` (**Tahoe-only** Instant Hotspot SSID
  extraction from the native request), `:1365-1373` (**Tahoe-only** Supplicant event on
  link-up), `:1499-1516` (LqmUpdate format per OS), `:1607-1659` (setWCL_LINK_STATE_UPDATE:
  Sequoia raw-byte parse + direct setLinkState vs Tahoe native + EAPOL handoff),
  `:1688-1721` (copyWCLExtendedBss layout).
- `AirportItlwmAWDLInterface.hpp:16-42` (header set + mgmt-pool ABI exports on 26),
  `AirportItlwmAWDLInterface.cpp:50-96` (vtable anchor table per OS: 15.8.2=563 slots,
  26=568, 27=579), `:569` (init path per OS).
- Legacy-only files (not compiled for the live targets): AirportItlwm.cpp:552,982;
  AirportSTAIOCTL.cpp:315,1136,1434,1441,1453,1477.

**Sequoia/Tahoe runtime divergences worth knowing**: capability byte 9 (type-86 scan);
Supplicant event; LQM wire format; EAPOL enterprise defer hook (Tahoe only — on Sequoia the
in-driver supplicant consumes EAPOL entirely); setWCL_LINK_STATE_UPDATE ownership of the BSD
link transition; WCL JOIN_ABORT payload; extended-BSS layout; AWDL mgmt-buffer ABI.

### 2.9 AWDL analysis

**What exists (Eric-only; none of it in the reference)**: a full
`IO80211AWDLProtocol` implementation — `AirportItlwmAWDLInterface`
(AirportItlwmAWDLInterface.cpp, 3462 lines) plus its BSD side
`AirportItlwmAWDLEthernetInterface` and the `AirportItlwmLowLatencyInterface` (llw0) pair.
Components:
- **Creation**: macOS (wifip2pd) asks via `setVIRTUAL_IF_CREATE(role 6)`
  (SkywalkInterface.cpp override at AirportItlwmAWDLInterface.cpp:2167-2174) →
  `AirportItlwm::createAWDLInterface` (:2176-2246): `AirportItlwmAWDLInterface::
  withController` → attach → RegistrationInfo (own IOMalloc'd records tracked in
  fAWDLNetInfo/fAWDLEthInfo) → deferBSDAttach → start → `IONetworkController::attachInterface`
  with `fCreatingAWDL` routing `createInterface()` (V2.cpp:727-738) to the AWDL Ethernet
  class. awdl0 publishes `HiddenInterface` so configd does not build "Wi-Fi 2"
  (AirportItlwmAWDLInterface.cpp:228-231) and its own MAC as ifnet uniqueid (:222-238).
- **Sync engine**: host-side availability-window timeline reconstructed from received
  action frames (`syncFromFrame`, `awTimerFired`, `scheduleNextAW`), election/sync state
  getters/setters, PSF/MI template storage (`setAWDL_SYNC_FRAME_TEMPLATE`,
  `setAWDL_OOB_AUTO_REQUEST`), peer timeline tracking + aligned listen dwells
  (`trackPeer`, `scheduleAlignedListen`, `-itlawdldata` own-sequence mode), PSF/MI transmit
  during dwells (`sendAWDLFrame`/`buildAWDLFrame`, `-itlawdltx`), peer-cache completion
  emulation (464-byte records, timer-deferred event 51 — ForbiddenItlwm PR #57 protocol),
  UMI-ack emulation (event 69), HT capability TLV for the peer manager
  (getHT_CAPABILITY, SkywalkInterface.cpp:1129-1157), the AWDL **data path** (stage 4:
  `inputAWDLData` rebuilding Ethernet frames from AWDL data headers, `enqueueData`/`flushData`
  256-deep queues), and the companion llw0 (`createLowLatencyInterface`
  :2271-2391, `completeLowLatencyInterface` :2393-2432 with a gated 1 s wait for BSD
  registration).
- **HAL hooks**: `ic_vendor_action_handler` / `ic_awdl_data_handler` wired in
  `AirportItlwm::start` (V2.cpp:396-402); RX funnel `awdlActionFrameHandler` /
  `awdlDataFrameHandler` (V2.cpp:550-576). The iwx HAL has the listener machinery
  (`ic_awdl_listen`, listen channel/BA-accept plumbing — ItlIwx.cpp:6996-7014, 10863-10908,
  12880; `ic_awdl_llw_tx` for llw0 TX).
- **Gates (boot args, include/HAL/ItlAWDLBootArg.hpp)**: AWDL+AirDrop is **OFF by default**;
  `-itlawdl` (or ForbiddenItlwm's `-itlawdliface`) enables it, **WCL targets only**
  (ItlAWDLBootArg.hpp:19-28). `-itlawdlllw` additionally opts into llw0 (off by default —
  "its creation path has panicked on every machine that ran it so far", :36-42).
  `-itlawdllegacyba`/`-itlawdlcoexbatx` → legacy BA on TX (:44-49). Fine-grained test flags
  listed at :7-10 (-itlawdllisten/tx/data/promisc/p2p/aw/hunt/baaccept/listener/client).
- **Safety gates in code**: (1) `nativeTableMismatch()` (AirportItlwmAWDLInterface.cpp:59-104)
  verifies the running kernel's IO80211AWDLProtocol vtable against pinned anchor slots
  (15.8.2/24H232: 563 slots; Tahoe 25G229/332/342: 568; macOS 27: 579) — any mismatch
  disables AWDL at start with an `AWDLBuildCheck` ioreg reason (V2.cpp:386-395); (2) card
  capability — no `ic_awdl_listen` (cards older than 9260) disables it
  (V2.cpp:411-422, "no AirDrop support for this card"); (3) capability advertisement is
  conditional — `capabilities[4] bit 0` (wifip2pd asks for awdl0 only when set) and dual-band
  bit `capabilities[3] 0x20` are set only when `fAWDLEnabled` (V2.cpp:1210-1221).
- **Teardown**: `stop()` destroys AWDL first (V2.cpp:583); `destroyAWDLInterface` /
  `destroyLowLatencyInterface` (AirportItlwmAWDLInterface.cpp:2434-2488 / :2469-2488) take
  out the driver's own RegistrationInfo records before the framework's typed free
  (`takeOutOwnRegistrationInfo` :111-124 — documented kfree_type/early.kalloc.288 panic
  avoidance, V2.hpp:279-282).

**Status for AX211**: active on **both** Sequoia and Tahoe when `-itlawdl` is present and the
vtable check passes; dormant otherwise. Subagent A's requirement ("legacy AWDL listener/P2P/
aux-ROC needed by macOS WCL") is satisfied by the iwx P2P-device/aux-ROC listener +
`ic_awdl_listen`, which the AX211 (so-gf-a0, P2P-device capable) provides. The AWDL data/AF
path is host-driven (no firmware AWDL), matching what the 9260+ iwlwifi P2P device can do.

### 2.10 IOPCIEDeviceWrapper

`IOPCIEDeviceWrapper.cpp` (146 lines):
- **Matching**: personality `itlwm` (WCL plists, IOProbeScore 70000, provider IOPCIDevice;
  AirportItlwm/Info.plist:31-36 keeps the legacy V1 personality, IOProbeScore 2000 — legacy
  targets only). `probe` (:60-114) walks ItlIwx::iwx_match → ItlIwm::iwm_match →
  ItlIwn::iwn_match and instantiates the matching `ItlHalService` subclass (`new ItlIwx` for
  8086:51f0).
- **Interrupt config**: the BE branch (`#ifdef AIRPORT_WCL`, :85-95) — if
  `IwxBE::pciFamily(deviceID) != None` (GL=0x272b, BZ=0xa840/0x7740/0x4d40 —
  itlwm/hal_iwx/iwx_be_config.h:5-14) calls
  `device->configureInterrupts(kIOInterruptTypePCIMessagedX, 1, 1, 0)` — the Tahoe-only API
  exposed by the patched MacKernelSDK (scripts/prepare_tahoe_sdk.py). **On the AX211
  (0x51f0) this branch is never taken**; the classic path runs instead: MSI-X disabled,
  MSI enabled (:96-108), probe fails if the device has neither cap.
  **[Plausible risk — not AX211]**: the branch is compiled into the **Sequoia** kext too
  (both targets share the patched SDK header); a GL/BZ card on a Sequoia kernel would call a
  vtable slot that Sequoia's IOPCIDevice does not implement. Harmless for the AX211-only
  specialization; if other chips are pruned (Subagent F open question), gate this call by
  `__IO80211_TARGET == __MAC_26_0` or drop the BE branch entirely.
- **Power**: PMinit/registerPowerDriver(2 states)/joinPMtree in start (:127-129), PMstop in
  stop (:138), `setPowerState` = IOPMAckImplied (:142-146). The wrapper's workloop IS the
  global `_fWorkloop` (:120) — the AirportItlwm controller reuses it
  (IOPCIEDeviceWrapper::getWorkLoop :55-58, V2.cpp:350-355).
- **Ownership**: `fHalService` is allocated here and handed to AirportItlwm::probe
  (V2.cpp:170-181) without an extra retain; the controller's `free()` releases it
  (V2.cpp:602-605) and `releaseAll()` also releases (V2.cpp:66-69) — see C-6 below for the
  double-release nuance.

### 2.11 Interface lifecycle

**start() order** (V2.cpp:287-548): Darwin-version gate (:291-317) → initCCLogs (corecapture
pipes + fault reporter; failure → releaseAll) → super::start → PCI enables + power domain →
initPCIPowerManagment → command gate on `_fWorkloop` → medium tables →
`fHalService->initWithController(this, _fWorkloop, _fCommandGate)` (:371) +
`ic_event_handler = eventHandler` (:372) → boot-arg tuning (-novht/-noht40/itlwm_he,
:374-385) → AWDL boot-arg + vtable + capability gates (:386-422) → `fHalService->attach`
(:405) → watchdog on the main workloop (:423-440) → scanSource (:441-451) →
**fNetIf = new AirportItlwmSkywalkInterface; init (creates joinTimer/wclEapolSource via
initWCL)** (:453-465) → fNetIf->attach (:475) → attachInterface(fNetIf) (:481) →
IONetworkController::attachInterface → **bsdInterface** (:487-498) → RegistrationInfo +
mExpansionData records + deferBSDAttach + fNetIf->start (:499-539) → setLinkStatus(valid)
(:540) → AUTO_JOIN if ess list empty (:541-542) → bsdInterface->registerService +
registerService (:543-546). The BSD attach completes later via
`AirportItlwmEthernetInterface::attachToDataLinkLayer` → gated `prepareBSDInterface`
(EthernetInterface.cpp:44-86) — the deferred-BSD-attach load-bearing Skywalk workaround
(inherited, provider-identity spoof at :95-102).

**stop() order** (V2.cpp:578-597): destroyAWDLInterface → stopWCL (cancels join/EAPOL timers
via gate, purges state) → super::stop → disableAdapter (watchdog off + HAL disable) →
setLinkStatus(valid) → fHalService->detach → ether_ifdetach → detachInterface(fNetIf) →
release fNetIf → releaseAll. No F-10-style teardown-order hazard found in the happy path.

**Findings:**
- **C-5 [Plausible risk — start-failure leaks]**: after `fNetIf->attach(this)` (:475), the
  failure paths at :481-486, :487-498 and :499-522 call `releaseAll()` but never
  detach/release `fNetIf`; `AirportItlwm::free()` (:599-620) doesn't release it either (nor
  does the `!fNetIf->init` path at :455-463 release the failed `new` object — the `new`
  succeeded, `init` failed, refcount 1, leak). Low impact (start failure bricks the device
  instance anyway) but a real leak on those paths; the reference had the same shape.
- **C-6 [Intentional behavior — ownership convention]**: `fHalService` is released in both
  `releaseAll()` (:66-69, sets NULL) and `free()` (:602-605, guarded by NULL) — the
  NULL-guard makes the pair safe; the wrapper never releases after handoff.
- **C-7 [Intentional behavior]**: `_fWorkloop`/`_fCommandGate` are **globals** (V2.cpp:24-25)
  — single-controller assumption (matches the family's own IO80211WorkQueue::workQueue()
  singleton); two cards in one machine would collide. Fine for the AX211 product.
- **C-8 [Intentional behavior]**: bsdInterface is not explicitly detached/released in
  stop() (only `ether_ifdetach` + super::stop); the AWDL/llw0 destroy paths DO explicitly
  detach+release their BSD interfaces (:2445-2452, :2473-2478). Inherited asymmetry; no
  use-after-free found (bsdInterface is not touched after ether_ifdetach in the stop path —
  verified: last use is `disableAdapter(bsdInterface)` at :590 before detach).

### 2.12 New-defect scan (integration layer)

1. **F-03/F-04 confirmed** (Part 1) — legacy scan-result rates empty + `HalService` landmine.
2. **F-05 confirmed** (Part 1) — en0 down no-op.
3. **F-11 gap** (Part 1) — recovery LinkStatus branch absent.
4. **F-10 residuals** (Part 1) — unguarded watchdogAction, member re-arm, non-gated cancel.
5. **C-9 [Plausible risk — dead computation]**: `AirportItlwm::setHardwareAddress`
   (V2.cpp:1023-1030) formats `requested`/`current` MAC strings into stack buffers and never
   uses them (leftover from a removed log). Harmless (compiler elides) but should go.
6. **C-10 [Trivial]**: duplicated `XYLog` in `stop()` (V2.cpp:580).
7. **C-11 [Intentional behavior — per-frame logging]**: the EAPOL hexdump logging exists only
   in `#ifndef AIRPORT_WCL` branches (outputPacket V2.cpp:959-964; inputPacket
   EthernetInterface.cpp:177-189) — **not compiled into the live Sequoia/Tahoe targets**.
   The WCL datapath (`enqueuePacket`/`outputStart`/`normalizeInputPacket`) is log-free. The
   F-01/F-02-class hot-path logging defect therefore does not exist in Eric's live build.
8. **C-12 [Intentional behavior — diagnostics]**: `wclTraceHotspot149` (WCL.cpp:719-771)
   builds ioreg dictionaries per beacon but only while a directed ch-149 hotspot scan is
   traced (`WCLHotspotTraceEnabled`, set at :590-599, 128-record cap) — bounded, opt-in-by-
   traffic-pattern; `finishWCLScan`'s `WCLScanLast` summary (:640-656) is per-scan, not
   per-frame. Acceptable.
9. **C-13 [Plausible risk — legacy scan completion]**: legacy-route `setSCAN_REQ` on WCL
   builds never completes (see §2.4 item 3).
10. **C-14 [Unverified hypothesis — opaque buffer size]**: `getWCL_BSS_INFO` copies
    `sizeof(wclBssInfo)` into the opaque `apple80211_beacon_msg*` (WCL.cpp:436-439); sizes
    0x840 (15) vs 0x844 (26) are reverse-engineered constants — verify against the native
    struct before relying on the Sequoia value.
11. **C-15 [Plausible risk — wrong-OS API reachability]**: BE `configureInterrupts` call
    compiled into the Sequoia kext (see §2.10); unreachable for AX211.
12. **C-16 [Intentional behavior]**: `getSSID` non-WCL branch uses `strlen(des_essid)`
    (SkywalkInterface.cpp:352-353) — potential over-read on a non-NUL-terminated 32-byte
    SSID, but legacy targets only; the WCL branch (:348-350) is length-bounded. Transfer the
    bounded form if the legacy file is ever revived.
13. **C-17 [Intentional behavior]**: event-polarity spot-checks all correct:
    DriverAvailable `available=ready` (:1453); ResetInterface 0=begin/1=complete;
    LinkStatusEvent up=1/0 with reason 255; AssocComplete `driverStatus = status ?
    kIOReturnError : Success` (:1565); ScanDone carries the IOReturn status; DeauthEvent
    reason from `ic_deauth_reason` (:1580). Failure notifications present on every request
    path (join: ConnectComplete fail + timer + abort; scan: ScanDone timeout/abort; key
    install: kIOReturnBadArgument/NotReady; country: not-ready silently kept).
14. **C-18 [Adjacent, net80211 — for Subagent B]**: F-12 not ported (see §2.6/C-4).

---

## Part 3 — Feature-preservation matrix inputs (capability advertisement inventory)

**Mechanism**: the apple80211 capability bitmap via `getCARD_CAPABILITIES`
(V2.cpp:1131-1266, WCL branch) is the single advertisement surface; per Apple disassembly
comments, Tahoe's WCLDeviceConfiguration reads the SAME bytes (HE byte 17 bit 7, EHT byte 17
bit 4, OWE byte 12 bit 0, 6 GHz byte 11 bit 6). PHY detail comes through the getter family.

| Capability | Advertised via | Where | Notes |
|---|---|---|---|
| WPA2/TKIP-group | capabilities[0] AES_CCM\|TKIP when C_RSN | V2.cpp:1170-1171 | explicit fix: hiding TKIP made Apple80211 reject WPA2/TKIP-group networks |
| WPA1 bit cleared | capabilities[1] &= ~WPA1 | V2.cpp:1172 | "WPA not enabled, like on Apple cards" |
| WME, SGI 20/40 | capabilities[2] | V2.cpp:1174-1176 | |
| Scan completion events | capabilities[5]=0x40 | V2.cpp:1173 | |
| Scan capability 22 | capabilities[2] \|= 0x40 | V2.cpp:1177-1178 | Apple80211Scan/ScanAsync reject scans without it |
| Capability 73 (directed scan via plain SCAN_REQ) | capabilities[9] \|= 0x02 | V2.cpp:1185-1187 | **Tahoe only** — type-86 SCAN_REQ_MULTIPLE answered with error on Tahoe |
| MFP | capabilities[6] bit 0 when C_MFP | V2.cpp:1189-1190 | gates WPA3/SAE filtering in Apple80211Associate2 |
| SAE (deferred join) | capabilities[9] \|= 0x08 when C_MFP && ic_sae_defer_join | V2.cpp:1191-1192 | |
| HE (Wi-Fi 6) | capabilities[17] bit 7 when C_HE | V2.cpp:1193-1196 | + getPHY_MODE 11AX when F_HEON (SkywalkInterface.cpp:461-462); HE MCS map in getWCL_EXTENDED_BSS_INFO +0xd4 (WCL.cpp:1706-1715); `itlwm_he=0` boot-arg off-switch (V2.cpp:380-385) |
| EHT (Wi-Fi 7) | capabilities[17] bit 4 when ic_eht_cap_valid | V2.cpp:1197-1199 | + 11BE in getPHY_MODE (:463-468) — dormant on AX211 (no EHT), active path for BE cards |
| OWE | capabilities[12] bit 0 when RSN+MFP | V2.cpp:1200-1202 | OWE join supported (classifyLegacyAuth EnhancedOpen, WCL.hpp:643-644) |
| 6 GHz | capabilities[11] bit 6 if any active 6 GHz channel | V2.cpp:1203-1209 | + NativeChannelInfo.sixGHz band override (WCL.hpp:282-289 — without it every 6 GHz channel is labeled 5 GHz); WCL_CHANNELS_INFO supports6GHz (WCL.cpp:1766-1767) |
| 160 MHz | ieeeChanFlag2apple VHT160/80P80 (SkywalkInterface.cpp:67-70, 84-87), getMCS_VHT bw (575-593), wclCurrentChannelSpec width 160 (WCL.cpp:37-54) | | AX211 name itself is "…160MHz" (fw config) |
| AWDL / AirDrop | capabilities[4] bit 0 + dual-band capabilities[3] 0x20, only with -itlawdl | V2.cpp:1210-1221 | wifip2pd only creates awdl0 when byte4 bit0 set |
| Vendor/model | newVendorString "Apple", newModelString = firmware name | V2.cpp:974-982 | identity spoof, load-bearing |
| Version | getDRIVER_VERSION `itlwm: 2.4.0_<git> fw: <ver>` | V2.cpp:1268-1278 | ITLWM_VERSION=2.4.0 + GIT_COMMIT from CI; bundle com.zxystd.AirportItlwm, CFBundleVersion=$(MODULE_VERSION) (WCL/Info.plist:17-20) |
| Hardware addr | getHW_ADDR → wclPermanentMAC (HardwareAddress 12B wire struct) | SkywalkInterface.cpp:1212-1219, WCL.hpp:76-89 | |
| Private MAC | setMacAddress (ether_addr on 15 / mloAddrArray on 26) → planMacUpdate state machine (Invalid/Unchanged/Busy/Change), ifnet_set_lladdr sync, no firmware restart unless associated+RUNNING (ic_wcl_mac_reconfig consumed at next reset) | V2.cpp:1014-1067, WCL.hpp:57-74, SkywalkInterface.cpp:1221-1231 | macOS rotates the scan MAC; driver converges without restart (comments V2.cpp:1044-1058). get/setPRIVATE_MAC, getRANDOMISATION_STATUS → Unsupported (SkywalkInterface.hpp:184, 228, 335) |
| Saved networks / reconnect | **macOS owns profiles** (airportd); driver is stateless across joins except the per-session DerivedCredentialCache (PBKDF2/SAE-PT memoization, cleared in stop/failure, WCL.hpp:581-618) and deferred join/scan parking across driver restarts (WCL.cpp:1052-1061, 1466-1476) | | no driver-side profile store; ic_ess/AUTO_JOIN only at cold start (V2.cpp:541-542) |
| WoW | wake-on-magic-packet advertised when PME D3cold | V2.cpp:1089-1099, 1513-1536 | no WoW offload ioctls |
| Enterprise EAPOL | PMK/MSK install + deferred user-EAPOL queue (Tahoe) | WCL.cpp:955-982, 159-207 | |
| MLO | setMloHardwareAddresses (Tahoe), peer MLD address in join/AssociationEvent | V2.cpp:994-1012, WCL.hpp:545-560 | dormant on AX211 |
| IBSS / hostap / softap / monitor | stubs → kIOReturnUnsupported | SkywalkInterface.hpp:297-299, 147-148, V2.hpp:142-144 | intentional |
| Regdomain | firmware country code wins; framework value as fallback; ZZ/00 push-down only while not RUN | V2.cpp:1292-1357 | |

---

## Open questions

1. **F-11 reachability on Eric** — can `ic_state == RUN` occur with `joinPending == false`
   (leftover des_essid + re-armed join_requested after DEAUTH ordering)? Needs runtime
   logging; if yes, the missing recovery LinkStatus branch is a live S2 bug. The transfer is
   cheap and safe either way.
2. **F-03 consumer impact on WCL builds** — which macOS components still fetch the legacy
   `apple80211_scan_result` (airportd cache? diagnostics?)? Determines severity of the
   empty-rates delivery.
3. **`apple80211_beacon_msg` native size** vs `sizeof(wclBssInfo)` per OS (C-14).
4. **Legacy `setSCAN_REQ` completion gap** (C-13) — confirm no live consumer.
5. **BE `configureInterrupts` on Sequoia** (C-15) — confirm the GL/BZ IDs are dropped with
   the AX211 specialization, or gate the call by `__IO80211_TARGET`.
6. **Watchdog in-flight race** — whether Eric's direct `cancelTimeout` in releaseAll can
   interleave with an executing `watchdogAction` on the workloop (Part 1/F-10); the
   reference's gated cancel removes the question.
7. **fNetIf start-failure leaks** (C-5) — worth fixing during any start() refactor.
8. **ITL_MACOS27 branches** — keep (forward-compat, GoldenGate target) or strip with the
   GoldenGate target decision (Subagent F open question 1)?
9. **bsdInterface release responsibility** on the station path (C-8) — inherited; confirm
   the framework path really owns it before any stop() reordering.
