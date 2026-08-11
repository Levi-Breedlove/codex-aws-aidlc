from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

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

ROUTE_FIELDS = (
    "Purpose",
    "Preconditions",
    "Authoritative inputs",
    "Permitted writes",
    "GitHub mode",
    "AWS mode",
    "Required authorization",
    "Stop conditions",
    "Receipt",
    "Next",
)

GATE_A_PROMPT_RECEIPT = """APPROVE REQUIREMENTS GATE A
Requirements revision: REQ-0001
Cost posture: MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED
Accepted assumptions: ASM-... or NONE
Approver: <name/handle>"""

GATE_A_PROJECT_RECEIPT = """APPROVE REQUIREMENTS GATE A
Requirements revision: <REQ-nnnn>
Cost posture: <exact-Gate-A-cost-posture>
Accepted assumptions: <assumption-IDs-or-NONE>
Approver: <name/handle>"""

GATE_B_PROMPT_RECEIPT = """APPROVE PRD AND CONSTRUCTION GATE B
Requirements revision: REQ-0001
Design revision: DES-0001
Construction authorization: AUTH-0001
Construction envelope SHA-256: sha256:<64-lowercase-hex>
Use the proposed construction envelope above.
Approver: <name/handle>"""

GATE_B_PROJECT_RECEIPT = """APPROVE PRD AND CONSTRUCTION GATE B
Requirements revision: <REQ-nnnn>
Design revision: <DES-nnnn>
Construction authorization: <AUTH-nnnn>
Construction envelope SHA-256: sha256:<64-lowercase-hex>
Use the proposed construction envelope above.
Approver: <name/handle>"""

AWS_RECEIPT_PREFIXES = (
    "AUTHORIZE AWS READ-ONLY PREFLIGHT\nRead authorization: AWS-READ-AUTH-0001",
    "AUTHORIZE AWS DEPLOYMENT\nAWS authorization: AWS-AUTH-0001",
    "AUTHORIZE AWS TEARDOWN\nTeardown authorization: TEARDOWN-AUTH-0001",
)


def read(relative: str) -> str:
    return (REPOSITORY_ROOT / relative).read_text(encoding="utf-8")


def outside_disclosures(markdown: str) -> str:
    return re.sub(r"(?ms)<details>.*?</details>", "", markdown)


def prose_without_records(markdown: str) -> str:
    """Return explanatory prose while ignoring tables, code, and comments."""

    lines: list[str] = []
    fenced = False
    for raw in markdown.splitlines():
        line = raw.strip()
        if line.startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced or not line:
            continue
        if line.startswith(("|", "<!--", "#", "<details>", "</details>", "<summary>")):
            continue
        lines.append(line)
    return "\n".join(lines)


class PromptPackContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.prompts = read("prompts/CODEX-PROMPTS.md")
        cls.agents = read("AGENTS.md")
        cls.project_agents = read("docs/project/AGENTS.md")
        cls.readme = read("README.md")
        cls.setup = read("docs/SETUP.md")
        cls.workflow = read("docs/WORKFLOW.md")
        cls.security = read("SECURITY.md")
        cls.prd = read("docs/project/PRD.md")
        cls.tasks = read("docs/project/TASKS.md")
        cls.verify = read("docs/project/VERIFY.md")
        cls.runbook = read("docs/project/RUNBOOK.md")
        cls.bugfix = read("docs/project/BUGFIX.md")
        cls.fastlane_skill = read(".agents/skills/fastlane/SKILL.md")
        cls.fastlane_define = read(".agents/skills/fastlane/references/define.md")
        cls.source_assisted_define = read(
            ".agents/skills/fastlane/references/source-assisted-define.md"
        )
        cls.fastlane_design = read(".agents/skills/fastlane/references/design.md")
        cls.fastlane_deliver = read(".agents/skills/fastlane/references/deliver.md")
        cls.owner_responses = read(
            ".agents/skills/fastlane/references/owner-responses.md"
        )
        cls.authorization_receipts = read(
            ".agents/skills/fastlane/references/authorization-receipts.md"
        )
        cls.operate_fastlane_aws = read(".agents/skills/operate-fastlane-aws/SKILL.md")
        cls.maintain_fastlane = read(".agents/skills/maintain-fastlane/SKILL.md")
        cls.adr_template = read("docs/adr/0000-template.md")
        cls.infrastructure_readme = read("infrastructure/README.md")
        engine_paths = [
            Path("scripts/bootstrap_doctor.py"),
            *sorted(Path("scripts/fastlane_engine").rglob("*.py")),
        ]
        cls.engine_source = "\n".join(read(path.as_posix()) for path in engine_paths)
        cls.task_engine_source = read("scripts/task_waves.py")
        cls.manifest = json.loads(read("bootstrap.manifest.json"))

    def prompt_section(self, prompt_id: str) -> str:
        pattern = re.compile(
            rf"^## {re.escape(prompt_id)} — .*?(?=^## [A-Z]+-\d+ — |\Z)",
            re.MULTILINE | re.DOTALL,
        )
        match = pattern.search(self.prompts)
        self.assertIsNotNone(match, f"Missing route interface {prompt_id}")
        return match.group(0) if match else ""

    def test_prompt_pack_is_a_bounded_owner_guide_and_route_interface(self) -> None:
        self.assertLessEqual(len(self.prompts.encode("utf-8")), 32 * 1024)
        self.assertIn("## Owner command guide", self.prompts)
        self.assertIn("## Where the machinery lives", self.prompts)
        self.assertIn("## Route interface contract", self.prompts)
        self.assertIn("This file is not a second lifecycle manual", self.prompts)
        self.assertNotIn("### Common operating contract", self.prompts)
        self.assertNotIn("### Human response contracts", self.prompts)

    def test_owner_command_guide_contains_only_usable_owner_inputs(self) -> None:
        for command in (
            "`init template`",
            "`A`",
            "`B: <requested detail>`",
            "`C: <requested detail>`",
            "`Accept all recommendations.`",
            "`Change the requirements: <correction>.`",
            "`Change the design: <correction>.`",
            "`$operate-fastlane-aws`",
        ):
            self.assertIn(command, self.prompts)
        self.assertIn("Reply naturally; no numeric prefix is required", self.prompts)
        self.assertNotIn("`1A`", self.prompts)
        self.assertIn("Can you explain this question?", self.prompts)
        self.assertNotIn("<choose A, B, or C>", self.prompts)
        self.assertNotRegex(self.prompts, r"R-[A-F0-9]{8,}")
        self.assertIn("one plain-language\nquestion per turn", self.prompts)

    def test_prompt_ids_are_unique_ordered_and_manifested(self) -> None:
        offsets: list[int] = []
        for prompt_id in PROMPT_IDS:
            matches = list(
                re.finditer(
                    rf"^## {re.escape(prompt_id)} — ", self.prompts, re.MULTILINE
                )
            )
            self.assertEqual(len(matches), 1, prompt_id)
            offsets.append(matches[0].start())
        self.assertEqual(offsets, sorted(offsets))
        self.assertEqual(self.manifest["canonical_prompt_ids"], PROMPT_IDS)

    def test_every_route_interface_declares_the_same_boundary_fields(self) -> None:
        for prompt_id in PROMPT_IDS:
            with self.subTest(prompt_id=prompt_id):
                section = self.prompt_section(prompt_id)
                for field in ROUTE_FIELDS:
                    self.assertEqual(section.count(f"**{field}:**"), 1, field)
                self.assertIn(f"[{prompt_id}]", section)
                self.assertLessEqual(len(section.encode("utf-8")), 2_000)

    def test_route_interfaces_keep_external_authority_separate(self) -> None:
        for prompt_id in PROMPT_IDS:
            section = self.prompt_section(prompt_id)
            with self.subTest(prompt_id=prompt_id):
                self.assertIn("**GitHub mode:**", section)
                self.assertIn("**AWS mode:**", section)
                self.assertIn("**Required authorization:**", section)

        for prompt_id in ("INTAKE-20", "DESIGN-20"):
            section = self.prompt_section(prompt_id)
            self.assertIn("human owner", section)
            self.assertIn("No GitHub writes", section)
            self.assertRegex(section, r"AWS mode:\*\* (?:None|NONE)")

        self.assertIn(
            "owner message naming the repository", self.prompt_section("SYNC-10")
        )
        self.assertIn(
            "exact current AWS read-only receipt", self.prompt_section("AWS-10")
        )
        self.assertIn(
            "separate complete exact current AWS read-only receipt",
            self.prompt_section("AWS-30"),
        )
        self.assertIn("exact current teardown receipt", self.prompt_section("AWS-50"))

    def test_gate_receipts_remain_exact_visible_and_owner_only(self) -> None:
        self.assertEqual(self.prompts.count(GATE_A_PROMPT_RECEIPT), 1)
        self.assertEqual(self.prompts.count(GATE_B_PROMPT_RECEIPT), 1)
        self.assertEqual(self.prd.count(GATE_A_PROJECT_RECEIPT), 1)
        self.assertEqual(self.prd.count(GATE_B_PROJECT_RECEIPT), 1)
        self.assertIn("Only a human owner may approve a gate", self.prompts)
        self.assertIn(
            "Do not paraphrase, reorder, complete, or self-accept",
            self.authorization_receipts,
        )
        self.assertIn(
            "The exact approval receipt remains last and byte-identical",
            self.owner_responses,
        )

    def test_aws_receipts_remain_separate_exact_actions(self) -> None:
        for prefix in AWS_RECEIPT_PREFIXES:
            with self.subTest(receipt=prefix.splitlines()[0]):
                self.assertEqual(self.prompts.count(prefix), 1)
                self.assertEqual(self.verify.count(prefix), 1)
                self.assertEqual(self.runbook.count(prefix), 1)
        self.assertIn(
            "AWS deployment and teardown remain separate exact authorizations",
            self.authorization_receipts,
        )
        self.assertIn("permits no mutation", self.authorization_receipts)

    def test_setup_is_chronological_owner_runnable_and_hook_safe(self) -> None:
        headings = (
            "### 1. Install Codex",
            "### 2. Install platform prerequisites",
            "### 3. Install uv through pipx",
            "### 4. Add the official AWS Core marketplace",
            "### 5. Sign in to Codex",
            "### 6. Install, enable, and verify AWS Core",
            "### 7. Review any AWS Core hooks",
            "### 8. Create the project and initialize Fastlane",
        )
        offsets = [self.setup.index(heading) for heading in headings]
        self.assertEqual(offsets, sorted(offsets))
        for command in (
            "codex --version",
            "pipx install uv",
            "uvx --version",
            "codex plugin marketplace add aws/agent-toolkit-for-aws",
            "codex login",
            "codex login status",
            "`/plugins`",
            "`/hooks`",
            "`init template`",
        ):
            self.assertIn(command, self.setup)
        normalized = " ".join(self.setup.split())
        self.assertIn("If Codex lists handlers supplied", normalized)
        self.assertIn("Do not add a separate hook file", normalized)
        self.assertIn(
            "repository hooks remain disabled until a current Gate B", normalized
        )

    def test_project_document_governance_has_one_authority_split(self) -> None:
        for rule in (
            "Never create separate human and machine copies",
            "Project facts and owner decisions belong here",
            "Codex procedures belong in phase references",
            "receipt syntax in the prompt registry",
            "routing behavior in the Engine and tests",
            "Do not tell Codex to populate, append, replace, migrate, sort, hash, parse, route, or validate",
            "The prompt registry keeps only usable owner commands, exact receipt bytes, and concise route interfaces",
        ):
            self.assertIn(rule, self.project_agents)

    def test_customer_project_documents_start_with_current_project_truth(self) -> None:
        contracts = {
            "docs/project/TASKS.md": (
                "Construction Progress",
                "Current state",
                "Roadmap",
                "Active work",
            ),
            "docs/project/VERIFY.md": (
                "Verification and Release Evidence",
                "Current state",
                "Important claims",
            ),
            "docs/project/RUNBOOK.md": (
                "Deployment and Operations Runbook",
                "Current state",
                "Go directly to",
            ),
            "docs/project/BUGFIX.md": (
                "Bugfix Record",
                "Current state",
                "No active bounded defect",
            ),
        }
        for relative, phrases in contracts.items():
            document = read(relative)
            with self.subTest(relative=relative):
                for phrase in phrases:
                    self.assertIn(phrase, document)
                first_state = document.index("Current state")
                self.assertLess(first_state, 1_500)
                self.assertEqual(document.count("Need from you"), 1)

    def test_project_documents_explain_records_without_embedding_agent_procedure(
        self,
    ) -> None:
        forbidden = (
            "replace this table",
            "populate this table",
            "append exactly one",
            "canonical-order",
            "schema migration",
            "must match the regex",
            "parse with",
            "scripts/task_waves.py",
            "scripts/bootstrap_doctor.py",
            "during task-10",
            "during build-10",
            "during aws-20",
            "during aws-30",
            "codex must append",
        )
        for relative in (
            "docs/project/TASKS.md",
            "docs/project/VERIFY.md",
            "docs/project/RUNBOOK.md",
            "docs/project/BUGFIX.md",
        ):
            prose = prose_without_records(read(relative)).lower()
            with self.subTest(relative=relative):
                for phrase in forbidden:
                    self.assertNotIn(phrase, prose)

    def test_machine_tokens_stay_out_of_the_ordinary_owner_path(self) -> None:
        forbidden_visible = (
            "task_waves.py",
            "bootstrap_doctor.py",
            "STRUCTURED_API",
            "REVIEWED_SCRIPT",
            "AWS-EXEC-",
            "canonical digest",
            "schema migration",
        )
        for relative in (
            "docs/project/TASKS.md",
            "docs/project/VERIFY.md",
            "docs/project/RUNBOOK.md",
            "docs/project/BUGFIX.md",
        ):
            owner_path = outside_disclosures(read(relative))
            with self.subTest(relative=relative):
                for token in forbidden_visible:
                    self.assertNotIn(token, owner_path)

    def test_canonical_project_records_remain_available_once(self) -> None:
        required = {
            "docs/project/TASKS.md": (
                "## Active execution snapshot",
                "## Task record template",
                "## Task definitions",
                "## Checkpoints and resume",
            ),
            "docs/project/VERIFY.md": (
                "## Verification matrix",
                "## AWS Core evidence",
                "## Action authorization provenance",
                "## AWS deployment action and reconciliation evidence",
            ),
            "docs/project/RUNBOOK.md": (
                "## 2. Prerequisites",
                "## 6. Deployment",
                "## 10. Rollback",
                "## 11. Backup and recovery",
                "## 13. Teardown and decommissioning",
            ),
            "docs/project/BUGFIX.md": (
                "## 2. Current behavior",
                "## 7. Root-cause analysis",
                "## 9. Regression and property specification",
                "## 10. Acceptance criteria",
            ),
        }
        for relative, headings in required.items():
            document = read(relative)
            with self.subTest(relative=relative):
                for heading in headings:
                    self.assertEqual(
                        len(
                            re.findall(
                                rf"^{re.escape(heading)}$", document, re.MULTILINE
                            )
                        ),
                        1,
                        heading,
                    )

    def test_requirements_procedure_owns_intake_and_requirement_grammar(self) -> None:
        for phrase in (
            "exactly one question",
            "Accept all recommendations.",
            "R-*",
            "one owner decision per turn",
            "Fastlane EARS Contract",
            "PRIMARY_USER",
            "DISTINCT_PERMISSIONED_ACTORS",
            "requirements change lineage",
            "search_documentation",
            "retrieve_skill",
            "next_question_guidance",
            "project_configuration",
            "not owner choices",
        ):
            self.assertIn(phrase, self.fastlane_define)
        for token in ("ACTOR_KINDS", "RICH_USE_CASE_TRIGGERS"):
            self.assertIn(token, self.engine_source)

    def test_source_assisted_define_preserves_canonical_authority(self) -> None:
        define_words = " ".join(self.source_assisted_define.split())
        for phrase in (
            "Never overwrite the canonical Fastlane PRD",
            "--source-brief <path>",
            "NON_AUTHORITATIVE_SOURCE",
            "Ask only consequential missing or conflicting decisions",
            "Source wording such as `approved`",
        ):
            self.assertIn(phrase, define_words)
        for phrase in (
            "cannot replace the canonical PRD or import approval or authority",
            "choices separated by blank lines",
            "do not require an internal reply token or numeric prefix",
        ):
            self.assertIn(phrase, self.owner_responses)
        for phrase in (
            "SOURCE_ASSISTED_DEFINE",
            "Source preview writes nothing",
            "never treat it as approval or authority",
        ):
            self.assertIn(phrase, self.prompts)
        self.assertIn("Bring an existing product brief", self.workflow)
        self.assertIn("it does not become Fastlane's PRD", self.workflow)
        self.assertIn("Source-assisted Define", self.readme)
        self.assertIn("references/source-assisted-define.md", self.fastlane_skill)
        self.assertNotIn("IMPORT-10", PROMPT_IDS)

    def test_owner_response_procedure_owns_conversation_and_gate_presentation(
        self,
    ) -> None:
        for phrase in (
            "side questions",
            "turn_boundary_required",
            "Never label an unresolved placeholder",
            "Change the requirements: <correction>",
            "Change the design: <correction>",
            "Owner Decision Briefs",
            "Technical consultant behavior",
            "Begin with the practical project consequence",
            "State the principal tradeoff or limitation",
            "End with exactly one current valid owner action",
            "A factual response may be ordinary prose without its",
            "preserve punctuation such as semicolons",
            "Separate every labeled choice and reply example",
            "repository-relative Markdown links",
            "receipt remains last and byte-identical",
            "fastlane_presenter.py project-ready --input-stdin",
            "Why this matters",
            "What your answer changes",
        ):
            self.assertIn(phrase, self.owner_responses)
        self.assertIn(
            "Owner-facing responses are technical consultation, not raw state relay.",
            self.fastlane_skill,
        )
        self.assertIn("intake_foundation.next_question_guidance", self.fastlane_skill)
        self.assertIn("intake_foundation.project_configuration", self.fastlane_skill)
        self.assertIn("fastlane_presenter.py project-ready", self.fastlane_skill)
        self.assertIn("Never render it during resume.", self.prompts)
        self.assertIn(
            "Never ask the owner to select project mode",
            self.fastlane_skill,
        )
        for phrase in (
            "derived `next_question_guidance` objective",
            "derived Codex-owned `project_configuration` actions",
            "internal classification into an owner question.",
        ):
            self.assertIn(phrase, self.prompts)

    def test_design_procedure_owns_architecture_and_validation_method(self) -> None:
        for phrase in (
            "search_documentation",
            "retrieve_skill",
            "DRV-*",
            "ARCH-*",
            "CAND-*",
            "TECH-*",
            "secure managed-serverless baseline",
            "Application source disposition",
            "SYSTEM_CONTEXT",
            "PRIMARY_OUTCOME",
            "Harness Profile",
            "PROP-*",
            "Gate B Technical Owner Brief",
            "Complete the AWS implementation approach during DESIGN-10, never during Gate A",
            "Compute`, `API and edge`, `Identity`, `Data`, `Messaging`, `Observability`, `Deployment`, and `Secrets and encryption",
            "not an exhaustive AWS product catalog",
            "ask the owner only when an unresolved owner constraint or product tradeoff genuinely requires a decision",
        ):
            self.assertIn(phrase, self.fastlane_design)

    def test_deliver_procedure_owns_tasks_runs_bugfix_release_and_sync(self) -> None:
        for phrase in (
            "scripts/task_waves.py",
            "SINGLE_TASK",
            "AUTONOMOUS",
            "claim exactly one",
            "last-known-green",
            "BUG-PROP-*",
            "NOT_READY",
            "READY_TO_DEPLOY",
            "RELEASE_VERIFIED",
            "PENDING_SYNC",
            "singular `app/`",
        ):
            self.assertIn(phrase, self.fastlane_deliver)
        self.assertIn("Maximum workers must be exactly 1", self.task_engine_source)

    def test_task_record_keeps_state_while_engine_and_deliver_own_procedure(
        self,
    ) -> None:
        for heading in (
            "## Derived requirement disposition contract",
            "## Coordinator contract",
            "## Status and transition contract",
            "## Required task record schema",
        ):
            self.assertNotIn(heading, self.tasks)
        for phrase in (
            "exact task fields",
            "legal transitions",
            "attempt bounds",
            "does not teach that grammar",
        ):
            self.assertIn(phrase, self.fastlane_deliver)
        self.assertIn("TASK_STATUSES", self.engine_source)
        self.assertIn("ALLOWED_TRANSITIONS", self.task_engine_source)

    def test_aws_operation_skill_owns_execution_journal_and_reconciliation(
        self,
    ) -> None:
        for phrase in (
            "STRUCTURED_API",
            "REVIEWED_SCRIPT",
            "AWS-EXEC-*",
            "STARTED",
            "SUCCEEDED",
            "FAILED",
            "PARTIAL",
            "UNKNOWN",
            "independently\n   current exact read authority",
            "RETAIN, INVESTIGATE, or REMOVE",
            "READY_FOR_TEARDOWN",
            "AWS-50",
            "Neither document owns this execution procedure",
        ):
            self.assertIn(phrase, self.operate_fastlane_aws)
        for token in (
            "AWS_EXECUTION_CONTRACT_HEADERS",
            "AWS_EXECUTION_CONTRACT_INVALID",
            "AUTHORIZE AWS READ-ONLY PREFLIGHT",
            "AUTHORIZE AWS DEPLOYMENT",
            "AUTHORIZE AWS TEARDOWN",
        ):
            self.assertIn(token, self.engine_source)

    def test_prompt_pack_does_not_duplicate_phase_algorithms(self) -> None:
        forbidden = (
            "Rich-use-case triggers are",
            "Actor kinds are",
            "A persisted `RUNNING` run is interrupted state",
            "Allocate one new `AWS-TEARDOWN-nnnn`",
            "Append exactly one terminal",
            "Semantic digest:",
            "Canonical order",
            "For each listed residual",
        )
        for phrase in forbidden:
            self.assertNotIn(phrase, self.prompts)

    def test_engine_owns_readiness_routing_and_non_authoritative_views(self) -> None:
        for token in (
            "DOCUMENT_SUMMARY_FILES",
            "strip_generated_summary",
            "DOCUMENT_SUMMARY_STALE",
            "OWNER_BRIEF_SOURCE_STALE",
            "OWNER_BRIEF_COVERAGE_INCOMPLETE",
            "APPLICATION_SOURCE_DISPOSITION_FIELD",
            "DIAGRAM_STATUSES",
        ):
            self.assertIn(token, self.engine_source)
        self.assertIn("generated, non-authoritative views", self.project_agents)

    def test_greenfield_application_source_is_singular_and_engine_bound(self) -> None:
        for source in (self.fastlane_design, self.engine_source):
            self.assertIn("app/**", source)
        self.assertIn("singular `app/`", self.fastlane_deliver)
        for token in ("apps/**", "src/**"):
            self.assertIn(token, self.fastlane_design)
            self.assertIn(token, self.engine_source)
        self.assertIn("GREENFIELD_APP_ROOT", self.engine_source)
        self.assertIn("INFRASTRUCTURE_ONLY", self.engine_source)

    def test_aws_core_is_current_attributable_and_not_authority(self) -> None:
        for source in (self.agents, self.fastlane_design, self.operate_fastlane_aws):
            self.assertIn("AWS Core", source)
        for source in (self.fastlane_design, self.operate_fastlane_aws):
            self.assertIn("search_documentation", source)
            self.assertIn("retrieve_skill", source)
        self.assertIn("AWS Core supplies current AWS knowledge", self.fastlane_design)
        self.assertIn("The owner authorizes", self.fastlane_design)
        self.assertIn("Missing evidence pauses", self.agents)

    def test_challenger_agents_remain_read_only_and_non_authoritative(self) -> None:
        for relative in (
            ".codex/agents/fastlane-requirements-challenger.toml",
            ".codex/agents/fastlane-architecture-challenger.toml",
        ):
            source = read(relative)
            with self.subTest(relative=relative):
                self.assertIn('sandbox_mode = "read-only"', source)
                self.assertIn("claim no task", source)
                self.assertIn("change no state", source)
                self.assertIn("Never edit files", source)
                self.assertIn("approve", source)
                self.assertIn("AWS", source)

    def test_repository_hooks_remain_optional_and_non_authoritative(self) -> None:
        hooks_doc = read(".codex/hooks/README.md")
        hook_source = read(".codex/hooks/fastlane_hook.py")
        self.assertIn("Fastlane works without repository hooks", hooks_doc)
        self.assertIn(
            "example has empty command fields and cannot activate itself", hooks_doc
        )
        self.assertIn("Gate B", hooks_doc)
        self.assertFalse((REPOSITORY_ROOT / ".codex/hooks.json").exists())
        self.assertIn("bootstrap_doctor.py", hook_source)
        self.assertIn("permissionDecision", hook_source)

    def test_public_surfaces_use_fastlane_engine_terminology(self) -> None:
        for relative in (
            "README.md",
            "SECURITY.md",
            "docs/WORKFLOW.md",
            "docs/project/TASKS.md",
            "docs/project/VERIFY.md",
            "docs/project/RUNBOOK.md",
            "prompts/CODEX-PROMPTS.md",
            ".agents/skills/fastlane/SKILL.md",
        ):
            source = read(relative)
            with self.subTest(relative=relative):
                self.assertIsNone(re.search(r"\bdoctor\b", source, re.IGNORECASE))
        self.assertIn("Fastlane Engine", self.readme)

    def test_instruction_surfaces_keep_context_headroom(self) -> None:
        self.assertLessEqual(len(read("AGENTS.md").encode("utf-8")), 5_900)
        self.assertLessEqual(
            len(read(".agents/skills/fastlane/SKILL.md").encode("utf-8")), 8_500
        )
        self.assertLessEqual(len(self.fastlane_deliver.encode("utf-8")), 10_000)
        self.assertLessEqual(len(self.readme.splitlines()), 140)
        self.assertLessEqual(len(self.readme.encode("utf-8")), 9_000)
        self.assertLessEqual(len(self.prompts.encode("utf-8")), 32 * 1024)

    def test_manifest_and_customer_navigation_match_the_current_product(self) -> None:
        self.assertEqual(self.manifest["bootstrap_version"], "1.2.36")
        self.assertIn("**Pack version:** 1.2.36", self.prompts)
        self.assertIn("Current customer build: **1.2.36**", self.readme)
        self.assertIn(
            "https://github.com/Levi-Breedlove/codex-aws-aidlc/generate",
            self.readme,
        )
        self.assertNotIn("Levi-Breedlove/aws-bootstrap/generate", self.readme)
        for required in self.manifest["required_files"]:
            self.assertTrue((REPOSITORY_ROOT / required).is_file(), required)
        for link in (
            "docs/SETUP.md",
            "docs/WORKFLOW.md",
            "docs/TROUBLESHOOTING.md",
            "SECURITY.md",
        ):
            self.assertIn(link, self.readme)

    def test_adr_and_infrastructure_surfaces_cannot_grant_authority(self) -> None:
        self.assertIn("The PRD remains authoritative", self.fastlane_design)
        self.assertIn(
            "link `ADR-NNNN` to `../adr/NNNN-lowercase-slug.md`",
            self.fastlane_design,
        )
        self.assertIn("supporting rationale", self.workflow)
        for source in (self.adr_template, self.infrastructure_readme):
            self.assertIn("no construction", source)
            self.assertIn("AWS authority", source)
        self.assertIn("SUPPORTING_RATIONALE_ONLY", self.adr_template)


if __name__ == "__main__":
    unittest.main()
