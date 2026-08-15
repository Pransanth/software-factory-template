#!/usr/bin/env python3
"""Regression tests for the generic product-test adapter (audit finding F-21).

Every test builds a real throwaway git repository in a temp dir and runs the
adapter against it. Nothing here assumes the product is written in Python --
that assumption IS the bug this file guards against, so the "product" in these
tests is a shell script or a plain executable, never a `test_*.py`.

Before the repair, `run-project-tests.py` searched for `app/**/test_*.py`. A Go
project with a deliberately failing test produced:

    Keine Tests unter <repo>/app gefunden -- nichts zu pruefen.
    EXIT=0

`test_non_python_product_with_a_failing_test_is_not_reported_as_green` is the
direct regression for exactly that observation.
"""
import importlib.util
import os
import stat
import subprocess
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

GUARDS_DIR = Path(__file__).resolve().parent
REPO_ROOT = GUARDS_DIR.parents[1]


def _load_project_tests():
    spec = importlib.util.spec_from_file_location(
        "project_tests_under_test", GUARDS_DIR / "project_tests.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pt = _load_project_tests()


def _git(repo, *args):
    result = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True
    )
    if result.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} fehlgeschlagen: {result.stderr.strip()}"
        )
    return result


class AdapterTestCase(unittest.TestCase):
    """Builds a throwaway repository with a factory-shaped layout."""

    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name) / "repo"
        (self.repo / "factory" / "guards").mkdir(parents=True)
        (self.repo / ".claude").mkdir()
        (self.repo / "CLAUDE.md").write_text("# factory\n", encoding="utf-8")
        _git(self.repo.parent, "init", "-q", "repo")
        _git(self.repo, "config", "user.email", "t@example.invalid")
        _git(self.repo, "config", "user.name", "Test")
        self.addCleanup(self._tmp.cleanup)

    def write_config(self, text):
        (self.repo / "factory" / "project-tests.conf").write_text(
            text, encoding="utf-8"
        )

    def add_product_file(self, relative_path, content="x\n"):
        path = self.repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def make_executable(self, relative_path, body, exit_code=0):
        path = self.repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"#!/bin/sh\n{body}\nexit {exit_code}\n", encoding="utf-8"
        )
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
        return path

    def commit_all(self):
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "state")

    def run_adapter(self):
        """Run the adapter's main() with REPO_ROOT pointed at the temp repo."""
        original = pt.REPO_ROOT
        pt.REPO_ROOT = self.repo
        try:
            return pt.main(["run-project-tests.py"])
        finally:
            pt.REPO_ROOT = original


class TemplateStateTests(AdapterTestCase):
    def test_template_without_product_is_the_only_green_zero_test_state(self):
        self.write_config("mode: template\n")
        self.commit_all()
        code, state, lines = pt.evaluate(self.repo)
        self.assertEqual(code, pt.EXIT_OK)
        self.assertEqual(state, pt.STATE_TEMPLATE_WITHOUT_PRODUCT)
        # The state must be stated in the clear, not merely implied by exit 0.
        self.assertTrue(
            any(pt.STATE_TEMPLATE_WITHOUT_PRODUCT in line for line in lines),
            lines,
        )

    def test_template_declaration_with_product_code_is_blocked(self):
        """Copying the factory into a real project and leaving `mode: template`
        must not silently keep the free pass."""
        self.write_config("mode: template\n")
        self.add_product_file("src/server.go", "package main\n")
        self.commit_all()
        code, state, _ = pt.evaluate(self.repo)
        self.assertEqual(code, pt.EXIT_BLOCKED)
        self.assertEqual(state, pt.STATE_REAL_PROJECT_WITHOUT_TEST_CONFIGURATION)


class MissingConfigurationTests(AdapterTestCase):
    def test_real_project_without_configuration_is_a_hard_blocker(self):
        self.write_config("mode: real-project\n")
        self.add_product_file("cmd/main.go", "package main\n")
        self.commit_all()
        code, state, lines = pt.evaluate(self.repo)
        self.assertEqual(code, pt.EXIT_BLOCKED)
        self.assertEqual(state, pt.STATE_REAL_PROJECT_WITHOUT_TEST_CONFIGURATION)
        self.assertTrue(any("blocker:" in line for line in lines), lines)

    def test_missing_configuration_file_with_product_code_is_never_a_pass(self):
        self.add_product_file("cmd/main.go", "package main\n")
        self.commit_all()
        code, state, lines = pt.evaluate(self.repo)
        self.assertEqual(code, pt.EXIT_BLOCKED)
        self.assertEqual(state, pt.STATE_REAL_PROJECT_WITHOUT_TEST_CONFIGURATION)
        self.assertTrue(any("fehlt" in line for line in lines), lines)

    def test_missing_configuration_without_product_code_is_a_template(self):
        """A factory-shaped repository with no product owes no test answer yet.

        Blocking here would fail every throwaway repository the factory's own
        tests build, for a question that does not apply to them. This is not a
        way around the requirement: reaching this state in a real project would
        mean deleting all product code, and the configuration file is part of
        the control plane, so removing it shows up as a manifest diff.
        """
        self.commit_all()
        code, state, _ = pt.evaluate(self.repo)
        self.assertEqual(code, pt.EXIT_OK)
        self.assertEqual(state, pt.STATE_TEMPLATE_WITHOUT_PRODUCT)

    def test_adding_product_code_turns_that_template_into_a_blocker(self):
        """The pair that matters: same missing file, different obligation."""
        self.commit_all()
        self.assertEqual(pt.evaluate(self.repo)[0], pt.EXIT_OK)
        self.add_product_file("cmd/main.go", "package main\n")
        self.commit_all()
        self.assertEqual(pt.evaluate(self.repo)[0], pt.EXIT_BLOCKED)

    def test_real_project_mode_without_suites_blocks_even_without_product_files(self):
        self.write_config("mode: real-project\n")
        self.commit_all()
        code, state, _ = pt.evaluate(self.repo)
        self.assertEqual(code, pt.EXIT_BLOCKED)
        self.assertEqual(state, pt.STATE_REAL_PROJECT_WITHOUT_TEST_CONFIGURATION)


class ConfiguredSuiteTests(AdapterTestCase):
    def test_a_single_green_suite_passes(self):
        self.make_executable("tools/ok.sh", "echo gruen", exit_code=0)
        self.write_config(
            "mode: real-project\n\n[suite: unit]\ncommand: ./tools/ok.sh\n"
        )
        self.add_product_file("cmd/main.go", "package main\n")
        self.commit_all()
        self.assertEqual(self.run_adapter(), pt.EXIT_OK)

    def test_a_single_red_suite_fails(self):
        self.make_executable("tools/bad.sh", "echo rot", exit_code=1)
        self.write_config(
            "mode: real-project\n\n[suite: unit]\ncommand: ./tools/bad.sh\n"
        )
        self.add_product_file("cmd/main.go", "package main\n")
        self.commit_all()
        self.assertEqual(self.run_adapter(), pt.EXIT_TESTS_FAILED)

    def test_multiple_suites_all_run(self):
        marker_a = self.repo / "ran_a"
        marker_b = self.repo / "ran_b"
        self.make_executable("tools/a.sh", f"touch {marker_a}", exit_code=0)
        self.make_executable("tools/b.sh", f"touch {marker_b}", exit_code=0)
        self.write_config(
            "mode: real-project\n\n"
            "[suite: a]\ncommand: ./tools/a.sh\n\n"
            "[suite: b]\ncommand: ./tools/b.sh\n"
        )
        self.add_product_file("cmd/main.go", "package main\n")
        self.commit_all()
        self.assertEqual(self.run_adapter(), pt.EXIT_OK)
        self.assertTrue(marker_a.exists(), "erste Suite lief nicht")
        self.assertTrue(marker_b.exists(), "zweite Suite lief nicht")

    def test_second_suite_red_makes_the_whole_run_fail(self):
        """A later red suite must never be hidden by an earlier green one."""
        marker = self.repo / "ran_second"
        self.make_executable("tools/green.sh", "echo ok", exit_code=0)
        self.make_executable("tools/red.sh", f"touch {marker}", exit_code=3)
        self.write_config(
            "mode: real-project\n\n"
            "[suite: green]\ncommand: ./tools/green.sh\n\n"
            "[suite: red]\ncommand: ./tools/red.sh\n"
        )
        self.add_product_file("cmd/main.go", "package main\n")
        self.commit_all()
        self.assertEqual(self.run_adapter(), pt.EXIT_TESTS_FAILED)
        self.assertTrue(marker.exists(), "die zweite Suite wurde gar nicht ausgefuehrt")

    def test_workdir_is_honoured(self):
        marker = self.repo / "service" / "ran_here"
        self.make_executable("service/run.sh", f"touch {marker}", exit_code=0)
        self.write_config(
            "mode: real-project\n\n"
            "[suite: svc]\ncommand: ./run.sh\nworkdir: service\n"
        )
        self.add_product_file("cmd/main.go", "package main\n")
        self.commit_all()
        self.assertEqual(self.run_adapter(), pt.EXIT_OK)
        self.assertTrue(marker.exists())

    def test_unrunnable_command_is_blocked_not_passed(self):
        self.write_config(
            "mode: real-project\n\n"
            "[suite: missing]\ncommand: ./does-not-exist.sh\n"
        )
        self.add_product_file("cmd/main.go", "package main\n")
        self.commit_all()
        self.assertEqual(self.run_adapter(), pt.EXIT_TESTS_FAILED)


class NonPythonRegressionTests(AdapterTestCase):
    def test_non_python_product_with_a_failing_test_is_not_reported_as_green(self):
        """The exact scenario observed red against the pre-repair guard.

        A Go product tree with a deliberately failing test used to produce
        "Keine Tests ... gefunden" and exit 0. Now it either runs the declared
        command (and fails) or blocks for a missing configuration -- but it can
        never be a silent pass.
        """
        self.add_product_file("app/cmd/main.go", "package main\n\nfunc main() {}\n")
        self.add_product_file(
            "app/cmd/main_test.go",
            'package main\n\nimport "testing"\n\n'
            'func TestBroken(t *testing.T) { t.Fatal("rot") }\n',
        )
        self.write_config("mode: template\n")
        self.commit_all()

        code, state, _ = pt.evaluate(self.repo)
        self.assertNotEqual(code, pt.EXIT_OK, "das alte stille Gruen ist zurueck")
        self.assertEqual(state, pt.STATE_REAL_PROJECT_WITHOUT_TEST_CONFIGURATION)

    def test_adapter_contains_no_python_test_discovery(self):
        """No filename heuristic may creep back in as a security argument."""
        source = (GUARDS_DIR / "project_tests.py").read_text(encoding="utf-8")
        # Only the docstring may mention the old pattern, as history. The code
        # must not glob for it.
        code_lines = [
            line
            for line in source.splitlines()
            if "rglob" in line or "glob(" in line
        ]
        self.assertEqual(
            code_lines, [], f"Datei-Heuristik im Adapter gefunden: {code_lines}"
        )


class ShellSafetyTests(AdapterTestCase):
    def test_shell_metacharacters_are_rejected(self):
        for command in (
            "sh -c true | tee x",
            "true; rm -rf /",
            "true && false",
            "echo $HOME",
            "echo `id`",
            "true > out",
        ):
            with self.subTest(command=command):
                with self.assertRaises(pt.ConfigError):
                    pt.parse_config(
                        f"mode: real-project\n\n[suite: s]\ncommand: {command}\n"
                    )

    def test_commands_are_argument_lists_not_shell_strings(self):
        config = pt.parse_config(
            "mode: real-project\n\n"
            '[suite: s]\ncommand: pytest -q "tests/with space"\n'
        )
        self.assertEqual(
            config["suites"][0].argv, ["pytest", "-q", "tests/with space"]
        )

    def test_no_subprocess_call_uses_shell(self):
        source = (GUARDS_DIR / "project_tests.py").read_text(encoding="utf-8")
        self.assertNotIn("shell=True", source)


class ConfigParsingTests(AdapterTestCase):
    def test_mode_is_required(self):
        with self.assertRaises(pt.ConfigError):
            pt.parse_config("[suite: s]\ncommand: true\n")

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(pt.ConfigError):
            pt.parse_config("mode: whatever\n")

    def test_suite_without_command_is_rejected(self):
        with self.assertRaises(pt.ConfigError):
            pt.parse_config("mode: real-project\n\n[suite: s]\nworkdir: app\n")

    def test_two_commands_in_one_suite_are_rejected(self):
        """Two commands in one suite would hide one result behind the other."""
        with self.assertRaises(pt.ConfigError):
            pt.parse_config(
                "mode: real-project\n\n[suite: s]\ncommand: true\ncommand: false\n"
            )

    def test_unknown_key_is_rejected(self):
        with self.assertRaises(pt.ConfigError):
            pt.parse_config("mode: real-project\n\n[suite: s]\ncmd: true\n")

    def test_comments_and_blank_lines_are_ignored(self):
        config = pt.parse_config(
            "# Kopfkommentar\n\nmode: real-project\n\n"
            "# eine Suite\n[suite: s]\ncommand: true\n"
        )
        self.assertEqual(config["mode"], "real-project")
        self.assertEqual(len(config["suites"]), 1)


class ThisRepositoryTests(unittest.TestCase):
    """The factory template itself must stay in the documented template state."""

    def test_template_repository_reports_template_without_product(self):
        code, state, lines = pt.evaluate(REPO_ROOT)
        self.assertEqual(
            state,
            pt.STATE_TEMPLATE_WITHOUT_PRODUCT,
            f"Vorlage nicht im erwarteten Zustand: {lines}",
        )
        self.assertEqual(code, pt.EXIT_OK)

    def test_configuration_file_exists_and_is_control_plane(self):
        config_path = REPO_ROOT / pt.CONFIG_RELATIVE_PATH
        self.assertTrue(config_path.is_file(), "factory/project-tests.conf fehlt")
        manifest = (REPO_ROOT / "factory" / "control-plane.sha256").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            pt.CONFIG_RELATIVE_PATH,
            manifest,
            "Die Testkonfiguration steht nicht im Control-Plane-Manifest -- sie "
            "waere damit waehrend normaler Finding-Arbeit veraenderbar.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
