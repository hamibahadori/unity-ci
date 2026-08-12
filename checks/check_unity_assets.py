#!/usr/bin/env python3
"""Unity asset hygiene: .meta pairing and path case collisions.

Both failures are invisible on the machine that causes them and break the project for everyone
else:

- A missing .meta means Unity regenerates the GUID on the next import, silently breaking every
  reference to that asset — prefabs lose scripts, scenes lose objects. An orphaned .meta is dead
  weight that confuses the importer.
- Windows and macOS are case-insensitive; Linux is not. Two tracked paths differing only in case
  work on the author's machine and break for every Linux teammate, and for CI itself.

Usage:  python checks/check_unity_assets.py
Exit:   0 clean, 1 violations found.
"""

import subprocess
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
from unity_ci import is_excluded, load_config, project_root

# Unity does not create .meta files for these.
META_EXEMPT_NAMES = {".gitignore", ".gitattributes", ".keep"}


def tracked_files(root: Path):
    result = subprocess.run(["git", "ls-files", "-z"], cwd=root, check=True,
                            capture_output=True, text=True)
    return [PurePosixPath(entry) for entry in result.stdout.split("\0") if entry]


def check_meta_pairing(paths, asset_root, config, violations):
    tracked = {path.as_posix() for path in paths}
    asset_paths = [p for p in paths if p.parts and p.parts[0] == asset_root
                   and not is_excluded(p.as_posix(), config)]

    for path in asset_paths:
        if path.suffix == ".meta":
            described = path.as_posix()[: -len(".meta")]
            is_tracked_file = described in tracked
            is_tracked_directory = any(other.startswith(described + "/") for other in tracked)
            if not is_tracked_file and not is_tracked_directory:
                violations.append(f"orphaned .meta with no asset: {path.as_posix()}")
            continue

        if path.name in META_EXEMPT_NAMES:
            continue
        if f"{path.as_posix()}.meta" not in tracked:
            violations.append(f"asset with no .meta: {path.as_posix()}")

    # Unity writes a .meta for every folder too.
    directories = set()
    for path in asset_paths:
        for parent in path.parents:
            text = parent.as_posix()
            if text not in (".", asset_root):
                directories.add(text)

    for directory in sorted(directories):
        if f"{directory}.meta" not in tracked:
            violations.append(f"folder with no .meta: {directory}")


def check_case_collisions(paths, violations):
    files = {}
    directories = {}
    for path in paths:
        files.setdefault(path.as_posix().lower(), set()).add(path.as_posix())
        for parent in path.parents:
            text = parent.as_posix()
            if text != ".":
                directories.setdefault(text.lower(), set()).add(text)

    for group in (files, directories):
        for _lowered, originals in sorted(group.items()):
            if len(originals) > 1:
                violations.append(
                    "paths differing only in case (breaks on case-sensitive filesystems): "
                    + ", ".join(sorted(originals))
                )


def main() -> int:
    root = project_root()
    config = load_config(root)
    paths = tracked_files(root)

    violations = []
    check_meta_pairing(paths, config["asset_root"], config, violations)
    check_case_collisions(paths, violations)

    if violations:
        print(f"Unity asset hygiene violations ({len(violations)}):\n")
        for violation in violations:
            print(f"  {violation}")
        return 1

    print(f"Unity asset hygiene: clean ({len(paths)} tracked paths).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
