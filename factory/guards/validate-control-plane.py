#!/usr/bin/env python3
"""Guard: normal finding work must not silently change the factory's own controls.

Usage:
    python3 factory/guards/validate-control-plane.py            # check
    python3 factory/guards/validate-control-plane.py --update   # re-stamp manifest

Why this exists (audit finding F-05): the factory's guards decide whether a
finding may close, and CI runs those guards *from the pull request's own
head*. So a branch that changed both a product file and, say,
factory/guards/validate-finding.py was checked by the very guard it had just
weakened -- and the required status check, which only asserts that a job
named `factory-checks` succeeded, could not tell the difference. The same
held for factory/scripts/gh-query.sh, the layer that reports CI status and
performs the merge, and for the CI workflow file itself.

Local Edit/Write deny rules cannot close this: they exist only on the
machine running Claude Code, they are configuration that the person running
it can change, and they say nothing about what arrives in a pull request.
This guard is the server-side half. It runs inside the same CI job as every
other factory check and compares the control plane against a stamped
manifest, so a control-plane change becomes a visible, deliberate act
instead of a side effect of a normal fix.

What counts as control plane: everything that decides whether work is
allowed to proceed, or that produces the evidence such a decision is based
on -- the guards, the factory scripts, the Claude Code hooks, the reviewer
agent definition, the skills, the workflow rules, the shared settings file,
the CI workflow, and CLAUDE.md itself.

factory/reviews/ is deliberately NOT in the manifest: review artifacts are
append-only and appear legitimately during normal work. Their protection is
a different mechanism (the SubagentStop hook is the only writer, plus the
Edit/Write deny and sandbox denyWrite entries) -- and the files implementing
*that* mechanism are in the manifest.

Honest limit, stated plainly: a change that rewrites a control-plane file
AND re-stamps the manifest in the same commit passes this guard. That is
unavoidable -- a repository cannot bootstrap trust in itself from inside
itself. What the guard converts is the failure mode: silent, invisible
drift becomes a manifest diff that is impossible to miss in review, and an
explicit statement that the author meant to change the control plane. A
FACTORY_CHANGE like that is exactly what
.claude/rules/factory-workflow.md requires an independent review and a
human decision for.

Exit code 0: the control plane matches the manifest.
Exit code 1: it does not (changed, added, removed, or missing manifest), or
             the file list could not be determined.
"""
import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

MANIFEST_VERSION = "factory-control-plane-v1"

# (directory prefix, allowed suffixes) -- an empty suffix tuple means "any file".
CONTROL_PLANE_DIR_RULES = (
    ("factory/guards/", (".py",)),
    ("factory/scripts/", (".sh",)),
    (".claude/hooks/", (".py",)),
    (".claude/agents/", (".md",)),
    (".claude/skills/", ()),
    (".claude/rules/", (".md",)),
    (".github/workflows/", (".yml", ".yaml")),
)

CONTROL_PLANE_FILES = (
    ".claude/settings.json",
    "CLAUDE.md",
)

# factory/guards/validate-control-plane.py -> parents[2] = repo root
DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_RELATIVE_PATH = "factory/control-plane.sha256"


class ControlPlaneError(RuntimeError):
    """The control plane could not be determined. Never treat this as 'unchanged'."""


def is_control_plane_path(relative_path):
    if relative_path == MANIFEST_RELATIVE_PATH:
        return False  # a manifest cannot contain its own hash
    if relative_path in CONTROL_PLANE_FILES:
        return True
    for prefix, suffixes in CONTROL_PLANE_DIR_RULES:
        if relative_path.startswith(prefix):
            if not suffixes or relative_path.endswith(suffixes):
                return True
    return False


def _tracked_files(repo_root):
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"], cwd=str(repo_root), capture_output=True
        )
    except OSError as exc:
        raise ControlPlaneError(f"git ist nicht ausfuehrbar: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise ControlPlaneError(
            f"'git ls-files' in {repo_root} fehlgeschlagen (kein Git-Repository?): {detail}"
        )
    return sorted(
        entry.decode("utf-8", "surrogateescape")
        for entry in result.stdout.split(b"\0")
        if entry
    )


def current_control_plane(repo_root):
    """{relative_path: sha256} for every tracked control-plane file."""
    entries = {}
    for relative_path in _tracked_files(repo_root):
        if not is_control_plane_path(relative_path):
            continue
        path = repo_root / relative_path
        try:
            entries[relative_path] = hashlib.sha256(path.read_bytes()).hexdigest()
        except (FileNotFoundError, IsADirectoryError, PermissionError) as exc:
            raise ControlPlaneError(
                f"Control-Plane-Datei {relative_path} ist nicht lesbar: {exc}"
            ) from exc
    if not entries:
        raise ControlPlaneError(
            "Keine einzige Control-Plane-Datei gefunden -- ein leeres Manifest waere "
            "bedeutungslos."
        )
    return entries


def read_manifest(manifest_path):
    if not manifest_path.is_file():
        raise ControlPlaneError(
            f"Manifest {manifest_path} fehlt. Ohne Manifest ist keine Aussage darueber "
            "moeglich, ob die Kontrollebene unveraendert ist."
        )
    entries = {}
    for raw_line in manifest_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            raise ControlPlaneError(f"Manifest-Zeile nicht lesbar: {raw_line!r}")
        digest, relative_path = parts[0], parts[1].strip()
        entries[relative_path] = digest
    return entries


def render_manifest(entries):
    lines = [
        f"# {MANIFEST_VERSION}",
        "#",
        "# sha256 der Factory-Kontrollebene. Erzeugt mit:",
        "#   python3 factory/guards/validate-control-plane.py --update",
        "#",
        "# Eine Aenderung an dieser Datei bedeutet: die Kontrollebene selbst wurde",
        "# geaendert. Das ist ein FACTORY_CHANGE, kein normales Finding -- siehe",
        "# .claude/rules/factory-workflow.md.",
        "",
    ]
    lines += [f"{entries[path]}  {path}" for path in sorted(entries)]
    return "\n".join(lines) + "\n"


def compare(current, manifest):
    """Return a list of human-readable difference descriptions."""
    problems = []
    for path in sorted(set(manifest) - set(current)):
        problems.append(
            f"Im Manifest, aber nicht mehr im Repository: {path} "
            "(Control-Plane-Datei entfernt oder umbenannt)."
        )
    for path in sorted(set(current) - set(manifest)):
        problems.append(
            f"Im Repository, aber nicht im Manifest: {path} "
            "(neue Control-Plane-Datei)."
        )
    for path in sorted(set(current) & set(manifest)):
        if current[path] != manifest[path]:
            problems.append(
                f"Inhalt geaendert: {path} (Manifest {manifest[path][:12]}…, "
                f"aktuell {current[path][:12]}…)."
            )
    return problems


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument(
        "--update",
        action="store_true",
        help="Manifest neu stempeln. Bewusster FACTORY_CHANGE-Schritt, kein Routinebefehl.",
    )
    args = parser.parse_args(argv[1:])

    repo_root = args.repo_root.resolve()
    manifest_path = repo_root / MANIFEST_RELATIVE_PATH

    try:
        current = current_control_plane(repo_root)
    except ControlPlaneError as exc:
        print(f"CONTROL_PLANE_ERROR: {exc}", file=sys.stderr)
        return 1

    if args.update:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(render_manifest(current), encoding="utf-8")
        print(f"Control-Plane-Manifest neu gestempelt: {manifest_path} ({len(current)} Dateien)")
        return 0

    try:
        manifest = read_manifest(manifest_path)
    except ControlPlaneError as exc:
        print(f"CONTROL_PLANE_ERROR: {exc}", file=sys.stderr)
        return 1

    problems = compare(current, manifest)
    if problems:
        print(
            "CONTROL_PLANE_VERAENDERT: die Kontrollebene weicht vom gestempelten "
            "Manifest ab.",
            file=sys.stderr,
        )
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print(
            "\nNormale Finding-Arbeit darf die Kontrollebene nicht veraendern. Ist die "
            "Aenderung beabsichtigt, ist sie ein FACTORY_CHANGE: eigener Branch, "
            "unabhaengiger Review des gesamten Control-Plane-Diffs, menschliche "
            "Entscheidung, dann 'validate-control-plane.py --update'.",
            file=sys.stderr,
        )
        return 1

    print(f"Control-Plane unveraendert ({len(current)} Dateien gegen Manifest geprueft).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
