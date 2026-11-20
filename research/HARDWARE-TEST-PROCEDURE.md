# Hardware Test Procedure — AirportAX211 (Owner-Executable)

Non-destructive test plan for the MSI Modern 14 C12MO (Intel AX211,
8086:51f0). Execute per macOS installation. Requires: the matching kext
zip for the running macOS version, an admin account, and optionally a USB
installer as rollback. Expected duration: 45-60 minutes per OS.

⚠️ Before starting: back up your current EFI and note your current kext
versions. Do not replace your working AirportItlwm until the new build
passes section 1-3 in a temporary-load test.

## 0. Preparation (per OS)

1. Download the artifact for your OS from the passing CI run:
   `AirportItlwm-Sequoia-Debug-<sha>.zip` (macOS 15.8.2) or
   `AirportItlwm-Tahoe-Debug-<sha>.zip` (macOS 26.7.x).
2. Verify: `shasum -a 256 AirportItlwm-*.zip` matches the sidecar file.
3. Unzip; confirm `AirportItlwm.kext/Contents/MacOS/AirportItlwm` is
   x86_64: `lipo -info .../AirportItlwm`.
4. Load test WITHOUT touching your EFI:
   `sudo kmutil load -p ~/Downloads/AirportItlwm.kext` (System Settings →
   Privacy & Security → Allow, if prompted). If your existing Wi-Fi kext
   is loaded, boot a minimal config or use the EFI substitution in 0.5
   instead.
5. For the full test: place the kext in EFI/OC/Kexts (replacing the old
   AirportItlwm), run `ocvalidate`, enable the matching Darwin constraint
   (Sequoia kext → Darwin 24; Tahoe kext → Darwin 25), reboot.

## 1. Driver load and initialization

1.1. `log show --last boot | grep -iE "itlwm|AirportItlwm|iwx"` — expect:
     attach, firmware `iwlwifi-so-a0-gf-a0-68.ucode` load, PNVM parse
     ("Got IWL_UCODE_TLV_PNVM_SKU", SKU match), NVM read, alive.
1.2. `ioreg -r -c IOPCIEDeviceWrapper` — the personality matched your
     51f0 device; `kextstat | grep zxystd` shows the kext loaded from
     your path.
1.3. Menu bar shows Wi-Fi; en0 appears in `ifconfig`.

## 2. Firmware and PNVM verification

2.1. In the boot log, confirm PNVM: exactly ONE doorbell wait (no 2 s
     stall followed by an error), no "PNVM" failure lines.
2.2. Confirm HE enabled: log line with HE context / "Wi-Fi 6" in
     System Settings → Wi-Fi → details (or `wdutil info` shows HE caps).

## 3. Discovery and connection (per band)

For each: 2.4 GHz network, 5 GHz network, 6 GHz network (if available):
3.1. Scan lists the network with correct name/RSSI/band (System Settings
     and `wdutil info`).
3.2. Scan-result rates are populated: in the log, getSCAN_RESULT
     responses (or connect and check negotiated rate) — regression check
     for F-03.
3.3. Connect; obtain IP; browse. Note connect latency.
3.4. Wi-Fi 6 / 160 MHz: connect to a 160 MHz-capable AX AP on 5 GHz;
     `wdutil info` or the AP dashboard should show 160 MHz / HE MCS.

## 4. Security

4.1. WPA2-Personal: connect; wrong password is REJECTED (regression:
     F-08) and the correct password then works.
4.2. WPA3-SAE network: connect (this is the D-01 enablement — if it
     fails with the AP known-good, capture the log section).
4.3. WPA2/WPA3 transition network: connect.
4.4. PMF-required network (if available): connect.
4.5. Open/OWE network (if available): connect; OWE where the AP supports
     it.
4.6. WPA2-Enterprise (if available): connect via the macOS supplicant.

## 5. State and recovery

5.1. Saved-network reconnection: reboot; the network reconnects
     automatically.
5.2. Network switching: join network B, return to A — no stall, menu bar
     truthful throughout (regression: F-05 en0 state, F-11 link events).
5.3. Deauth recovery: use the AP's "disconnect client" (or walk out of
     range briefly): menu bar should drop, then recover (F-11) or
     reconnect via auto-join.
5.4. Repeated scanning: toggle Wi-Fi off/on 10 times; scan repeatedly —
     stable, no leak growth (see 8.2).
5.5. Scan cancellation: start a scan, immediately close the panel /
     connect to a known network — no stuck "scanning".
5.6. Incorrect password → settings show the password prompt (no silent
     retry loop past 3 attempts — F-12 regression check).

## 6. Throughput and stability

6.1. iperf3 to a LAN host: 5 minutes TCP, both directions. Expect
     AX211-class rates (hundreds of Mbit/s; record the numbers — do NOT
     compare against invented baselines).
6.2. Sleep/wake: close lid 30 s, wake — reconnects within a few seconds;
     repeat 5 times.
6.3. Overnight idle: leave connected 8+ hours; still connected and
     responsive in the morning.

## 7. macOS integration

7.1. System Settings → Wi-Fi reflects state truthfully (connected SSID,
     band, RSSI) across connect/disconnect/roam.
7.2. Menu bar icon matches state (F-11/F-05 regression).
7.3. Private MAC: enable "Private Wi-Fi Address" per network — reconnect
     works.
7.4. `wdutil info` shows sane operating info.

## 8. Resource stability (technical, optional but recommended)

8.1. `sudo log show --last 2h | grep -c "error:"` — compare early vs
     late boot.
8.2. Memory: run `sudo zprint | grep -i iox` style sampling, or observe
     kext memory in Activity Monitor across an hour of roaming — no
     monotonic growth (F-06 BA leak regression).
8.3. After 3+ days, check for firmware restarts in the log
     (iwx_nic_error / recovery lines) — some are environmental; frequent
     restarts are a defect.

## 9. Rollback

Replace the kext with your previous AirportItlwm build in EFI and reboot.
No persistent state is left behind (the kext stores nothing on disk).

## 10. Reporting

For any failure: capture `sudo log show --last boot --predicate
'process == "kernel" OR sender CONTAINS "itlwm"' > boot.log`, note the
section number, the AP model/band/security, and attach to the issue.
The Collect-EricWirelessDiagnostics.command script in scripts/ collects
the driver's diagnostic properties (including the hotspot trace records)
if deeper data is needed.
