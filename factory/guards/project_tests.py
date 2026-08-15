#!/usr/bin/env python3
"""The factory's generic product-test adapter (audit finding F-21).

The single place that decides whether a repository's PRODUCT tests count as
performed. `run-project-tests.py` is only a thin entry point around this.

## Why this module exists

Before this, the factory hard-coded its own test framework as if it were a
general truth about product code: it looked for `app/**/test_*.py` and ran
them with unittest. For a Go, Node, Java or multi-service project that search
finds nothing -- and "found nothing" was reported as exit 0. The one place
where the factory asks "does the product still work?" answered "yes" without
ever running a product test. That is the same failure class F-19 closed for
the factory's own tests, one level up and with more consequence.

The repair is not a better search. It is to stop searching: the factory no
longer knows how the target project is built. The project declares its test
commands in `factory/project-tests.conf`, and the factory runs exactly those.

## Why the configuration is control plane

`factory/project-tests.conf` is listed in `factory/control-plane.sha256`.
Whoever can decide which product tests count as valid verification must not be
able to weaken that during ordinary finding work -- that would be a way to make
a red product suite disappear without touching a single test file. Configuring
it is a deliberate, reviewable `FACTORY_CHANGE`, done once when the factory is
integrated into a real project.

## The three states, and why "no product tests" is not one answer

    TEMPLATE_WITHOUT_PRODUCT
        A bare copy of the factory template: no tracked files outside the
        factory's own paths, and the configuration declares `mode: template`.
        Expected to be green without product tests. This is the ONLY state in
        which zero product tests is a pass.

    REAL_PROJECT_WITHOUT_TEST_CONFIGURATION
        Tracked files exist outside the factory's own paths -- there is product
        code -- but no suite is configured (or the file still declares
        `mode: template`). Hard blocker, exit 2. Silence here would be exactly
        the false green this finding is about.

    CONFIGURED
        At least one suite is declared. Every suite runs. Any non-zero exit is
        an overall failure, and a later red suite cannot be hidden by an
        earlier green one.

A missing `factory/project-tests.conf` is always a blocker, never a pass: the
template ships one, so its absence means someone removed it.

## No shell, ever

Commands are tokenized with `shlex.split` -- a quoting-aware tokenizer that
executes nothing -- and handed to `subprocess.run` as an argument list with
`shell=False`. Shell metacharacters (`|`, `;`, `&`, `$`, backtick, `>`, `<`,
newline) are rejected at parse time rather than silently passed through as
literal arguments, so a reader cannot mistake `a | b` for a working pipeline.
No command ever originates from a finding, a review or any other agent-written
content; the only source is this one versioned, control-plane-protected file.
"""
import shlex
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_RELATIVE_PATH = "factory/project-tests.conf"

# Paths that belong to the factory itself. Tracked files outside of these are
# product code, whatever language they are written in. This is deliberately a
# git question, not a filename heuristic: no language, framework or naming
# convention is assumed anywhere in this module.
FACTORY_PATH_PREFIXES = (
    "factory/",
    ".claude/",
    ".github/",
)
FACTORY_ROOT_FILES = frozenset(
    {
        "CLAUDE.md",
        "README.md",
        ".gitignore",
    }
)

SHELL_METACHARACTERS = ("|", ";", "&", "$", "`", ">", "<", "\n")

STATE_TEMPLATE_WITHOUT_PRODUCT = "TEMPLATE_WITHOUT_PRODUCT"
STATE_REAL_PROJECT_WITHOUT_TEST_CONFIGURATION = (
    "REAL_PROJECT_WITHOUT_TEST_CONFIGURATION"
)
STATE_CONFIGURED = "CONFIGURED"

MODE_TEMPLATE = "template"
MODE_REAL_PROJECT = "real-project"
ALLOWED_MODES = (MODE_TEMPLATE, MODE_REAL_PROJECT)

EXIT_OK = 0
EXIT_TESTS_FAILED = 1
EXIT_BLOCKED = 2


class ConfigError(Exception):
    """The configuration itself is unusable. Never a silent pass."""


class Suite:
    """One declared product test suite."""

    def __init__(self, name, argv, workdir):
        self.name = name
        self.argv = argv
        self.workdir = workdir

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"Suite(name={self.name!r}, argv={self.argv!r})"


def _reject_shell_metacharacters(name, command):
    for character in SHELL_METACHARACTERS:
        if character in command:
            printable = "Zeilenumbruch" if character == "\n" else repr(character)
            raise ConfigError(
                f"Suite '{name}': das Kommando enthaelt das Shell-Metazeichen "
                f"{printable}. Kommandos werden ohne Shell ausgefuehrt, ein "
                "solches Zeichen wuerde also nicht wirken, sondern als "
                "gewoehnliches Argument uebergeben. Wenn eine Pipeline oder "
                "Verkettung noetig ist, gehoert sie in ein Skript des Projekts, "
                "das hier als ein Kommando aufgerufen wird."
            )


def parse_config(text):
    """Parse the configuration text into {"mode", "suites"}.

    Format -- deliberately the same plain `key: value` shape the rest of the
    factory uses, so no parser dependency is introduced:

        mode: real-project

        [suite: unit]
        command: go test ./...
        workdir: app
    """
    mode = None
    suites = []
    current_name = None
    current_command = None
    current_workdir = None

    def flush(line_number):
        nonlocal current_name, current_command, current_workdir
        if current_name is None:
            return
        if current_command is None:
            raise ConfigError(
                f"Suite '{current_name}' hat kein 'command:'. Eine Suite ohne "
                "Kommando koennte nichts pruefen und wird nicht als erfuellte "
                "Testpflicht akzeptiert."
            )
        _reject_shell_metacharacters(current_name, current_command)
        try:
            argv = shlex.split(current_command)
        except ValueError as exc:
            raise ConfigError(
                f"Suite '{current_name}': Kommando nicht zerlegbar ({exc})."
            ) from exc
        if not argv:
            raise ConfigError(f"Suite '{current_name}': leeres Kommando.")
        suites.append(Suite(current_name, argv, current_workdir))
        current_name = None
        current_command = None
        current_workdir = None

    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[") and line.endswith("]"):
            flush(number)
            header = line[1:-1].strip()
            if not header.lower().startswith("suite:"):
                raise ConfigError(
                    f"Zeile {number}: unbekannter Abschnitt '{line}'. Erlaubt "
                    "ist ausschliesslich '[suite: <name>]'."
                )
            current_name = header.split(":", 1)[1].strip()
            if not current_name:
                raise ConfigError(f"Zeile {number}: Suite ohne Namen.")
            continue

        if ":" not in line:
            raise ConfigError(f"Zeile {number}: '{line}' ist kein 'key: value'.")

        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()

        if key == "mode":
            if current_name is not None:
                raise ConfigError(
                    f"Zeile {number}: 'mode' gehoert in den Kopf der Datei, "
                    "nicht in eine Suite."
                )
            if value not in ALLOWED_MODES:
                raise ConfigError(
                    f"Zeile {number}: unbekannter mode '{value}'. Erlaubt: "
                    + ", ".join(ALLOWED_MODES)
                )
            mode = value
        elif key == "command":
            if current_name is None:
                raise ConfigError(
                    f"Zeile {number}: 'command' ausserhalb einer Suite."
                )
            if current_command is not None:
                raise ConfigError(
                    f"Zeile {number}: Suite '{current_name}' hat mehr als ein "
                    "'command:'. Mehrere Kommandos gehoeren in mehrere Suiten, "
                    "damit jedes einzeln ausgewiesen wird."
                )
            current_command = value
        elif key == "workdir":
            if current_name is None:
                raise ConfigError(
                    f"Zeile {number}: 'workdir' ausserhalb einer Suite."
                )
            current_workdir = value
        else:
            raise ConfigError(
                f"Zeile {number}: unbekannter Schluessel '{key}'. Erlaubt sind "
                "'mode', 'command' und 'workdir'."
            )

    flush(len(text.splitlines()) + 1)

    if mode is None:
        raise ConfigError(
            "Pflichtfeld 'mode' fehlt. Erlaubt: " + ", ".join(ALLOWED_MODES)
        )

    return {"mode": mode, "suites": suites}


def tracked_product_files(repo_root):
    """Tracked files that are not part of the factory itself.

    A git question, not a filename heuristic -- the whole point of F-21 is that
    the factory must not assume anything about the product's language.
    """
    # Without a git repository there are no tracked files, so there is no
    # demonstrable product code either. This is not a loophole: the factory
    # requires a git repository throughout (the preflight checks for one), so a
    # real installation never reaches this branch. Test fixtures that are not
    # repositories do, and blocking them would mean answering a question that
    # does not apply to them.
    if not (Path(repo_root) / ".git").exists():
        return []

    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise ConfigError(f"'git ls-files' nicht ausfuehrbar: {exc}") from exc
    if result.returncode != 0:
        raise ConfigError(
            "'git ls-files' fehlgeschlagen (kein Git-Repository?): "
            + (result.stderr or "").strip()
        )

    product = []
    for relative_path in result.stdout.split("\0"):
        if not relative_path:
            continue
        if relative_path in FACTORY_ROOT_FILES:
            continue
        if any(relative_path.startswith(prefix) for prefix in FACTORY_PATH_PREFIXES):
            continue
        product.append(relative_path)
    return product


def classify(repo_root, config, product_files):
    """Which of the three states this repository is in."""
    if config["suites"]:
        return STATE_CONFIGURED
    if product_files:
        return STATE_REAL_PROJECT_WITHOUT_TEST_CONFIGURATION
    if config["mode"] == MODE_REAL_PROJECT:
        # Declared real, but nothing configured and nothing to test yet. Treat
        # the declaration as authoritative: the project said it is real, so a
        # missing suite is a blocker, not a template.
        return STATE_REAL_PROJECT_WITHOUT_TEST_CONFIGURATION
    return STATE_TEMPLATE_WITHOUT_PRODUCT


def run_suite(suite, repo_root):
    """Run one suite. Returns its exit code. No shell involved."""
    workdir = repo_root
    if suite.workdir:
        workdir = (repo_root / suite.workdir).resolve()
        if not workdir.is_dir():
            print(
                f"  [BLOCKED] Suite '{suite.name}': workdir '{suite.workdir}' "
                "existiert nicht."
            )
            return EXIT_BLOCKED

    print(f"  [RUN]  Suite '{suite.name}': {' '.join(suite.argv)}")
    try:
        result = subprocess.run(suite.argv, cwd=str(workdir))
    except FileNotFoundError:
        print(
            f"  [BLOCKED] Suite '{suite.name}': Programm '{suite.argv[0]}' nicht "
            "gefunden. Ein nicht ausfuehrbares Testkommando ist kein bestandener "
            "Test."
        )
        return EXIT_BLOCKED
    except OSError as exc:
        print(f"  [BLOCKED] Suite '{suite.name}': nicht ausfuehrbar ({exc}).")
        return EXIT_BLOCKED
    return result.returncode


def evaluate(repo_root, config_path=None):
    """Full adapter run. Returns (exit_code, state, lines_to_print)."""
    repo_root = Path(repo_root).resolve()
    path = Path(config_path) if config_path else repo_root / CONFIG_RELATIVE_PATH

    if not path.is_file():
        # No configuration file at all. Whether that is a blocker depends on
        # whether there is any product to test: a repository with tracked files
        # outside the factory's own paths owes an answer to "how is this tested",
        # and silence is not one. A repository without product code owes nothing
        # yet -- that is a template, and treating it as a blocker would fail
        # every throwaway factory-shaped repository (including the ones the
        # factory's own tests build) for a question that does not apply to it.
        #
        # Deleting the shipped configuration to reach this state is not a way
        # out: it would also mean deleting every product file, and the file is
        # part of the control plane, so its removal shows up as a manifest diff.
        try:
            product_files = tracked_product_files(repo_root)
        except ConfigError as exc:
            return (
                EXIT_BLOCKED,
                STATE_REAL_PROJECT_WITHOUT_TEST_CONFIGURATION,
                [
                    f"PROJECT_TESTS: {STATE_REAL_PROJECT_WITHOUT_TEST_CONFIGURATION}",
                    f"blocker: '{CONFIG_RELATIVE_PATH}' fehlt und der Produktbestand "
                    f"ist nicht bestimmbar: {exc}",
                ],
            )

        if not product_files:
            return (
                EXIT_OK,
                STATE_TEMPLATE_WITHOUT_PRODUCT,
                [
                    f"PROJECT_TESTS: {STATE_TEMPLATE_WITHOUT_PRODUCT}",
                    f"hinweis: '{CONFIG_RELATIVE_PATH}' fehlt, es gibt aber auch "
                    "keine getrackten Dateien ausserhalb der Factory-Pfade -- kein "
                    "Produktcode, also nichts zu konfigurieren.",
                    "Sobald Produktcode dazukommt, wird die Datei Pflicht.",
                ],
            )

        return (
            EXIT_BLOCKED,
            STATE_REAL_PROJECT_WITHOUT_TEST_CONFIGURATION,
            [
                f"PROJECT_TESTS: {STATE_REAL_PROJECT_WITHOUT_TEST_CONFIGURATION}",
                f"blocker: '{CONFIG_RELATIVE_PATH}' fehlt, aber es gibt "
                f"{len(product_files)} getrackte Datei(en) ausserhalb der "
                "Factory-Pfade.",
                "  z. B.: " + ", ".join(product_files[:3]),
                "Ohne diese Datei ist nicht bestimmbar, welche Produkttests als "
                "gueltige Verification gelten -- und 'nicht bestimmbar' ist kein "
                "bestandener Test.",
            ],
        )

    try:
        config = parse_config(path.read_text(encoding="utf-8"))
        product_files = tracked_product_files(repo_root)
    except ConfigError as exc:
        return (
            EXIT_BLOCKED,
            STATE_REAL_PROJECT_WITHOUT_TEST_CONFIGURATION,
            [
                f"PROJECT_TESTS: {STATE_REAL_PROJECT_WITHOUT_TEST_CONFIGURATION}",
                f"blocker: {exc}",
            ],
        )

    state = classify(repo_root, config, product_files)

    if state == STATE_TEMPLATE_WITHOUT_PRODUCT:
        return (
            EXIT_OK,
            state,
            [
                f"PROJECT_TESTS: {STATE_TEMPLATE_WITHOUT_PRODUCT}",
                "Keine getrackten Dateien ausserhalb der Factory-Pfade und "
                "'mode: template' -- eine reine Kopie der Vorlage ohne Produktcode.",
                "Das ist der EINZIGE Zustand, in dem null Produkttests als bestanden "
                "gelten. Sobald Produktcode dazukommt, ist eine Testkonfiguration "
                "Pflicht (siehe factory/ONBOARDING.md).",
            ],
        )

    if state == STATE_REAL_PROJECT_WITHOUT_TEST_CONFIGURATION:
        detail = (
            f"{len(product_files)} getrackte Datei(en) ausserhalb der "
            "Factory-Pfade gefunden, aber keine Suite konfiguriert."
            if product_files
            else "'mode: real-project' deklariert, aber keine Suite konfiguriert."
        )
        example = product_files[:3]
        lines = [
            f"PROJECT_TESTS: {STATE_REAL_PROJECT_WITHOUT_TEST_CONFIGURATION}",
            f"blocker: {detail}",
        ]
        if example:
            lines.append("  z. B.: " + ", ".join(example))
        lines.append(
            f"Trage die Testkommandos des Projekts in '{CONFIG_RELATIVE_PATH}' ein. "
            "Diese Datei ist Control Plane: die Aenderung ist ein FACTORY_CHANGE und "
            "wird einmalig beim Onboarding gemacht, nicht waehrend normaler "
            "Finding-Arbeit."
        )
        return (EXIT_BLOCKED, state, lines)

    return (None, state, [])


def main(argv):
    repo_root = REPO_ROOT
    exit_code, state, lines = evaluate(repo_root)

    for line in lines:
        print(line)
    if exit_code is not None:
        return exit_code

    config = parse_config((repo_root / CONFIG_RELATIVE_PATH).read_text(encoding="utf-8"))
    suites = config["suites"]
    print(f"PROJECT_TESTS: {STATE_CONFIGURED} ({len(suites)} Suite(n))")

    failures = []
    for suite in suites:
        code = run_suite(suite, repo_root)
        if code == 0:
            print(f"  [OK]   Suite '{suite.name}'")
        else:
            print(f"  [FAIL] Suite '{suite.name}': Exit {code}")
            failures.append((suite.name, code))

    print(f"project_tests_suites: {len(suites)}")
    print(f"project_tests_failed: {len(failures)}")

    if failures:
        # Every failing suite is named. A later red suite is never hidden by an
        # earlier green one -- all suites run, and all failures are reported.
        for name, code in failures:
            print(f"  fehlgeschlagen: {name} (Exit {code})")
        print("PROJECT_TESTS: FAILED")
        return EXIT_TESTS_FAILED

    print("PROJECT_TESTS: PASSED")
    return EXIT_OK


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.exit(main(sys.argv))
