"""Pure Design-8 extension and dependency-acquisition policy."""

from __future__ import annotations

import hashlib
import re
import shlex
from pathlib import PurePosixPath
from typing import Any

from ..core.contracts import (
    ContractTable,
    _heading_section_lines,
    contract_table_after_heading,
)
from ..core.ids import (
    STABLE_CONTRACT_ID,
    canonical_id_list,
    clean_cell,
    explicit_value,
    unresolved,
)
from .models import (
    ApplicationSourceDisposition,
    DatasetImplementation,
    DependencyAddition,
    Design8Extension,
    EnvironmentPromotion,
    WellArchitectedConsideration,
)


DATASET_IMPLEMENTATION_HEADING = "### Dataset implementation mapping"
DATASET_IMPLEMENTATION_HEADERS = (
    "Dataset ID",
    "Store/component",
    "Implementation IDs",
    "Access and encryption enforcement",
    "Retention and deletion mechanism",
    "Backup and recovery mechanism",
    "Residency and migration mechanism",
    "Audit mechanism",
    "Validation IDs",
)
DATASET_IMPLEMENTATION_NONE = (
    "NOT_APPLICABLE — no typed DATASET records in the current approved "
    "Requirements contract"
)

ENVIRONMENT_PROMOTION_HEADING = "### Environment and promotion model"
ENVIRONMENT_PROMOTION_HEADERS = (
    "Environment ID",
    "Class",
    "Purpose",
    "Account/Region boundary",
    "Artifact boundary",
    "Configuration, secrets, and data boundary",
    "Promotion source",
    "Promotion criteria/evidence",
    "Rollback/teardown boundary",
    "Basis IDs",
    "Validation IDs",
)
ENVIRONMENT_CLASSES = {"LOCAL", "NON_PRODUCTION", "PRODUCTION"}

WELL_ARCHITECTED_HEADING = "### Well-Architected considerations"
WELL_ARCHITECTED_DISCLAIMER = (
    "This is a project design consideration review, not an official AWS "
    "Well-Architected Review or AWS Well-Architected Tool result."
)
WELL_ARCHITECTED_HEADERS = (
    "Pillar",
    "Applicability",
    "Requirement/risk basis IDs",
    "Design IDs",
    "Consideration and tradeoff",
    "Safeguard",
    "Validation/evidence IDs",
    "Evidence maturity",
    "Revisit trigger",
)
WELL_ARCHITECTED_PILLARS = (
    "Operational Excellence",
    "Security",
    "Reliability",
    "Performance Efficiency",
    "Cost Optimization",
    "Sustainability",
)
EVIDENCE_MATURITY = {"PLANNED", "SOURCE_VERIFIED", "NOT_APPLICABLE"}

DEPENDENCY_POLICY_HEADING = "### Dependency acquisition policy"
DEPENDENCY_POLICY_HEADERS = (
    "Dependency ID",
    "TECH ID",
    "Scope",
    "Ecosystem and package",
    "Immutable version",
    "Approved source",
    "Lockfile",
    "Integrity rule",
    "Lifecycle scripts",
    "Build network",
    "License disposition",
    "Exact acquisition command",
    "Evidence destination",
)
DEPENDENCY_ACQUISITION_NONE = (
    "DENY_UNDECLARED — no dependency acquisition is approved by this design"
)
DEPENDENCY_EVIDENCE_DESTINATION = (
    "docs/project/VERIFY.md#dependency-acquisition-evidence"
)

ENVIRONMENT_ID = re.compile(r"ENV-\d{3,}")
DEPENDENCY_ID = re.compile(r"DEP-\d{3,}")
TECHNOLOGY_ID = re.compile(r"TECH-\d{4,}")
DEPENDENCY_SCOPES = {"RUNTIME", "DEVELOPMENT", "BUILD", "TOOLING"}
DEPENDENCY_COMMAND = re.compile(
    r"^(?:"
    r"(?:python(?:3(?:\.\d+)?)?|py(?: -\d+(?:\.\d+)?)?) -m pip "
    r"(?:install|download|wheel)\b|"
    r"pip(?:3(?:\.\d+)?)? (?:install|download|wheel)\b|"
    r"uv (?:add|sync|lock|pip install)\b|"
    r"poetry (?:add|install|update|lock)\b|"
    r"pipenv (?:install|sync|update|lock)\b|"
    r"npm (?:install|i|ci|update)\b|"
    r"pnpm (?:install|add|update|fetch)\b|"
    r"yarn (?:install|add|up)\b|"
    r"bun (?:install|add|update)\b|"
    r"cargo (?:add|install|update|fetch)\b|"
    r"go (?:get|mod download|mod tidy)\b|"
    r"bundle (?:install|update)\b|"
    r"gem (?:install|update)\b|"
    r"dotnet (?:restore\b|add\b.*\bpackage\b)"
    r")",
    re.IGNORECASE,
)
FLOATING_VERSION = re.compile(
    r"(?:^|[^a-z0-9])(?:latest|current|head|main|master|next|any)(?:$|[^a-z0-9])|"
    r"[<>=~^*]",
    re.IGNORECASE,
)
PYPI_PACKAGE = re.compile(r"PYPI: ([a-z0-9]+(?:-[a-z0-9]+)*)")
IMMUTABLE_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9.!+_-]*")
SHA256_HEX = re.compile(r"[0-9a-f]{64}")
DNS_HOST = re.compile(
    r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?"
)
DEPENDENCY_LOCKFILE_NONE = (
    "NOT_APPLICABLE — direct wheel digest is command-bound; no lockfile mutation"
)
DEPENDENCY_LIFECYCLE_DENY = "DENY_BUILD_HOOKS — wheel-only direct install"
PIP_WHEEL_PREFIX = tuple(
    "python -m pip install --no-deps --only-binary=:all: --no-index".split()
)


def _section_has_exact_line(text: str, heading: str, expected: str) -> bool:
    section = _heading_section_lines(text, heading)
    return bool(section and expected in tuple(clean_cell(line) for line in section[1]))


def _table(
    text: str,
    heading: str,
    headers: tuple[str, ...],
    code: str,
    issues: list[str],
) -> ContractTable | None:
    try:
        table = contract_table_after_heading(text, heading, headers)
    except ValueError as exc:
        issues.append(f"{code}: {exc}")
        return None
    if table is None:
        issues.append(f"{code}: missing exact {heading} table")
    return table


def _ordered_ids(
    rows: tuple[tuple[str, ...], ...],
    pattern: re.Pattern[str],
    label: str,
    code: str,
    issues: list[str],
) -> None:
    identifiers = [row[0] for row in rows]
    invalid = [item for item in identifiers if pattern.fullmatch(item) is None]
    if invalid:
        issues.append(f"{code}: invalid {label} IDs: " + ", ".join(invalid))
    duplicates = sorted({item for item in identifiers if identifiers.count(item) > 1})
    if duplicates:
        issues.append(f"{code}: duplicate {label} IDs: " + ", ".join(duplicates))
    if identifiers != sorted(identifiers):
        issues.append(f"{code}: {label} rows must be sorted by ID")


def _refs(
    value: str,
    known_ids: set[str],
    field: str,
    code: str,
    issues: list[str],
    *,
    allow_none: bool = False,
) -> tuple[str, ...]:
    try:
        identifiers = canonical_id_list(value, STABLE_CONTRACT_ID, field)
    except ValueError as exc:
        issues.append(f"{code}: {exc}")
        return ()
    if not identifiers and not allow_none:
        issues.append(f"{code}: {field} must name at least one current ID")
    unknown = sorted(set(identifiers) - known_ids)
    if unknown:
        issues.append(f"{code}: {field} references unknown IDs: " + ", ".join(unknown))
    return tuple(identifiers)


def _concrete_fields(
    identifier: str,
    fields: tuple[tuple[str, str], ...],
    code: str,
    issues: list[str],
) -> None:
    missing = [name for name, value in fields if not explicit_value(value)]
    if missing:
        issues.append(
            f"{code}: {identifier} has unresolved fields: " + ", ".join(missing)
        )


def _dataset_implementations(
    text: str,
    requirements: Any,
    known_ids: set[str],
    issues: list[str],
) -> tuple[tuple[DatasetImplementation, ...], bytes | None]:
    expected_ids = [
        item.dataset_id
        for item in requirements.datasets
        if item.classification != "NONE"
    ]
    code = "DATASET_IMPLEMENTATION_INVALID"
    if not expected_ids:
        if not _section_has_exact_line(
            text, DATASET_IMPLEMENTATION_HEADING, DATASET_IMPLEMENTATION_NONE
        ):
            issues.append(
                f"{code}: an approved compatible Requirements contract without "
                f"typed datasets requires exactly {DATASET_IMPLEMENTATION_NONE!r}"
            )
            return (), None
        canonical = (
            f"DATASET_IMPLEMENTATION_NONE: {DATASET_IMPLEMENTATION_NONE}\n".encode()
        )
        return (), canonical
    table = _table(
        text,
        DATASET_IMPLEMENTATION_HEADING,
        DATASET_IMPLEMENTATION_HEADERS,
        code,
        issues,
    )
    if table is None:
        return (), None
    _ordered_ids(table.rows, re.compile(r"DATASET-\d{3,}"), "dataset", code, issues)
    observed_ids = [row[0] for row in table.rows]
    if observed_ids != expected_ids:
        issues.append(
            f"{code}: rows must exactly match current Requirements datasets in order: "
            + ", ".join(expected_ids)
        )
    result: list[DatasetImplementation] = []
    for row in table.rows:
        dataset_id = row[0]
        _concrete_fields(
            dataset_id,
            tuple(zip(DATASET_IMPLEMENTATION_HEADERS[1:8], row[1:8])),
            code,
            issues,
        )
        implementation_ids = _refs(
            row[2], known_ids, f"{dataset_id} Implementation IDs", code, issues
        )
        if implementation_ids and not any(
            TECHNOLOGY_ID.fullmatch(item) for item in implementation_ids
        ):
            issues.append(
                f"{code}: {dataset_id} Implementation IDs must include a current TECH ID"
            )
        validation_ids = _refs(
            row[8], known_ids, f"{dataset_id} Validation IDs", code, issues
        )
        result.append(
            DatasetImplementation(
                dataset_id,
                row[1],
                implementation_ids,
                row[3],
                row[4],
                row[5],
                row[6],
                row[7],
                validation_ids,
            )
        )
    return tuple(result), table.canonical_bytes


def _environment_record(
    row: tuple[str, ...],
    known_ids: set[str],
    seen: dict[str, str],
    issues: list[str],
) -> EnvironmentPromotion:
    code = "ENVIRONMENT_PROMOTION_INVALID"
    environment_id, environment_class = row[:2]
    if environment_class not in ENVIRONMENT_CLASSES:
        issues.append(
            f"{code}: {environment_id} Class must be LOCAL, NON_PRODUCTION, or PRODUCTION"
        )
    _concrete_fields(
        environment_id,
        tuple(
            (ENVIRONMENT_PROMOTION_HEADERS[index], row[index])
            for index in (2, 3, 4, 5, 7, 8)
        ),
        code,
        issues,
    )
    if not clean_cell(row[4]).startswith("IMMUTABLE: "):
        issues.append(
            f"{code}: {environment_id} Artifact boundary must start with IMMUTABLE:"
        )
    promotion_source = clean_cell(row[6])
    if promotion_source != "NONE" and promotion_source not in seen:
        issues.append(
            f"{code}: {environment_id} Promotion source must name one earlier ENV ID"
        )
    basis_ids = _refs(row[9], known_ids, f"{environment_id} Basis IDs", code, issues)
    validation_ids = _refs(
        row[10], known_ids, f"{environment_id} Validation IDs", code, issues
    )
    if environment_class == "PRODUCTION":
        account_boundary = clean_cell(row[3])
        if not (
            account_boundary.startswith("ISOLATED: ")
            and explicit_value(
                account_boundary.removeprefix("ISOLATED: "), allow_none=False
            )
        ):
            issues.append(
                f"{code}: {environment_id} production Account/Region boundary must be ISOLATED: <explicit boundary>"
            )
        if promotion_source == "NONE" or seen.get(promotion_source) != "NON_PRODUCTION":
            issues.append(
                f"{code}: {environment_id} production promotion requires an earlier NON_PRODUCTION source"
            )
        criteria = clean_cell(row[7])
        if not (
            criteria.startswith("SEPARATE_OWNER_AUTHORIZATION: ")
            and explicit_value(
                criteria.removeprefix("SEPARATE_OWNER_AUTHORIZATION: "),
                allow_none=False,
            )
        ):
            issues.append(
                f"{code}: {environment_id} production criteria must be SEPARATE_OWNER_AUTHORIZATION: <explicit evidence>"
            )
    return EnvironmentPromotion(
        environment_id,
        environment_class,
        row[2],
        row[3],
        row[4],
        row[5],
        promotion_source,
        row[7],
        row[8],
        basis_ids,
        validation_ids,
    )


def _environment_profile_issues(
    result: list[EnvironmentPromotion],
    requirements: Any,
    coverage: Any,
    roots: int,
    issues: list[str],
) -> None:
    code = "ENVIRONMENT_PROMOTION_INVALID"
    if roots != 1:
        issues.append(
            f"{code}: exactly one environment must have Promotion source NONE"
        )
    target = getattr(requirements, "completion_target", None)
    if target in {"DEPLOYED", "RECOVERY"} and not any(
        item.environment_class in {"NON_PRODUCTION", "PRODUCTION"} for item in result
    ):
        issues.append(
            f"{code}: {target} requires a declared non-local target environment"
        )
    production = any(item.environment_class == "PRODUCTION" for item in result)
    nonproduction = any(item.environment_class == "NON_PRODUCTION" for item in result)
    if (
        getattr(coverage, "delivery_profile", None) == "high-risk"
        and production
        and not nonproduction
    ):
        issues.append(
            f"{code}: high-risk production requires an isolated non-production predecessor"
        )


def _environments(
    text: str,
    requirements: Any,
    coverage: Any,
    known_ids: set[str],
    issues: list[str],
) -> tuple[tuple[EnvironmentPromotion, ...], bytes | None]:
    code = "ENVIRONMENT_PROMOTION_INVALID"
    table = _table(
        text,
        ENVIRONMENT_PROMOTION_HEADING,
        ENVIRONMENT_PROMOTION_HEADERS,
        code,
        issues,
    )
    if table is None:
        return (), None
    if not table.rows:
        issues.append(f"{code}: at least one environment is required")
    _ordered_ids(table.rows, ENVIRONMENT_ID, "environment", code, issues)
    result: list[EnvironmentPromotion] = []
    roots = 0
    seen: dict[str, str] = {}
    for row in table.rows:
        record = _environment_record(row, known_ids, seen, issues)
        if record.promotion_source == "NONE":
            roots += 1
        seen[record.environment_id] = record.environment_class
        result.append(record)
    _environment_profile_issues(result, requirements, coverage, roots, issues)
    return tuple(result), table.canonical_bytes


def _well_architected(
    text: str,
    known_ids: set[str],
    issues: list[str],
) -> tuple[tuple[WellArchitectedConsideration, ...], bytes | None]:
    code = "WELL_ARCHITECTED_CONSIDERATION_INVALID"
    if not _section_has_exact_line(
        text, WELL_ARCHITECTED_HEADING, WELL_ARCHITECTED_DISCLAIMER
    ):
        issues.append(
            f"{code}: the section must state exactly that it is not an official AWS review or Tool result"
        )
    table = _table(
        text,
        WELL_ARCHITECTED_HEADING,
        WELL_ARCHITECTED_HEADERS,
        code,
        issues,
    )
    if table is None:
        return (), None
    observed = [row[0] for row in table.rows]
    if observed != list(WELL_ARCHITECTED_PILLARS):
        issues.append(
            f"{code}: pillars must appear exactly once in canonical order: "
            + ", ".join(WELL_ARCHITECTED_PILLARS)
        )
    result: list[WellArchitectedConsideration] = []
    for row in table.rows:
        pillar, applicability = row[:2]
        applicable = applicability == "APPLICABLE"
        not_applicable = applicability.startswith(
            "NOT_APPLICABLE — "
        ) and explicit_value(applicability)
        _concrete_fields(
            pillar,
            (
                ("Consideration and tradeoff", row[4]),
                ("Safeguard", row[5]),
                ("Revisit trigger", row[8]),
            ),
            code,
            issues,
        )
        basis_ids = _refs(
            row[2], known_ids, f"{pillar} Requirement/risk basis IDs", code, issues
        )
        design_ids = _refs(row[3], known_ids, f"{pillar} Design IDs", code, issues)
        validation_ids = _refs(
            row[6],
            known_ids,
            f"{pillar} Validation/evidence IDs",
            code,
            issues,
            allow_none=not_applicable,
        )
        maturity = clean_cell(row[7])
        aws_evidence = any(item.startswith("AWS-EV-") for item in validation_ids)
        state_checks = {
            "Applicability must be APPLICABLE or NOT_APPLICABLE — <reason>": applicable
            or not_applicable,
            "Evidence maturity must be PLANNED, SOURCE_VERIFIED, or NOT_APPLICABLE": maturity
            in EVIDENCE_MATURITY,
            "applicable consideration needs evidence maturity": not applicable
            or maturity != "NOT_APPLICABLE",
            "non-applicability requires NOT_APPLICABLE maturity": not not_applicable
            or maturity == "NOT_APPLICABLE",
            "SOURCE_VERIFIED requires AWS-EV evidence": maturity != "SOURCE_VERIFIED"
            or aws_evidence,
            "AWS-EV evidence requires SOURCE_VERIFIED": maturity == "SOURCE_VERIFIED"
            or not aws_evidence,
        }
        issues.extend(
            f"{code}: {pillar} {detail}"
            for detail, valid in state_checks.items()
            if not valid
        )
        result.append(
            WellArchitectedConsideration(
                *row[:2],
                basis_ids,
                design_ids,
                *row[4:6],
                validation_ids,
                maturity,
                row[8],
            )
        )
    return tuple(result), table.canonical_bytes


def _strict_wheel_source(value: str, package: str | None, version: str) -> str | None:
    match = re.fullmatch(
        r"https://(?P<host>[a-z0-9.-]+)(?P<path>/[A-Za-z0-9._~+/-]+\.whl)",
        value,
    )
    if match is None or package is None:
        return None
    host, raw_path = match.group("host"), match.group("path")
    path = PurePosixPath(raw_path)
    wheel_prefix = f"{package.replace('-', '_')}-{version.replace('-', '_')}-"
    valid = bool(DNS_HOST.fullmatch(host) and path.as_posix() == raw_path)
    valid &= all(part not in {".", ".."} for part in path.parts)
    valid &= path.name.startswith(wheel_prefix) and path.name.endswith(".whl")
    return host if valid else None


def _dependency_control_issues(
    dependency_id: str,
    row: tuple[str, ...],
    scope: str,
    command: str,
    issues: list[str],
) -> None:
    match = PYPI_PACKAGE.fullmatch(clean_cell(row[3]))
    package = match.group(1) if match else None
    version, source = clean_cell(row[4]), clean_cell(row[5])
    source_host = _strict_wheel_source(source, package, version)
    digest_match = re.fullmatch(r"SHA256: ([0-9a-f]{64})", clean_cell(row[7]))
    digest = digest_match.group(1) if digest_match else None
    license_value = clean_cell(row[10])
    allowed = re.fullmatch(r"SPDX: ([^;]+); ALLOWED", license_value)
    exception = re.fullmatch(r"SPDX: ([^;]+); EXCEPTION: (.+)", license_value)
    valid_exception = exception and explicit_value(exception.group(2), allow_none=False)
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = []
    artifact = f"{package} @ {source}#sha256={digest}"
    control_checks = {
        "requires PYPI: <canonical-package>": package is not None,
        "requires a version-bound HTTPS wheel": bool(source_host)
        and IMMUTABLE_VERSION.fullmatch(version) is not None,
        "requires no lockfile mutation": scope == "TOOLING"
        and clean_cell(row[6]) == DEPENDENCY_LOCKFILE_NONE,
        "requires one command-bound SHA256": digest is not None,
        "requires wheel-only build denial": clean_cell(row[8])
        == DEPENDENCY_LIFECYCLE_DENY,
        "requires only the wheel source host": clean_cell(row[9])
        == f"ALLOW_HTTPS: {source_host}",
        "has an invalid license disposition": bool(allowed or valid_exception),
        "requires the exact wheel command": tuple(tokens)
        == (*PIP_WHEEL_PREFIX, artifact),
        "Immutable version is floating": not FLOATING_VERSION.search(version),
    }
    issues.extend(
        f"DEPENDENCY_POLICY_INVALID: {dependency_id} {detail}"
        for detail, valid in control_checks.items()
        if not valid
    )


def _dependency_record(
    row: tuple[str, ...],
    known_ids: set[str],
    commands: set[str],
    issues: list[str],
) -> DependencyAddition:
    code = "DEPENDENCY_POLICY_INVALID"
    dependency_id, technology_id, scope = row[:3]
    if TECHNOLOGY_ID.fullmatch(technology_id) is None or technology_id not in known_ids:
        issues.append(f"{code}: {dependency_id} TECH ID is not current")
    if scope not in DEPENDENCY_SCOPES:
        issues.append(
            f"{code}: {dependency_id} Scope must be RUNTIME, DEVELOPMENT, BUILD, or TOOLING"
        )
    _concrete_fields(
        dependency_id,
        tuple(zip(DEPENDENCY_POLICY_HEADERS[3:], row[3:])),
        code,
        issues,
    )
    command = canonical_command(row[11])
    _dependency_control_issues(dependency_id, row, scope, command, issues)
    if not is_dependency_acquisition_command(command):
        issues.append(
            f"{code}: {dependency_id} Exact acquisition command must be one recognized package-manager acquisition command"
        )
    if command in commands:
        issues.append(f"{code}: duplicate Exact acquisition command {command!r}")
    commands.add(command)
    if row[12] != DEPENDENCY_EVIDENCE_DESTINATION:
        issues.append(
            f"{code}: {dependency_id} Evidence destination must be exactly {DEPENDENCY_EVIDENCE_DESTINATION}"
        )
    return DependencyAddition(*row)


def _dependency_policy(
    text: str,
    known_ids: set[str],
    issues: list[str],
) -> tuple[tuple[DependencyAddition, ...], bytes | None, bool]:
    code = "DEPENDENCY_POLICY_INVALID"
    if _section_has_exact_line(
        text, DEPENDENCY_POLICY_HEADING, DEPENDENCY_ACQUISITION_NONE
    ):
        canonical = f"DEPENDENCY_ACQUISITION: {DEPENDENCY_ACQUISITION_NONE}\n".encode()
        return (), canonical, True
    table = _table(
        text,
        DEPENDENCY_POLICY_HEADING,
        DEPENDENCY_POLICY_HEADERS,
        "DEPENDENCY_POLICY_MISSING",
        issues,
    )
    if table is None:
        return (), None, True
    if not table.rows:
        issues.append(
            f"{code}: use the exact DENY_UNDECLARED sentinel when no acquisition is approved"
        )
    _ordered_ids(table.rows, DEPENDENCY_ID, "dependency", code, issues)
    result: list[DependencyAddition] = []
    commands: set[str] = set()
    for row in table.rows:
        result.append(_dependency_record(row, known_ids, commands, issues))
    return tuple(result), table.canonical_bytes, not bool(result)


def derive_design8_extension(
    text: str,
    requirements_contract: Any,
    coverage_contract: Any,
    known_ids: set[str],
) -> tuple[Design8Extension, list[str]]:
    """Validate the four Design-8 records and return their fixed-order digest."""

    issues: list[str] = []
    datasets, dataset_bytes = _dataset_implementations(
        text, requirements_contract, known_ids, issues
    )
    environments, environment_bytes = _environments(
        text, requirements_contract, coverage_contract, known_ids, issues
    )
    considerations, consideration_bytes = _well_architected(text, known_ids, issues)
    additions, dependency_bytes, acquisition_prohibited = _dependency_policy(
        text, known_ids, issues
    )
    parts = (
        dataset_bytes,
        environment_bytes,
        consideration_bytes,
        dependency_bytes,
    )
    canonical_bytes = (
        b"DESIGN_CONTRACT_EXTENSION_SCHEMA: 8\n" + b"".join(parts)  # type: ignore[arg-type]
        if all(part is not None for part in parts)
        else None
    )
    canonical_sha256 = (
        "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()
        if canonical_bytes is not None
        else None
    )
    return (
        Design8Extension(
            status="READY" if not issues else "BLOCKED",
            dataset_implementations=datasets,
            environments=environments,
            well_architected=considerations,
            dependency_additions=additions,
            acquisition_prohibited=acquisition_prohibited or bool(issues),
            canonical_sha256=canonical_sha256,
            canonical_bytes=canonical_bytes,
        ),
        issues,
    )


def derive_project_design8_state(
    text: str,
    requirements_contract: Any,
    coverage_contract: Any,
    known_design_ids: set[str],
    *,
    grandfather_schema_5: bool,
    grandfather_schema_6: bool,
    approved_schema_7: bool,
) -> tuple[Design8Extension, int, list[str], tuple[str, ...]]:
    """Return the current extension, effective schema, issues, and missing rows."""

    if grandfather_schema_5:
        return Design8Extension(), 5, [], ()
    if grandfather_schema_6:
        return Design8Extension(), 6, [], ()
    if approved_schema_7:
        return Design8Extension(), 7, [], ()
    extension, issues = derive_design8_extension(
        text,
        requirements_contract,
        coverage_contract,
        known_design_ids,
    )
    missing = (
        tuple(sorted(DESIGN8_HEADINGS)) if extension.canonical_bytes is None else ()
    )
    return extension, 8, issues, missing


def canonical_project_design_bytes(
    *,
    effective_schema: int,
    source_disposition: ApplicationSourceDisposition | None,
    requirements_contract: Any,
    current_tables: tuple[ContractTable | None, ...],
    extension: Design8Extension,
    first_wave_table: ContractTable | None,
    first_wave_sentinel: bytes | None,
    spike_table: ContractTable | None,
    spike_sentinel: bytes | None,
    expected_spike_id: str | None,
) -> tuple[bytes, str, list[str]]:
    """Build the project-contract identity in its historical byte order."""

    issues: list[str] = []
    parts = [f"PROJECT_DESIGN_CONTRACT_SCHEMA: {effective_schema}\n".encode()]
    if source_disposition is not None:
        parts.append(
            f"APPLICATION_SOURCE_DISPOSITION: {source_disposition.canonical_value}\n".encode()
        )
    if (
        requirements_contract.grandfathered_approved_gate_a
        and requirements_contract.canonical_sha256 is None
    ):
        issues.append(
            "Grandfathered Gate A design requires a canonical legacy requirements projection"
        )
    elif requirements_contract.grandfathered_approved_gate_a:
        parts.append(
            f"LEGACY_GATE_A_BRIDGE: {requirements_contract.canonical_sha256}\n".encode()
        )
    parts.extend(table.canonical_bytes for table in current_tables if table is not None)
    if extension.canonical_bytes is not None and effective_schema == 8:
        parts.append(extension.canonical_bytes)
    if first_wave_table is not None:
        parts.append(first_wave_table.canonical_bytes)
    elif first_wave_sentinel is not None:
        parts.append(first_wave_sentinel)
    if spike_table is not None and expected_spike_id is not None:
        parts.append(spike_table.canonical_bytes)
    elif spike_sentinel is not None:
        parts.append(spike_sentinel)
    canonical_bytes = b"".join(parts)
    digest = "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()
    return canonical_bytes, digest, issues


def project_design_is_uninitialized(
    current_tables: tuple[ContractTable | None, ...],
    effective_schema: int,
    extension: Design8Extension,
) -> bool:
    """Detect incomplete optional Design input without claiming a blocked contract."""

    unresolved_current = any(
        unresolved(cell)
        for table in current_tables
        if table is not None
        for row in table.rows
        for cell in row
    )
    return unresolved_current or (effective_schema == 8 and extension.status != "READY")


def canonical_command(command: str) -> str:
    """Return the policy's whitespace-stable command identity."""

    return re.sub(r"\s+", " ", clean_cell(command)).strip()


def is_dependency_acquisition_command(command: str) -> bool:
    """Recognize commands that can add, resolve, update, or fetch dependencies."""

    return DEPENDENCY_COMMAND.search(canonical_command(command)) is not None


def dependency_command_allowed(extension: Design8Extension, command: str) -> bool:
    """Require an exact current DEP row for every recognized acquisition command."""

    if not is_dependency_acquisition_command(command):
        return True
    if extension.acquisition_prohibited or extension.status != "READY":
        return False
    candidate = canonical_command(command)
    return any(
        canonical_command(item.exact_acquisition_command) == candidate
        for item in extension.dependency_additions
    )


DESIGN8_HEADINGS = frozenset(
    {
        DATASET_IMPLEMENTATION_HEADING,
        ENVIRONMENT_PROMOTION_HEADING,
        WELL_ARCHITECTED_HEADING,
        DEPENDENCY_POLICY_HEADING,
    }
)
DESIGN8_HEADERS = frozenset(
    {
        DATASET_IMPLEMENTATION_HEADERS,
        ENVIRONMENT_PROMOTION_HEADERS,
        WELL_ARCHITECTED_HEADERS,
        DEPENDENCY_POLICY_HEADERS,
    }
)


__all__ = (
    "DATASET_IMPLEMENTATION_HEADERS",
    "DATASET_IMPLEMENTATION_HEADING",
    "DATASET_IMPLEMENTATION_NONE",
    "DEPENDENCY_ACQUISITION_NONE",
    "DEPENDENCY_EVIDENCE_DESTINATION",
    "DEPENDENCY_POLICY_HEADERS",
    "DEPENDENCY_POLICY_HEADING",
    "DESIGN8_HEADINGS",
    "ENVIRONMENT_PROMOTION_HEADERS",
    "ENVIRONMENT_PROMOTION_HEADING",
    "WELL_ARCHITECTED_DISCLAIMER",
    "WELL_ARCHITECTED_HEADERS",
    "WELL_ARCHITECTED_HEADING",
    "WELL_ARCHITECTED_PILLARS",
    "canonical_command",
    "canonical_project_design_bytes",
    "dependency_command_allowed",
    "derive_design8_extension",
    "derive_project_design8_state",
    "is_dependency_acquisition_command",
    "project_design_is_uninitialized",
)
