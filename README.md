# unity-ci

Fast, dependency-light CI for Unity projects — plus the pattern that lets your game's rules engine
be unit-tested as ordinary .NET.

Four Python checks and two pipeline definitions (GitLab CI and GitHub Actions), all running in
seconds on stock Python and .NET images.

---

## What you get

- **Feedback in about 20 seconds.** The whole lint stage is faster than most projects' checkout.
- **No editor in the loop.** Nothing here needs a Unity install, so the pipeline works on any
  runner from the first commit, with no setup beyond copying two files.
- **The same checks locally.** Identical commands, identical output — so they get run before the
  push, not discovered in review.
- **Failures that are otherwise invisible.** Missing `.meta` files, case-only path collisions and
  binaries committed outside LFS all look fine on the machine that created them and break for
  everyone else.
- **Your rules engine tested on every pull request** — if you keep it engine-free, which the
  [pattern below](#keeping-a-unity-free-core-package) explains how to do.

## How much can you verify without the editor?

More than you might expect. Everything except the parts that genuinely touch Unity's runtime:

| | Needs the editor? |
| --- | --- |
| Code conventions, casing, namespaces | no |
| `.meta` pairing, path case collisions | no |
| Git LFS hygiene | no |
| Spelling | no |
| **The entire rules engine, if you keep it engine-free** | **no** |
| `MonoBehaviour`s, `AssetDatabase`, scenes, prefabs | yes — these stay a Test Runner step |

Running the editor headlessly in CI is very doable, but it needs a licence activated on the build
machine, an image measured in gigabytes, and a per-run cost in compute minutes. How involved that
setup is depends on which Unity licence you hold, and it can change over time.

This project takes the other route: **get everything that does not need the editor running first,
cheaply and immediately.** You can always add an editor-based job later for the parts that need it
— the two complement each other, and the fast checks stay useful either way.

---

## What the checks catch

### `check_core_purity.py`
Your engine-free assemblies must not reference `UnityEngine` or `UnityEditor`. This is what
protects the whole arrangement below — one stray `using UnityEngine;` and your rules engine stops
being testable outside the editor, silently, until someone tries.

Zero config: it finds every assembly declaring `"noEngineReferences": true` in its `.asmdef`, plus
that assembly's `.Tests` sibling. Comments are ignored, so a doc comment may still name `Vector2Int`
to explain why your own type exists.

### `check_naming.py`
C# casing: PascalCase types/methods/constants, `_camelCase` private fields, camelCase locals and
parameters with no single letters, no Unity `m_` prefix, and `== null` never `is null` — because
Unity's "fake null" for destroyed objects only works through the overloaded operator, so `is null`
is a real bug, not a style preference.

Also checks that a file's namespace matches its assembly's **`rootNamespace` read from the
`.asmdef`**, and that a file name matches one of the types it declares. Deriving namespaces from
the project rather than a hardcoded table is what makes this work on any project unmodified — and
it cannot drift from what Unity itself believes.

Regex-based, deliberately. Unity projects normally gitignore their generated `.csproj` files, so a
Roslyn analyser would need the editor to produce them first. A regex decides these particular rules
reliably and keeps the check instant and dependency-free.

### `check_unity_assets.py`
Every asset has a `.meta`, every `.meta` has an asset, and no two tracked paths differ only in case.

Both failures are invisible on the machine that causes them. A missing `.meta` makes Unity
regenerate the GUID on next import, **silently breaking every reference to that asset** — prefabs
lose scripts, scenes lose objects. And Windows and macOS are case-insensitive while Linux is not,
so a case-only collision works for the author and breaks every Linux teammate, and CI itself.

### `check_lfs.py`
Nothing matching an LFS pattern in `.gitattributes` was committed as a normal blob.

This catches someone cloning and committing a `.png` without `git lfs install` having run. Git
stores the whole binary in history instead of a pointer, nothing warns you, the repository grows
permanently, and `git lfs migrate` — a history rewrite — is the only cure.

It inspects what git has **stored**, not the working tree, so it gives the same answer whether or
not LFS content is smudged in. A check that behaves differently locally than in CI is one nobody
runs locally.

---

## Keeping a Unity-free core package

This is the part that turns "some lint" into "actual test coverage". The idea: your game's **rules**
— movement, collision resolution, scoring, win/lose evaluation, AI decisions — do not need Unity.
Only the presentation of those rules does.

If you keep them in their own assembly with no `UnityEngine` dependency, that assembly compiles as
ordinary .NET and its tests run under `dotnet test` in seconds, on every merge request, with no
editor involved.

### 1. Separate the assemblies

```
Assets/Scripts/Core/     YourGame.Core.asmdef        rules. no Unity.
Assets/Scripts/Game/     YourGame.Game.asmdef        MonoBehaviours, views, input, flow
Assets/Tests/Core/       YourGame.Core.Tests.asmdef  runs in Unity AND under dotnet test
Assets/Tests/Game/       YourGame.Game.Tests.asmdef  Unity only
```

### 2. Declare the intent in the asmdef

```json
{
  "name": "YourGame.Core",
  "rootNamespace": "YourGame.Core",
  "noEngineReferences": true
}
```

`noEngineReferences: true` makes **Unity's own compiler** reject a Unity reference, in the editor,
immediately. This is the fastest feedback you will get and costs nothing.

### 3. Replace the Unity types you actually use

In practice this list is short. A grid-based puzzle game's entire rules engine needed only two:

| Unity type | Replace with |
| --- | --- |
| `Vector2Int` / `Vector3Int` | a small `readonly struct` of your own |
| `Mathf.Abs`, `Min`, `Max`, `Clamp` | `System.Math` |
| `Mathf.Approximately` | your own epsilon comparison |
| `Debug.Log` | nothing — rules code should return results, not log |
| `Random` | inject a seeded `System.Random`, which also makes tests deterministic |

Your own vector type needs less than you expect: construction, componentwise arithmetic, value
equality and `GetHashCode` (grid cells end up as dictionary keys everywhere), and a `ToString` that
**matches Unity's format** — `(1, 2)` — so exception messages and logs read exactly as before.

**Do not change serialized types.** Unity assets on disk store cells as `{x: 1, y: 1}`. If a
`ScriptableObject` serializes `List<Vector2Int>`, leave it: change the type and every authored asset
silently empties. Keep the Unity type in the serialized field and convert where the data crosses
into your core package. One conversion point, in one file, is the whole cost.

### 4. Add a csproj that builds it outside Unity

```
dotnet/YourGame.Core/YourGame.Core.csproj              netstandard2.1
dotnet/YourGame.Core.Tests/YourGame.Core.Tests.csproj  net9.0, NUnit
```

Three things matter:

- **Glob the same files Unity compiles** — `<Compile Include="..\..\Assets\Scripts\Core\**\*.cs" />`
  — never a copy. Two copies drift, and the day they do you will not notice.
- **Pin `<LangVersion>`** to whatever Unity supports (C# 9 for Unity 2022–6.x). Without it `dotnet`
  accepts C# 12 syntax that Unity rejects: green CI, broken editor.
- **Give each project its own folder.** Two csproj files in one directory share an `obj/` and
  collide during restore.

Two `.gitignore` details worth knowing before you pick folder names: Unity's stock ignore file has
`/[Bb]uild/` for player builds, so a folder called `build/` will not be tracked, and `*.csproj` is
usually ignored too — hence a `dotnet/` folder and a `!dotnet/**/*.csproj` negation.

### 5. Three guards, not one

Each covers a hole the others leave:

1. **`noEngineReferences: true`** — Unity rejects it in the editor, instantly. Only helps someone
   with the editor open.
2. **The `dotnet` build** — references nothing from Unity, so the types do not resolve. Catches it
   in CI, but is defeated by adding a Unity reference to that csproj, which looks like a plausible
   fix for the errors.
3. **`check_core_purity.py`** — reads the source, so no project-file edit satisfies it, and it fails
   in the fast lint stage with an explanation instead of a wall of `CS0246`.

### The payoff

On the project this came from: **158 rules tests in about 50 ms, on every merge request.** Fast
enough that nobody is tempted to skip them, and covering exactly the code where a regression would
be hardest to spot by playing the game.

---

## Usage

### Install

Copy `checks/` into your Unity project (commonly `ci/checks/`), or add this repository as a
submodule:

```bash
git submodule add https://github.com/hamibahadori/unity-ci.git ci/unity-ci
```

Then copy the pipeline file you need — `.gitlab-ci.yml` or `.github/workflows/unity-ci.yml` — to
your project root and set `UNITY_CI_CHECKS` to wherever the checks ended up.

### Run locally

Identical to CI, which is the point — nobody trusts a check they cannot reproduce:

```bash
python ci/checks/check_core_purity.py
python ci/checks/check_naming.py
python ci/checks/check_unity_assets.py
python ci/checks/check_lfs.py
```

They locate the project by walking up from the working directory for an `Assets` folder. Override
with `UNITY_CI_PROJECT_ROOT` when running from elsewhere:

```bash
UNITY_CI_PROJECT_ROOT=/path/to/project python ci/checks/check_naming.py
```

Requirements: Python 3.9+, `git`, and `git-lfs` for the LFS check. No pip packages.

### Configure

**Most projects need no configuration.** The checks read your `.asmdef` files for namespaces and
engine-free assemblies. If the defaults are wrong, copy `unity-ci.json.example` to `unity-ci.json`
at your project root and set only the keys you need.

Copy `_typos.toml.example` to `_typos.toml` for the spell checker. A false positive is fixed by
adding the word to `[default.extend-words]`, **not** by weakening the check — otherwise the gate
quietly rots back to advisory.

### Run them on every commit

The whole suite takes under two seconds, which is the argument for the hook: cheaper than the round
trip to CI, and far cheaper than a reviewer finding it.

```bash
git config core.hooksPath ci/unity-ci/hooks
```

That points git at the whole directory, so the hook updates with the rest of unity-ci. If you
already keep hooks of your own, copy the single file instead:

```bash
cp ci/unity-ci/hooks/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
```

`git commit --no-verify` bypasses it, which is reasonable for a work-in-progress commit on your own
branch — CI is still the gate that matters. The hook also **skips rather than blocks** if it cannot
find the checks or a working Python: a misconfigured hook should never stop you committing.

`check_lfs.py` reads the **index**, so the hook catches a binary committed without LFS at the moment
it happens rather than one commit too late.

### An `.editorconfig` is worth pairing with this

Mirror the naming rules in `.editorconfig` so Rider and Visual Studio flag them as you type. Finding
them before you push beats finding them in review.

---

## Design notes

**One lint job, not five.** Measured on a real project: the five checks take **1.7 seconds
combined**, while each *job* pays roughly 11 seconds of fixed overhead — image pull, prepare,
clone, cleanup — plus 7 seconds of `apt`. Splitting them costs about 4× the compute for a prettier
pipeline graph. The single job runs every check before failing and labels each one, so a single
push surfaces every problem and no diagnostic information is lost.

**Merge-request-only by default.** GitLab.com's free tier has a limited monthly compute allowance.
On GitHub, public repositories have unlimited minutes, so adding `push:` there is cheap.

**Warnings versus failures.** `check_lfs.py` warns about large non-LFS files rather than failing:
the right fix is a `.gitattributes` decision by a human, not an automatic block. Everything else
fails, because a check that only warns is a check that gets ignored.

**Bonus: compile Unity code without opening the editor.** Unity writes real `.csproj` files at the
project root — gitignored, regenerated on import — carrying every assembly reference the editor
uses. So `dotnet build YourGame.Game.csproj` type-checks your Unity code in seconds without waiting
for a domain reload. Invaluable during wide refactors. It cannot *run* Unity tests, and the projects
are only as fresh as the last import, so it complements the Test Runner rather than replacing it.

---

## Developing unity-ci itself

### The self-test

```bash
python tests/run_self_test.py
```

Two fixture projects under `tests/fixtures/` — one correct, one with a deliberate violation of
every rule — and a runner asserting that each check **passes the clean one and fails the broken
one**.

The second half is the point. These are several hundred lines of regex against C#, and a tweak that
quietly stops matching would otherwise go unnoticed until it let a real problem through. A check
that can no longer fail is worse than no check, because it still reports green and looks like
coverage.

Each broken case also asserts on a substring of the output, so a check cannot satisfy the suite by
failing for an unrelated reason — crashing on a missing folder is not the same as catching a
violation. And each clean case asserts the check did **not** report zero files inspected, because
the suite caught exactly that on its first run: the git-backed checks reported *"clean (0 tracked
paths)"* and passed, having looked at nothing.

The clean fixture deliberately contains the constructs that have broken the naming check before —
operator overloads, auto-properties, expression-bodied members, `static readonly`, `const` — so a
regression fails here rather than in someone's project.

**Fixtures must be tracked or staged.** `git ls-files` only sees the index, so a newly written
fixture is invisible to the git-backed checks. The runner refuses to proceed in that state rather
than passing vacuously.

**The LFS fixture needs care if you ever re-add it.** `tests/fixtures/broken/.gitattributes` routes
`*.bin` through LFS, and `blob.bin` is committed as a plain blob anyway — the exact mistake someone
makes cloning and committing without `git lfs install`. Reproducing that deliberately means
neutralising the LFS **process** filter, not just `clean`, which takes precedence:

```bash
git -c filter.lfs.process= -c filter.lfs.clean=cat add tests/fixtures/broken/blob.bin
```

Re-add it normally and git converts it to a pointer, the violation disappears, and that self-test
case starts failing for a reason that is not obvious.

This is also why the repository has its own `unity-ci.json` setting `exclude: ["tests/fixtures/"]`
— without it, the repository's own lint would fail on its own test data.

### Workflow linting

The `self-test` job runs [actionlint](https://github.com/rhysd/actionlint) over
`.github/workflows/`. This exists because a broken workflow shipped from this repository once: a
`hashFiles()` call in a job-level `if`, which is valid YAML and invalid to Actions — `jobs.<id>.if`
allows only `always`, `cancelled`, `success` and `failure`, because it is evaluated before the job
reaches a runner. A YAML parser cannot see that. actionlint can, offline, in a second.

There is no equivalent step for `.gitlab-ci.yml`, since `glab ci lint` needs an authenticated
GitLab project and this repository lives on GitHub. Run it manually when changing that file.

### How the fixtures stay out of the way

The fixtures are ordinary tracked files, not a temporary copy, which works because `git ls-files`
and `git ls-tree` are relative to the working directory — pointing `UNITY_CI_PROJECT_ROOT` at a
fixture makes the git-backed checks see only that fixture.

The repository's own lint run does not see them either: it looks for source under `Assets/` at the
root, which does not exist here. If that ever changes, `exclude` in `unity-ci.json` is the escape
hatch.

---

## Licence

MIT. See [LICENSE](LICENSE).
