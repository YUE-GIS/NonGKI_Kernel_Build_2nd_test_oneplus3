#!/usr/bin/env python3
"""Reduce kernel fingerprints before build.

1. Enable CONFIG_KSU_NOPRINTK so KernelSU emits no dmesg logging at all.
   Implemented in kernel/kernel_includes.h: all pr_*/printk become no-ops.
2. Pin LINUX_COMPILER in scripts/mkcompile_h to the stock clang string, so
   /proc/version matches the vendor kernel instead of exposing the build GCC.

Usage: harden_kernel.py <kernel-root> <defconfig-path-relative-to-root>
"""
import os
import sys

root = sys.argv[1] if len(sys.argv) > 1 else "."
defconfig = sys.argv[2] if len(sys.argv) > 2 else "arch/arm64/configs/lineageos_oneplus3_defconfig"

STOCK_COMPILER = ("Android (6877366 based on r383902b1) clang version 11.0.2 "
                  "(https://android.googlesource.com/toolchain/llvm-project "
                  "b397f81060ce6d701042b782172ed13bee898b79)")

# ---------------------------------------------------------------- 1. KSU NOPRINTK
def_p = os.path.join(root, defconfig)
if not os.path.isfile(def_p):
    raise SystemExit("FAIL: defconfig not found: %s" % def_p)

s = open(def_p, encoding="utf-8").read()
if "CONFIG_KSU_NOPRINTK=y" in s:
    print("[-] CONFIG_KSU_NOPRINTK already in defconfig")
else:
    kconfig_candidates = [
        os.path.join(root, "drivers/kernelsu/Kconfig"),
        os.path.join(root, "KernelSU/kernel/Kconfig"),
        os.path.join(root, "KernelSU-Next/kernel/Kconfig"),
    ]
    found = [p for p in kconfig_candidates if os.path.isfile(p) and "KSU_NOPRINTK" in open(p, encoding="utf-8", errors="replace").read()]
    if not found:
        raise SystemExit("FAIL: no KSU Kconfig with KSU_NOPRINTK found, option would be dropped by olddefconfig")
    if not s.endswith("\n"):
        s += "\n"
    s += "# Silence all KernelSU dmesg logging (fingerprint reduction)\nCONFIG_KSU_NOPRINTK=y\n"
    open(def_p, "w", encoding="utf-8", newline="\n").write(s)
    print("[+] defconfig += CONFIG_KSU_NOPRINTK=y   (verified against %s)" % os.path.relpath(found[0], root))

# ---------------------------------------------------------------- 2. LINUX_COMPILER
mk = os.path.join(root, "scripts/mkcompile_h")
if not os.path.isfile(mk):
    raise SystemExit("FAIL: scripts/mkcompile_h not found")

s = open(mk, encoding="utf-8").read()
old = "echo \\#define LINUX_COMPILER \\\"`$CC -v 2>&1 | grep ' version '`\\\""
# The stock compiler string contains bare parentheses, which the shell would
# reject as a syntax error at parse time. Wrap the whole thing in real double
# quotes and keep the inner ones escaped.
new = 'echo "#define LINUX_COMPILER \\"%s\\""' % STOCK_COMPILER

if new in s:
    print("[-] LINUX_COMPILER already pinned")
elif old in s:
    open(mk, "w", encoding="utf-8", newline="\n").write(s.replace(old, new))
    print("[+] LINUX_COMPILER pinned to stock clang string")
else:
    raise SystemExit("FAIL: LINUX_COMPILER anchor not found in scripts/mkcompile_h")

print("OK")
