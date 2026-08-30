from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Sequence

try:
    from fastlane_process import resolve_trusted_git
except ModuleNotFoundError:  # Loaded as scripts.maintenance_preflight in tests.
    from scripts.fastlane_process import resolve_trusted_git


# Compactness here preserves the validated maintenance line budget.
# fmt: off
SCHEMA_VERSION = 1
MODES = {"AUDIT", "PLAN", "IMPLEMENT", "PUBLISH"}
ROOT_KEYS = set("schema_version mode branch commit outcome non_goals allowed_files acceptance_criteria maximum_changed_files maximum_net_production_lines publication".split())
PUBLICATION_KEYS = {"operations", "targets", "authorization_reference"}
PUBLICATION_OPERATIONS = set("COMMIT PUSH OPEN_PR MERGE DELETE_BRANCH PUBLISH_RELEASE".split())
COMMIT = re.compile(r"^[0-9a-f]{40}$")
BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _git(root: Path, *args: str) -> str:
    result = subprocess.run([resolve_trusted_git(root), "-C", str(root), *args], check=False, capture_output=True, encoding="utf-8", timeout=15)
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or "git inspection failed")
    return result.stdout


def _strings(value: object, label: str, errors: list[str], *, required: bool) -> list[str]:
    if not isinstance(value, list) or (required and not value):
        errors.append(f"{label} must be {'a non-empty' if required else 'a'} list")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{label}[{index}] must be non-empty text")
        else:
            result.append(item.strip())
    if len(result) != len(set(result)):
        errors.append(f"{label} must not contain duplicates")
    return result


def _path(value: str, label: str, errors: list[str]) -> str | None:
    if "\\" in value:
        errors.append(f"{label} must use POSIX separators")
        return None
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or parsed.as_posix() != value or not parsed.parts or ":" in parsed.parts[0] or any(part in {"", ".", ".."} for part in parsed.parts):
        errors.append(f"{label} must be one contained repository-relative path")
        return None
    return value


def _changed_files(root: Path) -> list[str]:
    tracked = _git(root, "diff", "--name-only", "HEAD", "--").splitlines()
    untracked = _git(root, "ls-files", "--others", "--exclude-standard").splitlines()
    return sorted(set(item.replace("\\", "/") for item in [*tracked, *untracked] if item))


def _git_paths(root: Path, *args: str) -> list[str]:
    return sorted(item.replace("\\", "/") for item in _git(root, *args).splitlines() if item)


def _commit_state(root: Path) -> tuple[Any, ...]:
    staged = _git_paths(root, "diff", "--cached", "--name-only", "HEAD", "--")
    unstaged = _git_paths(root, "diff", "--name-only", "--")
    untracked = _git_paths(root, "ls-files", "--others", "--exclude-standard")
    unmerged = _git_paths(root, "diff", "--name-only", "--diff-filter=U", "--")
    markers = ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply", "sequencer")
    active = [name for name in markers if (root / _git(root, "rev-parse", "--git-path", name).strip()).exists()]
    patch = _git(root, "diff", "--cached", "--binary", "--full-index", "--no-ext-diff", "HEAD", "--")
    digest = "sha256:" + hashlib.sha256(patch.encode()).hexdigest()
    return staged, unstaged, untracked, unmerged, active, digest


def _net_production_lines(root: Path, changed: list[str]) -> int:
    net = 0
    untracked = set(_git(root, "ls-files", "--others", "--exclude-standard").splitlines())
    for line in _git(root, "diff", "--numstat", "HEAD", "--").splitlines():
        added, removed, path = line.split("\t", 2)
        canonical = path.replace("\\", "/")
        if canonical.startswith("tests/") or canonical == "bootstrap.manifest.json":
            continue
        if added.isdigit() and removed.isdigit():
            net += max(0, int(added) - int(removed))
    for relative in sorted(untracked):
        canonical = relative.replace("\\", "/")
        if canonical.startswith("tests/") or canonical == "bootstrap.manifest.json":
            continue
        path = root / relative
        if path.is_file() and not path.is_symlink():
            try:
                net += len(path.read_text(encoding="utf-8").splitlines())
            except (OSError, UnicodeDecodeError):
                net += 1
    return net


def _validate_contract(payload: object, root: Path, implementation_contract: object | None, observed: tuple[Any, ...] | None) -> tuple[dict[str, Any], bool]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return {"schema_version": SCHEMA_VERSION, "status": "FAIL", "errors": ["contract must be an object"]}, False
    missing = sorted(ROOT_KEYS - set(payload))
    unknown = sorted(set(payload) - ROOT_KEYS)
    if missing:
        errors.append("contract is missing fields: " + ", ".join(missing))
    if unknown:
        errors.append("contract has unknown fields: " + ", ".join(unknown))
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    mode = payload.get("mode")
    if mode not in MODES:
        errors.append("mode must be AUDIT, PLAN, IMPLEMENT, or PUBLISH")
        mode = "UNKNOWN"
    branch = payload.get("branch")
    if not isinstance(branch, str) or BRANCH.fullmatch(branch) is None or ".." in branch or "//" in branch:
        errors.append("branch must be one exact canonical branch name")
    commit = payload.get("commit")
    if not isinstance(commit, str) or COMMIT.fullmatch(commit) is None:
        errors.append("commit must be one lowercase 40-character SHA")
    outcome = payload.get("outcome")
    if not isinstance(outcome, str) or not outcome.strip():
        errors.append("outcome must be non-empty text")
    _strings(payload.get("non_goals"), "non_goals", errors, required=True)
    criteria = _strings(payload.get("acceptance_criteria"), "acceptance_criteria", errors, required=True)
    raw_allowed = _strings(payload.get("allowed_files"), "allowed_files", errors, required=mode == "IMPLEMENT")
    allowed = [item for index, item in enumerate(raw_allowed) if _path(item, f"allowed_files[{index}]", errors)]
    maximum_files = payload.get("maximum_changed_files")
    maximum_lines = payload.get("maximum_net_production_lines")
    for value, label in ((maximum_files, "maximum_changed_files"), (maximum_lines, "maximum_net_production_lines")):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"{label} must be a non-negative integer")
    publication = payload.get("publication")
    operations: list[str] = []
    if mode in {"AUDIT", "PLAN"}:
        if allowed or maximum_files != 0 or maximum_lines != 0 or publication is not None:
            errors.append(f"{mode} must be read-only with zero change budget and no publication authority")
    elif mode == "IMPLEMENT":
        if publication is not None:
            errors.append("IMPLEMENT must not contain publication authority")
        if isinstance(maximum_files, int) and maximum_files < 1:
            errors.append("IMPLEMENT requires a positive changed-file budget")
        if isinstance(maximum_lines, int) and maximum_lines < 1:
            errors.append("IMPLEMENT requires a positive production-line budget")
    elif mode == "PUBLISH":
        if allowed or maximum_files != 0 or maximum_lines != 0:
            errors.append("PUBLISH must not carry an implementation change budget")
        if not isinstance(publication, dict) or set(publication) != PUBLICATION_KEYS:
            errors.append("PUBLISH requires exact operations, targets, and authorization_reference")
        else:
            operations = _strings(publication.get("operations"), "publication.operations", errors, required=True)
            if any(item not in PUBLICATION_OPERATIONS for item in operations):
                errors.append("publication.operations contains an unsupported operation")
            _strings(publication.get("targets"), "publication.targets", errors, required=True)
            reference = publication.get("authorization_reference")
            if not isinstance(reference, str) or REFERENCE.fullmatch(reference) is None:
                errors.append("publication.authorization_reference must be one non-personal stable reference")

    commit_only = mode == "PUBLISH" and operations == ["COMMIT"]
    if operations and len(operations) != 1:
        errors.append("each PUBLISH contract must contain only one operation")
    if implementation_contract is not None and not commit_only:
        errors.append("an implementation contract is allowed only for COMMIT")
    root = root.resolve()
    if observed is None:
        try:
            observed_branch = _git(root, "branch", "--show-current").strip()
            observed_commit = _git(root, "rev-parse", "HEAD").strip()
            changed = _changed_files(root)
            production_lines = _net_production_lines(root, changed)
            commit_state = _commit_state(root) if commit_only else ([], [], [], [], [], None)
            if commit_only and observed_commit != _git(root, "rev-parse", "HEAD").strip():
                raise ValueError("repository changed during inspection")
            observed = observed_branch, observed_commit, changed, production_lines, commit_state
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            errors.append(f"repository inspection failed: {exc}")
            observed = "UNKNOWN", "UNKNOWN", [], 0, ([], [], [], [], [], None)
    observed_branch, observed_commit, changed, production_lines, commit_state = observed
    if isinstance(branch, str) and observed_branch != branch:
        errors.append("observed branch does not match the contract")
    if isinstance(commit, str) and observed_commit != commit:
        errors.append("observed commit does not match the contract baseline")
    implementation_digest = None
    if commit_only:
        if not isinstance(implementation_contract, dict):
            errors.append("COMMIT requires one exact IMPLEMENT contract")
        elif implementation_contract.get("mode") != "IMPLEMENT":
            errors.append("COMMIT requires an IMPLEMENT-mode implementation contract")
        else:
            if implementation_contract.get("branch") != branch or implementation_contract.get("commit") != commit:
                errors.append("IMPLEMENT and PUBLISH branch/baseline must match exactly")
            inner, _ = _validate_contract(implementation_contract, root, None, observed)
            errors.extend(f"implementation contract: {item}" for item in inner["errors"])
            canonical = json.dumps(implementation_contract, sort_keys=True, separators=(",", ":"))
            implementation_digest = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
        staged, unstaged, untracked, unmerged, active, _ = commit_state
        errors.extend(
            message
            for condition, message in (
                (not staged, "COMMIT requires a nonempty staged change"),
                (bool(unstaged), "COMMIT forbids unstaged changes"),
                (bool(untracked), "COMMIT forbids untracked files"),
                (bool(unmerged), "COMMIT forbids unmerged index entries"),
                (staged != changed, "COMMIT requires the exact changed set to be staged"),
                (bool(active), "COMMIT forbids active Git operation state: " + ", ".join(active)),
            )
            if condition
        )
    else:
        unexpected = sorted(set(changed) - set(allowed))
        if unexpected:
            errors.append("changed files exceed the allowlist: " + ", ".join(unexpected))
        if isinstance(maximum_files, int) and len(changed) > maximum_files:
            errors.append("changed-file budget exceeded")
        if isinstance(maximum_lines, int) and production_lines > maximum_lines:
            errors.append("net production-line budget exceeded")
    if (mode in {"AUDIT", "PLAN"} or mode == "PUBLISH" and not commit_only) and changed:
        errors.append(f"{mode} requires a clean worktree")
    if not criteria:
        errors.append("at least one observable acceptance criterion is required")
    result = {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "status": "PASS" if not errors else "FAIL",
        "observed_branch": observed_branch,
        "observed_commit": observed_commit,
        "changed_files": changed,
        "net_production_lines": production_lines,
        "publication_authority_present": publication is not None,
        "implementation_contract_sha256": implementation_digest,
        "staged_diff_sha256": commit_state[-1] if commit_only else None,
        "errors": errors,
    }
    return result, not errors


def validate_contract(payload: object, root: Path, implementation_contract: object | None = None) -> tuple[dict[str, Any], bool]:
    return _validate_contract(payload, root, implementation_contract, None)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a Fastlane maintenance scope contract read-only.")
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--implementation-contract", type=Path)
    parser.add_argument("--root", default=Path.cwd(), type=Path)
    parser.add_argument("--json", action="store_true", required=True)
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.contract.read_text(encoding="utf-8"))
        implementation = json.loads(args.implementation_contract.read_text(encoding="utf-8")) if args.implementation_contract else None
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"schema_version": SCHEMA_VERSION, "status": "FAIL", "errors": [f"contract could not be read: {exc}"]}, indent=2, sort_keys=True))
        return 2
    result, passed = validate_contract(payload, args.root, implementation)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 2


# fmt: on
if __name__ == "__main__":
    sys.exit(main())
