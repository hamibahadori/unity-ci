#!/usr/bin/env python3
"""C# casing and naming conventions for a Unity project.

Deliberately regex-based rather than semantic. Unity projects usually gitignore their generated
.csproj files, so a Roslyn analyser would mean booting the editor just to produce project files —
a multi-gigabyte dependency for rules a regex can decide reliably.

Namespace rules are NOT hardcoded. Each assembly's expected namespace is read from the
`rootNamespace` in its .asmdef, so this works on any project without configuration and cannot drift
from what Unity itself believes. Assemblies with an empty rootNamespace are skipped.

Rules enforced:
  - types, methods and public members  PascalCase
  - private/protected instance fields  _camelCase
  - constants and static readonly      PascalCase
  - locals and parameters              camelCase, and never a single letter
  - namespace matches the owning assembly's rootNamespace
  - file name matches one of the types it declares, or is `<Type>.<Part>.cs` for a part of a
    `partial` type
  - no Unity `m_` prefix
  - `== null`, never `is null`  (Unity's fake-null only works with the overloaded operator)

Test assemblies (name ending `.Tests`) allow underscore-separated method names, the common
Method_Scenario_Result convention.

Usage:  python checks/check_naming.py
Exit:   0 clean, 1 violations found.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from unity_ci import find_asmdefs, is_excluded, load_config, owning_asmdef, project_root

PASCAL_CASE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
UNDERSCORE_CAMEL_CASE = re.compile(r"^_[a-z][A-Za-z0-9]*$")
CAMEL_CASE = re.compile(r"^[a-z][A-Za-z0-9]*$")
PASCAL_CASE_SEGMENTS = re.compile(r"^[A-Z][A-Za-z0-9]*(?:_[A-Za-z][A-Za-z0-9]*)*$")

# A field: modifiers, a type, a name, then '=' or ';'.
# Excluded by construction: auto-properties ('{' before the terminator), expression-bodied members
# ('=>'), and anything with a parameter list or '!' — which covers methods and operator overloads,
# where the '==' of `operator ==(...)` would otherwise read as a field initializer.
FIELD_DECLARATION = re.compile(
    r"^\s*(?:\[[^\]]*\]\s*)*"
    r"(?P<modifiers>(?:public|private|protected|internal)"
    r"(?:\s+(?:static|readonly|const|volatile|new|override))*)"
    r"\s+(?P<remainder>[^;={(!]+?)\s*(?:=(?![>=])|;)"
)

TYPE_DECLARATION = re.compile(
    r"^\s*(?:public|internal|private)?\s*"
    r"(?P<modifiers>(?:(?:static|abstract|sealed|partial|readonly)\s+)*)"
    r"(?:class|struct|enum|interface|record)\s+(?P<name>\w+)"
)

METHOD_DECLARATION = re.compile(
    r"^\s*(?:\[[^\]]*\]\s*)*"
    r"(?P<modifiers>(?:public|private|protected|internal)"
    r"(?:\s+(?:static|virtual|override|abstract|sealed|async|new|extern))*)"
    r"\s+(?!(?:if|for|foreach|while|switch|return|using|lock)\b)"
    r"[\w<>,\[\]\.\?\s]+?\s+(?P<name>\w+)\s*\((?P<parameters>[^)]*)\)"
)

NAMESPACE_DECLARATION = re.compile(r"^\s*namespace\s+(?P<name>[\w\.]+)")

LOCAL_DECLARATION = re.compile(
    r"^\s*(?:var|int|float|double|bool|string|char|long|byte|"
    r"Vector2Int|Vector3|Vector2|Color|Quaternion)\s+(?P<name>\w+)\s*(?:=|;|\bin\b)"
)

IS_NULL = re.compile(r"\bis\s+(?:not\s+)?null\b")
HUNGARIAN_PREFIX = re.compile(r"\bm_[A-Za-z]")

# Framework contracts, not our naming choices. "operator" is not a method name at all — it is the
# keyword of an overload whose real name is a symbol.
EXEMPT_METHOD_NAMES = {"ToString", "Equals", "GetHashCode", "operator"}


def strip_strings_and_comments(source: str) -> str:
    """Blank out string literals and comments so their contents never trip a rule.

    Replaced with spaces rather than removed, so line and column numbers survive.
    """
    result = []
    index = 0
    length = len(source)
    while index < length:
        char = source[index]
        two = source[index:index + 2]
        if two == "//":
            end = source.find("\n", index)
            end = length if end == -1 else end
            result.append(" " * (end - index))
            index = end
        elif two == "/*":
            end = source.find("*/", index + 2)
            end = length if end == -1 else end + 2
            result.append("".join(c if c == "\n" else " " for c in source[index:end]))
            index = end
        elif two == '@"':
            end = index + 2
            while end < length:
                if source[end] == '"':
                    if source[end:end + 2] == '""':
                        end += 2
                        continue
                    end += 1
                    break
                end += 1
            result.append("".join(c if c == "\n" else " " for c in source[index:end]))
            index = end
        elif char in ('"', "'"):
            end = index + 1
            while end < length:
                if source[end] == "\\":
                    end += 2
                    continue
                if source[end] == char or source[end] == "\n":
                    end += 1
                    break
                end += 1
            result.append(" " * (end - index))
            index = end
        else:
            result.append(char)
            index += 1
    return "".join(result)


def split_parameters(parameter_text: str):
    if not parameter_text.strip():
        return
    depth = 0
    current = []
    parameters = []
    for character in parameter_text:
        if character in "<([":
            depth += 1
        elif character in ">)]":
            depth -= 1
        if character == "," and depth == 0:
            parameters.append("".join(current))
            current = []
        else:
            current.append(character)
    parameters.append("".join(current))

    for parameter in parameters:
        tokens = parameter.split("=")[0].strip().replace("[", " ").replace("]", " ").split()
        if len(tokens) >= 2:
            yield tokens[-1]


def check_field(field_match, line_number, report):
    modifiers = field_match.group("modifiers").split()
    remainder = field_match.group("remainder").strip()
    name_match = re.search(r"(\w+)$", remainder)
    if name_match is None:
        return
    name = name_match.group(1)

    is_constant = "const" in modifiers or ("static" in modifiers and "readonly" in modifiers)
    is_private = "private" in modifiers or "protected" in modifiers

    if is_constant:
        if not PASCAL_CASE.match(name):
            report(line_number, f"constant '{name}' must be PascalCase")
    elif is_private:
        if not UNDERSCORE_CAMEL_CASE.match(name):
            report(line_number, f"private field '{name}' must be _camelCase")
    elif not PASCAL_CASE.match(name):
        report(line_number, f"public member '{name}' must be PascalCase")


def check_file(path, relative, expected_namespace, is_test_assembly, violations):
    code = strip_strings_and_comments(path.read_text(encoding="utf-8-sig"))
    method_name_pattern = PASCAL_CASE_SEGMENTS if is_test_assembly else PASCAL_CASE

    def report(line_number, message):
        violations.append(f"{relative}:{line_number}: {message}")

    declared_types = []
    partial_types = set()
    declared_namespace = None

    for line_number, line in enumerate(code.splitlines(), start=1):
        if HUNGARIAN_PREFIX.search(line):
            report(line_number, "Unity's 'm_' prefix is not this project's convention; use '_camelCase'")
        if IS_NULL.search(line):
            report(line_number, "use '== null' / '!= null', never 'is null' (UnityEngine.Object fake-null)")

        namespace_match = NAMESPACE_DECLARATION.match(line)
        if namespace_match:
            declared_namespace = namespace_match.group("name")

        type_match = TYPE_DECLARATION.match(line)
        if type_match:
            name = type_match.group("name")
            declared_types.append(name)
            if "partial" in type_match.group("modifiers").split():
                partial_types.add(name)
            if not PASCAL_CASE.match(name):
                report(line_number, f"type '{name}' must be PascalCase")
            continue

        method_match = METHOD_DECLARATION.match(line)
        if method_match:
            name = method_match.group("name")
            if name not in EXEMPT_METHOD_NAMES and not method_name_pattern.match(name):
                report(line_number, f"method '{name}' must be PascalCase")
            for parameter in split_parameters(method_match.group("parameters")):
                if not CAMEL_CASE.match(parameter):
                    report(line_number, f"parameter '{parameter}' must be camelCase")
                elif len(parameter) == 1:
                    report(line_number, f"parameter '{parameter}' is a single letter; use a descriptive name")
            continue

        field_match = FIELD_DECLARATION.match(line)
        if field_match:
            check_field(field_match, line_number, report)
            continue

        local_match = LOCAL_DECLARATION.match(line)
        if local_match:
            name = local_match.group("name")
            if not CAMEL_CASE.match(name):
                report(line_number, f"local '{name}' must be camelCase")
            elif len(name) == 1:
                report(line_number, f"local '{name}' is a single letter; use a descriptive name")

    if expected_namespace:
        if declared_namespace is None:
            violations.append(f"{relative}: no namespace declared; expected '{expected_namespace}'")
        elif declared_namespace != expected_namespace and not declared_namespace.startswith(
                expected_namespace + "."):
            violations.append(
                f"{relative}: namespace '{declared_namespace}' does not match its assembly's "
                f"rootNamespace '{expected_namespace}'"
            )

    if declared_types:
        check_file_name(path.stem, relative, declared_types, partial_types, violations)


def check_file_name(stem, relative, declared_types, partial_types, violations):
    """A file is named after a type it declares — or, for a type split across files with `partial`,
    after that type and a part: `BoardView.Gizmos.cs` holding part of `partial class BoardView`.

    The part form is accepted only when the type named before the first dot is declared `partial` in
    that same file. Anything looser — accepting any dotted name once a file holds some partial type,
    say — would let a misnamed file through on the strength of an unrelated declaration.
    """
    if stem in declared_types:
        return

    if "." in stem:
        owner = stem.split(".", 1)[0]
        if owner in partial_types:
            return
        if owner in declared_types:
            violations.append(
                f"{relative}: named as a part of '{owner}' ('{owner}.<Part>.cs'), but '{owner}' is "
                f"not declared partial; a type in one file is named after that type alone"
            )
            return

    violations.append(
        f"{relative}: file name does not match any type it declares ({', '.join(declared_types)})"
    )


def main() -> int:
    root = project_root()
    config = load_config(root)
    asmdefs = find_asmdefs(root)
    violations = []
    checked = 0

    for source_root in config["source_roots"]:
        for path in sorted((root / source_root).rglob("*.cs")):
            relative = path.relative_to(root).as_posix()
            if is_excluded(relative, config):
                continue

            owner = owning_asmdef(path, asmdefs)
            expected_namespace = owner[1].get("rootNamespace", "") if owner else ""
            assembly_name = owner[1].get("name", "") if owner else ""
            checked += 1
            check_file(path, relative, expected_namespace,
                       assembly_name.endswith(".Tests"), violations)

    if violations:
        print(f"Naming convention violations ({len(violations)}):\n")
        for violation in violations:
            print(f"  {violation}")
        return 1

    print(f"Naming conventions: clean ({checked} file(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
