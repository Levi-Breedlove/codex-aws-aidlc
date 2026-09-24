from __future__ import annotations

import unittest

from tests.alpha_project_fixture import (
    no_persistent_data_details,
    complete_alpha_design,
)

from scripts import bootstrap_doctor as doctor
from scripts.fastlane_engine import owner_decisions
from scripts.fastlane_engine.project_delivery_validation import (
    task_command_boundary_issues,
)
from scripts.fastlane_engine.owner_decision_sections import (
    design8_owner_decision_additions,
)
from scripts.fastlane_engine.design import (
    DEPENDENCY_EVIDENCE_DESTINATION,
    command_matches_prefix,
    dependency_command_allowed,
)
from tests.test_bootstrap_doctor import (
    PROJECT_ROOT,
    complete_design_contract,
    replace_contract_table,
)


def complete_design8() -> str:
    return complete_design_contract(
        (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
    )


def dependency_table(**overrides: str) -> str:
    headers = doctor.DEPENDENCY_POLICY_HEADERS
    digest = "b" * 64
    source = "https://files.pythonhosted.org/packages/ruff-0.16.0-py3-none-any.whl"
    row = [
        "DEP-001",
        "TECH-0005",
        "TOOLING",
        "PYPI: ruff",
        "0.16.0",
        source,
        "NOT_APPLICABLE — direct wheel digest is command-bound; no lockfile mutation",
        f"SHA256: {digest}",
        "DENY_BUILD_HOOKS — wheel-only direct install",
        "ALLOW_HTTPS: files.pythonhosted.org",
        "SPDX: MIT; ALLOWED",
        "python -m pip install --no-deps --only-binary=:all: --no-index "
        f'"ruff @ {source}#sha256={digest}"',
        DEPENDENCY_EVIDENCE_DESTINATION,
    ]
    for field, value in overrides.items():
        row[headers.index(field)] = value
    return "\n".join(
        (
            "| " + " | ".join(headers) + " |",
            "|" + "---|" * len(headers),
            "| " + " | ".join(row) + " |",
        )
    )


def markdown_table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    return "\n".join(
        (
            "| " + " | ".join(headers) + " |",
            "|" + "---|" * len(headers),
            *("| " + " | ".join(row) + " |" for row in rows),
        )
    )


def replace_table_with_line(text: str, heading: str, line: str) -> str:
    start = text.index(heading)
    table_start = text.index("|", start)
    table_end = text.index("\n\n", table_start)
    return text[:table_start] + line + text[table_end:]


def design8_over_approved_requirements14() -> str:
    source = (PROJECT_ROOT / "tests/fixtures/legacy_1234_pre_aws_prd.md").read_text(
        encoding="utf-8"
    )
    source = source.replace(
        "| Project design contract schema | `7` |",
        "| Project design contract schema | `8` |",
        1,
    )
    source = source.replace(
        "### State view",
        f"{doctor.DATASET_IMPLEMENTATION_HEADING}\n\n"
        f"{doctor.DATASET_IMPLEMENTATION_NONE}\n\n### State view",
        1,
    )
    environment = markdown_table(
        doctor.ENVIRONMENT_PROMOTION_HEADERS,
        [
            (
                "ENV-001",
                "LOCAL",
                "Preserve the approved local outcome",
                "Local development; no AWS authority",
                "IMMUTABLE: approved source commit and package digest",
                "Local configuration; no stored secrets; synthetic data",
                "NONE",
                "Current Gate B and required local Harness evidence",
                "Restore the approved baseline and remove local fixtures",
                "DES-0001, FR-001",
                "HARNESS-004",
            )
        ],
    )
    source = source.replace(
        "### First construction wave",
        f"{doctor.ENVIRONMENT_PROMOTION_HEADING}\n\n{environment}\n\n"
        "### First construction wave",
        1,
    )
    considerations = markdown_table(
        doctor.WELL_ARCHITECTED_HEADERS,
        [
            (
                pillar,
                "APPLICABLE",
                "FR-001",
                "ARCH-0001, TECH-0001",
                f"{pillar} tradeoffs remain bounded by the approved local outcome",
                "Keep the selected architecture and exact Harness checks current",
                "AWS-EV-0001, HARNESS-004",
                "SOURCE_VERIFIED",
                "Revisit when the target, risk, or selected design changes",
            )
            for pillar in doctor.WELL_ARCHITECTED_PILLARS
        ],
    )
    start = source.index("### Lightweight Well-Architected decision review")
    end = source.index("## 21. Implementation boundaries and order", start)
    source = (
        source[:start]
        + f"{doctor.WELL_ARCHITECTED_HEADING}\n\n"
        + doctor.WELL_ARCHITECTED_DISCLAIMER
        + "\n\n"
        + considerations
        + "\n\n"
        + source[end:]
    )
    source = source.replace(
        "This table is the complete bounded local-construction authority presented at Gate B.",
        "This table is the complete bounded local-construction authority presented at Gate B.\n\n"
        f"{doctor.DEPENDENCY_POLICY_HEADING}\n\n"
        f"{doctor.DEPENDENCY_ACQUISITION_NONE}",
        1,
    )
    return source


class Design8ContractTests(unittest.TestCase):
    def derive(self, text: str):
        return doctor.derive_design_contract(text, "DES-0001", required=True)

    def test_complete_projection_is_typed_and_every_table_is_digest_bound(self) -> None:
        source = complete_design8()
        baseline, issues = self.derive(source)
        self.assertEqual(issues, [])
        self.assertEqual(baseline.schema_version, 9)
        self.assertEqual(baseline.status, "READY")
        extension = baseline.project_contract.design_v8
        self.assertEqual(extension.status, "READY")
        self.assertEqual(
            [item.dataset_id for item in extension.dataset_implementations],
            ["DATASET-001"],
        )
        self.assertEqual(
            [item.environment_id for item in extension.environments], ["ENV-001"]
        )
        self.assertEqual(
            [item.pillar for item in extension.well_architected],
            list(doctor.WELL_ARCHITECTED_PILLARS),
        )
        self.assertTrue(extension.acquisition_prohibited)
        self.assertIsNotNone(extension.canonical_sha256)

        mutations = (
            source.replace(
                "Amazon DynamoDB owner-record component behind the local adapter",
                "Versioned owner-record component behind the local adapter",
                1,
            ),
            source.replace(
                "Validate the approved walking skeleton with synthetic fixtures",
                "Validate the approved local outcome with synthetic fixtures",
                1,
            ),
            source.replace(
                "Operational Excellence consequences are planned",
                "Operational Excellence tradeoffs are planned",
                1,
            ),
            source.replace(doctor.DEPENDENCY_ACQUISITION_NONE, dependency_table(), 1),
        )
        for candidate_text in mutations:
            with self.subTest(marker=candidate_text != source):
                candidate, candidate_issues = self.derive(candidate_text)
                self.assertEqual(candidate_issues, [])
                self.assertEqual(candidate.status, "READY")
                self.assertNotEqual(
                    candidate.project_contract.canonical_sha256,
                    baseline.project_contract.canonical_sha256,
                )
                self.assertNotEqual(
                    candidate.canonical_sha256, baseline.canonical_sha256
                )

    def test_dataset_mapping_is_an_exact_requirements_bijection(self) -> None:
        source = complete_design8()
        for rows, expected in (
            ([], "rows must exactly match current Requirements datasets"),
            (
                [
                    (
                        "DATASET-999",
                        "Store",
                        "ARCH-0001, TECH-0011",
                        "Server-side access and encryption",
                        "Bounded retention and deletion",
                        "Recreate fixtures",
                        "Approved geography and migration",
                        "Audit without sensitive values",
                        "AC-DATA-001, HARNESS-003",
                    )
                ],
                "rows must exactly match current Requirements datasets",
            ),
        ):
            with self.subTest(rows=rows):
                changed = replace_contract_table(
                    source,
                    doctor.DATASET_IMPLEMENTATION_HEADING,
                    doctor.DATASET_IMPLEMENTATION_HEADERS,
                    rows,
                )
                contract, issues = self.derive(changed)
                self.assertEqual(contract.status, "BLOCKED")
                self.assertTrue(any(expected in item for item in issues), issues)

    def test_canonical_no_persistent_data_uses_the_no_mapping_sentinel(self) -> None:
        source = complete_design8()
        source = replace_contract_table(
            source,
            doctor.DATASET_HEADING,
            doctor.DATASET_HEADERS,
            [
                (
                    "DATASET-001",
                    "NO PERSISTENT DATA",
                    "NONE",
                    "NONE",
                    "NONE",
                    "NONE",
                    "NONE",
                    "NONE",
                    "NONE",
                    "NONE",
                    "NONE",
                    "NONE",
                    "NONE",
                    "NONE",
                )
            ],
        )
        source = complete_alpha_design(no_persistent_data_details(source))
        source = replace_table_with_line(
            source,
            doctor.DATASET_IMPLEMENTATION_HEADING,
            doctor.DATASET_IMPLEMENTATION_NONE,
        )
        contract, issues = self.derive(source)
        self.assertEqual(issues, [])
        self.assertEqual(contract.status, "READY")
        self.assertEqual(
            contract.project_contract.design_v8.dataset_implementations, ()
        )

    def test_environment_graph_and_production_boundary_fail_closed(self) -> None:
        source = complete_design8()
        table = doctor.contract_table_after_heading(
            source,
            doctor.ENVIRONMENT_PROMOTION_HEADING,
            doctor.ENVIRONMENT_PROMOTION_HEADERS,
        )
        assert table is not None
        unknown_source = list(table.rows[0])
        unknown_source[6] = "ENV-999"
        changed = replace_contract_table(
            source,
            doctor.ENVIRONMENT_PROMOTION_HEADING,
            doctor.ENVIRONMENT_PROMOTION_HEADERS,
            [tuple(unknown_source)],
        )
        contract, issues = self.derive(changed)
        self.assertEqual(contract.status, "BLOCKED")
        self.assertTrue(any("earlier ENV ID" in item for item in issues), issues)

        nonproduction = (
            "ENV-002",
            "NON_PRODUCTION",
            "Validate the approved release candidate",
            "ISOLATED: dedicated non-production account; us-west-2",
            "IMMUTABLE: approved package digest from ENV-001",
            "Environment-specific configuration, separate secrets, and synthetic data",
            "ENV-001",
            "Current Gate B and required non-production Harness evidence",
            "Rollback the immutable artifact and separately authorize teardown",
            "DES-0001, RISK-001",
            "HARNESS-010",
        )
        production = (
            "ENV-003",
            "PRODUCTION",
            "Serve the approved production target",
            "ISOLATED: dedicated production account; us-west-2",
            "IMMUTABLE: same package digest as ENV-002",
            "Environment-specific configuration and separately held secrets",
            "ENV-002",
            "SEPARATE_OWNER_AUTHORIZATION: exact current promotion evidence",
            "Rollback the immutable artifact and separately authorize teardown",
            "DES-0001, RISK-001",
            "HARNESS-010",
        )
        changed = replace_contract_table(
            source,
            doctor.ENVIRONMENT_PROMOTION_HEADING,
            doctor.ENVIRONMENT_PROMOTION_HEADERS,
            [table.rows[0], nonproduction, production],
        )
        contract, issues = self.derive(changed)
        self.assertEqual(issues, [])
        self.assertEqual(contract.status, "READY")

        for index, value in (
            (3, "NOT ISOLATED: shared production account"),
            (3, "ISOLATED: TODO"),
            (7, "NO SEPARATE_OWNER_AUTHORIZATION: current evidence"),
            (7, "SEPARATE_OWNER_AUTHORIZATION: TODO"),
        ):
            with self.subTest(index=index, value=value):
                invalid = list(production)
                invalid[index] = value
                candidate = replace_contract_table(
                    source,
                    doctor.ENVIRONMENT_PROMOTION_HEADING,
                    doctor.ENVIRONMENT_PROMOTION_HEADERS,
                    [table.rows[0], nonproduction, tuple(invalid)],
                )
                blocked, blocked_issues = self.derive(candidate)
                self.assertEqual(blocked.status, "BLOCKED")
                self.assertTrue(
                    any(
                        "ENVIRONMENT_PROMOTION_INVALID" in item
                        for item in blocked_issues
                    ),
                    blocked_issues,
                )

    def test_well_architected_rows_are_complete_without_official_review_claim(
        self,
    ) -> None:
        source = complete_design8()
        table = doctor.contract_table_after_heading(
            source, doctor.WELL_ARCHITECTED_HEADING, doctor.WELL_ARCHITECTED_HEADERS
        )
        assert table is not None
        reversed_rows = replace_contract_table(
            source,
            doctor.WELL_ARCHITECTED_HEADING,
            doctor.WELL_ARCHITECTED_HEADERS,
            list(reversed(table.rows)),
        )
        contract, issues = self.derive(reversed_rows)
        self.assertEqual(contract.status, "BLOCKED")
        self.assertTrue(any("canonical order" in item for item in issues), issues)

        overclaim = source.replace(
            doctor.WELL_ARCHITECTED_DISCLAIMER,
            "This design passed an official AWS Well-Architected Review.",
            1,
        )
        contract, issues = self.derive(overclaim)
        self.assertEqual(contract.status, "BLOCKED")
        self.assertTrue(any("not an official AWS review" in item for item in issues))

        for evidence, maturity in (
            ("AWS-EV-0001, HARNESS-004", "PLANNED"),
            ("HARNESS-004", "SOURCE_VERIFIED"),
        ):
            with self.subTest(evidence=evidence, maturity=maturity):
                row = list(table.rows[0])
                row[6], row[7] = evidence, maturity
                changed = replace_contract_table(
                    source,
                    doctor.WELL_ARCHITECTED_HEADING,
                    doctor.WELL_ARCHITECTED_HEADERS,
                    [tuple(row), *table.rows[1:]],
                )
                blocked, blocked_issues = self.derive(changed)
                self.assertEqual(blocked.status, "BLOCKED")
                self.assertTrue(
                    any("WELL_ARCHITECTED" in item for item in blocked_issues),
                    blocked_issues,
                )

        planned_rows = []
        for original in table.rows:
            row = list(original)
            row[6], row[7] = "HARNESS-004", "PLANNED"
            planned_rows.append(tuple(row))
        planned_source = replace_contract_table(
            source,
            doctor.WELL_ARCHITECTED_HEADING,
            doctor.WELL_ARCHITECTED_HEADERS,
            planned_rows,
        )
        planned, planned_issues = self.derive(planned_source)
        self.assertEqual(planned_issues, [])
        additions = design8_owner_decision_additions(
            "deployment/recovery", planned.project_contract.design_v8, enabled=True
        )
        self.assertEqual(additions.evidence_ids, ())

        mixed_rows = list(table.rows)
        row = list(mixed_rows[0])
        row[6], row[7] = "HARNESS-004", "PLANNED"
        mixed_rows[0] = tuple(row)
        mixed_source = replace_contract_table(
            source,
            doctor.WELL_ARCHITECTED_HEADING,
            doctor.WELL_ARCHITECTED_HEADERS,
            mixed_rows,
        )
        mixed, mixed_issues = self.derive(mixed_source)
        self.assertEqual(mixed_issues, [])
        inventory, inventory_issues = owner_decisions._derive_gate_b_decision_inventory(
            mixed,
            "REQ-0001",
            "DES-0001",
            "AUTH-0001",
            status="READY",
        )
        self.assertEqual(inventory_issues, [])
        deployment = next(
            item
            for item in inventory["decisions"]
            if item["domain"] == "deployment/recovery"
        )
        self.assertEqual(deployment["maturity"], "PLANNED_AFTER_APPROVAL")
        self.assertEqual(
            deployment["evidence_ids"],
            ["AWS-EV-0006", "AWS-EV-0007", "AWS-EV-0001"],
        )
        self.assertIn("verifies only part", deployment["evidence_status"])
        self.assertIn("remaining elements are planned", deployment["evidence_status"])

    def test_dependency_policy_is_default_deny_and_prefix_is_never_sufficient(
        self,
    ) -> None:
        source = complete_design8()
        denied, denied_issues = self.derive(source)
        self.assertEqual(denied_issues, [])
        command = dependency_table().splitlines()[-1].split(" | ")[-2]
        self.assertTrue(command_matches_prefix(command, "python -m pip install"))
        self.assertFalse(
            dependency_command_allowed(denied.project_contract.design_v8, command)
        )

        allowed_source = source.replace(
            doctor.DEPENDENCY_ACQUISITION_NONE, dependency_table(), 1
        )
        allowed, allowed_issues = self.derive(allowed_source)
        self.assertEqual(allowed_issues, [])
        self.assertFalse(allowed.project_contract.design_v8.acquisition_prohibited)
        self.assertTrue(
            dependency_command_allowed(allowed.project_contract.design_v8, command)
        )
        self.assertFalse(
            dependency_command_allowed(
                allowed.project_contract.design_v8,
                command.replace("ruff-0.16.0", "ruff-0.16.1", 1),
            )
        )

        invalid_rows = (
            {"Immutable version": "latest"},
            {"Scope": "DEVELOPMENT"},
            {"Ecosystem and package": "PYPI: Ruff"},
            {"Lockfile": "requirements-dev.lock"},
            {"Integrity rule": "trust registry"},
            {"Integrity rule": f"SHA256: {'a' * 64}"},
            {"Lifecycle scripts": "DENY"},
            {"Build network": "ALLOW_HTTPS: files.pythonhosted.org; pypi.org"},
            {
                "Approved source": "https://files.pythonhosted.org/packages/ruff-0.16.0.tar.gz"
            },
            {
                "Approved source": "VCS_COMMIT: https://github.com/astral-sh/ruff.git@"
                + "a" * 40
            },
            {"Exact acquisition command": command.replace("--no-deps ", "", 1)},
            {
                "Exact acquisition command": command.replace(
                    "--only-binary=:all: ", "", 1
                )
            },
            {"Exact acquisition command": command.replace("--no-index ", "", 1)},
            {"Exact acquisition command": "uv sync"},
            {"Build network": "ALLOW_HTTPS: *.pypi.org"},
            {"Approved source": "https://user@example.test/simple"},
            {"License disposition": "SPDX: GPL-3.0-only; NOT ALLOWED"},
            {"License disposition": "SPDX: MIT; NO EXCEPTION"},
        )
        for overrides in invalid_rows:
            with self.subTest(overrides=overrides):
                invalid_source = source.replace(
                    doctor.DEPENDENCY_ACQUISITION_NONE,
                    dependency_table(**overrides),
                    1,
                )
                blocked, blocked_issues = self.derive(invalid_source)
                self.assertEqual(blocked.status, "BLOCKED")
                self.assertTrue(
                    any("DEPENDENCY_POLICY_INVALID" in item for item in blocked_issues),
                    blocked_issues,
                )

        for bulk_command in ("uv sync", "npm ci", "poetry install"):
            self.assertFalse(
                dependency_command_allowed(
                    denied.project_contract.design_v8, bulk_command
                )
            )

        missing = source.replace(doctor.DEPENDENCY_ACQUISITION_NONE, "", 1)
        blocked, issues = self.derive(missing)
        self.assertEqual(blocked.status, "BLOCKED")
        self.assertTrue(blocked.project_contract.design_v8.acquisition_prohibited)
        self.assertTrue(
            any(item.startswith("DEPENDENCY_POLICY_MISSING: ") for item in issues),
            issues,
        )

    def test_dependency_command_identity_preserves_quoted_whitespace(self) -> None:
        source = complete_design8().replace(
            doctor.DEPENDENCY_ACQUISITION_NONE, dependency_table(), 1
        )
        design, issues = self.derive(source)
        self.assertEqual(issues, [])
        extension = design.project_contract.design_v8
        approved = extension.dependency_additions[0].exact_acquisition_command
        self.assertTrue(dependency_command_allowed(extension, approved))
        for changed in (
            approved.replace("ruff @ ", "ruff  @ ", 1),
            approved.replace("ruff @ ", "ruff\t@ ", 1),
            approved.replace("ruff @ ", "ruff\u00a0@ ", 1),
            approved.replace("python -m", "python  -m", 1),
            approved.replace("python -m", "python\t-m", 1),
            approved.replace("python -m", "python\u00a0-m", 1),
            approved + "\u00a0",
        ):
            with self.subTest(command=changed):
                self.assertFalse(dependency_command_allowed(extension, changed))
                codes = [
                    code
                    for code, _ in task_command_boundary_issues(
                        "TASK-001",
                        f"```powershell\n{changed}\n```",
                        ("python",),
                        9,
                        extension,
                    )
                ]
                self.assertIn("TASK_DEPENDENCY_ACQUISITION_BOUNDARY", codes)

    def test_dependency_policy_parser_does_not_repair_an_invalid_quoted_argument(
        self,
    ) -> None:
        approved = dependency_table().splitlines()[-1].split(" | ")[-2]
        for spacing in ("  ", "\t", "\u00a0"):
            changed = approved.replace("ruff @ ", "ruff" + spacing + "@ ", 1)
            with self.subTest(spacing=repr(spacing)):
                source = complete_design8().replace(
                    doctor.DEPENDENCY_ACQUISITION_NONE,
                    dependency_table(**{"Exact acquisition command": changed}),
                    1,
                )
                design, issues = self.derive(source)
                self.assertEqual(design.status, "BLOCKED")
                self.assertIn(
                    "DEPENDENCY_POLICY_INVALID: DEP-001 requires the exact wheel command",
                    issues,
                )
                self.assertEqual(
                    design.project_contract.design_v8.dependency_additions[
                        0
                    ].exact_acquisition_command,
                    changed,
                )

    def test_dependency_default_deny_recognizes_spacing_variants(self) -> None:
        denied, issues = self.derive(complete_design8())
        self.assertEqual(issues, [])
        for command in (
            "python  -m pip install package",
            "npm\tinstall package",
            "uv\u00a0sync",
        ):
            with self.subTest(command=command):
                self.assertFalse(
                    dependency_command_allowed(
                        denied.project_contract.design_v8, command
                    )
                )

    def test_exact_approved_design7_digest_is_compatible_but_partial_is_not(
        self,
    ) -> None:
        source = (PROJECT_ROOT / "tests/fixtures/legacy_1234_pre_aws_prd.md").read_text(
            encoding="utf-8"
        )
        digest = (
            "sha256:9e925fbaf47a328ab9ea327d6d7f1058d9945154d8ecabe27384a9115bf23cbc"
        )
        approved = source.replace(
            "| Design contract SHA-256 | TODO (exact current `design_contract.canonical_sha256`) |",
            f"| Design contract SHA-256 | `{digest}` |",
            1,
        )
        compatible, issues = doctor.derive_design_contract(
            approved,
            "DES-0001",
            required=True,
            grandfather_approved_v1=True,
        )
        self.assertEqual(issues, [])
        self.assertEqual(compatible.schema_version, 7)
        self.assertTrue(compatible.project_contract.approved_schema7_compatibility)
        self.assertEqual(compatible.canonical_sha256, digest)
        self.assertNotIn("design_v8", compatible.project_contract.to_dict())
        legacy_task_issues = task_command_boundary_issues(
            "TASK-0001",
            "```text\nuv sync\n```",
            ("uv sync",),
            compatible.project_contract.schema_version,
            compatible.project_contract.design_v8,
        )
        self.assertEqual(legacy_task_issues, [])

        partial = approved + "\n### Dependency acquisition policy\n"
        migration, migration_issues = doctor.derive_design_contract(
            partial,
            "DES-0001",
            required=True,
            grandfather_approved_v1=True,
        )
        self.assertEqual(migration.status, "BLOCKED")
        self.assertEqual(migration.project_contract.status, "MIGRATION_REQUIRED")
        self.assertTrue(
            any("schema 8" in item for item in migration_issues), migration_issues
        )

    def test_exact_approved_design7_retains_legacy_relationship_grammar(self) -> None:
        source = (PROJECT_ROOT / "tests/fixtures/legacy_1234_pre_aws_prd.md").read_text(
            encoding="utf-8"
        )
        custom = source.replace(
            "ARCH-0001 -->|serves| API-001",
            "ARCH-0001 -->|reports health to| API-001",
            1,
        )
        self.assertNotEqual(custom, source)
        probe, _probe_issues = doctor.derive_design_contract(
            custom,
            "DES-0001",
            required=True,
            grandfather_approved_v1=True,
        )
        self.assertIsNotNone(probe.canonical_sha256)
        approved = custom.replace(
            "| Design contract SHA-256 | TODO (exact current `design_contract.canonical_sha256`) |",
            f"| Design contract SHA-256 | `{probe.canonical_sha256}` |",
            1,
        )

        compatible, issues = doctor.derive_design_contract(
            approved,
            "DES-0001",
            required=True,
            grandfather_approved_v1=True,
        )

        self.assertEqual(issues, [])
        self.assertEqual(compatible.schema_version, 7)
        self.assertTrue(compatible.project_contract.approved_schema7_compatibility)
        self.assertEqual(compatible.canonical_sha256, probe.canonical_sha256)

    def test_gate_b_owner_inventory_projects_design8_without_a_new_domain(self) -> None:
        design, issues = self.derive(complete_design8())
        self.assertEqual(issues, [])
        inventory, inventory_issues = owner_decisions._derive_gate_b_decision_inventory(
            design,
            "REQ-0001",
            "DES-0001",
            "AUTH-0001",
            status="READY",
        )
        self.assertEqual(inventory_issues, [])
        by_domain = {item["domain"]: item for item in inventory["decisions"]}
        self.assertEqual(set(by_domain), set(owner_decisions.TECHNICAL_DOMAIN_ORDER))
        self.assertIn("DATASET-001", by_domain["data"]["selection"])
        self.assertIn("ENV-001", by_domain["deployment/recovery"]["selection"])
        self.assertIn(
            "Operational Excellence",
            by_domain["deployment/recovery"]["selection"],
        )
        self.assertIn(
            "Dependency acquisition: DENY_UNDECLARED",
            by_domain["validation/construction"]["selection"],
        )
        self.assertIn(
            "Canonical Design-9",
            by_domain["validation/construction"]["source"],
        )
        deployment = by_domain["deployment/recovery"]
        self.assertEqual(deployment["maturity"], "SOURCE_VERIFIED")
        self.assertIn("AWS-EV-0001", deployment["evidence_ids"])

    def test_new_design8_over_approved_requirements14_requires_migration(
        self,
    ) -> None:
        source = design8_over_approved_requirements14()
        contract, issues = doctor.derive_design_contract(
            source,
            "DES-0001",
            required=True,
            grandfather_approved_v1=True,
        )
        self.assertTrue(
            any("PROJECT_DESIGN_SCHEMA_MIGRATION_REQUIRED" in issue for issue in issues)
        )
        self.assertEqual(contract.status, "BLOCKED")
        self.assertEqual(contract.project_contract.status, "MIGRATION_REQUIRED")
        self.assertEqual(contract.schema_version, 8)
        self.assertEqual(
            contract.project_contract.design_v8.dataset_implementations, ()
        )
        self.assertIsNotNone(contract.canonical_sha256)

    def test_legacy_design_schemas_reject_design8_headings_and_headers(self) -> None:
        source = (
            PROJECT_ROOT / "tests/fixtures/legacy_schema6_approved_prd.md"
        ).read_text(encoding="utf-8")
        for suffix in (
            "\n### Dependency acquisition policy\n",
            "\n### Unrelated heading\n\n| "
            + " | ".join(doctor.DEPENDENCY_POLICY_HEADERS)
            + " |\n",
            "\n| Application source disposition | `GREENFIELD_APP_ROOT: app/**` |\n",
        ):
            with self.subTest(suffix=suffix):
                contract, issues = doctor.derive_design_contract(
                    source + suffix,
                    "DES-0001",
                    required=True,
                    grandfather_approved_v1=True,
                )
                self.assertEqual(contract.project_contract.status, "MIGRATION_REQUIRED")
                self.assertTrue(issues)


if __name__ == "__main__":
    unittest.main()
