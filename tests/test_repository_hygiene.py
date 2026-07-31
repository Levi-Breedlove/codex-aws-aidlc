from __future__ import annotations

import hashlib
import io
import json
import re
import tabnanny
import tokenize
import tomllib
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    "",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
RESERVED_EMAIL_DOMAINS = (
    ".example",
    ".invalid",
    ".test",
    "example.com",
    "users.noreply.github.com",
)
SYNTHETIC_ACCOUNTS = {"111122223333", "123456789012"}
SYNTHETIC_SECRET_LINE_HASHES = {
    "tests/test_bootstrap_doctor.py": {
        "72393cbf3537b84ece87e2945cd2829e15257858aa8b5107f2fd76207c27681a",
    },
    "tests/test_intake_response.py": {
        "4ee793c22fe6ee7686b182fe35cfe2e55e388690fc3ba4ddb9514988861d1b39",
        "b8af8b0c6ff4d65ce3f72dd4c7ee8f024ff7d43a87c437afea632ee31d05201e",
    },
    "tests/test_setup_assistant.py": {
        "3f1c83943e8c044adbdde1ba7589bee70b01042726a87d01f5564dbe23cb52e8",
    },
}
WINDOWS_USER_DIRECTORY = "Users"
UNIX_USER_DIRECTORY = "Users"
UNIX_HOME_DIRECTORY = "home"
UNIX_ROOT_DIRECTORY = "root"
IPV4_OCTET = r"(?:25[0-5]|2[0-4]\d|1?\d?\d)"
MACHINE_PATTERNS = (
    re.compile(rf"(?i)\b[A-Z]:[\\/]{WINDOWS_USER_DIRECTORY}[\\/][^\\/\s]+"),
    re.compile(
        rf"(?i)(?:/{UNIX_USER_DIRECTORY}/|/{UNIX_HOME_DIRECTORY}/)"
        rf"[^/\s]+(?:/|\b)"
    ),
    re.compile(rf"(?i)/{UNIX_ROOT_DIRECTORY}(?:/|\b)"),
    re.compile(rf"(?i)/mnt/[a-z]/{WINDOWS_USER_DIRECTORY}/"),
    re.compile(r"(?i)\b(?:AppData|OneDrive)[\\/]"),
    re.compile(r"(?i)\b(?:DESKTOP|LAPTOP)-[A-Z0-9-]+\b"),
    re.compile(r"(?i)\b(?:[0-9A-F]{2}[:-]){5}[0-9A-F]{2}\b"),
    re.compile(rf"(?<!\d)10\.{IPV4_OCTET}\.{IPV4_OCTET}\.{IPV4_OCTET}(?!\d)"),
    re.compile(
        rf"(?<!\d)172\.(?:1[6-9]|2\d|3[01])\."
        rf"{IPV4_OCTET}\.{IPV4_OCTET}(?!\d)"
    ),
    re.compile(rf"(?<!\d)192\.168\.{IPV4_OCTET}\.{IPV4_OCTET}(?!\d)"),
)
EMAIL_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
ACCOUNT_PATTERN = re.compile(
    r"(?i)(?:\baccount(?:\s+id)?\s*[:=]\s*|"
    r"arn:(?:aws|aws-us-gov|aws-cn):[^\s:]+:[^\s:]*:)(\d{12})\b"
)
RISKY_FIELD_IDS = {
    "account",
    "account_id",
    "arn",
    "credentials",
    "email",
    "hostname",
    "local_path",
    "secret",
    "token",
    "transcript",
    "username",
}


def containing_line_sha256(text: str, offset: int) -> str:
    """Return a stable digest for the exact stripped line containing offset."""

    start = text.rfind("\n", 0, offset) + 1
    end = text.find("\n", offset)
    line = text[start:] if end < 0 else text[start:end]
    return hashlib.sha256(line.strip().encode("utf-8")).hexdigest()


def manifest_inventory() -> list[str]:
    manifest = json.loads(
        (REPOSITORY_ROOT / "bootstrap.manifest.json").read_text(encoding="utf-8")
    )
    return manifest["required_files"]


def release_texts() -> list[tuple[str, str]]:
    texts: list[tuple[str, str]] = []
    for relative in manifest_inventory():
        path = REPOSITORY_ROOT.joinpath(*relative.split("/"))
        if path.suffix.casefold() not in TEXT_SUFFIXES:
            continue
        texts.append((relative, path.read_text(encoding="utf-8")))
    return texts


class RepositoryHygieneTests(unittest.TestCase):
    def test_release_python_sources_compile_and_have_unambiguous_indentation(
        self,
    ) -> None:
        failures: list[str] = []
        for relative in manifest_inventory():
            if not relative.endswith(".py"):
                continue
            path = REPOSITORY_ROOT.joinpath(*relative.split("/"))
            try:
                with tokenize.open(path) as stream:
                    source = stream.read()
                compile(source, relative, "exec", dont_inherit=True)
                tabnanny.process_tokens(
                    tokenize.generate_tokens(io.StringIO(source).readline)
                )
            except (IndentationError, SyntaxError, tabnanny.NannyNag) as exc:
                failures.append(f"{relative}: {type(exc).__name__}")
        self.assertEqual(failures, [])

    def test_release_text_format_is_canonical(self) -> None:
        failures: list[str] = []
        for relative in manifest_inventory():
            path = REPOSITORY_ROOT.joinpath(*relative.split("/"))
            if path.suffix.casefold() not in TEXT_SUFFIXES:
                continue
            payload = path.read_bytes()
            try:
                payload.decode("utf-8")
            except UnicodeDecodeError:
                failures.append(f"{relative}: not UTF-8")
                continue
            if b"\x00" in payload:
                failures.append(f"{relative}: NUL byte")
            if payload and not payload.endswith(b"\n"):
                failures.append(f"{relative}: missing final newline")
            for line_number, line in enumerate(payload.splitlines(), start=1):
                if line.rstrip(b" \t") != line:
                    failures.append(f"{relative}:{line_number}: trailing whitespace")
        self.assertEqual(failures, [])

    def test_release_contains_no_high_confidence_secret_material(self) -> None:
        token_patterns = (
            re.compile(r"(?:" + "AK" + r"IA|" + "AS" + r"IA)[0-9A-Z]{16}"),
            re.compile("git" + r"hub_pat_[A-Za-z0-9_]{20,}"),
            re.compile("gh" + r"[pousr]_[A-Za-z0-9]{20,}"),
            re.compile("sk-" + r"proj-[A-Za-z0-9_-]{20,}"),
            re.compile("-----BEGIN " + r"(?:RSA |OPENSSH )?PRIVATE KEY-----"),
        )
        aws_secret_name = "aws_" + "secret_access_key"
        client_secret_name = "client_" + "secret"
        assignment = re.compile(
            rf"(?i)\b(?:{aws_secret_name}|{client_secret_name})\s*[:=]\s*"
            r"[\"']?([A-Za-z0-9/+=_-]{6,})"
        )
        failures: list[str] = []
        for relative, text in release_texts():
            if any(pattern.search(text) for pattern in token_patterns):
                failures.append(f"{relative}: high-confidence secret signature")
            allowed_lines = SYNTHETIC_SECRET_LINE_HASHES.get(relative, set())
            for match in assignment.finditer(text):
                if containing_line_sha256(text, match.start()) not in allowed_lines:
                    failures.append(f"{relative}: secret-like assigned value")
        self.assertEqual(failures, [])

    def test_release_contains_no_private_machine_or_account_data(self) -> None:
        failures: list[str] = []
        for relative, text in release_texts():
            if any(pattern.search(text) for pattern in MACHINE_PATTERNS):
                failures.append(f"{relative}: personal machine signature")
            for match in EMAIL_PATTERN.finditer(text):
                address = match.group(0).casefold()
                domain = address.rsplit("@", 1)[1]
                if address == "git@github.com":
                    continue
                if domain in RESERVED_EMAIL_DOMAINS or domain.endswith(
                    (".example", ".invalid", ".test")
                ):
                    continue
                failures.append(f"{relative}: non-reserved email")
            for match in ACCOUNT_PATTERN.finditer(text):
                if match.group(1) not in SYNTHETIC_ACCOUNTS:
                    failures.append(f"{relative}: unexplained AWS account identifier")
        self.assertEqual(failures, [])

    def test_private_path_network_and_account_variants_are_detected(self) -> None:
        samples = (
            "C:" + "\\Users\\alice",
            "/" + "Users/alice",
            "/" + "home/alice",
            "/" + "root",
            "10" + ".0.0.7",
            "172" + ".16.0.1",
            "192" + ".168.20.5",
        )
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertTrue(
                    any(pattern.search(sample) for pattern in MACHINE_PATTERNS)
                )
        account = ACCOUNT_PATTERN.search("Account ID: " + "999999" + "999999")
        self.assertIsNotNone(account)

    def test_local_secret_and_device_state_is_ignored(self) -> None:
        ignore = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")
        required = (
            ".env",
            ".env.*",
            "*.pem",
            "*.key",
            "credentials",
            ".aws/",
            "kubeconfig",
            ".terraform/",
            "*.tfstate",
            ".vscode/",
            ".idea/",
            ".codex/hooks.json",
            "*.zip",
            "artifacts/",
        )
        for pattern in required:
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, ignore)

    def test_ruff_and_actions_monitoring_are_exact_and_read_only(self) -> None:
        config = tomllib.loads(
            (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        ruff = config["tool"]["ruff"]
        self.assertEqual(ruff["required-version"], "==0.16.0")
        self.assertEqual(ruff["target-version"], "py311")
        self.assertEqual(ruff["line-length"], 88)
        self.assertEqual(ruff["extend-exclude"], ["*.md"])
        self.assertEqual(ruff["lint"]["select"], ["E4", "E7", "E9", "F"])
        self.assertEqual(
            ruff["lint"]["per-file-ignores"],
            {
                "scripts/setup_assistant.py": ["E402"],
                "tests/test_context_packets.py": ["E402"],
                "tests/test_fastlane_presenter.py": ["E402"],
                "tests/test_product_journeys.py": ["E402"],
            },
        )

        dependabot = (REPOSITORY_ROOT / ".github/dependabot.yml").read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            dependabot,
            "version: 2\n"
            "updates:\n"
            '  - package-ecosystem: "github-actions"\n'
            '    directory: "/"\n'
            '    target-branch: "fast-lane"\n'
            "    schedule:\n"
            '      interval: "weekly"\n',
        )
        for forbidden in (
            "automerge",
            "auto-merge",
            "registries:",
            "token:",
            "password:",
            "github-actions: write",
        ):
            self.assertNotIn(forbidden, dependabot.casefold())

        workflow = (REPOSITORY_ROOT / ".github/workflows/ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("Run extracted release and Fastlane Engine smoke", workflow)
        self.assertNotIn("Run extracted release and doctor smoke", workflow)

    def test_feedback_form_is_privacy_safe(self) -> None:
        form = (
            REPOSITORY_ROOT / ".github" / "ISSUE_TEMPLATE" / "fastlane-feedback.yml"
        ).read_text(encoding="utf-8")
        ids = re.findall(r"^\s+id:\s*([A-Za-z0-9_-]+)\s*$", form, re.MULTILINE)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(ids)
        self.assertTrue(RISKY_FIELD_IDS.isdisjoint(ids))
        self.assertNotIn("type: upload", form)
        for phrase in (
            "Use synthetic or non-sensitive project details",
            "Do not include credentials, access tokens, real AWS account IDs or ARNs",
            "Do not paste a local path",
            "I used synthetic or non-sensitive project information",
            "I removed credentials, tokens, real AWS identifiers",
        ):
            self.assertIn(phrase, form)
        for phrase in (
            "Codex corrected a problem it created",
            "Leave blank if nothing was confusing",
        ):
            self.assertIn(phrase, form)
        self.assertNotIn("safe in-scope", form)
        self.assertNotIn("agent-owned", form)
        privacy_section = form[form.index("id: privacy") :]
        self.assertEqual(privacy_section.count("required: true"), 2)


if __name__ == "__main__":
    unittest.main()
