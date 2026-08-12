#!/usr/bin/env python3
"""Git LFS hygiene: nothing that should be in LFS was committed as a normal blob.

The failure this catches: someone clones and commits a .png without `git lfs install` having run.
Git stores the whole binary in history instead of a pointer. Nothing warns you, the repository
grows permanently, and rewriting history is the only cure — so it has to be caught at review time,
before it is in main.

This inspects what git has *stored* (`git lfs ls-files` and `git ls-tree`), not the working tree,
so it gives the same answer whether or not LFS content has been smudged in. That matters: a check
that behaves differently on a developer machine than in CI is one nobody trusts or runs locally.

Usage:  python checks/check_lfs.py
Exit:   0 clean, 1 violations found. Oversized non-LFS files are warnings only — the right fix is
        a .gitattributes decision, not an automatic failure.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from unity_ci import is_excluded, load_config, project_root

COMMIT = "HEAD"


def run_git(root, arguments, **kwargs):
    return subprocess.run(["git"] + arguments, cwd=root, check=True,
                          capture_output=True, text=True, **kwargs)


def stored_blob_sizes(root):
    """Path -> the size git actually stores. An LFS pointer is ~130 bytes."""
    result = run_git(root, ["ls-tree", "-r", "-l", "-z", COMMIT])
    sizes = {}
    for entry in result.stdout.split("\0"):
        if not entry:
            continue
        metadata, _, path = entry.partition("\t")
        fields = metadata.split()
        if len(fields) >= 4 and fields[1] == "blob" and fields[3] != "-":
            sizes[path] = int(fields[3])
    return sizes


def paths_matching_lfs_attribute(root, paths):
    if not paths:
        return set()
    result = run_git(root, ["check-attr", "--stdin", "-z", "filter"], input="\0".join(paths))
    fields = [field for field in result.stdout.split("\0") if field != ""]
    matching = set()
    for index in range(0, len(fields) - 2, 3):
        if fields[index + 2] == "lfs":
            matching.add(fields[index])
    return matching


def main() -> int:
    root = project_root()
    config = load_config(root)
    threshold = config["large_file_warning_bytes"]

    sizes = stored_blob_sizes(root)
    all_paths = sorted(p for p in sizes if not is_excluded(p, config))
    should_be_lfs = paths_matching_lfs_attribute(root, all_paths)

    try:
        actually_lfs = {line.strip() for line
                        in run_git(root, ["lfs", "ls-files", "--name-only"]).stdout.splitlines()
                        if line.strip()}
    except subprocess.CalledProcessError:
        print("LFS: git-lfs is not installed — cannot verify. Install it, or the check is vacuous.")
        return 1

    violations = sorted(should_be_lfs - actually_lfs)
    stragglers = sorted(actually_lfs - should_be_lfs)
    warnings = sorted(p for p in all_paths if p not in should_be_lfs and sizes[p] > threshold)

    if warnings:
        print(f"Warnings — large files outside LFS ({len(warnings)}):\n")
        for path in warnings:
            print(f"  {path}: {sizes[path]} bytes, not covered by any LFS pattern")
        print("\nConsider adding the extension to .gitattributes.\n")

    if stragglers:
        print(f"Warnings — in LFS but no longer matched by a pattern ({len(stragglers)}):\n")
        for path in stragglers:
            print(f"  {path}")
        print("")

    if violations:
        print(f"LFS violations ({len(violations)}):\n")
        for path in violations:
            print(f"  {path}: matches an LFS pattern in .gitattributes but is stored as a normal "
                  f"blob ({sizes[path]} bytes)")
        print("\nFix: run `git lfs install`, then re-add the file so it is stored as a pointer.\n"
              "Files already in history need `git lfs migrate`.")
        return 1

    print(f"LFS: clean ({len(actually_lfs)} LFS-tracked path(s) verified).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
