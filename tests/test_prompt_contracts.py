from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = REPOSITORY_ROOT
PROMPT_PACK = PROJECT_ROOT / "prompts" / "CODEX-PROMPTS.md"

PROMPT_IDS = [
    "BOOT-00",
    "INTAKE-10",
    "REQ-10",
    "INTAKE-20",
    "DESIGN-10",
    "DESIGN-20",
    "BUG-10",
    "TASK-10",
    "BUILD-10",
    "BUILD-20",
    "SYNC-10",
    "RELEASE-10",
    "AWS-10",
    "AWS-20",
    "AWS-30",
    "AWS-40",
    "AWS-50",
]

CONTRACT_LABELS = [
    "Preconditions",
    "Authoritative inputs",
    "Permitted writes",
    "GitHub mode",
    "AWS mode",
    "Required authorization",
    "Stop conditions",
    "Receipt",
    "Next",
]

DEFAULT_PROJECT_DOC_MAX_BYTES = 32 * 1024
RESERVED_GLOBAL_INSTRUCTION_HEADROOM_BYTES = 8 * 1024
MAX_REPOSITORY_INSTRUCTION_CHAIN_BYTES = min(
    DEFAULT_PROJECT_DOC_MAX_BYTES - RESERVED_GLOBAL_INSTRUCTION_HEADROOM_BYTES,
    18_000,
)
MAX_SKILL_DESCRIPTION_CHARACTERS = 320
MAX_REPOSITORY_SKILL_INDEX_CHARACTERS = 1_200
MAX_BOOT_PROMPT_BYTES = 32 * 1024
MAX_PHASE_PROMPT_BYTES = 8 * 1024
MAX_DESIGN_PROMPT_BYTES = 6_300


class PromptPackContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.prompts = PROMPT_PACK.read_text(encoding="utf-8")
        cls.prd = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        cls.agents = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        cls.tasks = (PROJECT_ROOT / "docs/project/TASKS.md").read_text(encoding="utf-8")
        cls.runbook = (PROJECT_ROOT / "docs/project/RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        cls.verify = (PROJECT_ROOT / "docs/project/VERIFY.md").read_text(
            encoding="utf-8"
        )
        cls.security = (PROJECT_ROOT / "SECURITY.md").read_text(encoding="utf-8")
        cls.root_readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
        cls.bootstrap_source = (REPOSITORY_ROOT / "bootstrap.py").read_text(
            encoding="utf-8"
        )
        cls.workflow = (PROJECT_ROOT / "docs/WORKFLOW.md").read_text(encoding="utf-8")
        cls.fastlane_deliver = (
            PROJECT_ROOT / ".agents/skills/fastlane/references/deliver.md"
        ).read_text(encoding="utf-8")
        cls.operate_fastlane_aws = (
            PROJECT_ROOT / ".agents/skills/operate-fastlane-aws/SKILL.md"
        ).read_text(encoding="utf-8")
        cls.fastlane_design = (
            PROJECT_ROOT / ".agents/skills/fastlane/references/design.md"
        ).read_text(encoding="utf-8")
        cls.authorization_receipts = (
            PROJECT_ROOT
            / ".agents/skills/fastlane/references/authorization-receipts.md"
        ).read_text(encoding="utf-8")

    def prompt_section(self, prompt_id: str) -> str:
        pattern = re.compile(
            rf"^## {re.escape(prompt_id)} — .*?(?=^## [A-Z]+-\d+ — |\Z)",
            re.MULTILINE | re.DOTALL,
        )
        match = pattern.search(self.prompts)
        self.assertIsNotNone(match, f"Missing section for {prompt_id}")
        return match.group(0) if match else ""

    def test_public_surfaces_use_fastlane_engine_terminology(self) -> None:
        public_surfaces = (
            "AGENTS.md",
            "SECURITY.md",
            "README.md",
            "docs/HOOKS.md",
            "docs/TROUBLESHOOTING.md",
            "docs/WORKFLOW.md",
            "docs/project/PRD.md",
            "docs/project/RUNBOOK.md",
            "docs/project/TASKS.md",
            "prompts/CODEX-PROMPTS.md",
            "scripts/AGENTS.md",
            ".agents/skills/build-fastlane/SKILL.md",
            ".agents/skills/fastlane/SKILL.md",
            ".agents/skills/fastlane/references/deliver.md",
            ".agents/skills/fastlane/references/owner-responses.md",
            ".agents/skills/maintain-fastlane/SKILL.md",
        )
        for relative in public_surfaces:
            with self.subTest(relative=relative):
                text = PROJECT_ROOT.joinpath(*relative.split("/")).read_text(
                    encoding="utf-8"
                )
                self.assertIsNone(
                    re.search(r"\bdoctor\b", text, re.IGNORECASE),
                    relative,
                )
        self.assertIn("Fastlane Engine", self.root_readme)
        self.assertIn(
            "scripts/bootstrap_doctor.py",
            (PROJECT_ROOT / "docs/TROUBLESHOOTING.md").read_text(encoding="utf-8"),
        )

    def test_repository_instruction_chains_leave_default_context_headroom(
        self,
    ) -> None:
        agent_files = sorted(PROJECT_ROOT.rglob("AGENTS.md"))
        self.assertGreater(len(agent_files), 0)
        self.assertLessEqual(len((PROJECT_ROOT / "AGENTS.md").read_bytes()), 5_900)
        self.assertLessEqual(
            len((PROJECT_ROOT / ".agents/skills/fastlane/SKILL.md").read_bytes()),
            8_500,
        )
        self.assertLessEqual(
            len((PROJECT_ROOT / "docs/WORKFLOW.md").read_bytes()), 32_000
        )
        self.assertLessEqual(len(self.root_readme.splitlines()), 80)

        for agent_file in agent_files:
            chain: list[Path] = []
            directory = agent_file.parent
            while True:
                candidate = directory / "AGENTS.md"
                if candidate.is_file():
                    chain.append(candidate)
                if directory == PROJECT_ROOT:
                    break
                self.assertIn(PROJECT_ROOT, directory.parents)
                directory = directory.parent

            chain_bytes = sum(len(path.read_bytes()) for path in chain)
            self.assertLessEqual(
                chain_bytes,
                MAX_REPOSITORY_INSTRUCTION_CHAIN_BYTES,
                (
                    f"{agent_file.relative_to(PROJECT_ROOT)} instruction chain "
                    f"uses {chain_bytes} bytes; keep at least "
                    f"{RESERVED_GLOBAL_INSTRUCTION_HEADROOM_BYTES} bytes below "
                    "Codex's default project_doc_max_bytes"
                ),
            )

    def test_agent_correction_rerun_is_exact_ephemeral_and_bounded(self) -> None:
        coordinator = (PROJECT_ROOT / ".agents/skills/fastlane/SKILL.md").read_text(
            encoding="utf-8"
        )
        exact_command = (
            "python scripts/bootstrap_doctor.py --root . --json "
            "--prior-remediation-fingerprint "
            "<report.remediation.fingerprint>"
        )
        self.assertIn(exact_command, " ".join(coordinator.split()))
        normalized = " ".join(coordinator.split())
        self.assertIn("rerun exactly once", normalized)
        self.assertIn("only to this immediate next Engine invocation", normalized)
        self.assertIn("never persist it", normalized)
        self.assertIn("If the same fingerprint remains", normalized)
        self.assertIn("human safety review", normalized)

    def test_repository_skill_index_stays_compact(self) -> None:
        descriptions: list[str] = []
        for skill in sorted((PROJECT_ROOT / ".agents" / "skills").glob("*/SKILL.md")):
            content = skill.read_text(encoding="utf-8")
            match = re.search(r"(?m)^description:\s*(.+)$", content)
            self.assertIsNotNone(match, skill)
            description = match.group(1) if match else ""
            self.assertLessEqual(
                len(description),
                MAX_SKILL_DESCRIPTION_CHARACTERS,
                skill,
            )
            descriptions.append(description)

        self.assertLessEqual(
            sum(len(description) for description in descriptions),
            MAX_REPOSITORY_SKILL_INDEX_CHARACTERS,
        )

    def test_individual_prompt_sections_stay_context_bounded(self) -> None:
        for prompt_id in PROMPT_IDS:
            section_bytes = len(self.prompt_section(prompt_id).encode("utf-8"))
            limit = (
                MAX_BOOT_PROMPT_BYTES
                if prompt_id == "BOOT-00"
                else MAX_PHASE_PROMPT_BYTES
            )
            self.assertLessEqual(
                section_bytes,
                limit,
                (
                    f"{prompt_id} uses {section_bytes} bytes; keep prompt "
                    "instructions phase-scoped instead of loading the full pack"
                ),
            )

    def test_design_prompt_stays_within_strict_contract_budget(self) -> None:
        section_bytes = len(self.prompt_section("DESIGN-10").encode("utf-8"))
        self.assertLessEqual(section_bytes, MAX_DESIGN_PROMPT_BYTES)

    def test_stable_prompt_ids_are_unique_and_ordered(self) -> None:
        positions: list[int] = []
        for prompt_id in PROMPT_IDS:
            heading = re.compile(rf"^## {re.escape(prompt_id)} — ", re.MULTILINE)
            matches = list(heading.finditer(self.prompts))
            self.assertEqual(
                len(matches),
                1,
                f"Expected one canonical heading for {prompt_id}",
            )
            positions.append(matches[0].start())
        self.assertEqual(positions, sorted(positions))

    def test_every_prompt_declares_the_common_contract(self) -> None:
        for prompt_id in PROMPT_IDS:
            section = self.prompt_section(prompt_id)
            for label in CONTRACT_LABELS:
                self.assertIn(label, section, f"{prompt_id} is missing {label}")

    def test_human_gate_receipts_are_exact_and_owner_only(self) -> None:
        for document in (self.prompts, self.prd):
            self.assertIn("APPROVE REQUIREMENTS GATE A", document)
            self.assertIn("APPROVE PRD AND CONSTRUCTION GATE B", document)
            self.assertIn("Cost posture:", document)
            self.assertIn("Accepted assumptions:", document)
            self.assertIn("Construction authorization:", document)

        self.assertIn("Only the owner", self.prompts)
        self.assertIn("Only the owner", self.agents)
        for reserved in ("`Codex`", "`agent`", "`automation`", "`system`", "`AI`"):
            self.assertIn(reserved, self.prd)
            self.assertIn(reserved, self.prompts)

    def test_gate_and_revision_vocabulary_does_not_drift(self) -> None:
        required = {
            "READY_WITH_PROPOSED_ASSUMPTIONS",
            "READY_FOR_OWNER_APPROVAL",
            "READY_FOR_CONSTRUCTION_APPROVAL",
            "APPROVED_FOR_DESIGN",
            "APPROVED_FOR_CONSTRUCTION",
            "STALE",
        }
        for value in required:
            self.assertIn(value, self.prd)
            self.assertIn(value, self.prompts)

        for document in (self.agents, self.prd, self.prompts):
            self.assertNotIn("READY_WITH_ACCEPTED_ASSUMPTIONS", document)

    def test_tool_access_is_not_authorization(self) -> None:
        self.assertIn("Tool availability is never authorization", self.prompts)
        self.assertIn(
            "Credentials and connector availability are not authorization", self.agents
        )

    def test_markdown_fences_and_launch_commands_are_complete(self) -> None:
        self.assertEqual(self.prompts.count("~~~") % 2, 0)
        self.assertEqual(self.prd.count("```") % 2, 0)
        self.assertIn("START AWS CODEX FASTLANE", self.prompts)
        self.assertIn("PREREQUISITES_READY", self.prompt_section("BOOT-00"))

    def test_plain_language_setup_is_friendly_resumable_and_verifies_aws_core(
        self,
    ) -> None:
        boot = self.prompt_section("BOOT-00")
        coordinator = (PROJECT_ROOT / ".agents/skills/fastlane/SKILL.md").read_text(
            encoding="utf-8"
        )
        coordinator_config = (
            PROJECT_ROOT / ".agents/skills/fastlane/agents/openai.yaml"
        ).read_text(encoding="utf-8")
        for phrase in ("init template", "initialize template", "start Fastlane"):
            self.assertIn(phrase, boot)
        self.assertIn("init template", coordinator_config)
        self.assertIn("single coordinator", coordinator)
        self.assertIn("continue setup", boot)
        self.assertIn("python scripts/setup_assistant.py welcome", boot)
        self.assertIn("Reproduce stdout exactly once", boot)
        self.assertIn("no more than these three values", boot)
        for phrase in (
            "project name",
            "preferred AWS Region",
            "development budget posture",
        ):
            self.assertIn(phrase, boot)
        self.assertNotIn("Technical status:", boot)
        self.assertIn("PREREQUISITES_READY", boot)
        self.assertIn("Fresh templates require current official AWS Core", self.agents)
        self.assertIn("never repeat setup", self.agents)
        self.assertIn("Never ask an initialized project for another", boot)
        self.assertIn("aws-core@agent-toolkit-for-aws", boot)
        self.assertIn("does not inspect credentials, access an AWS account", boot)
        self.assertIn("pytest", boot)
        setup_source = (PROJECT_ROOT / "scripts/setup_assistant.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("subprocess.run", setup_source)
        self.assertNotIn("shell=True", setup_source)

    def test_aws_core_uses_official_current_marketplace_without_pin_fallback(
        self,
    ) -> None:
        boot = self.prompt_section("BOOT-00")
        for document in (boot, self.root_readme, self.agents):
            self.assertIn("aws/agent-toolkit-for-aws", document)
            self.assertIn("aws-core@agent-toolkit-for-aws", document)
        self.assertIn("Do not pin", self.agents)
        self.assertIn("does not pin a plugin version or commit", self.root_readme)
        self.assertIn("PREREQUISITES_READY", boot)

    def test_optional_challengers_are_conditional_and_non_authoritative(self) -> None:
        requirements = self.prompt_section("REQ-10")
        design = self.prompt_section("DESIGN-10")
        tasks = self.prompt_section("TASK-10")
        gate_a = self.prompt_section("INTAKE-20")
        gate_b = self.prompt_section("DESIGN-20")
        self.assertIn("fastlane-requirements-challenger", requirements)
        self.assertIn("Quick MVP uses no\nsubagent by default", requirements)
        self.assertIn("fastlane-architecture-challenger", design)
        self.assertIn("after completing the proposed design", design.lower())
        self.assertIn("only writer", requirements)
        self.assertIn("only writer", design)
        self.assertIn("continue ordinary\nrequirements work", requirements)
        self.assertIn("material AWS feasibility fact", gate_a)
        self.assertIn("material AWS design evidence", gate_b)

        coordinator = (PROJECT_ROOT / ".agents/skills/fastlane/SKILL.md").read_text(
            encoding="utf-8"
        )
        ledger = (PROJECT_ROOT / "docs/project/TASKS.md").read_text(encoding="utf-8")
        for surface in (self.agents, coordinator, tasks, ledger):
            compact = " ".join(surface.split())
            self.assertIn("Maximum workers", compact)
            self.assertIn("task claim", compact)
            self.assertIn("mutable execution", compact)
            self.assertIn("not a worker", compact)
            self.assertIn("claims no task", compact)
            self.assertIn("changes no state", compact)

        infrastructure_guide = (PROJECT_ROOT / "infrastructure/AGENTS.md").read_text(
            encoding="utf-8"
        )
        infrastructure_compact = " ".join(infrastructure_guide.split())
        self.assertIn(
            "coordinator alone performs every repository and infrastructure edit",
            infrastructure_compact,
        )
        self.assertIn("Helpers and challengers are read-only", infrastructure_compact)
        self.assertIn("never edit", infrastructure_compact)
        self.assertNotIn(
            "workers may edit assigned disjoint paths", infrastructure_compact.lower()
        )
        for descendant_surface in (self.agents, coordinator, infrastructure_guide):
            descendant_compact = " ".join(descendant_surface.split())
            self.assertIn("descendant subagent", descendant_compact)
            self.assertIn("cannot spawn a writer", descendant_compact)

        for name in (
            "fastlane-requirements-challenger",
            "fastlane-architecture-challenger",
        ):
            content = (PROJECT_ROOT / ".codex" / "agents" / f"{name}.toml").read_text(
                encoding="utf-8"
            )
            self.assertIn('sandbox_mode = "read-only"', content)
            self.assertIn("Never edit files", content)
            self.assertRegex(content, r"Never .*approve")
            self.assertIn("not a task worker", content)
            self.assertIn("claim no task", content)
            self.assertIn("change no state", content)
            self.assertIn("synchronous read-only critique", content)
            self.assertIn("descendant subagent", content)
            self.assertIn("Never spawn a writer", content)

    def test_aws_core_is_wired_through_planning_build_and_operations(self) -> None:
        deliver_reference = (
            PROJECT_ROOT / ".agents/skills/fastlane/references/deliver.md"
        ).read_text(encoding="utf-8")
        operate_skill = (
            PROJECT_ROOT / ".agents/skills/operate-fastlane-aws/SKILL.md"
        ).read_text(encoding="utf-8")
        architecture_challenger = (
            PROJECT_ROOT / ".codex/agents/fastlane-architecture-challenger.toml"
        ).read_text(encoding="utf-8")
        for surface in (
            self.agents,
            deliver_reference,
            operate_skill,
            architecture_challenger,
        ):
            self.assertIn("AWS Core", surface)
        self.assertIn("official current AWS Core", deliver_reference)
        self.assertIn("release-readiness", deliver_reference)
        self.assertIn("pause only the affected AWS-specific task", deliver_reference)
        self.assertIn("cannot replace those live calls", operate_skill)
        self.assertIn("aws-core@agent-toolkit-for-aws", operate_skill)
        self.assertIn("Fresh templates require current official AWS Core", self.agents)

    def test_design_and_aws_preflight_require_fresh_aws_core_evidence(self) -> None:
        requirements = self.prompt_section("REQ-10")
        design = self.prompt_section("DESIGN-10")
        aws_preflight = self.prompt_section("AWS-10")
        verify = (PROJECT_ROOT / "docs/project/VERIFY.md").read_text(encoding="utf-8")
        for section, phase in ((design, "DESIGN-10"), (aws_preflight, "AWS-10")):
            self.assertIn("retrieve_skill", section)
            self.assertIn("search_documentation", section)
            self.assertIn("aws-core@agent-toolkit-for-aws", section)
            self.assertIn("docs/project/VERIFY.md", section)
            self.assertIn(phase, section)
            self.assertRegex(
                section.lower(), r"(?:block|stop).*(?:missing|failed|stale|wrong)"
            )
        for phrase in (
            "`REQUIRED`, `OPTIONAL`, or\n`NOT_MATERIAL`",
            "service/Region feasibility",
            "identity/authorization",
            "sensitive data/uploads",
            "public exposure",
            "deletion/recovery",
            "quotas, availability",
            "material cost",
            "current REQ and affected requirements",
            "no architecture\nselected",
            "Record credentials/account access as `NO`",
            "Missing/stale discovery is\nCodex work, not owner setup",
        ):
            self.assertIn(phrase, requirements)
        self.assertLess(
            requirements.index("`search_documentation`"),
            requirements.index("`retrieve_skill`"),
        )
        self.assertIn("## AWS Core evidence", verify)
        for phase in ("REQ-10", "DESIGN-10", "AWS-10"):
            self.assertEqual(verify.count(f"| `{phase}` |"), 2)
        expected_discovery_ids = {
            "REQ-10": "AWS-DISC-0001",
            "DESIGN-10": "AWS-DISC-0002",
            "AWS-10": "AWS-DISC-0003",
        }
        for phase, discovery_id in expected_discovery_ids.items():
            self.assertEqual(verify.count(f"| `{phase}` | `{discovery_id}` |"), 2)
        self.assertEqual(len(set(expected_discovery_ids.values())), 3)
        self.assertNotIn("| `BOOT-00` |", verify)
        self.assertEqual(verify.count("| `retrieve_skill` |"), 3)
        self.assertEqual(verify.count("| `search_documentation` |"), 3)
        self.assertIn(
            "Fresh prerequisite capability\nobservations are ephemeral", verify
        )
        operate_skill = (
            PROJECT_ROOT / ".agents/skills/operate-fastlane-aws/SKILL.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "aws_execution.progress_state",
            "AWS_READ_SCOPE_REQUIRED",
            "AWS_PREFLIGHT_READY",
            "fast-dev",
            "WAITING_AWS_MUTATION_AUTH",
            "CODEX_LIVE_TOOL_CALL",
            "Credentials inspected` = `NO",
            "AWS account accessed` = `NO",
        ):
            self.assertIn(phrase, operate_skill)
        operate_compact = " ".join(operate_skill.split())
        self.assertIn(
            "legacy readiness boolean is compatibility output only", operate_compact
        )

        self.assertIn("Fresh templates require current official AWS Core", self.agents)
        self.assertLess(
            operate_skill.index("search_documentation"),
            operate_skill.index("retrieve_skill"),
        )
        self.assertIn("explicit-gate`, require", operate_skill)
        self.assertIn("fast-dev`, require", operate_skill)
        fastlane_skill = (PROJECT_ROOT / ".agents/skills/fastlane/SKILL.md").read_text(
            encoding="utf-8"
        )
        owner_responses = (
            PROJECT_ROOT / ".agents/skills/fastlane/references/owner-responses.md"
        ).read_text(encoding="utf-8")
        design_reference = (
            PROJECT_ROOT / ".agents/skills/fastlane/references/design.md"
        ).read_text(encoding="utf-8")
        self.assertRegex(self.prompts, r"proves\s+availability, not use")
        self.assertIn("proves availability only", design_reference)
        self.assertRegex(
            fastlane_skill,
            r"validated `search_documentation` then matching `retrieve_skill` chain",
        )
        self.assertIn("Never accept self-asserted audit prose", owner_responses)
        self.assertIn("unavailable or unobservable calls", self.prompts)
        self.assertIn("Persist no raw skill content", self.prompts)

    def test_design_edits_existing_diagrams_in_place_and_gate_b_checks_them(
        self,
    ) -> None:
        design = self.prompt_section("DESIGN-10")
        gate_b = self.prompt_section("DESIGN-20")
        self.assertIn("existing PRD Mermaid blocks in place", design)
        self.assertIn("not append by default", design)
        self.assertIn("Part I flow changes through REQ-10", design)
        self.assertIn("diagram-to-design conflict", gate_b)
        self.assertIn("unused optional\ndiagram paths", gate_b)
        self.assertIn(
            "existing diagram slots were specialized in place",
            gate_b,
        )

    def test_architecture_selection_contract_is_explicit_and_fail_closed(self) -> None:
        design = self.prompt_section("DESIGN-10")
        design_reference = (
            PROJECT_ROOT / ".agents/skills/fastlane/references/design.md"
        ).read_text(encoding="utf-8")
        challenger = (
            PROJECT_ROOT / ".codex/agents/fastlane-architecture-challenger.toml"
        ).read_text(encoding="utf-8")

        for heading in (
            "### Adaptive coverage plan",
            "### Architecture drivers",
            "### Whole-system candidates",
            "### Selected architecture",
            "### Architecture traceability",
            "### Material AWS evidence",
            "### Change impact record",
        ):
            self.assertIn(heading, self.prd)
        for stable_id in ("DRV-*", "CAND-*", "ARCH-*", "AWS-EV-*"):
            self.assertIn(stable_id, design)
            self.assertIn(stable_id, design_reference)
        self.assertIn("hard constraints before preferences", design)
        self.assertIn("select only an eligible candidate", design)
        self.assertIn("managed-serverless baseline", design)
        self.assertIn("never add a straw option", design_reference)
        self.assertIn("arbitrary numerical scoring", design_reference)
        self.assertIn("Generic connectors, memory, or", design_reference)
        self.assertIn("challenger prose cannot replace those calls", design_reference)
        self.assertIn("name the selected `ARCH-*` as the", design)
        self.assertIn("include the selected `ARCH-*`", design)
        self.assertIn("full design-contract digest", self.prd)
        self.assertIn("Adaptive Coverage Plan", design)
        self.assertIn("Adaptive Coverage Plan", design_reference)
        self.assertIn("Change impact record", design)
        self.assertIn("Change impact record", design_reference)
        for field in (
            "Security impact",
            "Reliability impact",
            "Operational burden",
            "Migration path",
        ):
            self.assertIn(field, self.prd)
        self.assertIn("grandfathered until the next design-controlled change", self.prd)
        for finding in (
            "unsupported AWS claim",
            "unmet requirement",
            "hard-constraint violation",
            "reliability or recovery gap",
            "rejected-alternative concern",
            "unresolved current AWS fact",
        ):
            self.assertIn(finding, challenger)
        self.assertIn("Never edit files", challenger)
        self.assertIn("Never", challenger)
        self.assertIn("satisfy AWS evidence", challenger)

    def test_technology_register_is_authoritative_and_exact(self) -> None:
        heading = "### Technology and toolchain decision register"
        self.assertIn(heading, self.prd)
        register = self.prd.split(heading, 1)[1].split("\n## 14.", 1)[0]
        self.assertIn("authoritative register", register)
        self.assertIn(
            "| Decision ID | Concern | Selection | Version policy | Source | "
            "Basis IDs | Alternatives and rationale | Compatibility/migration | "
            "Validation |",
            register,
        )
        expected = [
            ("TECH-0001", "APPLICATION_RUNTIME"),
            ("TECH-0002", "APPLICATION_FRAMEWORK"),
            ("TECH-0003", "FRONTEND_FRAMEWORK"),
            ("TECH-0004", "INFRASTRUCTURE_AS_CODE"),
            ("TECH-0005", "PACKAGE_BUILD_TOOLING"),
            ("TECH-0006", "TEST_TOOLING"),
            ("TECH-0007", "PROPERTY_TESTING"),
            ("TECH-0008", "SECURITY_VALIDATION"),
            ("TECH-0009", "DEPLOYMENT_TOOLING"),
        ]
        rows = re.findall(r"(?m)^\| (TECH-\d{4}) \| ([A-Z_]+) \|", register)
        self.assertEqual(rows, expected)
        for decision_id, concern in expected:
            self.assertIn(
                f"| {decision_id} | {concern} | TODO | TODO | TODO | TODO | "
                "TODO | TODO | TODO |",
                register,
            )
        self.assertIn("DES-0001; TECH: TECH-0001, TECH-0002", register)
        self.assertIn("DES-0001; TECH: NONE — no technology/toolchain impact", register)
        self.assertIn("OFFICIAL_CURRENT_NO_TEMPLATE_PIN", register)
        self.assertRegex(register, r"observed\s+version is evidence metadata")
        self.assertIn("exact comma-space-separated stable IDs", register)
        self.assertIn("never prose, duplicate IDs", register)
        self.assertIn("`EXACT` may use an opaque ecosystem version", register)
        self.assertIn(
            "`MINIMUM`\nuses a machine-comparable numeric dotted version", register
        )
        self.assertIn("An active `PROPERTY_TESTING` decision must use", register)
        self.assertRegex(
            register,
            r"`Selection` names the chosen technology or uses exactly\s+"
            r"`NOT_APPLICABLE — <reason>` when no technology applies",
        )
        self.assertRegex(
            register,
            r"ordinary dependency addition does not invalidate Gate\s+B unless "
            r"it changes\s+architecture, validation, security, cost, or deployment\s+"
            r"behavior",
        )

    def test_property_specs_flow_through_tasks_build_and_release_evidence(self) -> None:
        design = self.prompt_section("DESIGN-10")
        tasks = self.prompt_section("TASK-10")
        build = self.prompt_section("BUILD-10")
        autonomous = self.prompt_section("BUILD-20")
        release = self.prompt_section("RELEASE-10")
        test_agents = (PROJECT_ROOT / "tests/AGENTS.md").read_text(encoding="utf-8")

        self.assertIn(
            "classify every measurable Gate A requirement exactly once", design
        )
        self.assertIn("replay format must explicitly declare a", design)
        self.assertIn("Only `EXACT` accepts opaque", design)
        self.assertIn("Active `PROPERTY_TESTING` uses", design)
        self.assertIn("applicable `PROP-*`", tasks)
        self.assertIn("TASK-10 is copy-only for design decisions", tasks)
        self.assertIn("DES-0001; TECH: TECH-0001, TECH-0002", tasks)
        self.assertIn("run the approved property suite", build)
        self.assertIn("minimized counterexample", build)
        self.assertIn("SPECIFICATION_AMBIGUITY_OR_DEFECT", build)
        self.assertIn("route to REQ-10 or DESIGN-10", build)
        for section in (build, autonomous):
            self.assertIn("route to DESIGN-10", section)
            self.assertRegex(section, r"(?i)(?:never|cannot) substitute")
        self.assertIn("Missing or\nunresolved property evidence", release)

        for phrase in (
            "classify every measurable Gate A requirement",
            "APPLICABLE` / `NOT_APPLICABLE",
            "### Property execution contract",
            "Seed or reproduction format",
            "MIN_CASES: <positive integer>",
            "MAX_SECONDS: <positive integer>",
            "Never change an approved property",
        ):
            self.assertIn(phrase, self.prd)
        property_section = self.prd.split(
            "## 24. Property-based testing specification", 1
        )[1].split("\n## 25.", 1)[0]
        self.assertLess(
            property_section.index("| PROP-005 |"),
            property_section.index("### Property execution contract"),
        )
        self.assertIn(
            "| Property ID | Framework TECH ID | Exact command | Run target/time "
            "bound | Seed or reproduction format | Evidence destination |",
            property_section,
        )
        self.assertIn(
            "| PROP-001 | TODO | TODO | TODO | TODO | TODO |", property_section
        )
        self.assertIn(
            "replay format must explicitly declare either a seed", property_section
        )
        self.assertIn(
            "Every applicable property definition must contain concrete",
            property_section,
        )
        self.assertIn("one runnable local\ncommand, not prose", property_section)
        self.assertIn("without shell-control\n  chaining", design)
        for redundant in (
            "- language-appropriate framework or suite;",
            "- generated case or run target and time bound;",
            "- seed and reproduction-command format;",
        ):
            self.assertNotIn(redundant, property_section)
        self.assertIn(
            "Current REQ ID, requirement IDs, applicable acceptance/journey/PROP IDs",
            self.tasks,
        )
        for phrase in (
            "Evidence ID",
            "Task ID",
            "REQ / DES / AUTH",
            "Framework selection",
            "Observed exact version",
            "Exact command",
            "Observed run",
            "Replay seed or exact command",
            "Minimized counterexample",
            "Failure class / resolution",
            "Commit / worktree / artifact",
            "Durable source",
        ):
            self.assertIn(phrase, self.verify)
        self.assertIn("CASES: <positive integer>; ELAPSED_SECONDS:", self.verify)
        self.assertIn("latest uniquely timed row", self.verify)
        self.assertRegex(
            self.verify, r"preserve the smallest observed\s+counterexample"
        )
        self.assertIn("`FAILED` preserves\na property-test failure", self.verify)
        self.assertIn("matching Task completion evidence row", self.verify)
        self.assertIn(
            "`BACKLOG` is a fully specified dependency-gated task", self.tasks
        )
        self.assertIn("`BACKLOG` contributes to plan coverage", self.tasks)
        self.assertIn("BACKLOG means dependency-gated, not", tasks)
        self.assertIn("SKIPPED tasks do not satisfy property", tasks)
        self.assertIn("Only the passing status may be cited", build)
        self.assertIn("Never weaken an invariant", self.agents)
        self.assertIn("Never narrow a generator", test_agents)

    def test_receipts_require_complete_normalized_block_equality(self) -> None:
        self.assertIn("equal to this complete", self.prompts)
        self.assertIn("after trimming surrounding whitespace", self.prompts)
        self.assertIn("Reject extra non-blank", self.prompts)
        self.assertNotIn("response begins exactly", self.prompts)

    def test_gate_candidates_are_validated_before_write_and_stay_at_gate(self) -> None:
        command = (
            "python scripts/bootstrap_doctor.py --root . "
            "--validate-gate-receipt --input-stdin --json"
        )
        owner = (
            PROJECT_ROOT / ".agents/skills/fastlane/references/owner-responses.md"
        ).read_text(encoding="utf-8")
        gate_a = self.prompt_section("INTAKE-20")
        gate_b = self.prompt_section("DESIGN-20")

        self.assertIn(command, self.prompts)
        self.assertIn("--validate-gate-receipt --input-stdin --json", owner)
        self.assertIn("Only `PASS` with `candidate_accepted: true`", self.prompts)
        self.assertIn("write\nnothing", self.prompts)
        self.assertIn("without echoing the\nrejected candidate", self.prompts)
        self.assertIn(
            "**Next:** DESIGN-10 only after exact acceptance; otherwise remain at INTAKE-20.",
            gate_a,
        )
        self.assertIn("no Gate A approval was recorded", gate_a)
        self.assertIn("put the unchanged exact current Gate A receipt last", gate_a)
        self.assertIn(
            "**Next:** TASK-10 only after exact acceptance; otherwise remain at DESIGN-20.",
            gate_b,
        )
        self.assertIn("no Gate B approval was recorded", gate_b)
        self.assertIn("put the unchanged exact current Gate B receipt last", gate_b)
        for section in (gate_a, gate_b):
            self.assertIn("Invalid formatting alone does not return", section)
        self.assertIn("preserve the same pending gate", owner)
        self.assertIn("A formatting error\n  does not route backward", owner)

    def test_gate_writes_keep_prd_summary_and_records_atomic(self) -> None:
        requirements = self.prompt_section("REQ-10")
        gate_a = self.prompt_section("INTAKE-20")
        design = self.prompt_section("DESIGN-10")
        gate_b = self.prompt_section("DESIGN-20")

        self.assertIn("Document status requirements revision", requirements)
        self.assertIn("derived Gate A/Gate B states", requirements)
        self.assertIn("matching Document\nstatus Gate A state", gate_a)
        self.assertIn("Document status DES/AUTH/design/Gate B fields", design)
        self.assertIn("matching Document\nstatus Gate B state", gate_b)
        self.assertIn("lifecycle mirror as one coordinator\ncheckpoint", gate_a)
        self.assertIn("lifecycle mirror as one coordinator checkpoint", gate_b)

    def test_ready_recommendations_transition_to_pending_and_sync_snapshot(
        self,
    ) -> None:
        requirements = self.prompt_section("REQ-10")
        design = self.prompt_section("DESIGN-10")
        gate_b = self.prompt_section("DESIGN-20")

        self.assertIn("Gate A owner state to `PENDING_OWNER_APPROVAL`", requirements)
        self.assertIn("docs/project/TASKS.md's Active execution snapshot", requirements)
        self.assertIn("Gate B state to\n`PENDING_OWNER_APPROVAL`", design)
        self.assertIn("maximum\nworkers, baseline, and protected dirty paths", design)
        self.assertIn("docs/project/TASKS.md Active execution snapshot", gate_b)
        self.assertIn("APPROVED_FOR_CONSTRUCTION", gate_b)
        self.assertRegex(
            self.agents,
            r"Do not leave\s+an agent-ready gate marked `BLOCKED`",
        )

    def test_stale_gates_have_recovery_routes(self) -> None:
        boot = self.prompt_section("BOOT-00")
        self.assertRegex(boot, r"Gate A STALE goes to\s+INTAKE-10")
        self.assertIn("otherwise REQ-10", boot)
        self.assertRegex(boot, r"stale Gate B with current Gate A goes\s+to DESIGN-10")
        self.assertRegex(boot, r"uninitialized or stale task plan goes\s+to TASK-10")
        self.assertIn(
            "stale Gate B with a current Gate A routes to `DESIGN-10`", self.agents
        )

    def test_gate_receipts_record_provenance_without_extra_lines(self) -> None:
        gate_a = self.prompt_section("INTAKE-20")
        gate_b = self.prompt_section("DESIGN-20")
        for section in (gate_a, gate_b):
            self.assertIn("observed ISO 8601 authorization time", section)
            self.assertRegex(section, r"without\s+adding either value to the receipt")
            self.assertIn("Do not invent a source", section)
        self.assertIn("Authorization provided at", self.prd)
        self.assertIn("Authorization source", self.prd)
        self.assertIn("subset, superset, reordered list", self.prd)

    def test_launchpad_routes_from_existing_lifecycle_state(self) -> None:
        boot = self.prompt_section("BOOT-00")
        self.assertIn("The Fastlane Engine is the lifecycle router", boot)
        self.assertIn(
            "Never restart\n   BOOT-00 or prerequisites after initialization", boot
        )
        self.assertRegex(
            boot, r"current Gate A receipt\s+awaiting approval goes to INTAKE-20"
        )
        self.assertIn("approved Gate B with an uninitialized or stale task plan", boot)
        self.assertIn("Otherwise use the Engine state or stop on conflict", boot)

    def test_launchpad_and_build_use_executable_safety_controls(self) -> None:
        boot = self.prompt_section("BOOT-00")
        tasks = self.prompt_section("TASK-10")
        build = self.prompt_section("BUILD-20")

        self.assertIn("Never use `--force`", boot)
        self.assertIn("bootstrap_doctor.py", boot)
        self.assertIn("hash-bound decision", boot)
        self.assertIn("Task-plan revision", tasks)
        self.assertIn("explicit skipped-dependency waivers", tasks)
        self.assertIn("durable coordinator run ID", build)
        self.assertIn("No subagent may edit implementation files", build)
        self.assertIn("UNKNOWN", build)

    def test_run_lifecycle_commands_are_complete_and_mode_specific(self) -> None:
        single = self.prompt_section("BUILD-10")
        autonomous = self.prompt_section("BUILD-20")
        coordinator_claim = (
            "--claim TASK-0001 --owner codex-coordinator --run-id RUN-0001 "
            "--coordinator codex-coordinator --checkpoint CP-0000"
        )
        self.assertIn(
            "--start-run RUN-0001 --coordinator codex-coordinator --run-mode SINGLE_TASK",
            single,
        )
        self.assertIn(coordinator_claim, single)
        self.assertNotIn("codex-worker", single)
        self.assertIn(
            "--pause-run RUN-0001 --coordinator codex-coordinator --checkpoint CP-0002",
            single,
        )
        self.assertIn(
            "--set-status TASK-0001 DONE --evidence EV-0001 --run-id RUN-0001 --coordinator codex-coordinator --checkpoint CP-0001",
            single,
        )
        self.assertIn("--complete-run RUN-0001 --coordinator codex-coordinator", single)
        self.assertIn("--resume-run RUN-0001 --coordinator codex-coordinator", single)
        self.assertIn(
            "--start-run RUN-0001 --coordinator codex-coordinator --run-mode AUTONOMOUS",
            autonomous,
        )
        self.assertIn("--safe-ready --json", autonomous)
        self.assertIn(coordinator_claim, autonomous)
        self.assertNotIn("--isolated-worktrees", autonomous)
        self.assertIn("No subagent may edit implementation files", autonomous)
        self.assertNotIn("codex-worker", self.tasks)
        self.assertNotIn("--isolated-worktrees", self.tasks)
        self.assertIn("No subagent or worker edits files", self.tasks)
        self.assertIn("Maximum parallel workers | `1`", self.prd)
        self.assertIn("parallel writing is excluded", self.prd)
        self.assertNotIn("bounded parallelism", self.prd)
        self.assertRegex(
            autonomous,
            r"Never run the Engine against a persisted RUNNING\s+snapshot",
        )

    def test_aws_mutations_use_canonical_prompts_and_exact_action_receipts(
        self,
    ) -> None:
        build_single = self.prompt_section("BUILD-10")
        build_auto = self.prompt_section("BUILD-20")
        preflight = self.prompt_section("AWS-10")
        evidence = self.prompt_section("AWS-30")

        self.assertIn("BUILD-10 never\nexecutes an AWS mutation directly", build_single)
        self.assertIn("Route deployment through AWS-10 to AWS-20", build_auto)
        for build in (build_single, build_auto):
            self.assertIn("`NONE` or `DOCS_ONLY`", build)
            self.assertRegex(
                build,
                r"(?is)checkpoint.{0,180}AWS-10.{0,180}AWS-20.{0,180}AWS-50",
            )
        self.assertIn(
            "TASK-10 never emits\n`READ_ONLY` or `MUTATION`",
            self.prompt_section("TASK-10"),
        )
        self.assertIn("**AWS mode:** DOCS_ONLY until", preflight)
        self.assertIn("then READ_ONLY\nfor that named account scope", preflight)
        self.assertNotIn("DOCS_ONLY plus", preflight)
        self.assertIn("AUTHORIZE AWS READ-ONLY PREFLIGHT", self.prompts)
        self.assertIn("AUTHORIZE AWS DEPLOYMENT", self.prompts)
        self.assertIn("AUTHORIZE AWS TEARDOWN", self.prompts)
        self.assertIn("AUTHORIZE AWS READ-ONLY PREFLIGHT", self.runbook)
        self.assertIn("AUTHORIZE AWS DEPLOYMENT", self.runbook)
        self.assertIn("AUTHORIZE AWS TEARDOWN", self.runbook)
        self.assertIn("action-authorization evidence", self.runbook)
        self.assertIn("## Action authorization provenance", self.verify)
        self.assertIn("| Role or profile |", self.verify)
        self.assertIn(
            "<!-- bootstrap:aws-read-preflight-receipt:start -->", self.verify
        )
        self.assertIn("| Approver |", self.verify)
        self.assertIn("<!-- bootstrap:aws-deployment-receipt:start -->", self.verify)

        expected_read_receipt = """AUTHORIZE AWS READ-ONLY PREFLIGHT
Read authorization: AWS-READ-AUTH-0001
Construction authorization: AUTH-0001
Profile or role: <allowlisted profile or role>
Account: <12-digit account ID or approved alias>
Region: <AWS Region>
Environment: <environment>
Stack, application, and resources: <exact boundary>
Allowed read-only operations: <exact read-only operations>
Artifact digest: <immutable digest>
Prohibited operations: ALL_MUTATIONS
Valid until: <ISO 8601 time or exact one-operation condition>
Approver: <name/handle>"""

        def exact_read_receipt(document: str) -> str:
            matches = re.findall(
                r"(?s)(?:~~~|```)text\n"
                r"(AUTHORIZE AWS READ-ONLY PREFLIGHT\n.*?)\n(?:~~~|```)",
                document.replace("\r\n", "\n"),
            )
            self.assertEqual(len(matches), 1)
            return matches[0]

        for document in (self.prompts, self.runbook, self.verify):
            self.assertEqual(exact_read_receipt(document), expected_read_receipt)
        self.assertIn("<!-- bootstrap:aws-teardown-receipt:start -->", self.verify)

        self.assertIn("put\n`VERIFIED`, `PENDING_AWS`", evidence)

    def test_aws_delivery_evidence_is_technology_selected_and_authority_bound(
        self,
    ) -> None:
        preflight = self.prompt_section("AWS-10")
        deployment = self.prompt_section("AWS-20")
        residual_review = self.prompt_section("AWS-40")
        teardown = self.prompt_section("AWS-50")

        for document in (self.prd, self.runbook, self.verify, self.prompts):
            self.assertIn("CreateChangeSet", document)
            self.assertRegex(document, r"(?is)CreateChangeSet.{0,180}mutation")
            self.assertRegex(document, r"(?i)access(?:analyzer| analyzer)")
        self.assertIn("API: accessanalyzer.ValidatePolicy", preflight)
        self.assertNotIn("Create a CloudFormation change set here", preflight)
        self.assertIn("separate allowed operations", deployment)
        self.assertIn("GitHub OIDC", deployment)
        self.assertIn("short-lived credentials", deployment)
        self.assertIn("delayed AWS Budgets", deployment)
        self.assertIn("not guaranteed", deployment)

        self.assertRegex(self.prd, r"(?i)do not impose a\s+universal scanner")
        self.assertIn("## IaC validation evidence", self.verify)
        self.assertIn(
            "| Phase | TECH IDs | Validation method | Exact command or API | "
            "Artifact / plan / change-set binding | AWS account | AWS Region | "
            "AWS environment | Result | Observed at | Durable source |",
            self.verify,
        )
        self.assertIn("IaC plan/change-set binding", self.verify)
        self.assertIn("## Teardown reconciliation evidence", self.verify)
        for field in (
            "Expected manifest or stack",
            "Stack events and terminal status",
            "Resources retained",
            "Snapshots and backups",
            "Inventory or discovery limits",
        ):
            self.assertIn(field, self.verify)
        self.assertIn("expected removal", residual_review)
        self.assertRegex(residual_review, r"inventory/discovery (?:scope|limits)")
        self.assertIn("AWS-40", teardown)
        self.assertIn("no authenticated read-only", teardown)
        self.assertNotIn("Perform post-teardown read-only verification", teardown)

        self.assertIn("Lightweight Well-Architected decision review", self.prd)
        self.assertRegex(self.prd, r"not a separate audit or\s+gate")
        self.assertLessEqual(len(self.root_readme.splitlines()), 80)

    def test_aws_execution_lanes_are_derived_and_do_not_create_authority(self) -> None:
        for document in (self.verify, self.runbook, self.prompts):
            self.assertIn("STRUCTURED_API", document)
            self.assertIn("REVIEWED_SCRIPT", document)
            self.assertIn("AWS-EXEC-*", document)
        self.assertIn("request_match", self.runbook)
        self.assertIn("does not grant authority", self.verify)
        self.assertIn("grants nothing", self.prompts)
        self.assertIn("Natural-language descriptions do\nnot prove", self.verify)
        self.assertIn("Deployment and teardown remain separate", self.prompts)
        self.assertIn("<!-- bootstrap:aws-deployment-receipt:start -->", self.verify)
        self.assertIn("<!-- bootstrap:aws-teardown-receipt:start -->", self.verify)

    def test_profiles_are_overlays_not_additional_gates(self) -> None:
        for document in (self.prompts, self.prd, self.agents):
            self.assertIn("`quick-mvp`", document)
            self.assertIn("`standard`", document)
            self.assertIn("`high-risk`", document)
        self.assertIn("All profiles still use only Gate A and Gate B", self.prompts)
        self.assertIn("without adding lifecycle gates", self.agents)

    def test_owner_facing_profile_and_security_language_is_concrete(self) -> None:
        owner_documents = (
            self.root_readme,
            self.agents,
            self.prd,
            self.tasks,
            self.prompts,
        )
        rejected = (
            "controls " + "ceremony",
            "not weaker " + "security",
            "Deeper " + "threat",
            "threat " + "requirements",
            "privilege-escalation " + "properties",
        )
        for document in owner_documents:
            for phrase in rejected:
                self.assertNotIn(phrase, document)

        for document in (self.agents, self.prd, self.prompts):
            self.assertRegex(
                document,
                r"A Quick MVP is one small, reversible development release",
            )
            self.assertRegex(
                document,
                r"An AWS lane describes planned access; it does not authorize a\s+change",
            )
        self.assertRegex(
            self.root_readme,
            r"lowest practical total cost without\s+weakening required safeguards",
        )
        self.assertIn(
            "approved access succeeds and unapproved access is denied", self.prd
        )
        self.assertIn("Invalid, malformed, and oversized inputs are rejected", self.prd)
        self.assertIn("actual discovered defect", self.prd)
        for phrase in (
            "approved access succeeds and unapproved access is denied",
            "secrets stay out of code",
            "invalid or oversized input is rejected",
            "IAM permits only required actions",
            "sensitive data uses approved encryption",
        ):
            self.assertIn(phrase, self.security)

    def test_human_first_documents_label_the_exact_agent_reference(self) -> None:
        documents = {
            "root AGENTS": self.agents,
            "PRD": self.prd,
            "TASKS": self.tasks,
            "prompt pack": self.prompts,
            "app AGENTS": (PROJECT_ROOT / "app" / "AGENTS.md").read_text(
                encoding="utf-8"
            ),
            "infrastructure AGENTS": (
                PROJECT_ROOT / "infrastructure" / "AGENTS.md"
            ).read_text(encoding="utf-8"),
            "tests AGENTS": (PROJECT_ROOT / "tests" / "AGENTS.md").read_text(
                encoding="utf-8"
            ),
        }
        for name, document in documents.items():
            self.assertRegex(document, r"(?m)^## Agent reference", name)
        self.assertLessEqual(len(self.root_readme.splitlines()), 80)
        self.assertIn("## Start", self.root_readme)
        self.assertIn("## What to expect", self.root_readme)

    def test_readme_uses_one_line_gate_flow(self) -> None:
        gate_line = (
            "Gate A — approve requirements → Gate B — approve the PRD and "
            "construction boundary → Codex builds autonomously inside that boundary."
        )
        self.assertEqual(self.root_readme.count(gate_line), 1)
        self.assertNotIn("| Gate | You approve |", self.root_readme)

    def test_customer_readme_links_and_explicit_aws_handoff(self) -> None:
        links = {
            "Get started": "docs/SETUP.md",
            "Understand the workflow": "docs/WORKFLOW.md",
            "Troubleshoot": "docs/TROUBLESHOOTING.md",
            "Security": "SECURITY.md",
            "Optional hooks": "docs/HOOKS.md",
            "Maintainer evaluation": "docs/EVALUATION.md",
        }
        for label, target in links.items():
            with self.subTest(label=label):
                self.assertIn(f"[{label}]({target})", self.root_readme)
                self.assertTrue((REPOSITORY_ROOT / target).is_file())
        handoff = (
            "After Gate B, Codex builds locally. For AWS preflight, deployment "
            "verification, or teardown preparation, ask Codex to use "
            "`$operate-fastlane-aws`."
        )
        self.assertIn(handoff, " ".join(self.root_readme.split()))
        self.assertIn(handoff, " ".join(self.workflow.split()))
        self.assertIn("explicitly invoke `$operate-fastlane-aws`", self.prompts)
        workflow_words = " ".join(self.workflow.split())
        self.assertIn("exact current card ID, revision, and canonical digest", workflow_words)
        self.assertIn("requires no visible reply token", workflow_words)
        self.assertNotIn("safe only after the current reply token", workflow_words)
    def test_aws_lifecycle_map_and_lane_authority_are_plain_and_ordered(self) -> None:
        phase_positions = [
            self.workflow.index(f"| {phase} |")
            for phase in ("AWS-10", "AWS-20", "AWS-30", "AWS-40", "AWS-50")
        ]
        self.assertEqual(phase_positions, sorted(phase_positions))
        self.assertIn("Authorize the exact read-only account", self.workflow)
        self.assertIn(
            "Choose a residual disposition when required",
            self.workflow,
        )
        self.assertIn(
            "Fast Dev stays inside a current non-production Gate B envelope",
            self.root_readme,
        )
        self.assertIn(
            "explicit-gate deployment and teardown require their own exact receipts",
            self.root_readme,
        )

    def test_template_first_readme_sets_complete_user_expectations(self) -> None:
        for phrase in (
            "init template",
            "project name",
            "preferred AWS Region",
            "development budget",
            "https://github.com/Levi-Breedlove/aws-bootstrap/generate",
            "AWS Core",
            "AWS Agent Toolkit",
            "does not inspect AWS credentials or access an AWS account",
            "signed-in interactive Codex CLI",
            "uvx",
            "short, plain-language questions",
            "organized task plan",
            "exact authorization",
        ):
            self.assertIn(phrase, self.root_readme)
        for path in (
            "docs/project/PRD.md",
            "docs/project/TASKS.md",
            "docs/project/VERIFY.md",
            "docs/project/RUNBOOK.md",
        ):
            self.assertIn(path, self.root_readme)
        self.assertNotIn("codex plugin marketplace add", self.root_readme)
        self.assertNotIn("continue setup", self.root_readme)
        self.assertLessEqual(len(self.root_readme.splitlines()), 80)
        self.assertFalse((REPOSITORY_ROOT / "my-project" / "README.md").exists())

    def test_boot_prompt_has_stable_template_first_contract(self) -> None:
        boot = self.prompt_section("BOOT-00")
        self.assertIn("START AWS CODEX FASTLANE", boot)
        self.assertIn("Setup: <THIS_REPOSITORY|ADOPT_EXISTING_REPOSITORY>", boot)
        self.assertIn("no more than these three values", boot)
        self.assertIn("development budget posture", boot)
        self.assertIn("--in-place-template-instance --dry-run", boot)
        self.assertEqual(boot.count("--prerequisite-report-stdin"), 2)
        self.assertIn("exact in-memory `PREREQUISITES_READY` report", boot)
        self.assertIn("Never save that report", boot)
        self.assertIn("UNCONFIGURED_TEMPLATE", boot)
        self.assertIn("scripts/fastlane_presenter.py", boot)
        for field in ("Status:", "Updated:", "Need from you:", "Next:"):
            self.assertIn(field, self.prompts)
        for removed_field in (
            "Project:",
            "Region:",
            "Budget posture:",
            "Doctor:",
            "Next prompt:",
        ):
            self.assertNotIn(removed_field, boot)
        self.assertIn("At first intake, ask one to three", boot)
        self.assertIn("plain-language questions below the Define update", boot)
        self.assertIn("PREREQUISITES_READY", boot)
        self.assertNotIn("OWNER_ATTESTED_AND_PROBES_VERIFIED", boot)
        self.assertNotIn("hook conflict review", boot)

    def test_hook_docs_use_generated_opt_in_flow_and_discovery_order(self) -> None:
        hooks = (PROJECT_ROOT / "docs/HOOKS.md").read_text(encoding="utf-8")
        dependency = (PROJECT_ROOT / "docs/DEPENDENCY-POLICY.md").read_text(
            encoding="utf-8"
        )
        for document in (self.security, hooks):
            self.assertIn("configure-hooks --root .", document)
            self.assertIn("/hooks", document)
            self.assertIn(".codex/hooks.json", document)
            self.assertIn("restart", document.casefold())
        self.assertNotIn("manually copies", self.security)
        self.assertIn("copying the example does\nnot activate", self.security)
        self.assertLess(
            dependency.index("search_documentation"),
            dependency.index("retrieve_skill"),
        )

    def test_boot_setup_first_and_resume_are_single_action_contracts(self) -> None:
        boot = self.prompt_section("BOOT-00")
        for phrase in (
            "If the project is already initialized, do not print the welcome",
            "rerun prerequisites",
            "one owner action",
            "owner's attestation",
            "private trust database",
        ):
            self.assertIn(phrase, boot)
        self.assertRegex(
            boot,
            r"Only after `PREREQUISITES_READY`",
        )
        self.assertIn("never repeat setup", self.agents)
        self.assertIn("follows the Fastlane Engine-selected route", self.agents)
        self.assertIn(
            "does not compare hook hashes, request screenshots,\nrun synthetic probes",
            boot,
        )

    def test_routine_gate_and_aws_receipts_are_separate(self) -> None:
        common = self.prompts.split("### Human response contracts", 1)[1].split(
            "## Prompt index", 1
        )[0]
        routine = common.split("#### Routine status", 1)[1].split(
            "#### Gate receipt", 1
        )[0]
        routine_block = routine.split("~~~text", 1)[1].split("~~~", 1)[0]
        routine_fields = (
            "FASTLANE ·",
            "Status:",
            "Updated:",
            "Need from you:",
            "Next:",
            "Audit:",
        )
        for field in routine_fields:
            self.assertEqual(routine_block.count(field), 1)
        self.assertIn("Use one response type", common)
        self.assertIn("must not append a routine status or AWS receipt", common)

        gate_a = self.prompt_section("INTAKE-20")
        gate_b = self.prompt_section("DESIGN-20")
        self.assertIn("**Receipt:** Exact Gate A receipt", gate_a)
        self.assertIn("**Receipt:** Exact Gate B receipt", gate_b)
        self.assertNotIn("FASTLANE STATUS", gate_a)
        self.assertNotIn("FASTLANE STATUS", gate_b)
        self.assertNotIn("AWS AUTHORITY AND EVIDENCE RECEIPT", gate_a)
        self.assertNotIn("AWS AUTHORITY AND EVIDENCE RECEIPT", gate_b)

        for prompt_id in ("AWS-10", "AWS-20", "AWS-30", "AWS-40", "AWS-50"):
            self.assertIn(
                "AWS authority/evidence receipt", self.prompt_section(prompt_id)
            )
        for field in (
            "Account:",
            "Region:",
            "Environment:",
            "Resources:",
            "Operations:",
            "Cost ceiling:",
            "Rollback:",
            "Expiration:",
            "Observed results:",
        ):
            self.assertIn(field, common)
        for prompt_id in ("BOOT-00", "INTAKE-10"):
            self.assertNotIn(
                "AWS AUTHORITY AND EVIDENCE RECEIPT",
                self.prompt_section(prompt_id),
            )

    def test_repo_scoped_skills_have_distinct_safe_trigger_contracts(self) -> None:
        implicit = {
            "fastlane": "true",
            "maintain-fastlane": "true",
            "launch-fastlane": "false",
            "plan-fastlane": "false",
            "build-fastlane": "false",
            "explain-fastlane": "false",
            "operate-fastlane-aws": "false",
        }
        descriptions: set[str] = set()
        for name, expected_implicit in implicit.items():
            root = REPOSITORY_ROOT / ".agents" / "skills" / name
            skill = (root / "SKILL.md").read_text(encoding="utf-8")
            config = (root / "agents" / "openai.yaml").read_text(encoding="utf-8")
            self.assertTrue(skill.startswith("---\nname: " + name + "\n"))
            description = re.search(r"(?m)^description:\s*(.+)$", skill)
            self.assertIsNotNone(description)
            descriptions.add(description.group(1) if description else "")
            self.assertIn("interface:", config)
            self.assertIn("display_name:", config)
            self.assertIn("short_description:", config)
            self.assertIn("default_prompt:", config)
            self.assertIn(
                f"allow_implicit_invocation: {expected_implicit}",
                config,
            )
            for forbidden in ("model:", "permissions:", "hooks:", "mcp_servers:"):
                self.assertNotIn(forbidden, config)
        self.assertEqual(len(descriptions), len(implicit))
        aws_skill = (
            REPOSITORY_ROOT / ".agents" / "skills" / "operate-fastlane-aws" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Use only when the user explicitly invokes this skill", aws_skill)
        self.assertIn("They never authorize an AWS change", aws_skill)
        fastlane_config = (
            REPOSITORY_ROOT / ".agents/skills/fastlane/agents/openai.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("explicitly invoke $operate-fastlane-aws", fastlane_config)
        operator_config = (
            REPOSITORY_ROOT
            / ".agents/skills/operate-fastlane-aws/agents/openai.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: false", operator_config)
        explain_skill = (
            REPOSITORY_ROOT / ".agents/skills/explain-fastlane/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Activate only from an explicit owner request", explain_skill)
        self.assertIn("restore the exact", explain_skill)
        self.assertIn("Learning mode — explanation only", explain_skill)
        for alias in ("launch-fastlane", "plan-fastlane", "build-fastlane"):
            content = (
                REPOSITORY_ROOT / ".agents" / "skills" / alias / "SKILL.md"
            ).read_text(encoding="utf-8")
            self.assertIn("Delegate to `$fastlane`", content)
        maintain = (
            REPOSITORY_ROOT / ".agents/skills/maintain-fastlane/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("never adopter application planning", maintain)
        for mode in ("AUDIT", "PLAN", "IMPLEMENT", "PUBLISH"):
            self.assertIn(f"`{mode}`", maintain)
        self.assertIn("default to `AUDIT` or", maintain)
        self.assertIn("require explicit `PUBLISH` authority", maintain)
        self.assertIn("baseline branch and exact commit", maintain)
        self.assertIn("exact file allowlist", maintain)
        self.assertIn("observable acceptance criteria", maintain)
        self.assertIn("maximum changed files", maintain)
        self.assertIn("Unrelated discoveries are report-only", maintain)
        self.assertIn("Stop before widening", maintain)
        for route in ("BOOT", "INTAKE", "DESIGN", "BUILD"):
            self.assertIn(route, maintain)
        self.assertIn("short-lived maintenance branch", maintain)
        self.assertIn("targeting only\n   `fast-lane-maint`", maintain)
        for check in (
            "safety-tests (3.11)",
            "safety-tests (3.12)",
            "safety-tests (3.13)",
            "windows-smoke",
            "macos-setup-smoke",
        ):
            self.assertIn(f"`{check}`", maintain)
        self.assertIn("explicit emergency publication", maintain)
        self.assertIn("Never force-push or delete", maintain)
        self.assertIn("separate repository-setting action", maintain)

    def test_maintenance_modes_do_not_delegate_to_application_lifecycle(self) -> None:
        maintain = (
            REPOSITORY_ROOT / ".agents/skills/maintain-fastlane/SKILL.md"
        ).read_text(encoding="utf-8")
        config = (
            REPOSITORY_ROOT / ".agents/skills/maintain-fastlane/agents/openai.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("never starts", maintain)
        self.assertNotIn("Delegate to `$fastlane`", maintain)
        self.assertNotIn("init template", maintain)
        self.assertNotIn("APPROVE REQUIREMENTS GATE A", maintain)
        self.assertNotIn("APPROVE PRD AND CONSTRUCTION GATE B", maintain)
        self.assertIn("AUDIT, PLAN, IMPLEMENT, or PUBLISH", config)
        self.assertIn("without starting an application lifecycle", config)

    def test_task_cards_are_human_first_with_collapsed_exact_metadata(self) -> None:
        self.assertIn("## How to read a task card", self.tasks)
        self.assertIn("- Status: BACKLOG", self.tasks)
        self.assertIn("- Owner: UNASSIGNED", self.tasks)
        self.assertIn("- Blocker: NONE", self.tasks)
        self.assertIn("- GitHub issue: PENDING_SYNC", self.tasks)
        self.assertIn("<details>", self.tasks)
        self.assertIn("Exact metadata used by Codex and task_waves.py", self.tasks)
        required_metadata = (
            "Status",
            "Requirements",
            "Design",
            "Authorization",
            "Depends on",
            "Dependency waivers",
            "Owner",
            "Run ID",
            "Risk",
            "Write set",
            "External state",
            "AWS mode",
            "Attempt budget",
            "Attempts used",
            "Evidence",
            "Blocker",
            "Skip record",
            "GitHub issue",
            "Last checkpoint",
            "Last updated",
        )
        task_template = self.tasks.split("~~~text", 1)[1].split("~~~", 1)[0]
        for key in required_metadata:
            self.assertEqual(
                task_template.count(f"- {key}:"),
                1,
                f"Task template must contain one {key} metadata line",
            )

    def test_brownfield_adoption_requires_exact_user_confirmation(self) -> None:
        boot = self.prompt_section("BOOT-00")
        self.assertIn("does not authorize `ADOPT_TEMPLATE`", boot)
        self.assertIn("CONFIRM BOOTSTRAP ADOPTION PLAN", boot)
        self.assertIn("plan_sha256: <64 lowercase hex characters>", boot)
        self.assertIn("authorized_by: <human owner>", boot)
        self.assertIn("authorization_source: OWNER_CONFIRMATION", boot)
        self.assertIn(
            "schema version, both roots, and the complete ordered decision", boot
        )
        self.assertIn("It never hashes decisions alone", boot)
        self.assertIn("complete ordered decision map", self.agents)

    def test_task_prompt_and_ledger_define_validator_shape(self) -> None:
        task_prompt = self.prompt_section("TASK-10")
        for heading in (
            "#### Outcome",
            "#### Acceptance criteria",
            "#### Validation",
            "#### Execution log",
            "#### Agent execution details",
        ):
            self.assertIn(heading, task_prompt)
            self.assertIn(heading, self.tasks)
        self.assertIn("every remaining singleton metadata line", task_prompt)
        self.assertIn("A READY task cannot contain `TODO`", self.tasks)
        self.assertIn("- Dependency waivers: NONE", self.tasks)
        projection_header = (
            "| Property ID | Framework TECH ID | Exact command | "
            "Run target/time bound | Seed or reproduction format | "
            "Evidence destination |"
        )
        self.assertIn(projection_header, self.tasks)
        self.assertIn(projection_header.strip("| "), task_prompt)
        self.assertIn(
            "```bash\n<each exact property and Harness command owned by this task, once>\n```",
            self.tasks,
        )
        self.assertIn("exact Property execution projection table", task_prompt)

    def test_readiness_cards_are_complete_and_prompt_filled(self) -> None:
        gate_a_fields = (
            "Outcome",
            "Owner and users",
            "Scope and non-goals",
            "Measurable requirement/acceptance IDs",
            "Data boundary",
            "Identity/security boundary",
            "Environment/Region",
            "Failure/recovery",
            "Cost posture",
            "Intake provenance",
        )
        gate_b_fields = (
            "Design basis IDs",
            "Architecture/components",
            "Technology/toolchains/version policy",
            "Interfaces/data flow",
            "Identity/secrets",
            "Failure/retry/concurrency",
            "Deployment/operations",
            "Validation/evidence",
            "Rollback/recovery/teardown",
            "Brownfield compatibility/migration",
            "Outstanding gaps",
        )
        self.assertIn("### Gate A — readiness card", self.prd)
        self.assertIn("### Gate B — readiness card", self.prd)
        for field in (*gate_a_fields, *gate_b_fields):
            self.assertIn(f"| {field} |", self.prd)
        self.assertIn("| Authorized cost posture |", self.prd)
        self.assertIn(
            "Fill the Gate A readiness card with these exact fields",
            self.prompt_section("REQ-10"),
        )
        self.assertIn(
            "Fill the Gate B readiness card with these exact fields",
            self.prompt_section("DESIGN-10"),
        )
        gate_b = self.prompt_section("DESIGN-20")
        self.assertIn("all current readiness-card fields", gate_b)
        self.assertNotIn(
            "all ten fields from the current Gate B readiness card", gate_b
        )
        self.assertIn("`NOT_APPLICABLE — <reason>`", self.prd)

    def test_aws_core_design_evidence_is_advisory_and_tech_bindable(self) -> None:
        design = self.prompt_section("DESIGN-10")
        for document in (self.verify, design):
            self.assertIn("DES-0001; TECH: TECH-0001, TECH-0002", document)
            self.assertIn(
                "DES-0001; TECH: NONE — no technology/toolchain impact", document
            )
        self.assertIn("Advisory Design binding", self.verify)
        self.assertRegex(self.verify, r"never\s+selects a technology")
        self.assertIn("observed AWS Core version is metadata, never a pin", design)

    def test_cost_posture_and_secure_serverless_first_contract(self) -> None:
        boot = self.prompt_section("BOOT-00")
        intake = self.prompt_section("INTAKE-10")
        requirements = self.prompt_section("REQ-10")
        design = self.prompt_section("DESIGN-10")
        planning_references = "\n".join(
            (PROJECT_ROOT / ".agents/skills/fastlane/references" / name).read_text(
                encoding="utf-8"
            )
            for name in ("define.md", "design.md")
        )
        architecture_challenger = (
            PROJECT_ROOT / ".codex/agents/fastlane-architecture-challenger.toml"
        ).read_text(encoding="utf-8")

        self.assertIn("no more than these three values", boot)
        self.assertIn("development budget posture", boot)
        self.assertIn("MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED", boot)
        self.assertIn(
            "MINIMIZE_TOTAL_COST; HARD_CAP: <ISO_CURRENCY> <OWNER_AMOUNT>",
            boot,
        )
        self.assertIn("--cost-posture", boot)
        self.assertIn("A missing amount alone never blocks intake", intake)
        self.assertIn(
            "MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED",
            planning_references,
        )
        self.assertIn("Cost posture; Intake provenance", requirements)
        self.assertIn("Do not manufacture a numeric ceiling for Gate A", requirements)
        self.assertIn("Cost posture: <exact current Gate A cost posture>", self.prompts)

        for surface in (
            self.agents,
            self.prd,
            design,
            planning_references,
            architecture_challenger,
        ):
            self.assertIn("serverless", surface.lower())
        self.assertIn("secure pay-per-use\nserverless options", self.root_readme)
        for surface in (self.agents, self.prd, planning_references):
            self.assertIn("MINIMIZE_TOTAL_COST", surface)
        self.assertRegex(
            self.root_readme,
            r"lowest practical total cost without\s+weakening required safeguards",
        )
        self.assertIn("Never weaken one of those required controls", design)
        self.assertIn("measurable expansion or migration\ntriggers", design)
        self.assertIn(
            "Cost ceiling: <finite positive ISO-currency amount, for example USD: 20.00>",
            self.prompts,
        )
        self.assertIn("| AWS cost ceiling |", self.prd)
        self.assertIn("not a guaranteed AWS billing stop", self.prd)
        for surface in (self.root_readme, self.agents, self.prd, self.prompts):
            self.assertNotIn("{{MONTHLY_BUDGET}}", surface)

    def test_gate_b_binds_canonical_complete_envelope_digest(self) -> None:
        receipt_line = "Construction envelope SHA-256: sha256:<64-lowercase-hex>"
        self.assertIn("| Authorized construction envelope SHA-256 |", self.prd)
        self.assertIn("| Construction envelope SHA-256 reviewed |", self.prd)
        self.assertIn(receipt_line, self.prd)
        self.assertEqual(self.prompts.count(receipt_line), 2)
        self.assertIn("header, separator, and every boundary row", self.prd)
        self.assertIn("append one final LF", self.prd)
        self.assertIn("| Design contract SHA-256 |", self.prd)
        self.assertIn("Engine-derived current value", self.prompts)
        for table_name in (
            "Architecture driver",
            "Candidate",
            "Selection",
            "Traceability",
            "Material AWS evidence",
            "Technology decision",
            "Property applicability",
            "Property definition",
            "Property execution",
        ):
            self.assertIn(table_name, self.prd)
            self.assertRegex(self.prompts, table_name.replace(" ", r"\s+"))

    def test_construction_envelope_uses_bindable_grammars(self) -> None:
        required_rows = (
            "Project mode",
            "Delivery profile and effective risk",
            "Project AWS lane",
            "Authorized requirement and design IDs",
            "Design contract SHA-256",
            "Authorized baseline commit",
            "Protected dirty paths",
            "Allowed external-state targets",
            "Local command boundary",
            "Task boundary",
            "GitHub repository, branch, and merge constraints",
            "Authorization expiry or completion condition",
        )
        for row in required_rows:
            self.assertIn(f"| {row} |", self.prd)
        self.assertIn("`<profile> / <risk>`", self.prd)
        self.assertIn("`ALLOW_PREFIXES: prefix; prefix`", self.prd)
        self.assertIn("`DERIVED_FROM_AUTHORIZED_IDS_AND_WRITE_SET`", self.prd)
        self.assertIn(
            "`REPO: owner/name; BRANCH: branch; MERGE: ALLOWED\\|PROHIBITED`", self.prd
        )
        self.assertIn(
            "`ENVIRONMENT: <exact name>; CLASS: NON_PRODUCTION\\|PRODUCTION`",
            self.prd,
        )
        self.assertIn("`EXACT_DIGEST: sha256:<64 lowercase hex>`", self.prd)
        self.assertIn(
            "`DERIVED_FROM_AUTHORIZED_SOURCE: SHA-256 from baseline <full authorized commit>; <deterministic rule>`",
            self.prd,
        )
        self.assertIn(
            "`Expires at <ISO 8601 with timezone>; earlier completion: <exact condition>`",
            self.prd,
        )
        for row in (
            "AWS account",
            "AWS role or profile",
            "AWS Region",
            "AWS environment",
            "AWS stack or application",
            "AWS resource allowlist",
            "AWS allowed operations",
            "AWS cost ceiling",
            "AWS prohibited operations",
            "AWS artifact authorization and provenance",
            "AWS rollback boundary",
            "AWS authorization validity",
        ):
            self.assertIn(f"| {row} |", self.prd)
        for document in (
            self.prd,
            self.workflow,
            self.prompts,
        ):
            self.assertRegex(document, r"AWS allowed\s+operations")
            self.assertIn("union", document.lower())
        for document in (self.prd, self.prompts):
            self.assertRegex(
                document,
                r"(?is)explicit-gate.{0,240}MUTATE_LISTED_RESOURCES.{0,240}separate.{0,120}(?:action|AWS-20)",
            )
        self.assertNotIn("If a fast development deployment is proposed", self.prompts)

    def test_git_checkpoint_plan_and_release_lifecycles_are_explicit(self) -> None:
        self.assertIn("| Task-plan state | `UNINITIALIZED` |", self.tasks)
        for state in ("UNINITIALIZED", "CURRENT", "STALE"):
            self.assertIn(state, self.tasks)
        self.assertRegex(self.tasks, r"commits? only authorized wave changes")
        self.assertIn("Last known-green commit", self.tasks)
        for state in ("NOT_READY", "READY_TO_DEPLOY", "RELEASE_VERIFIED"):
            self.assertIn(state, self.verify)
            self.assertIn(state, self.prompt_section("RELEASE-10"))
        self.assertIn(
            "AWS-30 | Reconcile one deployment attempt read-only | RELEASE-10, or AWS-30 while stale",
            self.prompts,
        )
        aws_30 = self.prompt_section("AWS-30")
        self.assertIn("**Next:** `COMPLETE` or `BLOCKED` returns to RELEASE-10", aws_30)
        self.assertIn("One first `STALE` remains AWS-30", aws_30)
        self.assertIn("Local Git setup:", self.prompt_section("BOOT-00"))

    def test_done_requires_structured_observed_local_evidence(self) -> None:
        header = (
            "| Evidence ID | Task | Command or observation | Result | Actor | "
            "Observed at | Commit / worktree / artifact | Durable source | Status |"
        )
        self.assertIn("## Task completion evidence", self.verify)
        self.assertIn(header, self.verify)
        for document in (self.agents, self.tasks, self.prompts):
            self.assertIn("Task completion evidence", document)
        for field in (
            "command/result",
            "actor",
            "commit/worktree/artifact",
            "LOCAL_PASS",
            "VERIFIED",
        ):
            self.assertIn(field, self.prompts)

    def test_brownfield_mandatory_facts_are_not_nullable(self) -> None:
        self.assertIn("every baseline fact is mandatory", self.prd)
        self.assertIn("Only these fields\nare nullable", self.prd)
        self.assertIn("known defects and accepted debt\n`NONE_OBSERVED`", self.prd)
        self.assertIn(
            "Only drift, dirty changes, known debt/defects",
            self.prompt_section("REQ-10"),
        )

    def test_aws_mode_mapping_is_canonical(self) -> None:
        self.assertIn("Project AWS lane", self.prompts)
        self.assertIn("Local task modes", self.prompts)
        self.assertIn("Gate B AWS maximum", self.prompts)
        self.assertIn("Authenticated AWS route", self.prompts)
        self.assertIn("Gate B AWS boundary", self.prompts)
        self.assertIn("MUTATE_LISTED_RESOURCES", self.prompts)
        self.assertIn("Prompt AWS mode", self.prd)
        self.assertIn("Gate B AWS boundary", self.prd)
        self.assertIn("MUTATE_LISTED_RESOURCES", self.prd)
        self.assertNotIn("PLAN_ONLY", self.prd)
        self.assertIn(
            "| `explicit-gate` | `NONE` or `DOCS_ONLY` | `DOCS_ONLY`, "
            "`READ_ONLY`, or `MUTATE_LISTED_RESOURCES` |",
            self.prompts,
        )
        for phrase in (
            "A Gate B maximum of `NONE` allows local task mode `NONE` only",
            "Authenticated `READ_ONLY` and `MUTATION` are phase modes, never task metadata",
            "fail closed and replan",
            "Preserve DONE completion records and append-only VERIFY",
            "`aws_mode_boundary`",
        ):
            self.assertIn(phrase, self.prompts)
        for document in (
            self.prd,
            self.workflow,
            self.runbook,
            self.prompts,
            self.fastlane_design,
        ):
            self.assertRegex(document, r"AWS allowed\s+operations")
            self.assertIn("union", document.lower())
            for phase in ("AWS-10", "AWS-20", "AWS-30", "AWS-40", "AWS-50"):
                self.assertIn(phase, document)
        self.assertRegex(
            self.authorization_receipts,
            r"(?is)subset.{0,220}Gate B.{0,220}(?:current phase|phase mode).{0,220}(?:intersection|never broadens)",
        )
        self.assertRegex(
            self.prompts,
            r"(?is)explicit-gate maximum grants no\s+mutation by itself",
        )
        self.assertIn("phase-appropriate subset", self.fastlane_deliver)
        self.assertIn("mutation-capable Gate B envelope", self.fastlane_deliver)
        self.assertRegex(
            self.operate_fastlane_aws, r"subset permitted in the\s+current phase"
        )
        self.assertIn("mutation-capable Gate B envelope", self.operate_fastlane_aws)
        self.assertIn(
            "wildcard-free subset of the Gate B maximum", self.authorization_receipts
        )
        self.assertIn(
            "a receipt never broadens an approved", self.authorization_receipts
        )

    def test_define_and_bug_prompts_forbid_authenticated_account_access(self) -> None:
        expected_modes = {
            "INTAKE-10": "NONE",
            "REQ-10": "DOCS_ONLY",
            "INTAKE-20": "NONE",
            "DESIGN-10": "DOCS_ONLY",
            "DESIGN-20": "NONE",
            "BUG-10": "NONE, or DOCS_ONLY",
        }
        for prompt, mode in expected_modes.items():
            with self.subTest(prompt=prompt):
                section = self.prompt_section(prompt)
                self.assertIn(f"**AWS mode:** {mode}", section)
                self.assertRegex(
                    section,
                    r"(?is)(?:never|do not|neither).{0,120}access(?:es)?\s+an\s+AWS\s+account",
                )

    def test_manifest_matches_pack_and_required_files_exist(self) -> None:
        manifest_path = PROJECT_ROOT / "bootstrap.manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["bootstrap_version"], "1.0.5")
        self.assertEqual(manifest["canonical_prompt_ids"], PROMPT_IDS)
        self.assertIn("**Pack version:** 1.0.5", self.prompts)
        missing = [
            path
            for path in manifest["required_files"]
            if not (PROJECT_ROOT / path).is_file()
        ]
        self.assertEqual(missing, [])

    def test_continuation_and_side_question_contracts_are_executable(self) -> None:
        self.assertIn(
            "python scripts/fastlane_presenter.py owner --input-stdin",
            self.prompts,
        )
        self.assertIn(
            "python scripts/fastlane_presenter.py side-question",
            self.prompts,
        )
        boot = self.prompt_section("BOOT-00")
        self.assertIn("After each phase checkpoint, rerun the Engine", boot)
        self.assertIn("internal prompt ID is never itself a reason to pause", boot)

        gate_a = self.prompt_section("INTAKE-20")
        self.assertIn("same turn and begin Design", gate_a)
        self.assertIn("do not combine it with a routine response", gate_a)

        gate_b = self.prompt_section("DESIGN-20")
        self.assertIn("rerun the Engine in the same turn", gate_b)
        self.assertIn("task generation and permitted local construction", gate_b)

        build = self.prompt_section("BUILD-20")
        self.assertIn("derive progress only", build)
        self.assertIn("task totals and task-ID fields", build)
        self.assertIn("`NONE_CONTINUE_AUTOMATICALLY`", build)

        owner_reference = (
            PROJECT_ROOT / ".agents/skills/fastlane/references/owner-responses.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "never repeats a formal Gate A, Gate B, or AWS receipt", owner_reference
        )

    def test_context_speed_decision_and_evidence_contracts_are_canonical(self) -> None:
        coordinator = (PROJECT_ROOT / ".agents/skills/fastlane/SKILL.md").read_text(
            encoding="utf-8"
        )
        owner = (
            PROJECT_ROOT / ".agents/skills/fastlane/references/owner-responses.md"
        ).read_text(encoding="utf-8")
        workflow = (PROJECT_ROOT / "docs/WORKFLOW.md").read_text(encoding="utf-8")
        verify = (PROJECT_ROOT / "docs/project/VERIFY.md").read_text(encoding="utf-8")
        self.assertIn("maximum_initial_bytes", coordinator)
        self.assertIn("Never silently truncate a row", coordinator)
        self.assertIn("not an implicit initial load", coordinator)
        self.assertIn("resolved_initial_slices", coordinator)
        self.assertIn("resolved_on_demand_slices", coordinator)
        for label in (
            "Decision:",
            "Recommendation:",
            "Why:",
            "Tradeoff:",
            "Reply:",
            "After that:",
        ):
            self.assertIn(f"`{label}`", owner)
        self.assertIn("at most one clarification round", workflow)
        self.assertIn("Gate A continues into Design in the", workflow)
        self.assertIn("Gate B continues into task generation", workflow)
        for level in (
            "E0_PROPOSED",
            "E1_SOURCE_VERIFIED",
            "E2_LOCALLY_VALIDATED",
            "E3_AWS_READ_OBSERVED",
            "E4_DEPLOYED_OBSERVED",
            "E5_RECOVERY_OBSERVED",
        ):
            self.assertIn(level, verify)
        for area in (
            "Architecture",
            "Harness",
            "Local evidence",
            "Runbook",
            "AWS authority",
            "Teardown",
            "Package",
            "Model/user pilot",
        ):
            self.assertRegex(verify, rf"\| {re.escape(area)} \|")

    def test_normative_requirements_use_one_ears_and_acceptance_schema(self) -> None:
        header = (
            "| ID | Requirement | EARS form | Acceptance ID | Acceptance criteria | "
            "Acceptance form |"
        )
        self.assertEqual(self.prd.count(header), 8)
        for acceptance_form in ("GHERKIN", "MEASURABLE"):
            self.assertIn(acceptance_form, self.prd)
        self.assertIn(
            "| QAS ID | Requirement IDs | Source | Stimulus | Environment | "
            "Artifact | Response | Response measure |",
            self.prd,
        )
        self.assertIn("NOT_APPLICABLE", self.prd)

        task_template = self.tasks.split("~~~text", 1)[1].split("~~~", 1)[0]
        for forbidden_metadata in (
            "EARS form",
            "INVEST",
            "THIN_SLICE",
            "DEFINITION_OF_DONE",
        ):
            self.assertNotIn(f"- {forbidden_metadata}:", task_template)

    def test_task_10_requires_invest_thin_slices_and_existing_done_contract(
        self,
    ) -> None:
        task_prompt = self.prompt_section("TASK-10")
        deliver_reference = (
            PROJECT_ROOT / ".agents/skills/fastlane/references/deliver.md"
        ).read_text(encoding="utf-8")
        for surface in (self.tasks, task_prompt, deliver_reference):
            self.assertIn("Fastlane INVEST profile", surface)
            self.assertIn("Thin Vertical Slice", surface)
            self.assertIn("Fastlane Definition of Done", surface)
        for attribute in (
            "Independent",
            "Negotiable",
            "Valuable",
            "Estimable",
            "Small",
            "Testable",
        ):
            self.assertIn(attribute, self.tasks)
        for done_condition in (
            "all acceptance criteria pass",
            "exact validation ran and passed",
            "applicable property tests pass",
            "observed evidence is recorded",
            "inside REQ/DES/AUTH and write boundaries",
            "execution log and checkpoint state are current",
            "no unresolved blocker or placeholder remains",
            "required documentation and runbook changes are complete",
        ):
            self.assertIn(done_condition, self.tasks)
        self.assertIn("migration-only", self.tasks)
        self.assertIn("security-only", self.tasks)
        self.assertIn("infrastructure-only", self.tasks)
        self.assertIn("evidence-only", self.tasks)

    def test_tdd_mikado_and_risk_methods_are_conditional_not_new_gates(self) -> None:
        deliver_reference = (
            PROJECT_ROOT / ".agents/skills/fastlane/references/deliver.md"
        ).read_text(encoding="utf-8")
        define_reference = (
            PROJECT_ROOT / ".agents/skills/fastlane/references/define.md"
        ).read_text(encoding="utf-8")
        design_reference = (
            PROJECT_ROOT / ".agents/skills/fastlane/references/design.md"
        ).read_text(encoding="utf-8")
        maintain_skill = (
            PROJECT_ROOT / ".agents/skills/maintain-fastlane/SKILL.md"
        ).read_text(encoding="utf-8")
        workflow = (PROJECT_ROOT / "docs/WORKFLOW.md").read_text(encoding="utf-8")

        for phrase in (
            "Use Red/Green TDD when it provides meaningful executable feedback",
            "pure documentation",
            "manifest regeneration",
            "Preserve the Property-Based Testing contract exactly",
        ):
            self.assertIn(phrase, deliver_reference)
        self.assertRegex(deliver_reference, r"Chicago\s+School")
        self.assertRegex(deliver_reference, r"London\s+School")
        self.assertIn("Mikado Method", maintain_skill)
        self.assertIn("not a lifecycle phase or task state", maintain_skill)
        self.assertIn("Use STRIDE only when", define_reference)
        self.assertIn("Use LINDDUN only when", define_reference)
        self.assertIn("Use ATAM only", design_reference)
        self.assertIn("Nygard-style ADR only", design_reference)
        self.assertIn(
            "conditional techniques, not lifecycle stages or approval gates",
            " ".join(workflow.split()),
        )

    def test_gate_b_harness_profile_is_risk_derived_and_closed_loop(self) -> None:
        design_reference = (
            PROJECT_ROOT / ".agents/skills/fastlane/references/design.md"
        ).read_text(encoding="utf-8")
        deliver_reference = (
            PROJECT_ROOT / ".agents/skills/fastlane/references/deliver.md"
        ).read_text(encoding="utf-8")
        workflow = (PROJECT_ROOT / "docs/WORKFLOW.md").read_text(encoding="utf-8")

        header = (
            "| Harness ID | Layer | Selected check or tool | Trigger | Basis IDs | "
            "Exact command or API | Evidence destination | Required or conditional status |"
        )
        self.assertIn(header, self.prd)
        prd_words = " ".join(self.prd.split())
        for basis in (
            "selected `TECH-*` register",
            "delivery profile",
            "effective risk",
            "data classification",
            "identity boundary",
            "public exposure",
            "recovery target",
            "AWS lane",
        ):
            self.assertIn(basis, prd_words)
        for status in (
            "`REQUIRED`",
            "`CONDITIONAL — <trigger>`",
            "`NOT_APPLICABLE — <concrete reason>`",
        ):
            self.assertIn(status, self.prd)
        self.assertIn("does not impose a universal scanner", self.prd)
        self.assertIn("Gate B also records a risk-derived Harness Profile", workflow)

        evidence_header = (
            "| Evidence ID | Harness ID | Layer | Basis IDs | Exact command or API | "
            "Artifact / environment | Observed result | Observed at | Durable source | Status |"
        )
        self.assertIn(evidence_header, self.verify)
        self.assertIn("Preserve a failed row and append the later rerun", self.verify)

        design_prompt = self.prompt_section("DESIGN-10")
        task_prompt = self.prompt_section("TASK-10")
        build_prompt = self.prompt_section("BUILD-10")
        release_prompt = self.prompt_section("RELEASE-10")
        self.assertIn("Gate B Harness Profile", design_prompt)
        self.assertIn("Do not add Harness\nmetadata fields", task_prompt)
        self.assertIn("Harness execution evidence", build_prompt)
        self.assertIn("current observed evidence", release_prompt)
        self.assertIn("without adding task metadata", deliver_reference)
        design_words = " ".join(design_reference.split())
        self.assertIn("do not impose a universal scanner", design_words)
        for concern in (
            "syntax/build",
            "type checking when supported",
            "formatting or canonicalization",
            "linting",
            "secret scanning",
            "dependency/SCA",
            "container scanning when containers apply",
            "IaC/policy validation",
            "license checks when material",
        ):
            self.assertIn(concern, design_words)
        self.assertIn("`REQUIRED` with an exact command", design_reference)
        self.assertIn("`CONDITIONAL — <trigger>` with an exact", design_reference)
        self.assertIn("`NOT_APPLICABLE — <technology/risk reason>`", design_reference)
        self.assertIn("Do not add a second Harness table", design_reference)
        self.assertIn(
            "Semantic Anchors remain optional internal vocabulary", design_reference
        )
        self.assertNotIn("## HARNESS-10", self.prompts)

    def test_aws_core_role_and_design_discovery_seed_are_consistent(self) -> None:
        design_words = " ".join(self.fastlane_design.split())
        self.assertIn(
            "Codex selects and coordinates the proposed product architecture",
            design_words,
        )
        self.assertIn(
            "AWS Core supplies current AWS knowledge, decision guidance, procedures, "
            "and execution tools",
            design_words,
        )
        self.assertIn(
            "Codex chooses the architecture. AWS Core supplies current expertise; "
            "it cannot approve or authorize.",
            self.root_readme,
        )
        self.assertIn(
            "Fastlane requires the current official\n`aws-core@agent-toolkit-for-aws`",
            self.workflow,
        )
        self.assertNotIn("AWS Core selects", self.prompts)
        self.assertNotIn("AWS Core selects", self.verify)
        self.assertIn("Codex follows current AWS Core guidance to select", self.prompts)
        self.assertIn("Codex follows current AWS Core guidance to select", self.verify)
        evidence_rows = [
            [cell.strip() for cell in line.strip("|").split("|")]
            for line in self.prd.splitlines()
            if line.startswith("| AWS-EV-")
        ]
        self.assertTrue(evidence_rows)
        self.assertEqual({row[1] for row in evidence_rows}, {"AWS-DISC-0002"})
        design_discovery_rows = [
            line
            for line in self.verify.splitlines()
            if line.startswith("| `DESIGN-10` | `AWS-DISC-0002`")
        ]
        self.assertEqual(len(design_discovery_rows), 2)

    def test_method_contracts_leave_all_exact_authorization_receipts_intact(
        self,
    ) -> None:
        gate_a = """APPROVE REQUIREMENTS GATE A
Requirements revision: REQ-0001
Cost posture: MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED
Accepted assumptions: ASM-... or NONE
Approver: <name/handle>"""
        gate_b = """APPROVE PRD AND CONSTRUCTION GATE B
Requirements revision: REQ-0001
Design revision: DES-0001
Construction authorization: AUTH-0001
Construction envelope SHA-256: sha256:<64-lowercase-hex>
Use the proposed construction envelope above.
Approver: <name/handle>"""
        read_lines = (
            "AUTHORIZE AWS READ-ONLY PREFLIGHT",
            "Read authorization: AWS-READ-AUTH-0001",
            "Construction authorization: AUTH-0001",
            "Prohibited operations: ALL_MUTATIONS",
            "Valid until: <ISO 8601 time or exact one-operation condition>",
        )
        deployment_lines = (
            "AUTHORIZE AWS DEPLOYMENT",
            "AWS authorization: AWS-AUTH-0001",
            "Construction authorization: AUTH-0001",
            "Cost ceiling: <finite positive ISO-currency amount, for example USD: 20.00>",
            "Valid until: <ISO 8601 time or exact one-operation condition>",
        )
        teardown_lines = (
            "AUTHORIZE AWS TEARDOWN",
            "Teardown authorization: TEARDOWN-AUTH-0001",
            "Construction authorization: AUTH-0001",
            "Allowed deletion operations: <exact operations>",
            "Post-teardown verification: <read-only checks>",
        )
        self.assertIn(gate_a, self.prompts)
        self.assertIn(gate_b, self.prompts)
        for line in (*read_lines, *deployment_lines, *teardown_lines):
            self.assertIn(line, self.prompts)

    def test_consultations_are_consequence_first_plain_and_bounded(self) -> None:
        intake = self.prompt_section("INTAKE-10")
        boot = self.prompt_section("BOOT-00")
        requirements = self.prompt_section("REQ-10")
        owner = (
            PROJECT_ROOT / ".agents/skills/fastlane/references/owner-responses.md"
        ).read_text(encoding="utf-8")
        define = (
            PROJECT_ROOT / ".agents/skills/fastlane/references/define.md"
        ).read_text(encoding="utf-8")
        coordinator = (PROJECT_ROOT / ".agents/skills/fastlane/SKILL.md").read_text(
            encoding="utf-8"
        )
        challenger = (
            PROJECT_ROOT / ".codex/agents/fastlane-requirements-challenger.toml"
        ).read_text(encoding="utf-8")

        owner_compact = " ".join(owner.split())
        intake_compact = " ".join(intake.split())
        boot_compact = " ".join(boot.split())
        coordinator_compact = " ".join(coordinator.split())
        for phrase in (
            "real-world consequence",
            "at least 95 out of every 100 requests",
            "people using the product at the same time",
            "hidden location and device details",
            "at most three numbered questions",
            "Accept all recommendations.",
            "short copyable reply",
        ):
            self.assertIn(phrase, owner_compact)
        for surface in (intake, define):
            self.assertIn("real-world consequence", surface)
            self.assertIn("Accept all recommendations.", surface)
        self.assertIn("RTO: TODO; RPO: TODO", self.prd)
        self.assertIn("Project state changed: No.", owner)
        self.assertIn("clarification, not learning mode", " ".join(coordinator.split()))
        self.assertIn("tokenless copyable reply", intake_compact)
        self.assertIn("plain `owner_reply`", owner)
        self.assertNotIn("R-*; Accept all recommendations.", intake)

        for surface in (requirements, define, coordinator, challenger):
            self.assertIn("complete", surface.lower())
            self.assertIn("owner decision", surface.lower())
        for surface in (requirements, define, coordinator):
            self.assertIn("60 seconds", surface)
            self.assertIn("requirements revision", surface)
            self.assertIn("unavailable", surface.lower())
        self.assertIn(
            "Independent requirements challenge: UNAVAILABLE",
            requirements,
        )
        self.assertIn("Never edit files", challenger)
        self.assertIn(
            "Never expose reviewer timing or orchestration",
            " ".join(requirements.split()),
        )

        for surface in (intake, define, owner):
            compact = " ".join(surface.split())
            self.assertIn("uppercase A/B/C", compact)
            self.assertIn("exact", compact.lower())
        for surface in (intake, define):
            self.assertIn("current card", " ".join(surface.split()))
        self.assertIn("current Engine-validated `INTAKE-CARD-*`", owner_compact)
        self.assertIn("turn_boundary_required", intake)
        self.assertIn("turn_boundary_required", owner)
        self.assertIn("turn_boundary_required", coordinator)
        self.assertIn("new inbound owner message", coordinator_compact)
        self.assertIn("assistant example", intake_compact)
        self.assertIn("absent reply never confirms a choice", intake_compact)
        self.assertIn("OWNER_RESPONSE", intake)
        self.assertIn("OWNER_RESPONSE", self.prd)
        self.assertIn("INTAKE-CARD-*", self.prd)
        self.assertIn("OWNER_WORK_CONTEXT", self.prd)
        self.assertIn("EXISTING_APPLICATION_CHANGE", intake_compact)
        self.assertIn("REPAIR_OR_MIGRATION", intake_compact)
        self.assertIn("Empty code never proves a new application", intake_compact)
        self.assertIn(
            "No recommendation\u2014choose the option that matches your situation.",
            owner,
        )
        self.assertIn("`1: <choose A, B, or C>`", owner)
        self.assertIn(
            "`A` to `NEW_APPLICATION`, `B` to `EXISTING_APPLICATION_CHANGE`, and `C` to",
            intake,
        )
        self.assertIn("`REPAIR_OR_MIGRATION`", intake)
        self.assertIn(
            "| Intake ID | Field | Value | Basis | Status | Owner response |",
            self.prd,
        )
        self.assertIn("#### Normalized owner response register", self.prd)
        self.assertIn("Never store a raw chat transcript", self.prd)
        self.assertIn(
            "do not cryptographically authenticate", " ".join(self.prd.split())
        )
        self.assertIn("does not authenticate the owner's identity", intake)
        combined_intake_contract = (intake + define + owner + self.prd).casefold()
        for phrase in (
            "owner-safe status",
            "secret-like",
            "unconfirmed context",
            "never synthesize",
        ):
            self.assertIn(phrase, combined_intake_contract)
        self.assertIn(
            "exact `AWS skills` search/retrieve chain runs first", boot_compact
        )
        self.assertIn("Do not run an", boot_compact)
        self.assertIn("exploratory topic search before it", boot_compact)
        self.assertIn("do not repeat it after valid setup", boot_compact)
        self.assertLess(
            boot_compact.index("`AWS skills` search/retrieve chain"),
            boot_compact.index("Architecture-specific discovery begins"),
        )

    def test_internal_delivery_rules_are_compact_and_non_authoritative(
        self,
    ) -> None:
        workflow = self.workflow
        normalized = " ".join(workflow.split())
        self.assertNotIn("| FSC-", workflow)
        for phrase in (
            "Fastlane EARS Contract",
            "complete architecture comparison",
            "walking-skeleton",
            "STRIDE, LINDDUN, OWASP Top 10, ATAM, ADR",
            "Flow diagrams are optional presentation aids",
            "risk-derived Harness Profile",
            "No universal scanner",
            "optional design vocabulary",
            "not a Fastlane package, runtime dependency, owner workflow, authority",
            "procedural technique selection never claims deterministic proof",
        ):
            self.assertIn(phrase, normalized)

        tasks = (PROJECT_ROOT / "docs/project/TASKS.md").read_text(encoding="utf-8")
        prompts = (PROJECT_ROOT / "prompts/CODEX-PROMPTS.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("`WAVE-*` for the walking skeleton", tasks)
        self.assertIn(
            "approved `WAVE-*` ID in that walking-skeleton task's `Requirements` metadata",
            " ".join(prompts.split()),
        )
        component_table = (
            "| Component | Responsibility | Inputs | Outputs | Dependencies | "
            "Failure behavior | Owner |\n"
            "|---|---|---|---|---|---|---|\n"
            "| TODO | TODO | TODO | TODO | TODO | TODO | TODO |"
        )
        self.assertIn(component_table, self.prd)
        self.assertLess(
            self.prd.index(component_table), self.prd.index("### Layer boundaries")
        )
        for kind in ("PRIMARY_USER", "SECONDARY_USER", "OPERATOR", "EXTERNAL_SYSTEM"):
            self.assertIn(kind, self.prd)
        for trigger in (
            "LIFECYCLE_RESOURCE",
            "ASYNCHRONOUS_WORK",
            "RETRY_OR_RESUME",
            "APPROVAL_FLOW",
            "MIGRATION_OR_CUTOVER",
            "OTHER_MEANINGFUL_TRANSITION",
        ):
            self.assertIn(trigger, self.prd)
        self.assertIn("MAX_ATTEMPTS: <positive integer>", self.prd)
        self.assertIn("retry/resume", normalized)

    def test_request_scoped_adjuncts_never_become_engine_routes(self) -> None:
        coordinator = (PROJECT_ROOT / ".agents/skills/fastlane/SKILL.md").read_text(
            encoding="utf-8"
        )
        doctor_source = (PROJECT_ROOT / "scripts/bootstrap_doctor.py").read_text(
            encoding="utf-8"
        )
        route_match = re.search(
            r"(?ms)^def derive_route\(.*?(?=^def |\Z)", doctor_source
        )
        self.assertIsNotNone(route_match)
        route_source = route_match.group(0) if route_match else ""

        for prompt_id in ("BUG-10", "SYNC-10"):
            with self.subTest(prompt_id=prompt_id):
                section = self.prompt_section(prompt_id)
                normalized = " ".join(section.split())
                self.assertIn("explicitly requests", normalized)
                self.assertIn("adjunct", normalized)
                self.assertIn("Rerun the Engine", normalized)
                self.assertIn("return to its derived", normalized)
                self.assertRegex(normalized, r"never selects(?: or persists)?")
                self.assertNotIn(f'"{prompt_id}"', route_source)

        coordinator_words = " ".join(coordinator.split())
        self.assertIn("request-scoped adjunct", coordinator_words)
        self.assertIn("Preserve the Engine-derived route", coordinator_words)
        self.assertIn("cannot replace a lifecycle phase", coordinator_words)
        self.assertIn("rerun the Engine", coordinator_words)

    def test_build_single_task_hands_off_to_autonomous_continuation(self) -> None:
        single = self.prompt_section("BUILD-10")
        autonomous = self.prompt_section("BUILD-20")
        expected_handoff = (
            "| BUILD-10 | Execute one approved task | BUILD-10, BUILD-20, "
            "RELEASE-10, or STOP |"
        )
        self.assertIn(expected_handoff, self.prompts)
        self.assertIn("**Next:** BUILD-10, BUILD-20, RELEASE-10, or STOP.", single)
        self.assertIn("**Next:** Continue BUILD-20", autonomous)
        self.assertIn(
            "continue the next READY task in the same turn",
            autonomous,
        )

    def test_crosscutting_concerns_remain_explicit_and_conditional(self) -> None:
        workflow = " ".join(self.workflow.split())
        for concern in ("security", "testing", "observability", "error handling"):
            self.assertIn(concern, workflow)
        for method in (
            "STRIDE",
            "LINDDUN",
            "OWASP Top 10",
            "ATAM",
            "ADR",
            "formal inspection",
        ):
            self.assertIn(method, workflow)
        self.assertIn("only for material exposure", workflow)
        self.assertIn("not another lifecycle", workflow)

    def test_method_selection_keeps_procedure_and_validation_distinct(self) -> None:
        define_reference = (
            PROJECT_ROOT / ".agents/skills/fastlane/references/define.md"
        ).read_text(encoding="utf-8")
        design_reference = (
            PROJECT_ROOT / ".agents/skills/fastlane/references/design.md"
        ).read_text(encoding="utf-8")
        define_words = " ".join(define_reference.split())
        design_words = " ".join(design_reference.split())
        workflow_words = " ".join(self.workflow.split())

        self.assertIn("Selecting and applying STRIDE, LINDDUN", define_words)
        self.assertIn("Selecting and applying ATAM, ADR", design_words)
        self.assertIn("Choosing applicability is procedural review", design_words)
        self.assertIn(
            "deterministic validation begins with the recorded row's status",
            design_words,
        )
        self.assertIn(
            "procedural technique selection never claims deterministic proof",
            workflow_words,
        )

    def test_prd_and_prompt_bind_semantic_design_contracts(self) -> None:
        prd_words = " ".join(self.prd.split())
        prompt_words = " ".join(self.prompts.split())

        self.assertIn(
            "when confirmed owner work context is `NEW_APPLICATION`, Work kind "
            "must be `NEW_BUILD`",
            prd_words,
        )
        self.assertIn(
            "`NEW_APPLICATION` deterministically requires `NEW_BUILD`",
            prompt_words,
        )
        for document in (prd_words, prompt_words):
            with self.subTest(contract="owner-context", document=document[:40]):
                self.assertRegex(
                    document,
                    r"(?i)Never infer(?:.{0,100}`NEW_APPLICATION`| owner context)",
                )
            with self.subTest(contract="candidate-minimum", document=document[:40]):
                self.assertIn(
                    "at least two complete, credible, non-straw whole-system candidates",
                    document,
                )
                self.assertRegex(
                    document,
                    r"`NO_VIABLE_ALTERNATIVE`.{0,180}at least two total candidates.{0,100}exactly one (?:is )?eligible",
                )
            with self.subTest(contract="review-boundary", document=document[:40]):
                self.assertRegex(
                    document,
                    r"(?i)procedural coordinator.{0,40}(?:design )?review",
                )
                self.assertIn(
                    "Deterministic validation begins with the recorded row's status",
                    document,
                )

        harness_rows = {
            cells[0]: cells
            for cells in (
                [cell.strip() for cell in line.strip("|").split("|")]
                for line in self.prd.splitlines()
                if line.startswith("| HARNESS-")
            )
        }
        self.assertEqual(
            set(harness_rows), {f"HARNESS-{index:03d}" for index in range(1, 17)}
        )
        expected_layers = {
            "HARNESS-011": "End-to-end",
            "HARNESS-012": "End-to-end",
            "HARNESS-013": "Unit",
            "HARNESS-014": "Static",
            "HARNESS-015": "Security and privacy",
            "HARNESS-016": "Property",
        }
        for harness_id, layer in expected_layers.items():
            with self.subTest(harness_id=harness_id):
                self.assertEqual(len(harness_rows[harness_id]), 8)
                self.assertEqual(harness_rows[harness_id][1], layer)
                self.assertEqual(harness_rows[harness_id][2:6], ["TODO"] * 4)
                self.assertEqual(harness_rows[harness_id][7], "TODO")

        self.assertIn("Duplicate layers are intentional", prd_words)
        self.assertIn("Duplicate layers are intentional", prompt_words)
        self.assertRegex(
            prd_words,
            r"At Gate B, every row is resolved to `REQUIRED` or `NOT_APPLICABLE — <concrete reason>`",
        )
        self.assertIn(
            "At Gate B resolve every Harness row to `REQUIRED` or "
            "`NOT_APPLICABLE — <concrete reason>`",
            prompt_words,
        )

    def test_aws_read_proof_and_residual_disposition_contracts_are_synchronized(
        self,
    ) -> None:
        aws30 = self.prompt_section("AWS-30")
        aws40 = self.prompt_section("AWS-40")
        four_field_source = (
            "SOURCE: <stable owner-message source>; AUTHORIZED_AT: <ISO 8601 "
            "with timezone>; RESOURCES: <exact canonical list>; OPERATIONS: "
            "<exact canonical list>"
        )
        for document in (
            self.verify,
            self.runbook,
            self.workflow,
            aws30,
            self.fastlane_deliver,
            self.operate_fastlane_aws,
        ):
            with self.subTest(contract="aws30-source", document=document[:40]):
                normalized = " ".join(document.split())
                self.assertIn(four_field_source, normalized)
                self.assertIn("Read-only preflight row", normalized)
                self.assertIn("Action authorization provenance", normalized)

        two_field_source = (
            "SOURCE: <stable owner-message source>; AUTHORIZED_AT: <ISO 8601 "
            "with timezone>"
        )
        residual_documents = (
            self.verify,
            self.runbook,
            self.workflow,
            aws40,
            self.fastlane_deliver,
            self.operate_fastlane_aws,
        )
        for document in residual_documents:
            with self.subTest(contract="residual-disposition", document=document[:40]):
                normalized = " ".join(document.split())
                self.assertIn(two_field_source, normalized)
                self.assertIn("aws_residual_disposition", normalized)
                for choice in ("RETAIN", "INVESTIGATE", "REMOVE"):
                    self.assertIn(choice, normalized)
                self.assertRegex(
                    normalized,
                    r"(?i)set-level|complete current residual set",
                )
                self.assertRegex(
                    normalized,
                    r"(?i)Every choice after `RESIDUALS_REMAIN` must be strictly newer",
                )
                self.assertRegex(
                    normalized,
                    r"(?i)After (?:`READY_FOR_TEARDOWN`|READY), RETAIN and INVESTIGATE must be strictly newer",
                )
                self.assertRegex(
                    normalized,
                    r"(?i)owner-provenanced.{0,40}(?:`TEARDOWN`|TEARDOWN).{0,40}carry.{0,40}REMOVE",
                )
                self.assertNotIn("For each listed residual", document)

        for document in (self.verify, self.runbook, self.workflow, aws40):
            normalized = " ".join(document.split())
            self.assertIn("exact-scope", normalized)
            self.assertRegex(normalized, r"(?i)STALE.{0,100}fresh reads")

        aws40_words = " ".join(aws40.split())
        self.assertIn("only while that projection is PENDING", aws40_words)
        self.assertIn("current remove plus `residuals_remain`", aws40_words.casefold())
        self.assertIn(
            "current remove plus `ready_for_teardown`", aws40_words.casefold()
        )
        self.assertIn("exact teardown receipt", aws40_words)
        self.assertIn(
            "lifecycle intent itself never authorizes account access", aws40_words
        )
        prompt_words = " ".join(self.prompts.split())
        self.assertIn("only AWS-20 may mutate", prompt_words)
        self.assertIn("only AWS-50 may mutate", prompt_words)

    def test_flow_diagrams_are_optional_and_never_readiness_artifacts(self) -> None:
        for document in (self.prd, self.prompts):
            self.assertNotIn("### Primary flow", document)
        self.assertIn(
            "Flow diagrams are optional presentation aids and never readiness artifacts",
            " ".join(self.workflow.split()),
        )
        self.assertNotIn("| FSC-", self.workflow)
        doctor_source = (PROJECT_ROOT / "scripts/bootstrap_doctor.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("Primary flow", doctor_source)
        self.assertIn('JOURNEY_HEADING = "### Journey register"', doctor_source)
        self.assertIn(
            'STATE_APPLICABILITY_HEADING = "### State-model applicability"',
            doctor_source,
        )

if __name__ == "__main__":
    unittest.main()
