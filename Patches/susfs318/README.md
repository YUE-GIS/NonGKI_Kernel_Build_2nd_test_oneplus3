# SUSFS on OnePlus 3 (Linux 3.18)

This directory enables SUSFS on the OnePlus 3 kernel without an external
susfs4ksu patch.

## Why this approach

- `susfs4ksu` has **no 3.18 branch** (lowest is 4.9); this repo has no
  `susfs_patch_to_3.18.patch` either. The stock `patch-susfs` action therefore
  cannot be used here — it would try to apply a non-existent patch.
- SukiSU-Ultra's **`builtin` branch** bundles the SUSFS source **in-tree**.
  `build-ready/action.yml` already selects `builtin` whenever fork=`sukisu`,
  regardless of `SUSFS_ENABLE`. So we only need to switch the Kconfig options on.
- `SUSFS_ENABLE` is intentionally left `false`: every step in `patch-susfs` is
  gated on it, so `false` makes the whole action a safe no-op.

Verified against SukiSU-Ultra/SukiSU-Ultra @ `builtin`:
- `config KSU` has **no `depends on KPROBES`** (plain bool, default y) -> builds on 3.18.
- Kconfig contains the full SUSFS option set, incl. `KSU_SUSFS_SUS_MAP` and
  `KSU_SUSFS_PRIORITY_UID_FILTER`.

## Files

- `enable_susfs_318.py <defconfig>` — appends the SUSFS Kconfig options to the
  defconfig. Idempotent; re-reads the file and asserts every option landed.
- `backport_path_umount.py <kernel-root>` — injects upstream `can_umount()` and
  `path_umount()` into `fs/namespace.c`. Linux 3.18 lacks `path_umount()` (added
  in 5.9); KernelSU needs it to unmount its own overlays before a root check,
  otherwise unmount silently no-ops. Verifies the 4 required symbols exist
  before writing; idempotent; verifies after write.

Both scripts were tested locally against a real 3.18 `fs/namespace.c` and a
sample defconfig before being committed.

## Notes

- `mnt_id_reorder` is forced off in the workflow: susfs4ksu's README warns it
  bootloops on non-GKI kernels.
- Existing 3.18 fixes in `Patches/syscall_hook_patches.sh` (do_execve_common
  branch, call-site counting, <4.4 util.h live-stack fix) are untouched.
- To build: dispatch `build-oneplus3.yml` with `ksu_fork` empty (defaults to
  `sukisu`). Check the artifact name ends with `-KSU-sukisu-...`.
