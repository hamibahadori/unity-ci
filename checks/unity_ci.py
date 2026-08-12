#!/usr/bin/env python3
"""Shared plumbing for the unity-ci checks.

Three jobs:

1. Find the Unity project, wherever these scripts happen to live. They might be copied into
   `<project>/ci/`, added as a git submodule at `<project>/ci/unity-ci/`, or run from anywhere with
   UNITY_CI_PROJECT_ROOT set. Resolving off `__file__` would break two of those three.

2. Load optional per-project configuration from `unity-ci.json`, so a new project needs no edits to
   the scripts themselves.

3. Read Unity's `.asmdef` files. This is what keeps the checks close to zero-config: the assembly
   definitions already declare the namespace each folder should use and whether an assembly is
   meant to be engine-free, so the checks derive their rules from the project rather than from a
   hardcoded table that silently rots.
"""

import json
import os
from pathlib import Path

# Defaults chosen for a conventional Unity layout. Override any of them in unity-ci.json.
DEFAULT_CONFIG = {
    # Folders whose C# must not reference Unity. Defaults to every assembly that declares
    # "noEngineReferences": true, plus its .Tests sibling — see resolve_core_folders().
    "core_folders": None,
    # Where the C# lives. Used by the naming check.
    "source_roots": ["Assets/Scripts", "Assets/Tests"],
    # Root of Unity-managed assets, for the .meta pairing check.
    "asset_root": "Assets",
    # Files larger than this outside LFS are reported as a warning.
    "large_file_warning_bytes": 1024 * 1024,
    # Paths excluded from every check — vendored or third-party code you did not write.
    "exclude": [],
}


def project_root() -> Path:
    """The Unity project directory.

    UNITY_CI_PROJECT_ROOT wins, so CI and vendored copies can be explicit. Otherwise walk up from
    the working directory looking for an `Assets` folder, which is what makes a Unity project a
    Unity project.
    """
    override = os.environ.get("UNITY_CI_PROJECT_ROOT")
    if override:
        return Path(override).resolve()

    start = Path.cwd().resolve()
    for candidate in [start, *start.parents]:
        if (candidate / "Assets").is_dir():
            return candidate
    return start


def load_config(root: Path) -> dict:
    config = dict(DEFAULT_CONFIG)
    config_path = root / "unity-ci.json"
    if config_path.is_file():
        config.update(json.loads(config_path.read_text(encoding="utf-8-sig")))
    return config


def is_excluded(relative_path: str, config: dict) -> bool:
    return any(relative_path.startswith(prefix) for prefix in config["exclude"])


def find_asmdefs(root: Path) -> list:
    """Every assembly definition in the project, as (folder, parsed json).

    Sorted deepest-first so `owning_asmdef` can take the first match — Unity assigns a script to
    the *nearest* enclosing asmdef, and nested assemblies are common (Editor folders especially).
    """
    asmdefs = []
    for path in (root / "Assets").rglob("*.asmdef"):
        try:
            asmdefs.append((path.parent, json.loads(path.read_text(encoding="utf-8-sig"))))
        except json.JSONDecodeError:
            # A malformed asmdef is Unity's problem to report, not ours to crash on.
            continue
    asmdefs.sort(key=lambda entry: len(entry[0].parts), reverse=True)
    return asmdefs


def owning_asmdef(source_file: Path, asmdefs: list):
    """The assembly a given .cs file belongs to, or None if it is in Assembly-CSharp."""
    for folder, definition in asmdefs:
        if folder in source_file.parents:
            return folder, definition
    return None


def resolve_core_folders(root: Path, config: dict) -> list:
    """Folders whose code must stay free of Unity.

    Configured explicitly, or derived from the project: any assembly declaring
    "noEngineReferences": true has said, in the project's own words, that it does not use the
    engine — so that is what gets enforced. Its `.Tests` sibling is included too, because a pure
    assembly whose tests still need Unity cannot actually be tested outside the editor, which is
    the whole point of keeping it pure.
    """
    if config["core_folders"] is not None:
        return [root / folder for folder in config["core_folders"]]

    asmdefs = find_asmdefs(root)
    engine_free_names = {
        definition.get("name", "")
        for _folder, definition in asmdefs
        if definition.get("noEngineReferences") is True
    }

    folders = []
    for folder, definition in asmdefs:
        name = definition.get("name", "")
        is_engine_free = definition.get("noEngineReferences") is True
        tests_of_engine_free = name.endswith(".Tests") and name[: -len(".Tests")] in engine_free_names
        if is_engine_free or tests_of_engine_free:
            folders.append(folder)
    return folders
