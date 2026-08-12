#!/usr/bin/env python3
"""Git LFS hygiene: nothing that should be in LFS was committed as a normal blob.

The failure this catches: someone clones and commits a .png without `git lfs install` having run.
Git stores the whole binary in history instead of a pointer. Nothing warns you, the repository
grows permanently, and rewriting history is the only cure — so it has to be caught at review time,
before it is in main.

This inspects what git has *stored in the index*, not the working tree, so it gives the same answer
whether or not LFS content has been smudged in. That matters: a check that behaves differently on a
developer machine than in CI is one nobody trusts or runs locally.

The index rather than HEAD, specifically, so the pre-commit hook catches the mistake at the moment
it is made rather than one commit too late. After a CI checkout the index matches HEAD, so the
result there is identical.

Usage:  python checks/check_lfs.py
Exit:   0 clean, 1 violations found. Oversized non-LFS files are warnings only — the right fix is
        a .gitattributes decision, not an automatic failure.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from unity_ci import is_excluded, load_config, project_root

def run_git(root, arguments, **kwargs):
    return subprocess.run(["git"] + arguments, cwd=root, check=True,
                          capture_output=True, text=True, **kwargs)


# A gitlink — a submodule pointer. Its "object" is a commit in the *submodule's* repository, which
# does not exist here, so asking this repository for its size is meaningless. Consuming unity-ci as
# a submodule is a supported layout, so this is a normal thing to encounter, not an error.
GITLINK_MODE = "160000"


def stored_blob_sizes(root):
    """Path -> the size git has stored for it in the index. An LFS pointer is ~130 bytes."""
    listing = run_git(root, ["ls-files", "-s", "-z"])
    entries = []
    for entry in listing.stdout.split("\0"):
        if not entry:
            continue
        # "<mode> <object> <stage>\t<path>"
        metadata, _, path = entry.partition("\t")
        fields = metadata.split()
        if len(fields) >= 2 and fields[0] != GITLINK_MODE:
            entries.append((fields[1], path))

    if not entries:
        return {}

    query = "\n".join(object_id for object_id, _path in entries) + "\n"
    measured = run_git(root, ["cat-file", "--batch-check=%(objectsize)"], input=query)

    # One line per query, but an unreadable object answers "<oid> missing" instead of a size.
    # Parsing positionally rather than by line would silently misalign every entry after it.
    sizes = {}
    for (object_id, path), line in zip(entries, measured.stdout.splitlines()):
        size = line.strip()
        if size.isdigit():
            sizes[path] = int(size)
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
