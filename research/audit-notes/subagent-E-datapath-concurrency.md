# Subagent E — Data-Path & Concurrency Audit (Task M3-E)

Scope: `/home/z/my-project` (Eric-AirportItlwm, be200-tahoe, snapshot commit 84fb5d3 / HEAD e73c117), read-only.
Cross-referenced: `research/audit-notes/subagent-G-reference-fixes.md` (13 old fixes), `subagent-A-hardware-firmware.md`
(AX211 region map), `reference/` tree (laobamac lineage, final HEAD 46027fe).
All `path:line` citations are relative to `/home/z/my-project` unless prefixed `reference/`.
Build facts verified: `AIRPORT_WCL` and `AIRPORT_VTD` are defined for every configuration
(itlwm.xcodeproj/project.pbxproj:4347-4348, 4381-4382, 4415-4416, …). AX211 = `sc_use_mld_api` false,
`sc_msix` 0, family AX210 (per Subagent A §1) — all MLD/MSI-X/BZ branches below are noted as dead for AX211.

Labels used: **[Confirmed defect]** / **[Demonstrated inefficiency]** / **[Plausible risk]** / **[Unverified hypothesis]** /
**[Intentional behavior — do not "fix"]**.

---

## Part 1 — Old-fix counterpart evaluation (Eric side)

### F-01 — per-frame TX rate log in `iwx_tx_fill_cmd` — **PRESENT [Confirmed defect]**

Eric's implementation (`itlwm/hal_iwx/ItlIwx.cpp:8147-8204`, function `iwx_tx_fill_cmd`):

```c
8198	    rate_flags |= IWX_RATE_MCS_CCK_MSK_V1;
8200	    XYLog("%s hwrate: %d ridx: %d rate: %d minrate: %d\n", __FUNCTION__, hwrate, ridx, iwx_ridx2rate(rs, ridx) & IEEE80211_RATE_VAL, ieee80211_min_basic_rate(ic));
8201	    *rate_n_flags = htole32(rate_flags | hwrate);
```

- Called per transmitted frame from `iwx_tx` (ItlIwx.cpp:8567), which runs on the command gate
  (`_iwx_start_task` via `getMainCommandGate()->runAction`, ItlIwx.cpp:16752; or inline when already in gate, :16735).
- Two function calls (`iwx_ridx2rate`, `ieee80211_min_basic_rate`) are evaluated in the format arguments for
  every frame; `XYLog` is unconditional kprintf. Identical defect to the reference baseline.
- The rest of the function is byte-identical in structure to the reference final tree (reference/…/ItlIwx.cpp:6886-6945),
  including the intentional early `return &iwx_rates[ridx]` paths at Eric :8174/:8181 (HT/legacy paths leave
  `*flags == 0` so firmware TLC picks the rate — present in both trees, do not touch).
- **Transfer**: delete line 8200 (or replace with a comment as the reference did at reference:6939-6941). Control flow
  unchanged; `hwrate`/`ridx` remain used at :8201. Note the callers of the neighbor `DPRINTFN(3, ...)` at :8654 are
  debug-gated and were deliberately kept in the reference — keep them.

### F-07 — rate-printer off-by-one guards — **PRESENT (both sites) [Confirmed defect, memory safety]**

- `iwx_rs_pretty_ant` ItlIwx.cpp:744-757 — guard at **:753** `if (ant > ARRAY_SIZE(ant_name))` — table has 4 entries
  (indices 0-3, `IWX_ANT_AB`), so `ant == 4` (`IWX_ANT_C`, if_iwxreg.h per G F-07) passes and reads `ant_name[4]` OOB.
- `iwx_rs_pretty_bw` ItlIwx.cpp:759-773 — guard at **:769** `if (bw > ARRAY_SIZE(pretty_bw))` — table has 5 entries
  (20..320 MHz), so `bw == 5` (reachable from every TLC notification, G F-07) reads `pretty_bw[5]` OOB.
- Reachability in Eric: printers `iwx_rs_pretty_print_rate_v1` (:819) / `iwx_rs_pretty_print_rate` (:878) are called
  from `iwx_rs_update` at :14516/:14520 — the `IWX_TLC_MNG_UPDATE_NOTIF` handler (dispatch at :18027-18034).
  Control-plane frequency (per rate change, not per frame), but every rate update can hit the OOB read.
- Reference final uses `>=` at reference:527 and :543.
- **Transfer**: two one-character changes `>` → `>=` at :753 and :769. No other delta between the trees' printers.

### F-09 — PNVM failure semantics — **PRESENT (no-match path) + G's polarity warning applies [Confirmed defect on the no-match path; loaded path matches the validated baseline]**

Eric's `iwx_read_pnvm` (ItlIwx.cpp:2394-2492) and `iwx_load_pnvm` (:2495-2529); caller
`iwx_load_ucode_wait_alive` (:5723-5743, `err = iwx_load_pnvm(sc); if (err) return err;` at :5736-5738);
notification handler `IWX_PNVM_INIT_COMPLETE_NTFY` at :17759-17766 setting `sc_pnvm_payload_len`/
`sc_pnvm_status` via `iwx_record_pnvm_notification` (:17430-17440).

Return-value semantics of Eric's `iwx_read_pnvm`:

| return | path | meaning |
|---|---|---|
| 0 | :2472-2474 (`err = iwx_pnvm_handle_section(); if (!err) goto out;`) | SKU matched, section loaded into `pnvm_dram` |
| 0 | :2484-2486 — `if (sc->sc_device_family >= IWX_DEVICE_FAMILY_BZ) err = ENOENT;` — **non-BZ keeps err==0** | walked the file, **no SKU matched, nothing loaded** — indistinguishable from success |
| 0 | :2410-2413 (`!find` / name-derive failure `goto out`) | **no file parsed at all, nothing loaded** — also 0 |
| -EINVAL | :2450 | TLV length violation (note: **negative** errno) |
| EINVAL | :2423-2427 | `.pnvm` resource load failure (positive errno) |
| other | retained from `iwx_pnvm_handle_section` | section-handling error (walk continues; a later matching SKU can overwrite it) |

`iwx_load_pnvm` consequences:

1. Empty SKU → `return family >= BZ ? ENOENT : 0;` (:2503-2504). For AX211: benign 0, no doorbell — fine.
2. `err = iwx_read_pnvm(sc); if (err) return err;` (:2506-2508) — for AX211 **no-match returns 0**, so the code
   proceeds exactly as if a section had been loaded: clears `IWX_PNVM_COMPLETE` (:2509), kicks the doorbell
   (:2512-2515), and blocks up to 2000 ms in `iwx_wait_notification` (:2519). With nothing loaded the firmware
   never sends PNVM_INIT_COMPLETE_NTFY → **2 s gate-held stall, then ETIMEDOUT**, then
   `if (!err && sc->sc_pnvm_payload_len != sizeof(uint32_t)) return EINVAL;` (:2525-2526) or timeout error
   propagates → `iwx_load_ucode_wait_alive` fails (:5736-5738) → `iwx_init` retry loop (:16561-16575).
   **This is exactly the reference-baseline F-09 defect.**
3. For BZ, no-match returns ENOENT — but the caller treats **any** nonzero as fatal (:5737-5738), i.e. Eric's
   ENOENT is *fatal*, whereas the reference-final semantics made ENOENT *benign* (free + return 0, no doorbell).
   Shared-code entanglement note: the same `load_pnvm` serves both families; if you port the reference-final
   ENOENT handling, keep the BZ empty-SKU contract in mind.
4. `if (err == ENXIO) return err;` at :2520-2521 returns **before** `iwx_pnvm_free` (:2523) — on device-gone the
   rawdata buffer stays allocated until the next `iwx_read_pnvm` (:2406-2407 frees it) or
   `iwx_free_pnvm_dma` in `iwx_stop_device` (:3762). Bounded, but inconsistent with the other exits.

**G's special-warning verdict: Eric's PNVM failure handling is NOT unambiguous.** `iwx_read_pnvm()` == 0 still has
three meanings (loaded / no-match / name-derive-failure); errno polarity is mixed (positive EINVAL vs negative
-EINVAL); and `load_pnvm`'s treatment of the two "nothing loaded" cases differs by family. This is precisely the
trap G documented (reference §8): the intermediate CS7 mistake interpreted `0` as "nothing loaded" — the same
wrong polarity is latent in any future edit of Eric's :2506-2508.

Additional observations on this function (new, minor):
- `uncompressFirmware(...)` return value not checked (:2430); the output buffer is sized 20× the compressed blob
  (:2428). [Plausible risk, low — shipped .pnvm blobs decompress well under 20×]
- `malloc(fw->pnvm_rawsize, 1, 1)` (:2429) — the port's malloc shim ignores flags (see finding E-21).

**Correct transfer within Eric's architecture** (mirrors reference-final, adapted to Eric's two extra 0-returning
paths): in `iwx_read_pnvm` track `int loaded = 0;` set it only when a SKU-matching section was handled; after the
walk `if (!loaded && err == 0) err = ENOENT;` (make the two name-derive `goto out` paths take the same ENOENT
outcome or return their own errno); normalize `-EINVAL` → `EINVAL`. In `iwx_load_pnvm`: `ENOENT` →
`iwx_pnvm_free` + `return 0` (no doorbell, no wait); other nonzero → propagate; `0` → doorbell + 2 s wait exactly
as the validated baseline. On the real AX211 target (SKU matches `iwlwifi-so-a0-gf-a0.pnvm`) the loaded path is
exercised and is behaviorally identical to the hardware-validated laobamac baseline — the fix only changes the
no-match failure mode.

### F-13 — firmware-load DMA leak on nic-lock failure — **PRESENT [Confirmed defect]**

Eric's `iwx_ctxt_info_gen3_init` (ItlIwx.cpp:1384-1506). After allocating `prph_scratch_dma` (:1394),
fw image sections (`iwx_init_fw_sec`, :1421), `prph_info_dma` (:1429) and `iml_dma` (:1465), and after writing
`CSR_CTXT_INFO_ADDR`/`CSR_IML_DATA_ADDR`/`CSR_IML_SIZE_ADDR` and `AUTO_FUNC_BOOT_ENA` (:1477-1484) and
`iwx_set_ltr` (:1486):

```c
1488	    if (!iwx_nic_lock(sc))
1489	        return EBUSY;
```

— an early return that bypasses `fail1`/`fail0` (:1499-1505), leaking **all of `iml_dma`, `prph_info_dma`,
`prph_scratch_dma`, and the fw image section DMAs** (`iwx_ctxt_info_free_fw_img` is only called on the
`fail0` path and at :1423). The init retry loop in `iwx_init` (:16561-16575) retries `iwx_init_hw` on first
failure, so each failed attempt leaks another set and clobbers the live softc DMA pointers. The reference fix is
at reference/…/ItlIwx.cpp:1255-1260 (`goto fail1;` with explanatory comment; `fail1` frees `iml_dma`,
`fail0` frees the fw image + `prph_info_dma` + `prph_scratch_dma`, return ENOMEM — reference:1266-1271).

**Transfer**: replace ItlIwx.cpp:1488-1489 with

```c
    if (!iwx_nic_lock(sc)) {
        err = EBUSY;          /* or ENOMEM to mirror reference-final */
        goto fail1;
    }
```

— nothing else in Eric's layout differs (the CSR writes preceding the lock are identical in both trees; freeing is
safe because `UREG_CPU_INIT_RUN`/`ROM_START` — the actual boot kick — has not been written when the lock fails).
Also note `err` is unassigned on that path today, so a bare `goto fail1` without setting `err` would return
garbage — set it explicitly.

---

## Part 2 — Independent data-path and concurrency audit (AX211-relevant regions)

### 2.1 TX path trace (macOS packet → firmware)

1. **Skywalk/DLIL output thread**: `AirportItlwm::outputStart` (AirportItlwmV2.cpp:848-884) /
   `outputPacket` (:905-913) → `enqueuePacket` (lockEnqueue into `if_snd`, :915-928) → `(*ifp->if_start)(ifp)`
   (:870/:910) = `iwx_start`.
2. **`iwx_start` (ItlIwx.cpp:16730-16745)**: if already in the main workloop gate → run `_iwx_start_task` inline;
   otherwise `iwx_add_task(sc, sc_nswq, &sc->start_task)` — comment: "NDRV/DLIL output callbacks must not wait on
   the controller command gate". **[Intentional behavior — correct deferral; no output-thread blocking on the gate.]**
3. **`_iwx_start_task` (:16648-16727)** runs under `runAction` (gate): guards (:16659-16664), drains
   `ic_mgtq` (:16679) then `if_snd` (:16693), `ieee80211_encap` (:16705), `iwx_tx` (:16716); on TX error releases
   the node ref and counts outputErrors (:16717-16721).
4. **`iwx_tx` (:8414-8743)**:
   - entry guards SHUTDOWN/HW_ERR/RFKILL → free+ENXIO (:8416-8419);
   - queue selection (AX211 = non-MLD): `tid = qos TID`, `qid = first_data_qid`; per-TID TVQM queue only when
     BA agreed and `sc_tid_data[tid].qid` valid (:8519-8533) — matches "iwl_mvm_tx_mpdu selects data TIDs
     independently of BA state" only on MLD; legacy keeps laobamac semantics. Mgmt frames ride `first_data_qid`
     with `IWX_MGMT_TID` (one ring for mgmt+data — the rejected D-6 reorder still applies, do not "fix");
   - ring-slot checks under AIRPORT_VTD (:8536-8552): `ring->queued >= ring->ring_count - 1` → **frame dropped
     (freed) with ENOBUFS** — [Intentional behavior, inherited; deferred D-6 in reference];
   - **A-MSDU aggregation (Eric-new)**: `iwx_tx_amsdu` (:8294-8411) pulls additional compatible frames from
     `if_snd` (dequeue at :8342, `lockPrepend` pushback at :8356/8362/8371/8382), builds one aggregate mbuf
     (`mbuf_allocpacket(MBUF_DONTWAIT, hdrlen+limit)` :8361), finalizes each subframe's checksums
     (`mbuf_outbound_finalize` :8367/:8376), sets the AMSDU QoS bit (:8400-8401), and rewrites addr3 for MLO
     (:8402-8408). All under the gate — queue manipulation is serialized. See findings E-04/E-05.
   - `iwx_tx_fill_cmd` (:8567) → rate/TX flags (F-01 site); software encryption for non-CCMP (:8596-8603);
   - gen3 TX command copy (header into cmd DMA, :8615-8626); header trimmed (:8641);
   - `bus_dmamap_packet` maps the payload (:8643) — with AIRPORT_VTD this **copies the mbuf into the arena bounce
     buffer** and returns up to `IWX_TFH_NUM_TBS-2` segments pointing into it (compat.cpp:351-378);
   - TFD fill (TB0/TB1 = cmd DMA, TB2+ = payload, :8659-8687), byte-count table (:8698),
     per-frame trace record into `sc_tx_trace[]` (:8700-8723) — 48-entry static ring, no allocation, no logging
     [Intentional diagnostic; cheap; keep];
   - kick: `ring->cur = (ring->cur + 1) % getTxQueueSize(); IWX_WRITE(HBUS_TARG_WRPTR, qid<<16|cur)` (:8725-8726);
     qfullmsk set at hi_mark (:8729-8732); 15 s per-queue TX timer armed (:8733-8736).
5. **Completion**: RX notif → `iwx_rx_tx_cmd` (:7239-7370, single-frame path) and `iwx_rx_tx_ba_notif`
   (:7120-7184, compressed BA) → `iwx_ampdu_txq_advance` (:7186-7214): validates the completion index with
   `itlTxCompletionValid` (include/HAL/ItlTx.hpp:50-56), frees mbufs + releases node refs via `iwx_txd_done`
   (:7085-7099, `ieee80211_release_node`), clears TFDs (`iwx_clear_tx_desc` :7066-7083), updates `sc_tx_timer`,
   wakes gate sleepers on `&ring->queued` (:7206), schedules the AWDL peer task when peer queues drain
   (:7207-7212), and `iwx_clear_oactive` (:7101-7117) clears qfullmsk below low_mark and re-runs if_start.

**Buffer ownership** is clean: mbuf → `data->m` (owned by slot) + node ref `data->in` (:8650-8651); freed exactly
once in `iwx_txd_done` on completion or `iwx_reset_tx_ring`/`iwx_free_tx_ring` on reset/teardown (node-ref caveat
in E-07); DMA "unmap" is implicit with VTD (bounce buffers are persistent per-slot arena allocations).

### 2.2 RX path trace (interrupt → macOS)

1. **Primary interrupt**: `intrFilter` (ItlIwx.cpp:19812-19818) writes `CSR_INT_MASK = 0` (masks the vector) and
   returns true → `iwx_intr` action is scheduled on the main workloop. No state touched at primary level. ✔
2. **`iwx_intr` (:18240-18387, MSI+ICT — the AX211 path)**: ICT walk (:18250-18276), ack
   `IWX_WRITE(CSR_INT, r1 | ~sc_intmask)` (:18287), ALIVE → repost all 512 RX descs (:18289-18298), RF_KILL →
   check + `iwx_schedule_recovery` + `goto out_ena` (restore interrupts) (:18301-18307), SW_ERR → `iwx_nic_error`
   dump + recovery + `goto out` (**interrupts stay masked** until recovery re-inits) (:18309-18334), HW_ERR same
   (:18336-18344), FH_TX chunk-done → `wakeupOn(&sc->sc_fw)` (:18347-18352), RX causes → ack FH/periodic +
   **`iwx_notif_intr`** (:18354-18378). `out_ena:` re-enables only when generation unchanged (:18382-18384).
   Ack ordering (mask-in-filter → read ICT → ack CSR → process → restore) matches the Linux/iwlwifi recipe.
   Reentrancy: the workloop serializes actions; the filter re-masks, so level-triggered storms are throttled. ✔
3. **`iwx_notif_intr` (:18160-18237)**: reads the MQ write-back index (AX210+: first u16 of `rxq.stat`,
   :18170-18174), loops per RB: BZ completion-descriptor handling is dead for AX211 (rbid = `sc->rxq.cur`,
   :18186); per-packet `iwx_rx_pkt`; generation/SHUTDOWN/HW_ERR checks between packets (:18214-18218) and a
   re-entry cookie check (:18219-18222, defensive — workloop serializes anyway); credits published with
   `__sync_synchronize()` then `IWX_WRITE(RFH_Q0_FRBDCB_WIDX_TRG, last & ~7)` for non-BZ (:18176-18184) —
   the AX211 register, 8-buffer granularity; frames handed up via `if_input` (workloop-gated `_if_input`,
   _mbuf.cpp:62). BZ-only "return credits every 32 packets" (:18224-18231) is dead on AX211.
4. **`iwx_rx_pkt` (:17469-18157)**: VTD bounce-buffer copy-back — copies only `iwx_rx_buf_used()` bytes and
   **zero-fills the remainder** (`bus_dmamap_read_used`, :17483-17494 + :17447-17465) — [Intentional behavior,
   reference D-2]; loops packets in the buffer (AX210+: exactly one per RB, :18151-18152); first data MPDU takes
   the mbuf off the ring and re-arms the slot via `iwx_rx_addbuf` (:17540-17547); **mbuf exhaustion →
   `inputErrors++` + `break`** (:17542-17545) — the RB is not re-posted but the transfer descriptor still points
   at the old (same) buffer, so the ring survives; packet loss only. [Intentional-ish; acceptable]
   Per-RB mbuf allocation is `getController()->allocatePacket(size)` (:5887) — no m_getcl/m_gethdr; the OpenBSD
   mbuf path is commented out (:5889-5910).
   Command responses are copied into `sc_cmd_resp_pkt[idx]` under the `CMD_PENDING`-slot check (:17730-17757);
   `iwx_cmd_done` is invoked for any *handled* driver-originated response (`handled && !(qid & 0x80)`,
   :18145-18147) — see §AWDL.
5. **`iwx_rx_mpdu_mq` (:6733-7033)**: desc-size check per family (:6745-6753); CRC/overrun drop (:6798-6803);
   length sanity incl. monitor mode (:6805-6832); RADA trailer trim (:6840-6852); PAD memmove (:6855-6887);
   RSSI/band/channel for AX210 v3 desc (:6952-6982); AWDL diagnostic counters (cheap increments behind
   `sc_awdl_listen_active`/`ic_awdl_addr_gen`, :6761-6796, :6993-7023); reorder via `iwx_rx_reorder`
   (:7025-7028, iwlwifi-faithful incl. oldsn workaround :6372-6420 and release-on-BAR); else
   `iwx_rx_frame` → `ieee80211_input` → gate-serialized `_if_input` → Skywalk. Error paths free the mbuf —
   no leaks found in the RX error paths (every early return frees `m` or hands it to `ml` purged at :18198/:18216).

### 2.3 DMA management (ItlDma + rings)

- **ItlDmaArena** (itl80211/ItlDma.cpp/.hpp): 32 blocks × 1 MiB (256 pages × 4 KiB) = **32 MiB pool**,
  `IOBufferMemoryDescriptor` + `IODMACommand` per block, `IOMapper` (device/system) or direct
  (ItlDma.cpp:25-96); page-granular `allocate`/`deallocate` under an `IOSimpleLock` (:98-167) with
  high-water/failure counters; `deferRecycling()` marks freed pages `Retired` instead of releasing (:158-160) —
  used after a firmware rejected a queue while DMA may still be in flight (`iwx_tvqm_enable_txq` fail path,
  ItlIwx.cpp:4150-4153); `reclaim()` only when **bus mastering is off** (ItlDma.cpp:176-196) — called from
  `iwx_stop_device` after `setBusMasterEnable(false)` (ItlIwx.cpp:3727, 3771). This is the F-13-lesson era
  design done right: no DMA memory is *freed* while the device can master.
- **`iwx_dma_contig_alloc`** → `allocDmaMemory2` (ItlIwx.cpp:2745-2811): VTD path is arena-backed (alignment ≤
  page granularity is trivially satisfied; the 256-byte TX-desc alignment request is page-granular in practice);
  non-VTD path is `IOBufferMemoryDescriptor` + `IODMACommand`. `iwx_dma_contig_free` (:2813-2837) is idempotent
  against zeroed handles — so `goto fail1` with an unallocated `iml_dma` is safe (relevant to F-13 transfer).
- **Per-queue DMAs**: TX ring = desc_dma (256-B aligned) + bc_tbl + cmd_dma + per-slot `bus_dmamap_create`
  (ItlIwx.cpp:3042-3095); under VTD each slot map allocates a persistent bounce buffer from the arena
  (compat.cpp:199-225 — `MAX(size, 4096)` each). TVQM rings are `new iwx_tx_ring()` per fw-queue
  (:4012-4021), installed by reset+free+memcpy of the old slot then `delete` (:4141-4146) — allocation
  failure path frees everything (`fail:` :4149-4162). RX ring = free_desc/stat/used_desc + 512 maps+bufs
  (:2860-2924). Global (non-queue) DMAs: `ctxt_info_dma` (alloc at attach :20063-20065 region, freed only in
  `detach` :382), `ict_dma`, `prph_info/prph_scratch/iml/pnvm` (freed in `iwx_stop_device` :3757-3762),
  `fw_mon`. Pairing verified: every `iwx_dma_contig_alloc` has a matching free on either the stop or detach
  path — **except** the F-13 path (Part 1) and the late-start-failure path (E-16).
- **Teardown completeness**: `iwx_stop_device` resets all TX rings + RX ring after bus-master-off (:3726-3731);
  `detach` frees all rings, ICT, ctxt_info, fw image, paging, prph, iml, pnvm, fw_mon, then arena `reclaim()`
  (:378-400). TVQM queues are **not** returned to the firmware on BA teardown (`iwx_ampdu_tx_stop` :5401-5416
  only invalidates `sc_tid_data[tid].qid`) — reference deferred item **D-4 still deferred in Eric**
  [Intentional/deferred; wrong command risks fw crash — do not port blindly].
- **F-13 lesson comparison**: stop-path DMA discipline is sound (epoch + bus-master-off + reclaim); the remaining
  leak is exactly the init-path F-13 defect (Part 1).

### 2.4 Command path

- Entry: `iwx_send_cmd` (ItlIwx.cpp:7758-7778) re-enters via `getMainCommandGate()->runAction` when not in the
  gate; WCL diagnostics on error (:7770-7776).
- Serialization: **single command ring (queue 0, 128 slots gen3)** + the command gate; ring-full / slot-pending →
  ENOSPC (:7819-7832); WANT_RESP slots allocate `sc_cmd_resp_pkt[idx]` (malloc M_NOWAIT|M_ZERO, :7842-7858,
  freed on error at :8001-8005, handed to caller on success :7994-7998); oversized commands (>cmd data area) use
  an mbuf + bounce map (:7877-7907) freed in `iwx_cmd_done` (:8101-8107).
- Wait: sync commands sleep on `commandSleep(desc, deadline 1 s, THREAD_UNINT)` (:7970-7981); `commandSleep`
  **releases the gate while sleeping**, so the completion context (interrupt action on the same workloop) can
  acquire it — **no lock-inversion deadlock**. Wake: `iwx_cmd_done` (:8086-8116) clears `CMD_PENDING`, frees the
  oversized-cmd mbuf, `commandWakeup(&ring->desc[idx])`, decrements `ring->queued`.
- Notification waits: `iwx_wait_notification` (:5568-5582) — same gate-sleep pattern on `sc_init_complete` /
  `sc_uc.uc_intr`, woken from `iwx_rx_pkt` (:17762, :17770, :17656) — deadlock-free for the same reason.
- Timeout/unresponsive firmware: a sync command times out after a **hard-coded 1 s** (:7971-7972) and returns
  EWOULDBLOCK — **no recovery is scheduled from the command path itself**; recovery relies on SW_ERR/HW_ERR
  interrupts, RF-kill, watchdog TX timers (15 s, :16924-16951) or state-machine errors (`iwx_newstate_task`
  :15366-15378, with the LAR-deferral exception at :15376). [Plausible risk — a hung-but-silent firmware with no
  pending TX waits for user action; inherited from the laobamac lineage, not a regression.]
- Generational safety: `generation` captured at entry (:7796), re-checked after every sleep (:7989-7992);
  VTD adds `dmaEpoch` checks (:7797-7798, :7810, :7983-7987). `iwx_reset_tx_ring` for the cmd queue frees any
  stranded `sc_cmd_resp_pkt[i]` and wakes every slot (:3110-3117) — waiters observe generation change and bail.
- `iwx_free_resp` / response lifetime: `resp_pkt` transferred to the caller and freed via `iwx_free_resp`
  (:8078-8084) — audited call sites (`iwx_flush_sta_tids` :8816, `iwx_send_cmd_status` :8045/:8055/:8061,
  `iwx_tvqm_enable_txq` :4147/:4154, nvm :5563) all pair correctly.

### 2.5 Workloops / gates / event sources — full inventory

**Workloops:**
| # | Workloop | Created | Residents |
|---|---|---|---|
| 1 | `IO80211WorkQueue *_fWorkloop` (main) | `IOPCIEDeviceWrapper::start` (IOPCIEDeviceWrapper.cpp:120) | command gate `_fCommandGate` (V2.cpp:356-363); interrupt `sc->sc_ih` (ItlIwx.cpp:19915-19923); watchdog `watchdogTimer` (V2.cpp:423-440 — `fWatchdogWorkLoop = _fWorkloop` + retain); `scanSource` (V2.cpp:441-451); all CTimeout timers (CTimeout.cpp:52-57 via `_fCommandGate->runAction`, timeout.c:48-69); WCL `joinTimer`/`wclEapolSource` (WCL.cpp:284-291); AWDL `fAWTimer/fPeerCacheTimer/fUmiAckTimer/fListenTimer/fTxTimer` (AirportItlwmAWDLInterface.cpp:2522-2562, comment at :2518-2519) |
| 2 | `itlwm`/`AirportItlwm` (V1/non-Airport) `fWatchdogWorkLoop = IOWorkLoop::workLoop()` — **separate** | itlwm.cpp:355, AirportItlwm.cpp:410 | watchdog only — see E-12 (non-shipping variants) |

**Command gates:** exactly one per driver: `_fCommandGate` = `IOCommandGate::commandGate(this, tsleepHandler)`
(V2.cpp:356; itlwm.cpp:320; AirportItlwm.cpp:374). `ItlHalService` retains its own references
(ItlHalService.cpp:31-34, released :91-98) — no double-release against V2.releaseAll's releases (V2.cpp:73-75, 84-85).

**Threads/contexts and what they touch:**
| Context | Runs | State touched | Protection |
|---|---|---|---|
| Main-workloop action (interrupt) | `iwx_intr`/`iwx_intr_msix` | ICT, CSR, `iwx_notif_intr` → RX/TX-completion state machine, cmd_done | workloop gate |
| Main-workloop timer actions | watchdogAction, scanSource/fakeScanDone, CTimeout callbacks, WCL join/eapol, AWDL timers | MLME/BA/timeline state | workloop gate |
| Gate `runAction` callers | `_iwx_start_task`, tasks (`newstate/ba/mcc/init/setkey/scan/sae/mld_link/start`), `iwx_send_cmd` re-entry, `iwx_stop`/`iwx_stop_device`/`iwx_init_task` re-entry, tsleepHandler | all HAL state | command gate |
| taskq kernel threads (`systq` 1 thread, `sc_nswq` 1 thread — ItlIwx.cpp:20098-20099, _task.cpp:49-56) | task bodies — every HAL task **re-enters the gate itself** (`iwx_init_task` :20322-20332, `iwx_newstate_task` :15247-15254, `iwx_ba_task` :5237-5244, …) | HAL state | command gate after re-entry; task queue itself under `IORecursiveLock` (_task.cpp:66-89) |
| DLIL/output thread | `outputStart`/`outputPacket` → `iwx_start` → defers via `iwx_add_task` (ItlIwx.cpp:16740-16741); AWDL `outputAWDL`/`outputLowLatency` wrap in `runAction` (AWDLInterface.cpp:442-465) | if_snd enqueue only outside gate | lockEnqueue + gate deferral |
| PM thread_call | `handleSetPowerStateOff/On` → `runAction` → `setPowerStateOff/On` (V2.cpp:1592-1626) | adapter enable/disable | command gate |
| Primary interrupt (filter) | `intrFilter` | `CSR_INT_MASK` only | safe (single register write) |

**Cross-context shared state WITHOUT protection**: none found on the AX211 path after this pass. The nearest
candidates and why they're OK: `sc_rx_service_cookie` (single workloop mutator), `sc_diagnostic_sequence`
(atomics, ItlIwx.cpp:234-258), `ItlDmaArena::blocks` (IOSimpleLock), `qfullmsk`/ring counters (gate-only),
`wclStopping` (bool, benign). [Unverified hypothesis → resolved: none outstanding.]

### 2.6 Timers / tasks — re-arm and cancel-on-stop analysis (F-10 lesson, HAL side)

- **Airport V2 watchdog is ON the main workloop** (`fWatchdogWorkLoop = _fWorkloop`, V2.cpp:423-431) — the F-10
  *invariant* (serialize watchdog with MLME) **is satisfied in the shipping Airport product**. Re-arm is via the
  member pointer (`watchdogTimer->setTimeoutMS`, V2.cpp:127) rather than the canonical `timer->` sender, and
  `watchdogAction` lacks an `fHalService` NULL guard (:122-128) — both are robustness nits only, because
  `releaseAll` cancels the watchdog (V2.cpp:29-38) **before** `fHalService->release()` (:66-69) and
  `removeEventSource` drains in-flight callbacks under the workloop lock. [Plausible risk, low — recommend
  porting the reference's sender-arg re-arm + NULL guard as hygiene.]
- **HAL tasks**: `iwx_stop` cancels `init_task`, `sc_awdl_peer_task`, `newstate_task`, `start_task`,
  `mld_link_task`, `sc_scan_task`, `sc_sae_join_task`, `ba_task`, `mac_ctxt_task`, `chan_ctxt_task`, `mcc_task`
  (ItlIwx.cpp:16789-16818) **before** `iwx_stop_device` frees DMAs; running (non-queued) tasks re-enter the gate
  and observe the bumped generation + SHUTDOWN and bail (checked inside each task, e.g. :15266, :15321-15326,
  :5256-5261). `task_del` only dequeues — safe because taskq threads re-acquire the gate that `iwx_stop` holds.
  ✔
- **CTimeout/net80211 timers**: rx BA `session_timer`/`reorder_timer` are cancelled **and freed** under the gate in
  `iwx_clear_reorder_buffer` (:4576-4593), called from `iwx_stop` (:16894-16897) and from the rx-BA expiry paths
  (:10954, :5050). `ic_bgscan_timeout` deleted inside the gated detach prologue (:351); `sc_mld_tpt_timer`
  deleted+freed in `detach` (:370-371). net80211 node timers are torn down by `ieee80211_ifdetach` (:401)
  **before** the command gate is removed (V2.releaseAll :70-86) — the dependency direction (timers → gate) is
  respected. ✔
- **AWDL timers** (`fAWTimer` etc.): cancelled/removed in `destroyAWDLInterface` → `AirportItlwm::stop` runs it
  **before** super::stop/releaseAll (V2.cpp:583). WCL `joinTimer`/`wclEapolSource`/`scanSource` cancelled in
  `stopWCL` (WCL.cpp:314-327), which `stop()` invokes first (:587). ✔
- **PM thread_calls** freed in `unregistPM` (V2.cpp:1544-1554) at the end of `releaseAll` — after the gate is
  gone; but the thread_call bodies take the gate via `getCommandGate()->runAction` and the controller is retained
  across the call (V2.cpp:1565-1567/1573-1575) — a PM callback racing kext unload is held off by the retain.
  [Plausible risk, low.]

### 2.7 Interrupt handling (AX211: `iwx_intr` + ICT)

Covered in §2.2. Additional points:
- Masking happens in the **filter at primary level** (ItlIwx.cpp:19815-19816) before the action is deferred —
  no interrupt-storm window; restore happens once per action at `out_ena` with a generation check (:18382-18384).
- SW_ERR/HW_ERR paths deliberately leave interrupts masked (`goto out`) until recovery reinitializes the device
  (:18332, :18343) — correct for a dead firmware.
- `iwx_notif_intr` early-outs on SHUTDOWN/HW_ERR (:18162-18163) and on generation change mid-loop
  (:18214-18218) — prevents touching rings being reset by `iwx_stop_device` on the same workloop.
- Shared with command path? Yes — command completions ride the same RX ring/vector; the gate serializes them;
  sleeping command senders release the gate (see §2.4). No deadlock found.
- MSI-X (`iwx_intr_msix` :18389-18484) is BE-only (Subagent A §1.4); its per-vector automask
  (:18482) and error handling share `iwx_notif_intr`/`iwx_schedule_recovery` — entanglement is limited to those
  shared callees, which are family-guarded. ✔

### 2.8 Recovery

- Triggers: RF_KILL (:18304), SW_ERR (:18330), HW_ERR (:18340), CT-kill notif (:17680-17691), watchdog TX
  timeout (:16946-16947), state-machine errors (:15377), BZ RX bad rbid (:18197 — dead for AX211),
  `iwx_activate(DVACT_WAKEUP)` when hw not ready (:20434-20437).
- `iwx_schedule_recovery` (:293-301): records a diagnostic + `task_add(systq, &sc->init_task)` — enqueue-only,
  callable from any context. `iwx_init_task` (:20315-20390): re-enters the gate with a generation re-check
  (:20322-20332); rate-limits HW_ERR restarts (≥3 within 60 s or `sc_hw_err_final` → fatal, :20344-20355);
  then `iwx_stop` (full teardown incl. tasks, rings reset in stop_device) and `iwx_init` if IFF_UP and not fatal.
- Races with join/scan: `iwx_stop` cancels scan/sae/newstate tasks and resets scan state under the gate
  (:16789-16814); a concurrent `newstate_task` sleeping in a command observes the generation bump and exits
  (:15321-15326); WCL is notified `IEEE80211_EVT_DRIVER_STOPPED` on failed re-init (:20377-20382).
  The init retry inside `iwx_init` (:16561-16575) bumps generation and re-runs once. **No unprotected recovery
  race found.** ✔

### 2.9 Power

- Airport V2: `setPowerState` → thread_call → `runAction` → `setPowerStateOff` → `disableAdapter`
  (V2.cpp:1647-1653): **watchdog cancelled first** (:1486-1487) then `fHalService->disable` → `ItlIwx::disable`
  (ItlIwx.cpp:464-475) → `iwx_activate(DVACT_QUIESCE)` → `iwx_stop` (gated). Wake: `setPowerStateOn` →
  `enableAdapter` (:1655-1660) → `ItlIwx::enable` (:450-462) → `DVACT_RESUME` + `DVACT_WAKEUP` (hw-ready check,
  recovery if not). Ordering vs interface teardown: sleep quiesces the HAL but leaves the Skywalk interface
  attached — correct for S3/S5.
- WoW: `setWakeOnMagicPacket` records the flag only (V2.cpp:1586-1590); `magicPacketSupported` from PMCAP
  (:1528-1531). No WoW firmware programming — device is stopped (rfkill-only interrupt left on,
  ItlIwx.cpp:3753-3755). [Intentional minimal PM]
- `itlwm/pm.cpp` (non-Airport variant): `setPowerStateOff/On` only acknowledge the policy maker
  (pm.cpp:129-139) — **no HAL interaction at all** on sleep. Weak, but this variant is not the shipping
  Airport product. [Plausible risk if the legacy itlwm kext is ever shipped]

### 2.10 Memory / allocation families

- Custom `malloc`/`free` shim → `IOMalloc` with an 8-byte size header + bzero; **flags (M_NOWAIT etc.) are
  ignored** (itl80211/openbsd/sys/_malloc.h:27-49). All "M_NOWAIT" allocations (e.g. cmd resp buffers
  ItlIwx.cpp:7849, pnvm rawdata :2429, mcast cmd :524) are actually potentially-blocking IOMallocs on gate
  threads. [Plausible risk — inherited; acceptable in thread context, would be a bug if ever called from a
  true interrupt filter; today only `intrFilter` runs at primary level and allocates nothing.]
- mbufs: RX `allocatePacket` per refill (:5887); TX A-MSDU `mbuf_allocpacket(MBUF_DONTWAIT)` per aggregate
  (:8361); oversized commands mbuf_allocpacket (:7887). No per-packet kernel heap churn outside the arena.
- Persistent: DMA arena blocks (32 MiB), ring descs/cmd/bc tables, per-slot bounce buffers (≈4 KiB ×
  (128 cmd + 256 mgmt + 256×N TVQM + 512 RX) — bounded, ~1 MB per TX queue), firmware sections, IML, PNVM.
- `new`/`delete`: TVQM `iwx_tx_ring` per queue (:4012/:4145/:4160), CTimeout objects, taskq structs (IOMalloc),
  WCL/AWDL interface objects. No leaks found in these paths (fail paths delete the scratch ring).
- `iwx_record_diagnostic`/`iwx_publish_diagnostics` (:228-290): fixed 32-slot array + registry publish on
  workloop — no allocation per event. ✔

### 2.11 Teardown order trace (unload)

`AirportItlwm::stop` (V2.cpp:578-597) → `destroyAWDLInterface` (:583, AWDL timers removed) →
`fNetIf->stopWCL` (:587 → WCL.cpp:303-341: gated stop, join/eapol timers removed, **scanSource cancelled**
:326-327) → `super::stop` → `disableAdapter` (:590 — watchdog cancel + HAL disable → iwx_stop) →
`fHalService->detach` (:592 → ItlIwx::detach ItlIwx.cpp:339-407):
  1. gated prologue: dmaDetaching, dmaEpoch++, IFF_UP/RUNNING cleared, state=INIT, bgscan timeout deleted,
     SHUTDOWN, generation++, **bus master off**, interrupt source disabled, all TX rings reset (:343-361);
  2. outside gate: SHUTDOWN, generation++ (second bump — benign sloppiness, :365-366), task_del mcc,
     setkey-queue reset, tpt timer freed, `releaseAll` (**interrupt event source removed from workloop**,
     :373-376 + :409-430), `taskq_destroy(systq)` and `taskq_destroy(sc_nswq)` (drain running tasks,
     _task.cpp:228-264), all TX rings freed, RX ring freed, ICT/ctxt_info/fw-img/paging/prph/iml/pnvm/fw_mon
     freed, arena reclaim (:378-400), `ieee80211_ifdetach` (:401 — remaining net80211 timers; command gate still
     alive for their `timeout_del` runActions), `releaseAll` again (no-op).
→ back in V2.stop: `ether_ifdetach`, `detachInterface`, `fNetIf` released → `releaseAll()` (V2.cpp:27-88):
watchdog removed from (aliased) main workloop; WCL pipes/reporters stopped; **`fHalService->release()`** (ItlIwx
object freed; ItlHalService::free destroys the DMA arena, releases its own workloop/gate refs,
ItlHalService.cpp:81-111); command gate removed from workloop; **scanSource removed** (:77-83);
`_fWorkloop` released; `unregistPM`.

**Verdict**: the ordering is correct in the normal path — timers are cancelled before what they dereference
(AWDL → stopWCL → watchdog → gate/workloop), interrupt source removed before rings are freed, bus master off
before ring reset (VTD), taskqs drained before ring free, net80211 ifdetach before gate removal. Two residuals:
(a) scanSource is *formally* removed after `fHalService->release()` (V2.cpp:66-69 vs :77-83) — reversed vs the
reference-final F-10 ordering, but defanged because `stopWCL` already cancelled its timeout at WCL.cpp:326-327
and nothing re-arms it during teardown [Plausible risk, low; reorder for hygiene];
(b) **late-start failure paths** (V2.cpp:453-522: `fNetIf` new/init/attach, `attachInterface`,
`IONetworkController::attachInterface`, registration-info, `fNetIf->start`) call `super::stop` + `releaseAll`
**without `fHalService->detach`** — unlike the earlier failure paths (:423-447) which do detach. The interrupt
event source is still installed on `_fWorkloop` and the HAL taskqs/rings are alive when the workloop is released
and `fHalService->release()` runs. [Plausible risk — leak/dangling on failure paths only; add
`fHalService->detach(pciNub)` (guarded) to those paths.]

### 2.12 AWDL low-latency command mechanism (Eric-new commit analysis)

- **What it is**: `IWX_LOW_LATENCY_CMD` (MAC_CONF_GROUP, opcode 0x03) with `struct iwx_mac_low_latency_cmd`
  (if_iwxmld.h:145-151) — a per-MAC low-latency RX/TX toggle, an iwlmld-era command.
- **Who sends it**: `iwx_awdl_update_low_latency` (ItlIwx.cpp:11243-11268) — guarded by
  `if (!sc->sc_use_mld_api || !sc->sc_listener_up) return 0;` (:11245). **Therefore it is BE200/BE201
  (MLD) only; it is dead code on the AX211 path.** The follow-on `IWX_MAC_PM_POWER_TABLE` in the same function
  (P2P low-latency timeouts, :11258-11267) is under the same guard. `iwx_awdl_set_low_latency` (:11271-11285)
  adds rollback on error; `iwx_stop` clears `sc_awdl_low_latency` (:16870) under the gate.
- **What the "complete AWDL low-latency commands" fix does**: the command is sent synchronously
  (`iwx_send_cmd_pdu(..., flags 0, ...)` :11251-11252 → `async == 0` → `CMD_WAITING` set and the caller sleeps,
  ItlIwx.cpp:7963-7981). The firmware's reply is a driver-originated response (qid bit7 clear) with code
  `WIDE_ID(MAC_CONF_GROUP, LOW_LATENCY_CMD)`; the fix added it to the response-handling case list at **:17719**
  so the reply lands in the `handled = 1` set (initialized :17497) and `iwx_cmd_done(sc, qid, idx, code)` runs
  at **:18145-18147**, clearing `CMD_PENDING` and waking the sleeper. Before the fix the reply fell into
  `default: handled = 0` (:18123-18129, with an "unhandled firmware response" log), the waiter burned the full
  1 s deadline, and `iwx_awdl_set_low_latency` saw EWOULDBLOCK and rolled back — the AWDL peer's low-latency
  mode could never be enabled.
- **Races in the completion handling**: none found. The reply path checks
  `qid == IWX_DQA_CMD_QUEUE && idx < ring_count && (data[idx].flags & CMD_PENDING) && sc_cmd_resp_pkt[idx]`
  (:17733-17737) — for this command `sc_cmd_resp_pkt[idx]` is NULL (no WANT_RESP), so the copy is skipped and
  only `iwx_cmd_done` matters; `iwx_cmd_done` re-checks the `CMD_PENDING` flag (:8097-8099) so a stale/duplicate
  reply is a no-op; the slot cannot be reused by another command while the waiter owns it (`CMD_PENDING |
  CMD_WAITING` block at :7830-7832). All under the command gate. The rollback path re-sends the previous value
  under the same gate. **Sound.**
- **AWDL low-latency data path** (for completeness): LLW output `outputLowLatency` wraps
  `enqueueLowLatencyData` + `flushLowLatencyData` in `_fCommandGate->runAction`
  (AirportItlwmAWDLInterface.cpp:449-466); the fixed-size `fLowLatencyDataQ` is otherwise only touched by
  workloop timers/handlers — serialized. ✔
- **AX211 relevance**: none at runtime (guard at :11245). The only AX211-reachable AWDL "low-latency" surface is
  the legacy-listener/P2P queue machinery (Subagent A §8 "must-keep"), not this command.

---

## Part 2 — Findings register (numbered, labeled)

- **E-01 [Confirmed defect] F-01 present**: unconditional per-frame `XYLog` in `iwx_tx_fill_cmd`,
  ItlIwx.cpp:8200 (see Part 1). Runs under the command gate for every transmitted frame.
- **E-02 [Confirmed defect] F-07 present**: `>` should be `>=` in `iwx_rs_pretty_ant` (:753) and
  `iwx_rs_pretty_bw` (:769); OOB static-table read from TLC rate notifications (see Part 1).
- **E-03 [Confirmed defect] F-09 present (AX211 no-match path)**: `iwx_read_pnvm` returns 0 with nothing loaded
  (non-BZ) (:2484-2486, :2410-2413) → `iwx_load_pnvm` doorbells + 2 s wait + spurious failure (:2506-2526);
  3-meaning return value + mixed errno polarity (G warning applies). Loaded path OK on real hardware (see Part 1).
- **E-04 [Confirmed defect] F-13 present**: `iwx_ctxt_info_gen3_init` early `return EBUSY` on nic-lock failure
  leaks iml/prph_info/prph_scratch (+ fw image) DMAs, ItlIwx.cpp:1488-1489 (see Part 1).
- **E-05 [Confirmed defect — BE-live, AX211-latent] Uninitialized `ni_mld_addr` read in A-MSDU builder**:
  `IEEE80211_ADDR_COPY(qwh->i_addr3, ni->ni_mld_addr)` (ItlIwx.cpp:8404-8405) under
  `if (ic->ic_wcl_peer_is_mlo)`. `ni_mld_addr` is *never written anywhere in the tree* (grep: only
  ieee80211_node.h:377 declares it; ieee80211_var.h:951/:1002 only read it; no assignment exists), while
  `ic_wcl_peer_is_mlo` is set from the raw WCL join request (`join.peerIsMlo`, WCL.hpp:710, WCL.cpp:1226) with
  no capability gating against `sc_use_mld_api`. On BE200 joining an MLO AP with A-MSDU negotiated, addr3 of
  every aggregate is built from zeroed/garbage memory. On AX211 the branch is dead unless macOS sets peerIsMlo
  for a legacy association (believed impossible — the driver advertises no MLO capability — but unverified).
  Fix: copy from `ic->ic_wcl_peer_mld_addr` (which *is* populated, WCL.cpp:1227-1230) or gate the branch on
  `sc_use_mld_api`.
- **E-06 [Demonstrated inefficiency] Registry lookups on the data hot paths**:
  (a) TX completion: `sc->sc_pcitag->getProperty("AirportItlwm-HotspotScanSSID")` for **every** single-frame TX
  response (ItlIwx.cpp:7282), plus a second lookup `getProperty("AirportItlwm-HotspotTx")` inside the EAPOL/DHCP
  check (:7296) and `setProperty` per matched frame (:7329);
  (b) RX: `getProperty("AirportItlwm-HotspotScanRequest")` for **every received MPDU**
  (`iwx_trace_hotspot_rx`, :6628, called at :6755). IOKit property lookups take the registry lock and are not
  free; unlike F-01 these are not kprintf spam, but they are unconditional per-packet work for a diagnostic
  facility. Recommend caching the enabled flag (invalidated on a user-space property change) or moving behind
  a boot-arg.
- **E-07 [Plausible risk — inherited] TX ring reset/free drop node references**: `iwx_reset_tx_ring`
  (:3103-3144) and `iwx_free_tx_ring` (:3146-3174) free `data->m` but never `ieee80211_release_node(data->in)`
  (normal completion does, :7097). On stop/recovery with frames in flight, node refs leak until the node table
  is wiped by the newstate(INIT) transition. Identical in the reference tree (reference:2763-2832) — inherited
  laobamac behavior, not a regression; bounded impact. Do not "fix" without verifying node lifetime.
- **E-08 [Plausible risk — inherited] `ring->cur` advances modulo `getTxQueueSize()` = 65536** (ItlIwx.cpp:579-583)
  **while TVQM rings are 256 deep** (256-agg freeze workaround comment :3946-3951) and `idx`/`tail`/`queued`
  operate modulo `ring_count` (:8546, :7201, :7189). The write to `HBUS_TARG_WRPTR` (:8726) therefore carries an
  un-wrapped 16-bit value; slot math stays consistent because `queued` bounds the tail–cur delta, and the
  hardware-validated laobamac lineage (reference:354, :6718, :7203 — identical) proves the fw/fh tolerate it
  (fetchers mask by cb_size). Flagged for awareness only — **do not change without hardware validation.**
- **E-09 [Intentional behavior — inherited, deferred] TX ring-full drops frames** (`iwx_tx` :8548-8551,
  ENOBUFS + mbuf_freem) and mgmt/data share `first_data_qid` — reference D-6, still deferred. Do not port the
  rejected reorder.
- **E-10 [Intentional behavior — inherited, deferred] TVQM queues not returned on BA teardown**
  (`iwx_ampdu_tx_stop` :5401-5416) — reference D-4, still deferred (needs fw-spec verification).
- **E-11 [Plausible risk — new, low] A-MSDU subframe finalize-then-requeue**: in `iwx_tx_amsdu`,
  `mbuf_outbound_finalize(next, ...)` runs (:8376-8377) before the append decision; on append failure the frame
  is `lockPrepend`ed back to `if_snd` (:8382) with computed checksums already stored. When later dequeued and
  transmitted normally, the checksum may be finalized a second time over already-checksummed data. macOS
  `mbuf_outbound_finalize` is documented destructive; double-finalize semantics unverified. Low frequency
  (requires a mid-aggregation memory failure).
- **E-12 [Confirmed defect — NON-shipping variants only] F-10 watchdog pattern persists in itlwm/V1**:
  `itlwm.cpp:355` creates a **separate** `fWatchdogWorkLoop`, `watchdogAction` (:406-411) calls `if_watchdog`
  with no gate and no fHalService guard and re-arms via the member pointer; same in
  AirportItlwm.cpp:410/:438-444 (V1). The Airport **V2** (shipping WCL product) correctly aliases the main
  workloop (V2.cpp:423). If the legacy itlwm kext target is ever revived for AX211, port the V2 layout.
- **E-13 [Plausible risk — low] `watchdogAction` (V2) lacks `fHalService` NULL guard and re-arms via member**
  (V2.cpp:122-128). Safe today due to releaseAll ordering (watchdog cancelled before fHalService->release(),
  V2.cpp:29-38 vs :66-69) and workloop serialization; port the reference hygiene (guard + `timer->` re-arm).
- **E-14 [Plausible risk — low] `releaseAll` removes `scanSource` after `fHalService->release()`**
  (V2.cpp:66-69 vs :77-83) — reversed vs reference-final F-10 ordering; defanged by stopWCL's earlier
  `scanSource->cancelTimeout()` (WCL.cpp:326-327, invoked from stop() at V2.cpp:587). Reorder for hygiene.
- **E-15 [Plausible risk] No recovery trigger on plain command timeout**: sync commands fail after 1 s
  (ItlIwx.cpp:7971-7978) without scheduling recovery; detection depends on SW_ERR/HW_ERR/RFKILL interrupts or
  the 15 s TX watchdog (:16924-16951). Inherited; consider scheduling recovery on N consecutive command
  timeouts (careful with the LAR-deferral case, :15372-15377).
- **E-16 [Plausible risk] Late-start failure paths skip `fHalService->detach`**: V2.cpp:453-522 (fNetIf
  create/init/attach, attachInterface x2, registration info, fNetIf->start) call `super::stop` + `releaseAll`
  while the HAL is attached (interrupt source on `_fWorkloop`, taskqs, rings, arena) — leak/dangling only on
  those failure paths (compare the detach-then-releaseAll discipline at V2.cpp:423-447).
- **E-17 [Plausible risk — inherited, low] malloc shim ignores M_NOWAIT** (_malloc.h:27-49): "atomic"
  allocations are IOMalloc and may block; all current call sites are thread context (gate/taskq/workloop).
  Keep in mind for any future primary-interrupt-path allocation.
- **E-18 [Plausible risk — low] PNVM ENXIO exit skips `iwx_pnvm_free`** (ItlIwx.cpp:2520-2521 vs :2523) —
  bounded leak window until next read_pnvm/stop_device.
- **E-19 [Plausible risk — low] `uncompressFirmware` result unchecked** in `iwx_read_pnvm` (:2428-2431) — a
  failed inflate would parse garbage; 20× buffer headroom makes it unlikely for shipped blobs.
- **E-20 [Confirmed defect — cosmetic/robustness] `iwx_stop_device`/`detach` double state mutation**:
  `detach` bumps `sc_generation` a second time outside the gate (ItlIwx.cpp:366 after :353) and re-sets SHUTDOWN
  (:365) — benign (teardown context) but sloppy; also `iwx_stop` re-reads `ic->ic_bss` into `in` before the
  newstate transition (:16771) — used only for soft-state reset, fine.
- **E-21 [Intentional behavior — keep] `ItlDmaArena` VTD bounce-buffer architecture**: full TX copy-in /
  RX copy-out per packet (compat.cpp:351-419) — architectural (reference §14 documented `AIRPORT_VTD` as
  intentional; the RX zero-fill is documented intentional, reference D-2). Per-packet `memcpy` cost is the
  price of VT-d safety; not a defect.
- **E-22 [Intentional behavior — keep] `sc_tx_trace[]` per-frame ring** (:8700-8723): 48-entry static struct
  array, no allocation/log — cheap forensics for firmware asserts; keep.
- **E-23 [Confirmed OK] Command/response handoff** has no use-after-free: response copy (:17755) strictly
  precedes `iwx_cmd_done` wakeup (:18145-18147) on the same gate; slots pinned by CMD_PENDING/CMD_WAITING
  (:7830-7832, :8097-8099); reset path frees stranded buffers and wakes waiters (:3110-3117).
- **E-24 [Confirmed OK] `iwx_stop_device` VTD ordering** (mask ints → disable RX DMA → apm stop → sw reset →
  **bus master off** → ring resets → … → reclaim, :3695-3772) prevents device writes into freed buffers —
  the modern counterpart of the F-13 lesson, correctly implemented.

---

## Concurrency model in five lines

1. One `IO80211WorkQueue` (main workloop) + one `IOCommandGate`; **every** HAL state mutation ultimately runs
   under that gate — interrupt action, timers (watchdog/scan/WCL/AWDL/CTimeout), task bodies (self re-entry),
   PM thread_calls, and command senders all serialize there.
2. Sleepers on the gate (`commandSleep`) release it, so interrupt-driven completions never deadlock against
   waiters; generation counters (`sc_generation`, `dmaEpoch`) invalidate stale waiters across stop/recovery.
3. Two single-thread taskqs (`systq`, `sc_nswq`) enqueue work from any context; task bodies re-enter the gate
   and re-check generation — cancel-then-stop ordering in `iwx_stop` is correct.
4. Primary interrupt context only masks `CSR_INT_MASK` (intrFilter, :19812-19818) — no state, no allocation.
5. Output (DLIL) threads never block on the gate: `iwx_start` defers to `start_task` (:16740-16741) and AWDL
   output wraps in `runAction` (AWDLInterface.cpp:442-465).

## Teardown-order verdict

Normal-path teardown (stop → AWDL destroy → stopWCL → disable/watchdog-cancel → HAL detach [gated quiesce,
bus-master-off, ring reset, interrupt removal, taskq drain, DMA free, ifdetach] → releaseAll [watchdog, WCL,
HAL release incl. DMA arena, gate, scanSource, workloop, PM]) is **in the correct order**; residuals:
scanSource removed after fHalService->release (E-14, mitigated), late-start failure paths skip HAL detach
(E-16), and the non-shipping itlwm/V1 watchdog remains on a separate workloop (E-12).

## Open questions

1. **E-05**: does macOS ever set `join.peerIsMlo` for a driver that has not advertised MLO/EHT capability
   (AX211 case)? If not, the uninitialized `ni_mld_addr` read is BE-only — but the copy should still be fixed
   to use `ic_wcl_peer_mld_addr` before the BE path is next used.
2. **E-08**: confirm (via a fw/fh spec or Linux comparison) that `HBUS_TARG_WRPTR` values > ring_size-1 are
   masked by the TFD fetcher's cb_size — believed yes (validated lineage), but worth one targeted experiment
   if TX stalls are ever observed on AX211.
3. **E-15**: policy decision — should N consecutive command timeouts schedule recovery? (Watchdog covers the
   TX-pending case only.)
4. `iwx_pnvm_handle_section` error retention across the SKU walk (E-03 table, last row): if a matching SKU's
   section fails to load and a *later* matching SKU succeeds, the earlier error is silently replaced — verify
   intended.
5. For Subagent C: the V2 late-start failure paths (E-16) and the releaseAll scanSource ordering (E-14) sit on
   the controller side of the boundary — coordinate any change there with the HAL-side detach contract.
