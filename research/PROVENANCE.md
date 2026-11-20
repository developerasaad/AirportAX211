# Source Provenance — AirportAX211

This project is derived from the official Eric-AirportItlwm source. The
upstream snapshot was imported as a plain source archive, without importing
any upstream Git history, refs, branches, or remotes.

## Upstream snapshot

- Repository: https://github.com/Ersiter/Eric-AirportItlwm (read-only source provider)
- Branch: `be200-tahoe`
- Commit: `cf0c5263eae5981e78fdb2ffb0b9406702bc7fc6`
- Commit date: 2026-11-19T11:47:12Z
- Commit subject: `fix(iwx): complete AWDL low-latency commands`
- Archive URL (exact commit):
  https://codeload.github.com/Ersiter/Eric-AirportItlwm/zip/cf0c5263eae5981e78fdb2ffb0b9406702bc7fc6
- Archive SHA-256:
  `f47771f0ec30311c748673b7c65e47f1a3fd4a07e735e26c2901e1d638f9af65`
- Archive size: 19,670,166 bytes (323 files, 36 directories)
- Imported: 2026-11-20

## Import method

The archive was downloaded for the exact branch commit and extracted into the
workspace root. Extraction was verified byte-identical to the archive with
`diff -r` before the initial commit. The upstream commit identifier above is
provenance metadata only; it is not part of this repository's Git history.

## Licensing

Eric-AirportItlwm is GPL-2.0 licensed. The upstream `LICENSE`, firmware
license (`iwlwifi-firmware-license`), and copyright notices are preserved
in place. An independent Git history does not alter these obligations.

## Local reference

The previous AirportItlwm_AX211 implementation is preserved, unmodified and
read-only, under `reference/`. It is excluded from version control, CI
checkouts, and all build inputs (see `.gitignore`).
