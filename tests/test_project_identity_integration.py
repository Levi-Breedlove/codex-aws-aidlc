from __future__ import annotations

import html
import json
import shutil
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from unittest import mock

import bootstrap
from scripts import bootstrap_doctor
from scripts.fastlane_project_identity import (
    normalize_aws_region,
    normalize_project_name,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def copy_configured_project(destination: Path, project_name: str) -> Path:
    project = destination / "project"
    project.mkdir()
    manifest = json.loads(
        (REPOSITORY_ROOT / "bootstrap.manifest.json").read_text(encoding="utf-8")
    )
    for relative in manifest["required_files"]:
        source = REPOSITORY_ROOT.joinpath(*PurePosixPath(relative).parts)
        target = project.joinpath(*PurePosixPath(relative).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    values = dict(bootstrap.PLACEHOLDERS)
    values.update(
        {
            "{{PROJECT_NAME}}": normalize_project_name(project_name),
            "{{AWS_REGION}}": normalize_aws_region("US-WEST-2"),
            "{{COST_POSTURE}}": "MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED",
        }
    )
    for relative in manifest["required_files"]:
        if not bootstrap.should_render_path(relative):
            continue
        path = project.joinpath(*PurePosixPath(relative).parts)
        rendered = bootstrap.rendered_bytes(
            path,
            values,
            relative=relative,
            render=True,
        )
        if rendered != path.read_bytes():
            path.write_bytes(rendered)
    return project


class ProjectIdentityIntegrationTests(unittest.TestCase):
    def test_copy_encodes_json_and_markdown_without_changing_owner_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            target = root / "target"
            (source / "docs" / "project").mkdir(parents=True)
            (source / "bootstrap.yaml").write_text(
                '{"project":{"name":"{{PROJECT_NAME}}","region":"{{AWS_REGION}}"}}',
                encoding="utf-8",
            )
            (source / "docs" / "project" / "PRD.md").write_text(
                "| Workload | {{PROJECT_NAME}} |\n"
                "| Primary Region | {{AWS_REGION}} |\n",
                encoding="utf-8",
            )
            owner_name = (
                'Café "Home" \\ A | <demo> [x] *safe* & Sons `code` '
                "[link](https://example.invalid)"
            )
            values = {
                "{{PROJECT_NAME}}": normalize_project_name(owner_name),
                "{{AWS_REGION}}": normalize_aws_region(" US-WEST-2 "),
            }

            report = bootstrap.copy_template(source, target, values)

            self.assertEqual(report.written, 2)
            state = json.loads((target / "bootstrap.yaml").read_text(encoding="utf-8"))
            self.assertEqual(state["project"]["name"], owner_name)
            self.assertEqual(state["project"]["region"], "us-west-2")
            prd = (target / "docs" / "project" / "PRD.md").read_text(encoding="utf-8")
            workload_line = next(
                line for line in prd.splitlines() if line.startswith("| Workload | ")
            )
            encoded_workload = workload_line.removeprefix("| Workload | ").removesuffix(
                " |"
            )
            self.assertEqual(
                html.unescape(encoded_workload),
                owner_name,
            )

    def test_direct_copy_rejects_invalid_identity_before_creating_target(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            (source / "PRD.md").write_text(
                "{{PROJECT_NAME}} {{AWS_REGION}}", encoding="utf-8"
            )

            with self.assertRaises(ValueError):
                bootstrap.copy_template(
                    source,
                    target,
                    {
                        "{{PROJECT_NAME}}": "line\nbreak",
                        "{{AWS_REGION}}": "us-west-2",
                    },
                )

            self.assertFalse(target.exists())

    def test_cli_rejects_invalid_identity_before_dependency_or_write_checks(
        self,
    ) -> None:
        with mock.patch.object(
            bootstrap, "validate_repository_dependencies"
        ) as validate:
            result = bootstrap.main(
                [
                    "--target",
                    "unused",
                    "--project-name",
                    "hidden\u202evalue",
                    "--region",
                    "us-west-2",
                    "--dry-run",
                ]
            )

        self.assertEqual(result, 2)
        validate.assert_not_called()

        with mock.patch.object(
            bootstrap, "validate_repository_dependencies"
        ) as validate:
            result = bootstrap.main(
                [
                    "--target",
                    "unused",
                    "--project-name",
                    "Valid Project",
                    "--region",
                    "us-west-2-lax-1",
                    "--dry-run",
                ]
            )

        self.assertEqual(result, 2)
        validate.assert_not_called()

    def test_engine_normalizes_crlf_after_enforcing_raw_byte_limits(self) -> None:
        owner_name = "Cross-platform project"
        with tempfile.TemporaryDirectory() as temporary:
            project = copy_configured_project(Path(temporary), owner_name)
            for relative in (
                "docs/project/PRD.md",
                "docs/project/TASKS.md",
                "docs/project/VERIFY.md",
            ):
                path = project.joinpath(*PurePosixPath(relative).parts)
                raw = path.read_bytes()
                path.write_bytes(raw.replace(b"\n", b"\r\n"))

            report = bootstrap_doctor.inspect_project(project)
            codes = {item["code"] for item in report["diagnostics"]}
            self.assertNotIn("PRD_STRUCTURE", codes)
            self.assertNotIn("TASK_SNAPSHOT", codes)
            self.assertNotIn("STATE_PRD_DRIFT", codes)
            self.assertNotIn("STATE_VERIFY_DRIFT", codes)

    def test_engine_accepts_encoded_name_and_detects_identity_drift(self) -> None:
        owner_name = "Café \\ Home | [private] & safe"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = copy_configured_project(root, owner_name)
            report = bootstrap_doctor.inspect_project(project)
            codes = {item["code"] for item in report["diagnostics"]}
            self.assertNotIn("PROJECT_IDENTITY", codes)
            self.assertNotIn("STATE_PRD_DRIFT", codes)
            self.assertNotIn("STATE_VERIFY_DRIFT", codes)
            self.assertNotIn("PLACEHOLDER_UNRESOLVED", codes)

            state_path = project / "bootstrap.yaml"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["project"]["name"] = "line\nbreak"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            invalid = bootstrap_doctor.inspect_project(project)
            invalid_codes = {item["code"] for item in invalid["diagnostics"]}
            self.assertIn("PROJECT_IDENTITY", invalid_codes)

            state["project"]["name"] = owner_name
            state["project"]["region"] = "us-west-2-lax-1"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            invalid_region = bootstrap_doctor.inspect_project(project)
            region_codes = {item["code"] for item in invalid_region["diagnostics"]}
            self.assertIn("PROJECT_IDENTITY", region_codes)

        with tempfile.TemporaryDirectory() as temporary:
            project = copy_configured_project(Path(temporary), owner_name)
            prd_path = project / "docs" / "project" / "PRD.md"
            encoded_name = bootstrap.markdown_inline(owner_name)
            prd = prd_path.read_text(encoding="utf-8").replace(
                f"| Workload | {encoded_name} |",
                "| Workload | Different Project |",
                1,
            )
            prd_path.write_text(prd, encoding="utf-8", newline="\n")
            drift = bootstrap_doctor.inspect_project(project)
            drift_codes = {item["code"] for item in drift["diagnostics"]}
            self.assertIn("STATE_PRD_DRIFT", drift_codes)

        with tempfile.TemporaryDirectory() as temporary:
            project = copy_configured_project(Path(temporary), owner_name)
            verify_path = project / "docs" / "project" / "VERIFY.md"
            encoded_name = bootstrap.markdown_inline(owner_name)
            verify = verify_path.read_text(encoding="utf-8").replace(
                f"| Workload | {encoded_name} |",
                "| Workload | Different Project |",
                1,
            )
            verify_path.write_text(verify, encoding="utf-8", newline="\n")
            drift = bootstrap_doctor.inspect_project(project)
            drift_codes = {item["code"] for item in drift["diagnostics"]}
            self.assertIn("STATE_VERIFY_DRIFT", drift_codes)


if __name__ == "__main__":
    unittest.main()
