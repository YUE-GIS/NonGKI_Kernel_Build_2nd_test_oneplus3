#!/usr/bin/env python3
"""Backport path_umount() into fs/namespace.c for kernels < 5.9.

KernelSU calls path_umount() to unmount its own overlays before an app checks
for root. Linux 3.18 lacks it, so module unmount silently no-ops and overlays
stay visible to detection. Body is upstream's, unchanged.

Inserted at the '/*' opening the comment "Now umount can handle mount points
as well as block devices", placing it after do_umount() (its only dependency).

Idempotent; aborts instead of writing if dependencies or anchor are missing.
"""

import sys
from pathlib import Path

CAN_UMOUNT = """static int can_umount(const struct path *path, int flags)
{
\tstruct mount *mnt = real_mount(path->mnt);

\tif (flags & ~(MNT_FORCE | MNT_DETACH | MNT_EXPIRE | UMOUNT_NOFOLLOW))
\t\treturn -EINVAL;
\tif (!may_mount())
\t\treturn -EPERM;
\tif (path->dentry != path->mnt->mnt_root)
\t\treturn -EINVAL;
\tif (!check_mnt(mnt))
\t\treturn -EINVAL;
\tif (mnt->mnt.mnt_flags & MNT_LOCKED) /* Check optimistically */
\t\treturn -EINVAL;
\tif (flags & MNT_FORCE && !capable(CAP_SYS_ADMIN))
\t\treturn -EPERM;
\treturn 0;
}

"""

PATH_UMOUNT = """int path_umount(struct path *path, int flags)
{
\tstruct mount *mnt = real_mount(path->mnt);
\tint ret;

\tret = can_umount(path, flags);
\tif (!ret)
\t\tret = do_umount(mnt, flags);

\t/* we mustn't call path_put() as that would clear mnt_expiry_mark */
\tdput(path->dentry);
\tmntput_no_expire(mnt);
\treturn ret;
}

"""

ANCHOR = "Now umount can handle mount points as well as block devices"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: backport_path_umount.py <kernel-root>", file=sys.stderr)
        return 2

    ns = Path(sys.argv[1]) / "fs" / "namespace.c"
    if not ns.is_file():
        print(f"[-] not found: {ns}", file=sys.stderr)
        return 1

    src = ns.read_text(encoding="utf-8", errors="replace")

    if "int path_umount(" in src or "static int path_umount(" in src:
        print("[.] path_umount() already present; nothing to do")
        return 0

    for sym in ("may_mount(", "check_mnt(", "mntput_no_expire(", "real_mount("):
        if sym not in src:
            print(f"[-] dependency '{sym}' not found; aborting to avoid build break", file=sys.stderr)
            return 1

    lines = src.splitlines(keepends=True)
    anchor_idx = next((i for i, l in enumerate(lines) if ANCHOR in l), None)
    if anchor_idx is None:
        print("[-] anchor comment not found; aborting", file=sys.stderr)
        return 1

    start = anchor_idx
    while start > 0 and "/*" not in lines[start]:
        start -= 1
    if "/*" not in lines[start]:
        print("[-] could not find comment opening; aborting", file=sys.stderr)
        return 1

    snippet = ("" if "static int can_umount(" in src else CAN_UMOUNT) + PATH_UMOUNT
    ns.write_text("".join(lines[:start] + [snippet] + lines[start:]), encoding="utf-8")

    verify = ns.read_text(encoding="utf-8")
    if "int path_umount(" not in verify or "ret = do_umount(mnt, flags);" not in verify:
        print("[-] VERIFY FAILED after write", file=sys.stderr)
        return 1

    print("[+] path_umount() backported into fs/namespace.c")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
