# Migration Record — AirportAX211

Assignment §19-A record. Companion to PROVENANCE.md (source provenance).

## Workspace migration

- Original workspace: /home/z/my-project (the previous AirportItlwm_AX211
  project, HEAD 46027fe, branch main, remote developerasaad/AirportItlwm_AX211,
  clean working tree).
- Preservation: the complete project — .git history, all tracked and
  untracked content, research, scripts — was moved to
  /home/z/my-project/reference/ on 2026-11-20 using same-filesystem moves.
- Verification after the move: reference/.git HEAD unchanged (46027fe),
  `git status` identical to the pre-move state (clean), 8 commits, 233
  tracked files, `git fsck` clean, history readable. The reference is
  treated as immutable from that point on; no git operation has modified
  it since (read-only log/show/grep only).
- Sandbox infrastructure (upload mount, boot scripts, gateway config)
  stayed at the workspace root and is excluded from version control.

## Upstream source import

- Official source: https://github.com/Ersiter/Eric-AirportItlwm (read-only
  provider), branch be200-tahoe.
- Revision: cf0c5263eae5981e78fdb2ffb0b9406702bc7fc6 (2026-11-19,
  "fix(iwx): complete AWDL low-latency commands") — resolved via the GitHub
  API at import time.
- Import method: codeload ZIP archive for that exact commit (NO git clone,
  no upstream .git, no refs, no history). SHA-256:
  f47771f0ec30311c748673b7c65e47f1a3fd4a07e735e26c2901e1d638f9af65
  (19,670,166 bytes, 323 files). Extraction verified byte-identical to the
  archive with diff -r before committing.
- GPL-2.0 license, copyright notices, and the Intel firmware license were
  preserved in place.

## Independent repository

- Initialized: fresh `git init -b main` in /home/z/my-project (no upstream
  history imported; the upstream commit id is provenance metadata only).
- First commit: 84fb5d3 "Import Eric-AirportItlwm be200-tahoe source
  snapshot" — the untouched source plus only the housekeeping required by
  the assignment: .gitignore extensions (/reference/ exclusion, sandbox
  overlay, credential exclusions) and research/PROVENANCE.md.
- Destination remote: https://github.com/developerasaad/AirportAX211
  (branch main only; no other remotes; no force-pushes). The destination
  was empty at first push (verified) — no history was overwritten.
- Single-branch discipline: main only; all work is sequential reviewable
  commits (see REDUCTION-REPORT.md for the commit map).
- Credential handling: a restricted fine-grained GitHub token is stored
  only in the gitignored .ghtoken file and used via a GIT_ASKPASS helper;
  it is never printed, committed, or embedded in any remote URL. No
  secrets exist in the repository (verified per push).

## Commit map (development history)

84fb5d3 import → e73c117 CI workflow → 25e08eb audit records → 87c95e1
tier 1 → 67727ba tier 2 → a827dec IWM_MIN_DBM fix → 069c440 tier 3a →
a5d2800 tier 3b → 2151742 LE_READ_6 fix → 2637c6b tier 3b fallout →
4f09d44 fix batch (13 corrections + new fixes) → ad5fac4 review fixes →
9b4bcc1 tier 4+5 → (final docs commits).

## Reference exclusion verification

- .gitignore excludes /reference/ (plus the sandbox overlay and
  .ghtoken); every push was preceded by a staged-file check for
  reference/, token, and sandbox paths (all clean).
- The reference directory never entered the index, CI checkout, firmware
  generation input, or any artifact.
