#!/usr/bin/env python3
"""The engine-free assemblies must not reference Unity.

A game's rules — movement, scoring, win/lose evaluation — rarely need the engine; only their
presentation does. Kept in their own assembly, they compile as ordinary .NET and their tests run
under `dotnet test` in seconds, on any runner, with nothing else installed.

A single `using UnityEngine;` gives that up, and nothing notices until someone tries to build
outside Unity — by which time the dependency has usually spread. Hence this check.

Which folders are checked: whatever `core_folders` says in unity-ci.json, or — with no config —
every assembly declaring `"noEngineReferences": true`, plus its `.Tests` sibling.

Pair this with two other guards. Neither is sufficient alone:

- `"noEngineReferences": true` in the asmdef makes Unity's own compiler reject it, immediately, in
  the editor. Best feedback, but only for someone who has the editor open.
- A `dotnet build` of the assembly fails to resolve the types. Catches it in CI — but is defeated
  by adding a Unity reference to that csproj, which looks like a plausible fix for the errors.

This check reads the source, so no project-file edit satisfies it, and it fails fast with a message
that says what is wrong instead of a wall of CS0246.

Usage:  python checks/check_core_purity.py
Exit:   0 clean, 1 violations found.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from unity_ci import is_excluded, load_config, project_root, resolve_core_folders

# UnityEditor counts too: reaching for editor APIs makes an assembly uncompilable in a player build
# as well as outside Unity.
FORBIDDEN = re.compile(r"\b(UnityEngine|UnityEditor)\b")

# Prose mentions are fine and often useful — a vector type's doc comment explaining why it exists
# will legitimately name Vector2Int. Only code counts.
COMMENT_LINE = re.compile(r"^\s*(///|//|\*|/\*)")


def main() -> int:
    root = project_root()
    config = load_config(root)
    core_folders = resolve_core_folders(root, config)

    if not core_folders:
        print(
            "Core purity: no engine-free assemblies found.\n\n"
            'Either set "core_folders" in unity-ci.json, or mark the assembly with\n'
            '"noEngineReferences": true in its .asmdef — which also makes Unity enforce it.'
        )
        return 0

    violations = []
    checked = 0
    for folder in core_folders:
        for path in sorted(folder.rglob("*.cs")):
            relative = path.relative_to(root).as_posix()
            if is_excluded(relative, config):
                continue
            checked += 1
            for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
                if COMMENT_LINE.match(line):
                    continue
                if FORBIDDEN.search(line):
                    violations.append(f"{relative}:{number}: {line.strip()}")

    if violations:
        print(f"Engine-free assemblies must stay Unity-free — {len(violations)} violation(s):\n")
        for violation in violations:
            print(f"  {violation}")
        print(
            "\nThese assemblies are plain .NET so `dotnet test` can run them without a Unity\n"
            "licence. Use your own vector/math types instead of Vector2Int and Mathf. If a Unity\n"
            "type is genuinely needed, the code belongs in the Unity-facing assembly instead."
        )
        return 1

    names = ", ".join(folder.relative_to(root).as_posix() for folder in core_folders)
    print(f"Core purity: clean — {checked} file(s) across {names}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
