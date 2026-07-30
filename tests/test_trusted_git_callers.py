from __future__ import annotations

import ast
import subprocess
import unittest
from pathlib import Path
from unittest import mock

import bootstrap
from scripts import bootstrap_doctor, maintenance_preflight, package_release, task_waves


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TRUSTED_GIT = str((REPOSITORY_ROOT.parent / "trusted-tools" / "git.exe").resolve())


class TrustedGitCallerTests(unittest.TestCase):
    def test_every_runtime_wrapper_passes_an_absolute_resolved_git_path(self) -> None:
        binary_result = subprocess.CompletedProcess([], 0, stdout=b"", stderr=b"")
        text_result = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        cases = (
            (bootstrap, bootstrap.git_text, text_result, (REPOSITORY_ROOT, "status")),
            (
                maintenance_preflight,
                maintenance_preflight._git,
                text_result,
                (REPOSITORY_ROOT, "status"),
            ),
            (
                package_release,
                package_release._git_bytes,
                binary_result,
                (REPOSITORY_ROOT, "show", "HEAD:README.md"),
            ),
            (
                task_waves,
                task_waves.git_read,
                binary_result,
                (REPOSITORY_ROOT, "status"),
            ),
            (
                bootstrap_doctor,
                bootstrap_doctor.git_read,
                binary_result,
                (REPOSITORY_ROOT, "status"),
            ),
            (
                bootstrap_doctor,
                bootstrap_doctor.inspect_git_baseline,
                subprocess.CompletedProcess([], 0, stdout="a" * 40, stderr=""),
                (REPOSITORY_ROOT,),
            ),
        )
        for module, function, completed, arguments in cases:
            with (
                self.subTest(function=function.__name__),
                mock.patch.object(
                    module, "resolve_trusted_git", return_value=TRUSTED_GIT
                ) as resolve,
                mock.patch.object(
                    module.subprocess, "run", return_value=completed
                ) as run,
            ):
                function(*arguments)
                resolve.assert_called_once_with(arguments[0])
                argv = run.call_args.args[0]
                self.assertEqual(argv[0], TRUSTED_GIT)
                self.assertTrue(Path(argv[0]).is_absolute())

    def test_unsafe_git_resolution_prevents_every_subprocess(self) -> None:
        cases = (
            (bootstrap, bootstrap.git_text, (REPOSITORY_ROOT, "status"), ValueError),
            (
                maintenance_preflight,
                maintenance_preflight._git,
                (REPOSITORY_ROOT, "status"),
                OSError,
            ),
            (
                package_release,
                package_release._git_bytes,
                (REPOSITORY_ROOT, "show", "HEAD:README.md"),
                package_release.PackagingError,
            ),
            (
                task_waves,
                task_waves.git_read,
                (REPOSITORY_ROOT, "status"),
                OSError,
            ),
            (
                bootstrap_doctor,
                bootstrap_doctor.git_read,
                (REPOSITORY_ROOT, "status"),
                OSError,
            ),
        )
        for module, function, arguments, error in cases:
            with (
                self.subTest(function=function.__name__),
                mock.patch.object(
                    module,
                    "resolve_trusted_git",
                    side_effect=OSError(
                        "Trusted Git executable is unavailable or unsafe"
                    ),
                ),
                mock.patch.object(module.subprocess, "run") as run,
                self.assertRaises(error),
            ):
                function(*arguments)
            run.assert_not_called()

        with (
            mock.patch.object(
                bootstrap_doctor,
                "resolve_trusted_git",
                side_effect=OSError("Trusted Git executable is unavailable or unsafe"),
            ),
            mock.patch.object(bootstrap_doctor.subprocess, "run") as run,
        ):
            self.assertEqual(
                bootstrap_doctor.inspect_git_baseline(REPOSITORY_ROOT), "PENDING"
            )
            run.assert_not_called()

    def test_production_git_subprocesses_never_use_a_bare_literal(self) -> None:
        relative_paths = ["bootstrap.py"]
        relative_paths.extend(
            path.relative_to(REPOSITORY_ROOT).as_posix()
            for path in sorted((REPOSITORY_ROOT / "scripts").glob("*.py"))
        )
        relative_paths.extend(
            path.relative_to(REPOSITORY_ROOT).as_posix()
            for path in sorted((REPOSITORY_ROOT / ".codex" / "hooks").glob("*.py"))
        )
        violations: list[str] = []
        for relative in relative_paths:
            tree = ast.parse(
                (REPOSITORY_ROOT / relative).read_text(encoding="utf-8"),
                filename=relative,
            )
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                function = node.func
                if not (
                    isinstance(function, ast.Attribute)
                    and function.attr == "run"
                    and isinstance(function.value, ast.Name)
                    and function.value.id == "subprocess"
                ):
                    continue
                argv = node.args[0]
                if (
                    isinstance(argv, (ast.List, ast.Tuple))
                    and argv.elts
                    and isinstance(argv.elts[0], ast.Constant)
                    and argv.elts[0].value == "git"
                ):
                    violations.append(f"{relative}:{node.lineno}")
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
