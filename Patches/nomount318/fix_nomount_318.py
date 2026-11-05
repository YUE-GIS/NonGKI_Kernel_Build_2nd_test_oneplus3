#!/usr/bin/env python3
"""Patch maxsteeel/nomount kernel source for Linux 3.18 (OnePlus 3 / msm8996).

Usage: python3 fix_nomount_318.py <path-to-NoMount/kernel/src>
All edits are confined to nomount.c / nomount.h inside that directory.
"""
import os
import re
import sys

src = sys.argv[1] if len(sys.argv) > 1 else "."
hp = os.path.join(src, "nomount.h")
cp = os.path.join(src, "nomount.c")
h = open(hp, encoding="utf-8").read()
c = open(cp, encoding="utf-8").read()

applied = []

def sub(text, old, new, tag, count=1):
    n = text.count(old)
    if n < count:
        raise SystemExit("PATCH FAILED [%s]: expected >=%d match(es), found %d for %r"
                         % (tag, count, n, old[:70]))
    applied.append("%s x%d" % (tag, n))
    return text.replace(old, new, count)

# ---------------------------------------------------------------- nomount.h
COMPAT = r'''
/* ===== Linux 3.18 compatibility (oneplus3 auto-patch) ===== */
#include <linux/aio.h>
#include <linux/magic.h>
#include <linux/uio.h>
#include <linux/xattr.h>
#include <linux/spinlock.h>
#include <asm/compat.h>

/* 3.18 has no DCACHE_OP_REAL and no per-superblock inode-list lock. */
#ifndef DCACHE_OP_REAL
#define DCACHE_OP_REAL 0
#endif
static spinlock_t nm_sb_inode_lock;

#if LINUX_VERSION_CODE < KERNEL_VERSION(4, 5, 0)
#define in_compat_syscall() is_compat_task()
#ifndef BPF_FS_MAGIC
#define BPF_FS_MAGIC 0xCAFE4A11
#endif
#define lookup_one_len_unlocked(n, p, l) lookup_one_len(n, p, l)
#define inode_lock(i)   mutex_lock(&(i)->i_mutex)
#define inode_unlock(i) mutex_unlock(&(i)->i_mutex)
#define full_name_hash(_ns, _n, _l) \
        full_name_hash((const unsigned char *)(_n), (unsigned int)(_l))
#define __vfs_getxattr(_d, _i, _n, _b, _s) \
        vfs_getxattr((_d), (_n), (_b), (_s))
#define __vfs_setxattr(_d, _i, _n, _b, _s, _f) \
        vfs_setxattr((_d), (_n), (_b), (_s), (_f))
static inline char *nm_xattr_full(const struct xattr_handler *_h,
                                 const char *_n, char *_b, size_t _s)
{
    snprintf(_b, _s, "%s%s", _h->prefix ? _h->prefix : "", _n);
    return _b;
}
#define xattr_full_name(_h, _n) nm_xattr_full((_h), (_n), (char[256]){0}, 256)
#endif
/* ===== end 3.18 compatibility ===== */
'''

h = sub(h, "#include <linux/compat.h>\n",
        "#include <linux/compat.h>\n" + COMPAT, "inject compat header")

# DEFINE_MUTEX's compound-literal spinlock initializer is rejected by GCC 4.9
# on this 3.18 tree. Use runtime init instead (see nomount_init below).
h = sub(h, "static DEFINE_MUTEX(nm_mutex);", "static struct mutex nm_mutex;",
        "runtime mutex")

n_iter = h.count("->iterate_shared")
h = h.replace("->iterate_shared", "->iterate")
applied.append("iterate_shared member access ->iterate x%d" % n_iter)

# ---------------------------------------------------------------- nomount.c
c = sub(c, "struct nm_inode_info probe = {0}, *info = NULL;",
        "struct nm_inode_info probe, *info = NULL;\n"
        "    memset(&probe, 0, sizeof(probe));", "missing-braces probe")

c = sub(c, ".ctx.actor = nm_actor_proxy,",
        ".ctx.actor = (filldir_t)nm_actor_proxy,", "filldir_t cast", count=2)

c = sub(c, "    .iterate_shared = nm_dir_iterate_dir,\n",
        "#if LINUX_VERSION_CODE >= KERNEL_VERSION(4, 7, 0)\n"
        "    .iterate_shared = nm_dir_iterate_dir,\n"
        "#endif\n", "iterate_shared initializer")

# get_link / delayed_call do not exist before 4.5; drop the symlink proxy.
c = sub(c, "static const char *nm_get_link(struct dentry *dentry,",
        "#if LINUX_VERSION_CODE >= KERNEL_VERSION(4, 5, 0)\n"
        "static const char *nm_get_link(struct dentry *dentry,", "guard get_link")
c = sub(c, "    return ERR_PTR(-EINVAL);\n}\n\nstatic int nm_dir_iterate_dir",
        "    return ERR_PTR(-EINVAL);\n}\n#endif\n\nstatic int nm_dir_iterate_dir",
        "close get_link guard")

c = sub(c, "    .get_link = nm_get_link,\n",
        "#if LINUX_VERSION_CODE >= KERNEL_VERSION(4, 5, 0)\n"
        "    .get_link = nm_get_link,\n"
        "#endif\n", "guard get_link initializer")

c = sub(c,
        "    return proxy->orig->get(proxy->orig, dentry, inode, name, buffer, size FLAGS_VAL);",
        "#if LINUX_VERSION_CODE < KERNEL_VERSION(4, 5, 0)\n"
        "    return proxy->orig->get(dentry, name, buffer, size, proxy->orig->flags);\n"
        "#else\n"
        "    return proxy->orig->get(proxy->orig, dentry, inode, name, buffer, size FLAGS_VAL);\n"
        "#endif", "xattr get signature")

c = sub(c,
        "    return proxy->orig->set(proxy->orig, IDMAP_CALL dentry, inode, name, buffer, size, flags);",
        "#if LINUX_VERSION_CODE < KERNEL_VERSION(4, 5, 0)\n"
        "    return proxy->orig->set(dentry, name, buffer, size, flags, proxy->orig->flags);\n"
        "#else\n"
        "    return proxy->orig->set(proxy->orig, IDMAP_CALL dentry, inode, name, buffer, size, flags);\n"
        "#endif", "xattr set signature")

c = sub(c, "static int __init nomount_init(void)\n{\n",
        "static int __init nomount_init(void)\n{\n"
        "    mutex_init(&nm_mutex);\n"
        "    spin_lock_init(&nm_sb_inode_lock);\n",
        "runtime lock init")

# --- second wave: errors only reachable after the first wave compiles ---
n = c.count("->iterate_shared")
c = c.replace("->iterate_shared", "->iterate")
applied.append("nomount.c iterate_shared ->iterate x%d" % n)

c = sub(c, "            if (proxies[i].fake.get) proxies[i].fake.get = nm_xattr_get;\n",
        "#if LINUX_VERSION_CODE >= KERNEL_VERSION(4, 5, 0)\n"
        "            if (proxies[i].fake.get) proxies[i].fake.get = nm_xattr_get;\n"
        "#endif\n", "guard xattr-get handler assignment")

c = sub(c, "            if (proxies[i].fake.set) proxies[i].fake.set = nm_xattr_set;\n",
        "#if LINUX_VERSION_CODE >= KERNEL_VERSION(4, 5, 0)\n"
        "            if (proxies[i].fake.set) proxies[i].fake.set = nm_xattr_set;\n"
        "#endif\n", "guard xattr-set handler assignment")

c, n = re.subn(r"&[A-Za-z0-9_>.\-]*s_inode_list_lock", "&nm_sb_inode_lock", c)
applied.append("private inode-list lock x%d" % n)
if n < 4:
    raise SystemExit("PATCH FAILED: expected >=4 inode-list lock sites, got %d" % n)

# The struct-initializer-style member is '.' not '->', so it survived the
# earlier replacement. Guard it away; the existing .iterate assignment below
# covers kernels < 6.6 (including 3.18).
c = sub(c, "        if (fop->iterate) ops->fake_fop.iterate_shared = nm_hijacked_iterate_dir;\n",
        "#if LINUX_VERSION_CODE >= KERNEL_VERSION(4, 7, 0)\n"
        "        if (fop->iterate_shared) ops->fake_fop.iterate_shared = nm_hijacked_iterate_dir;\n"
        "#endif\n", "guard fop initializer iterate_shared")

# On 3.18 the xattr handler assignments are compiled out, which leaves these
# two functions unused; the kernel builds with -Werror=unused-function.
c = sub(c, "static int nm_xattr_get(",
        "static int __maybe_unused nm_xattr_get(", "mark nm_xattr_get maybe_unused")
c = sub(c, "static int nm_xattr_set(",
        "static int __maybe_unused nm_xattr_set(", "mark nm_xattr_set maybe_unused")

open(hp, "w", encoding="utf-8", newline="\n").write(h)
open(cp, "w", encoding="utf-8", newline="\n").write(c)

print("NoMount 3.18 patch applied:")
for a in applied:
    print("  -", a)
