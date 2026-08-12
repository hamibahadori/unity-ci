#!/usr/bin/env python3
"""Self-test: prove each check passes a clean project AND fails a broken one.

The second half is the one that matters. A check that can no longer fail is worse than no check,
because it still reports green and looks like coverage. Two of these checks are several hundred
lines of regex against C#; a tweak that quietly stops matching would otherwise go unnoticed until
it let a real problem through.

Each broken case also asserts on a substring of the output, so a check cannot "pass" this suite by
failing for an unrelated reason — crashing on a missing folder is not the same as catching a
violation.

The fixtures are ordinary tracked files inside this repository. That works because `git ls-files`
and `git ls-tree` are relative to the working directory, so pointing UNITY_CI_PROJECT_ROOT at a
fixture makes the git-backed checks see only that fixture. The repository's own lint run does not
see them either, because it looks for source under `Assets/` at the root, which does not exist here.

Usage:  python tests/run_self_test.py
Exit:   0 all expectations met, 1 otherwise.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKS = REPO_ROOT / "checks"
FIXTURES = REPO_ROOT / "tests" / "fixtures"

# (check, fixture, expected exit code, must contain, must NOT contain)
#
# The "must NOT contain" column exists because of a bug this suite caught on its very first run:
# the git-backed checks reported "clean (0 tracked paths)" and passed, having inspected nothing.
# A clean case that examines zero files is not evidence of anything, so the counts are asserted.
CASES = [
    ("check_core_purity.py", "clean", 0, "clean", "0 file(s)"),
    ("check_core_purity.py", "broken", 1, "Polluted.cs", None),

    ("check_naming.py", "clean", 0, "clean", "(0 file(s))"),
    ("check_naming.py", "broken", 1, "BadField", None),
    ("check_naming.py", "broken", 1, "badMethod", None),
    ("check_naming.py", "broken", 1, "rootNamespace", None),
    ("check_naming.py", "broken", 1, "is null", None),

    ("check_unity_assets.py", "clean", 0, "clean", "(0 tracked paths)"),
    ("check_unity_assets.py", "broken", 1, "Ghost.cs.meta", None),

    # LFS is the one check with no broken case, deliberately.
    #
    # A realistic violation means a file that .gitattributes routes through LFS but which git
    # stores as a plain blob — and creating one requires neutralising the LFS *process* filter at
    # `git add` time. That fixture existed briefly and was removed, because it made `git status`
    # permanently dirty for everyone: git compares the working tree *through* the clean filter,
    # which turns the file back into a pointer, so it never matches the raw blob in the index. A
    # repository whose status is never clean is one where real changes are easy to miss.
    #
    # The clean case still proves the check runs, reports, and does not crash. The behaviour it
    # guards is exercised for real every time someone commits a binary.
    ("check_lfs.py", "clean", 0, "clean", None),
]


def run(check: str, fixture: str):
    environment = dict(os.environ)
    environment["UNITY_CI_PROJECT_ROOT"] = str(FIXTURES / fixture)
    completed = subprocess.run(
        [sys.executable, str(CHECKS / check)],
        cwd=str(FIXTURES / fixture),
        capture_output=True,
        text=True,
        env=environment,
    )
    return completed.returncode, completed.stdout + completed.stderr


def main() -> int:
    # The git-backed checks read the index, so the fixtures have to be at least staged. In CI a
    # checkout has already tracked them; locally, a contributor who has only just written them
    # would otherwise get a confusing vacuous pass.
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "tests/fixtures"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    ).stdout.strip()
    if untracked:
        count = len(untracked.splitlines())
        print(f"NOTE: {count} fixture file(s) are untracked. `git ls-files` only sees tracked or "
              f"staged files,\n      so the git-backed checks would inspect nothing. Run: "
              f"git add tests/fixtures\n")
        return 1

    failures = []
    for check, fixture, expected_code, expected_text, forbidden_text in CASES:
        code, output = run(check, fixture)
        label = f"{check} on {fixture}"

        if code != expected_code:
            verb = "should have failed but passed" if expected_code else "should have passed but failed"
            failures.append(f"{label}: {verb} (exit {code})\n{indent(output)}")
        elif expected_text.lower() not in output.lower():
            failures.append(
                f"{label}: exit code was right but the output never mentioned "
                f"'{expected_text}' — is it failing for the right reason?\n{indent(output)}"
            )
        elif forbidden_text and forbidden_text.lower() in output.lower():
            failures.append(
                f"{label}: passed vacuously — output contains '{forbidden_text}', meaning the "
                f"check inspected nothing.\n{indent(output)}"
            )
        else:
            print(f"  ok    {label:<44} exit {code}, mentions '{expected_text}'")

    print()
    if failures:
        print(f"SELF-TEST FAILED — {len(failures)} of {len(CASES)} expectation(s) not met:\n")
        for failure in failures:
            print(f"- {failure}\n")
        return 1

    print(f"Self-test passed — {len(CASES)} expectations across "
          f"{len({case[0] for case in CASES})} checks.")
    return 0


def indent(text: str) -> str:
    return "\n".join("      " + line for line in text.strip().splitlines()) or "      (no output)"


if __name__ == "__main__":
    sys.exit(main())
