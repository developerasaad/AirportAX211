#!/usr/bin/env python3
"""Tier 1 pbxproj surgery (definitive): keep only AirportItlwm-Sequoia,
AirportItlwm-Tahoe native targets + fw_gen aggregate.

Correct object model: parses one-line and multi-line objects, tracks a
true reference graph (own-ID excluded), deletes seeded objects, strips
stale references, then garbage-collects unreferenced objects to fixpoint.
"""
import re, sys

PATH = 'itlwm.xcodeproj/project.pbxproj'
lines = open(PATH).read().split('\n')

DELETE_TARGETS = {
    '024A07AB23FCBC3C009FBA6C': 'itlwm', '35CBE655251CB89700435CBC': 'Big Sur',
    '35CBE6BF251CB8BF00435CBC': 'Mojave', '35CBE72A251CB8CA00435CBC': 'High Sierra',
    'F897ECB6266EFF93005EE8F7': 'Monterey', 'F89B6BB825021C9C000F77FF': 'Catalina',
    'F8AE64F5285471560085B4CF': 'Ventura', 'F8B210A72A2EC2680043ECBD': 'Sonoma14.0',
    'F8D94C802B9ABFE20081A3C4': 'Sonoma14.4', 'B4971F289F589AF39F00A715': 'GoldenGate',
}
KEEP_PHASES = {'3B64F62353D14E5EA028E18D','AFFBDFD057C2402C908ECB89','1A48D424B8D644E591B45862',
    '9BBFC49C29994E6CA78F1847','F8D94C832B9ABFE20081A3C4','F8D94CA52B9ABFE20081A3C4',
    'F8D94CEF2B9ABFE20081A3C4','F8D94CF12B9ABFE20081A3C4','5066D63C25287F8E00EE6F38'}
DELETE_PHASES = {
    '024A07A723FCBC3C009FBA6C','024A07A823FCBC3C009FBA6C','024A07A923FCBC3C009FBA6C',
    '024A07AA23FCBC3C009FBA6C',
    '35CBE658251CB89700435CBC','35CBE670251CB89700435CBC','35CBE6B5251CB89700435CBC','35CBE6B6251CB89700435CBC',
    '35CBE6C2251CB8BF00435CBC','35CBE6DA251CB8BF00435CBC','35CBE71F251CB8BF00435CBC','35CBE720251CB8BF00435CBC',
    '35CBE72D251CB8CA00435CBC','35CBE745251CB8CA00435CBC','35CBE78A251CB8CA00435CBC','35CBE78B251CB8CA00435CBC',
    'F897ECB9266EFF93005EE8F7','F897ECCA266EFF93005EE8F7','F897ED12266EFF93005EE8F7','F897ED14266EFF93005EE8F7',
    'F89B6BB425021C9C000F77FF','F89B6BB525021C9C000F77FF','F89B6BB625021C9C000F77FF','F89B6BB725021C9C000F77FF',
    'F8AE64F8285471560085B4CF','F8AE6509285471560085B4CF','F8AE6552285471560085B4CF','F8AE6554285471560085B4CF',
    'F8B210AA2A2EC2680043ECBD','F8B210BB2A2EC2680043ECBD','F8B211042A2EC2680043ECBD','F8B211062A2EC2680043ECBD',
}
DELETE_DEPS = {'5066D63E252880A700EE6F38','5066D6462528814900EE6F38','5066D6422528814000EE6F38',
    '5066D640252880AD00EE6F38','F897ECB7266EFF93005EE8F7','5066D6442528814400EE6F38',
    'F8AE64F6285471560085B4CF','F8B210A82A2EC2680043ECBD'}
DELETE_PROXIES = {'5066D63D252880A700EE6F38','5066D6452528814900EE6F38','5066D6412528814000EE6F38',
    '5066D63F252880AD00EE6F38','F897ECB8266EFF93005EE8F7','5066D6432528814400EE6F38',
    'F8AE64F7285471560085B4CF','F8B210A92A2EC2680043ECBD'}
DELETE_CONFIG_LISTS = {'024A07B623FCBC3C009FBA6C','35CBE6B7251CB89700435CBC','35CBE721251CB8BF00435CBC',
    '35CBE78C251CB8CA00435CBC','F897ED15266EFF93005EE8F7','F89B6BC025021C9C000F77FF',
    'F8AE6555285471560085B4CF','F8B211072A2EC2680043ECBD','F8D94CF22B9ABFE20081A3C4',
    'E269A2FD523105737C8438A1'}
DELETE_PRODUCT_REFS = {'024A07AC23FCBC3C009FBA6C','35CBE6BA251CB89700435CBC','35CBE724251CB8BF00435CBC',
    '35CBE78F251CB8CA00435CBC','F897ED18266EFF93005EE8F7','F89B6BB925021C9C000F77FF',
    'F8AE6558285471560085B4CF','F8B2110A2A2EC2680043ECBD','F8D94CF52B9ABFE20081A3C4',
    '21499BD3D46506653E65AF42'}
STRIP_FROM_KEPT = {'F8D94C9B2B9ABFE20081A3C4','F8D94C932B9ABFE20081A3C4','F8D94C962B9ABFE20081A3C4',
    'F8D94CA02B9ABFE20081A3C4','F8D94CCE2B9ABFE20081A3C4'}
LEGACY_BASENAMES = {'itlwm.cpp','itlwm.hpp','ItlNetworkUserClient.cpp','ItlNetworkUserClient.hpp',
    'pm.cpp','pm.hpp','AirportItlwm.cpp','AirportItlwm.hpp','AirportItlwmInterface.cpp',
    'AirportItlwmInterface.hpp','AirportSTAIOCTL.cpp','AirportVirtualIOCTL.cpp','AirportAWDL.cpp',
    'itlwm.kext'}

HDR = re.compile(r'^\t\t([0-9A-F]{24}) /\* (.*?) \*/ = \{$')
ONE = re.compile(r'^\t\t([0-9A-F]{24}) /\* (.*?) \*/ = \{(.*?)\};$')
TOK = re.compile(r'\b([0-9A-F]{24})\b')

def parse(ls):
    objs = {}   # id -> list of (start, end_excl) ranges (handles duplicates)
    i = 0
    while i < len(ls):
        m = HDR.match(ls[i])
        if m:
            j = i + 1; d = 1
            while d > 0 and j < len(ls):
                d += ls[j].count('{') - ls[j].count('}')
                j += 1
            objs.setdefault(m.group(1), []).append((i, j))
            i = j
            continue
        m = ONE.match(ls[i])
        if m:
            objs.setdefault(m.group(1), []).append((i, i + 1))
        i += 1
    return objs

def refs_of(ls, objs):
    """id -> set of ids it references (own id excluded)"""
    out = {}
    for oid, ranges in objs.items():
        r = set()
        for (a, b) in ranges:
            for k in range(a, b):
                for m in TOK.finditer(ls[k]):
                    t = m.group(1)
                    if t != oid:
                        r.add(t)
        out[oid] = r
    return out

def body(ls, ranges):
    return '\n'.join('\n'.join(ls[a:b]) for a, b in ranges)

# ---------- Phase 1: seeds ----------
objs = parse(lines)
# config objects inside deleted lists
delete_configs = set()
for lid in DELETE_CONFIG_LISTS:
    for m in re.finditer(r'([0-9A-F]{24}) /\* \w+ \*/', body(lines, objs[lid])):
        delete_configs.add(m.group(1))
# buildfiles of deleted phases
def phase_bf(pid):
    out = set()
    for (a, b) in objs[pid]:
        for k in range(a, b):
            m = re.match(r'^\t\t\t\t([0-9A-F]{24}) /\* .* \*/,$', lines[k])
            if m: out.add(m.group(1))
    return out
keep_bf = set()
for pid in KEEP_PHASES:
    keep_bf |= phase_bf(pid)
keep_bf -= STRIP_FROM_KEPT
del_bf = set()
for pid in DELETE_PHASES:
    del_bf |= phase_bf(pid)
del_bf -= keep_bf
# legacy fileRefs: referenced only by doomed buildfiles OR by group children we will strip
fileref_by_path = {}
for oid, ranges in objs.items():
    bd = body(lines, ranges)
    if 'isa = PBXFileReference' in bd:
        pm = re.search(r'path = ([^;]+);', bd)
        if pm:
            base = pm.group(1).strip().strip('"').split('/')[-1]
            if base in LEGACY_BASENAMES:
                fileref_by_path.setdefault(base, set()).add(oid)
referenced_by_keep = set()  # ids referenced from kept objects (phases, kept buildfiles, targets, project, groups later)
keep_obj_ids = (KEEP_PHASES | set(DELETE_TARGETS) and KEEP_PHASES) | {'C2631DEBF2864F9B8272D88C','A6465A40B44EE5DC353B726B','5066D63825287F7900EE6F38','024A07A323FCBC3C009FBA6C'}
refmap = refs_of(lines, objs)
for oid in keep_obj_ids:
    referenced_by_keep |= refmap.get(oid, set())
for oid in keep_bf:
    referenced_by_keep |= refmap.get(oid, set())

legacy_filerefs = set()
for base, ids in fileref_by_path.items():
    for fid in ids:
        if fid not in referenced_by_keep:
            legacy_filerefs.add(fid)

seeds = (set(DELETE_TARGETS) | DELETE_PHASES | DELETE_DEPS | DELETE_PROXIES
         | DELETE_CONFIG_LISTS | delete_configs | DELETE_PRODUCT_REFS
         | del_bf | STRIP_FROM_KEPT | legacy_filerefs)

# ---------- Phase 2: delete seed object ranges + strip seed references everywhere ----------
dead = [False] * len(lines)
for oid in seeds:
    for (a, b) in objs.get(oid, []):
        for k in range(a, b):
            dead[k] = True
# strip reference/list lines containing seed ids in surviving lines
stripped = 0
for k in range(len(lines)):
    if dead[k]: continue
    if set(TOK.findall(lines[k])) & seeds and re.match(r'^\t+[0-9A-F]{24} /\* .*? \*/,$', lines[k]):
        dead[k] = True; stripped += 1
# TargetAttributes sub-blocks for deleted targets
for k in range(len(lines)):
    if dead[k]: continue
    m = re.match(r'^\t+([0-9A-F]{24}) = \{$', lines[k])
    if m and m.group(1) in DELETE_TARGETS:
        dead[k] = True
        d = lines[k].count('{') - lines[k].count('}')
        j = k + 1
        while j < len(lines) and d > 0:
            dead[j] = True
            d += lines[j].count('{') - lines[j].count('}')
            j += 1

lines = [l for k, l in enumerate(lines) if not dead[k]]

# ---------- Phase 3: dedupe duplicate object definitions (keep first) ----------
objs = parse(lines)
dedup_dead = set()
for oid, ranges in objs.items():
    for (a, b) in ranges[1:]:
        for k in range(a, b):
            dedup_dead.add(k)
if dedup_dead:
    lines = [l for k, l in enumerate(lines) if k not in dedup_dead]
    print(f'deduped duplicate definitions: {len(dedup_dead)} lines')

# ---------- Phase 4: GC unreferenced objects to fixpoint (true reference graph) ----------
for it in range(20):
    objs = parse(lines)
    refmap = refs_of(lines, objs)
    inbound = {oid: set() for oid in objs}
    for oid, r in refmap.items():
        for t in r:
            if t in inbound:
                inbound[t].add(oid)
    # external references (rootObject line etc.) - lines not in any object
    ext = set()
    objlines = set()
    for oid, ranges in objs.items():
        for (a, b) in ranges:
            for k in range(a, b): objlines.add(k)
    for k, l in enumerate(lines):
        if k not in objlines:
            for m in TOK.finditer(l):
                ext.add(m.group(1))
    orphans = [oid for oid in objs if not inbound[oid] and oid not in ext]
    if not orphans:
        break
    dead = set()
    for oid in orphans:
        for (a, b) in objs[oid]:
            for k in range(a, b): dead.add(k)
    lines = [l for k, l in enumerate(lines) if k not in dead]
    print(f'GC pass {it}: removed {len(orphans)} orphans')

# ---------- cleanup blank runs ----------
cleaned, prev_blank = [], False
for l in lines:
    blank = (l.strip() == '')
    if blank and prev_blank: continue
    cleaned.append(l); prev_blank = blank
open(PATH, 'w').write('\n'.join(cleaned))
print(f'seeds deleted: {len(seeds)}, stripped refs: {stripped}')
