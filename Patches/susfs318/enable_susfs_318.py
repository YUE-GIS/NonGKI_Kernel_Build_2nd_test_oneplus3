#!/usr/bin/env python3
"""Enable SUSFS bundled in SukiSU-Ultra's `builtin` branch on Linux 3.18.

Why not toggle SUSFS_ENABLE in the workflow:
  patch-susfs/action.yml applies `susfs_patch_to_<kver>.patch` from susfs4ksu,
  which has no 3.18 branch. SukiSU-Ultra's `builtin` branch already carries the
  SUSFS source in-tree, so only its Kconfig options must be enabled. Keeping
  SUSFS_ENABLE=false makes patch-susfs a complete no-op.

Idempotent: only appends options that are not already present, then re-reads
the file to assert every option landed (no silent failure).
"""

import os
import sys
from pathlib import Path

# Verified against SukiSU-Ultra/SukiSU-Ultra @ refs/heads/builtin kernel/Kconfig.
SUSFS_OPTIONS = [
    "CONFIG_KSU_SUSFS=y",
    "CONFIG_KSU_SUSFS_SUS_PATH=y",
    "CONFIG_KSU_SUSFS_SUS_MOUNT=y",
    "CONFIG_KSU_SUSFS_SUS_KSTAT=y",
    "CONFIG_KSU_SUSFS_SPOOF_UNAME=y",
    "CONFIG_KSU_SUSFS_ENABLE_LOG=y",
    "CONFIG_KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS=y",
    "CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG=y",
    "CONFIG_KSU_SUSFS_OPEN_REDIRECT=y",
    "CONFIG_KSU_SUSFS_SUS_MAP=y",
    "CONFIG_KSU_SUSFS_PRIORITY_UID_FILTER=y",
]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: enable_susfs_318.py <defconfig-path>", file=sys.stderr)
        return 2

    defconfig = Path(sys.argv[1])
    if not defconfig.is_file():
        print(f"[-] defconfig not found: {defconfig}", file=sys.stderr)
        return 1

    lines = defconfig.read_text(encoding="utf-8", errors="replace").splitlines()
    added = []

    for opt in SUSFS_OPTIONS:
        key, want = opt.split("=", 1)
        # build-ready writes `CONFIG_KSU_SUSFS=n` when SUSFS_ENABLE=false.
        # We must REWRITE an existing `=n` to `=y`, not skip it — skipping
        # would leave SUSFS disabled while the build still succeeds (silent
        # failure). Only skip when the option is already set to what we want.
        replaced = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == opt:
                replaced = True  # already exactly what we want
                break
            if stripped.startswith(key + "="):
                lines[i] = opt
                replaced = True
                added.append(f"{key}: existing -> {want}")
                break
        if replaced:
            continue
        lines.append(opt)
        added.append(f"{key}: added = {want}")

    # THREAD_INFO_IN_TASK exists only in some KSU trees; enable when present.
    ksu_kconfig = os.environ.get("KSU_KCONFIG", "")
    if ksu_kconfig and Path(ksu_kconfig).is_file():
        if "THREAD_INFO_IN_TASK" in Path(ksu_kconfig).read_text(encoding="utf-8", errors="replace"):
            if not any(l.strip().startswith("CONFIG_THREAD_INFO_IN_TASK=") for l in lines):
                lines.append("CONFIG_THREAD_INFO_IN_TASK=y")
                added.append("CONFIG_THREAD_INFO_IN_TASK=y")

    defconfig.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Verify the EXACT value `=y`, not merely presence. A leftover `=n` line
    # would still read as "present" and silently leave SUSFS off.
    verify = [line.strip() for line in defconfig.read_text(encoding="utf-8").splitlines()]
    for opt in SUSFS_OPTIONS:
        if opt not in verify:
            key = opt.split("=", 1)[0]
            offenders = [l for l in verify if l.startswith(key + "=")]
            print(f"[-] VERIFY FAILED: {opt} not set (found: {offenders})", file=sys.stderr)
            return 1

    print(f"[+] enabled {len(added)} option(s); verified all {len(SUSFS_OPTIONS)} present")
    for opt in added:
        print(f"    + {opt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
