"""Bounded, immutable, single-observation project snapshots.

Canonical inputs are repository-relative regular files observed from one root.
The observer returns frozen file, Markdown, and trusted Git snapshots. It performs
bounded read-only filesystem and Git observation only; it never writes, accesses a
network, validates lifecycle state, or grants authority.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
import heapq
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
from types import MappingProxyType

from .digests import lf_normalized_text, sha256_hex
from .ids import validate_relative_path
from .markdown_index import MarkdownDocumentIndex

try:
    from fastlane_process import resolve_trusted_git
except ModuleNotFoundError:  # Loaded as scripts.fastlane_engine in unit tests.
    from scripts.fastlane_process import resolve_trusted_git


MAX_REQUIRED_FILES = 512
MAX_REQUIRED_FILE_BYTES = 16 * 1024 * 1024
MAX_PROJECT_SOURCE_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class ObservationError(ValueError):
    code: str
    message: str
    path: str | None = None

    def __str__(self) -> str:
        return self.message


class GitObservationError(RuntimeError):
    """SAFETY: report a failed bounded Git observation to pure evaluators."""


@dataclass(frozen=True)
class FileSnapshot:
    path: str
    raw_bytes: bytes
    presentation_text: str | None
    canonical_text: str | None
    byte_sha256: str
    lf_sha256: str | None
    byte_size: int


@dataclass(frozen=True)
class DirectoryEntrySnapshot:
    path: str
    name: str
    byte_size: int
    is_file: bool
    is_directory: bool
    is_symlink: bool


@dataclass(frozen=True)
class DirectorySnapshot:
    path: str
    exists: bool
    is_directory: bool
    is_symlink: bool
    entries: tuple[DirectoryEntrySnapshot, ...] = ()
    observation_error: str | None = None


@dataclass(frozen=True, order=True)
class GitQueryKey:
    operation: str
    arguments: tuple[str, ...] = ()

    @classmethod
    def from_arguments(cls, arguments: tuple[str, ...]) -> "GitQueryKey":
        """CANONICALIZATION: normalize equivalent query identities once."""

        if arguments[:2] == ("merge-base", "--is-ancestor"):
            return cls("merge-base-is-ancestor", arguments[2:])
        if arguments[:2] == ("rev-parse", "--verify"):
            return cls("resolve-commit", arguments[2:])
        if arguments == ("rev-parse", "--is-inside-work-tree"):
            return cls("repository-is-worktree")
        if arguments == ("rev-parse", "--is-bare-repository"):
            return cls("repository-is-bare")
        if arguments and arguments[0] == "diff":
            return cls("diff-name-only", arguments[1:])
        if arguments and arguments[0] == "ls-files":
            return cls("ls-files", arguments[1:])
        return cls(arguments[0] if arguments else "git", arguments[1:])


@dataclass(frozen=True)
class GitQueryResult:
    key: GitQueryKey
    returncode: int
    stdout: bytes = b""
    stderr: bytes = b""
    observation_error: str | None = None


@dataclass(frozen=True)
class GitSnapshot:
    executable: str | None = None
    root: str | None = None
    branch: str | None = None
    head_sha: str | None = None
    baseline_sha: str | None = None
    inside_work_tree: bool | None = None
    bare: bool | None = None
    working_tree_state: str = "UNKNOWN"
    dirty_paths: tuple[str, ...] = ()
    tracked_changes: tuple[str, ...] = ()
    staged_changes: tuple[str, ...] = ()
    untracked_paths: tuple[str, ...] = ()
    protected_dirty_paths: tuple[str, ...] = ()
    query_results: Mapping[GitQueryKey, GitQueryResult] = field(
        default_factory=lambda: MappingProxyType({})
    )
    process_count: int = 0
    duplicate_processes: int = 0

    @property
    def head(self) -> str | None:
        """COMPATIBILITY: retain the foundation snapshot attribute."""

        return self.head_sha

    @property
    def baseline(self) -> str | None:
        """COMPATIBILITY: retain the foundation snapshot attribute."""

        return self.baseline_sha

    def result(self, *arguments: str) -> GitQueryResult:
        key = GitQueryKey.from_arguments(tuple(arguments))
        result = self.query_results.get(key)
        if result is None:
            raise GitObservationError(
                "Required Git query was not captured in the project snapshot: "
                + " ".join(arguments)
            )
        if result.observation_error is not None:
            raise GitObservationError(result.observation_error)
        return result


@dataclass(frozen=True)
class ObservationMetrics:
    files_opened: int
    bytes_observed: int
    markdown_indexes: int
    git_processes: int = 0
    duplicate_git_processes: int = 0


@dataclass(frozen=True)
class ProjectSnapshot:
    observed_at: datetime
    root: Path
    project_identity: Mapping[str, str]
    files: Mapping[str, FileSnapshot]
    markdown: Mapping[str, MarkdownDocumentIndex]
    directories: Mapping[str, DirectorySnapshot]
    file_errors: Mapping[str, ObservationError]
    text_errors: Mapping[str, ObservationError]
    git: GitSnapshot
    bootstrap_state: Mapping[str, object]
    manifest: Mapping[str, object]
    observation_metrics: ObservationMetrics

    def file(self, relative: str) -> FileSnapshot | None:
        return self.files.get(relative)


class SnapshotObserver:
    """Open each requested file once and freeze the resulting observation."""

    def __init__(
        self,
        root: Path,
        *,
        observed_at: datetime | None = None,
        canonicalize_text: Callable[[str, str], str] | None = None,
        max_files: int = MAX_REQUIRED_FILES,
        max_file_bytes: int = MAX_REQUIRED_FILE_BYTES,
        max_source_bytes: int = MAX_PROJECT_SOURCE_BYTES,
    ) -> None:
        self.root = root.resolve()
        self.observed_at = observed_at or datetime.now(timezone.utc)
        self.canonicalize_text = canonicalize_text
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes
        self.max_source_bytes = max_source_bytes
        self._files: dict[str, FileSnapshot] = {}
        self._markdown: dict[str, MarkdownDocumentIndex] = {}
        self._directories: dict[str, DirectorySnapshot] = {}
        self._file_errors: dict[str, ObservationError] = {}
        self._text_errors: dict[str, ObservationError] = {}
        self._bytes_observed = 0

    def _validate(self, relative: str) -> Path:
        if validate_relative_path(relative) is None:
            raise ObservationError(
                "MANIFEST_UNSAFE_PATH",
                f"Unsafe project-relative path: {relative!r}",
            )
        if has_symlink_component(self.root, relative):
            raise ObservationError(
                "REQUIRED_FILE_SYMLINK",
                "Required path contains a symbolic link",
                relative,
            )
        path = self.root / relative
        if not path.resolve().is_relative_to(self.root):
            raise ObservationError(
                "MANIFEST_UNSAFE_PATH", "Path resolves outside the project", relative
            )
        if not path.exists():
            raise ObservationError(
                "REQUIRED_FILE_MISSING", "Required file is missing", relative
            )
        if not path.is_file():
            raise ObservationError(
                "REQUIRED_FILE_NOT_REGULAR",
                "Required path is not a regular file",
                relative,
            )
        return path

    def _read(self, relative: str, *, text_mode: bool = False) -> bytes:
        cached = self._files.get(relative)
        if cached is not None:
            return cached.raw_bytes
        if len(self._files) >= self.max_files:
            raise ObservationError(
                "MANIFEST_REQUIRED_FILES_LIMIT",
                f"required_files exceeds the {self.max_files}-entry limit",
                relative,
            )
        path = self._validate(relative)
        remaining = self.max_source_bytes - self._bytes_observed
        if remaining <= 0:
            subject = "text" if text_mode else "files"
            raise ObservationError(
                "PROJECT_SOURCE_LIMIT",
                f"Required project {subject} exceeds the {self.max_source_bytes}-byte aggregate limit",
                relative,
            )
        read_limit = min(self.max_file_bytes, remaining)
        try:
            with path.open("rb") as stream:
                raw = stream.read(read_limit + 1)
        except OSError as exc:
            message = (
                f"Unable to read UTF-8 text: {exc}"
                if text_mode
                else f"Unable to read file: {exc}"
            )
            raise ObservationError(
                "REQUIRED_FILE_UNREADABLE", message, relative
            ) from exc
        if len(raw) > read_limit:
            code = (
                "REQUIRED_FILE_TOO_LARGE"
                if read_limit == self.max_file_bytes
                else "PROJECT_SOURCE_LIMIT"
            )
            limit = (
                self.max_file_bytes
                if code == "REQUIRED_FILE_TOO_LARGE"
                else self.max_source_bytes
            )
            scope = "per-file" if code == "REQUIRED_FILE_TOO_LARGE" else "aggregate"
            subject = "text" if text_mode else "file"
            raise ObservationError(
                code,
                f"Required project {subject} exceeds the {limit}-byte {scope} limit",
                relative,
            )
        self._bytes_observed += len(raw)
        self._files[relative] = FileSnapshot(
            path=relative,
            raw_bytes=raw,
            presentation_text=None,
            canonical_text=None,
            byte_sha256=sha256_hex(raw),
            lf_sha256=None,
            byte_size=len(raw),
        )
        return raw

    def observe_binary(self, relative: str) -> FileSnapshot:
        self._read(relative)
        return self._files[relative]

    def capture_binary(self, relative: str) -> FileSnapshot | None:
        """Capture a binary file while retaining a deferred observation error."""

        try:
            return self.observe_binary(relative)
        except ObservationError as exc:
            self._file_errors.setdefault(relative, exc)
            return None

    def observe_text(
        self, relative: str, *, markdown: bool | None = None
    ) -> FileSnapshot:
        existing = self._files.get(relative)
        if existing is not None and existing.presentation_text is not None:
            return existing
        raw = self._read(relative, text_mode=True)
        try:
            presentation = lf_normalized_text(raw.decode("utf-8"))
        except UnicodeError as exc:
            raise ObservationError(
                "REQUIRED_FILE_UNREADABLE",
                f"Unable to read UTF-8 text: {exc}",
                relative,
            ) from exc
        canonical = (
            self.canonicalize_text(relative, presentation)
            if self.canonicalize_text is not None
            else presentation
        )
        snapshot = FileSnapshot(
            path=relative,
            raw_bytes=raw,
            presentation_text=presentation,
            canonical_text=canonical,
            byte_sha256=sha256_hex(raw),
            lf_sha256=sha256_hex(canonical.encode("utf-8")),
            byte_size=len(raw),
        )
        self._files[relative] = snapshot
        should_index = (
            relative.casefold().endswith(".md") if markdown is None else markdown
        )
        if should_index:
            self._markdown[relative] = MarkdownDocumentIndex.build(canonical)
        return snapshot

    def capture_text(
        self, relative: str, *, markdown: bool | None = None
    ) -> FileSnapshot | None:
        """Capture UTF-8 text while retaining errors for deterministic replay."""

        try:
            return self.observe_text(relative, markdown=markdown)
        except ObservationError as exc:
            if relative not in self._files:
                self._file_errors.setdefault(relative, exc)
            self._text_errors.setdefault(relative, exc)
            return None

    def observe_directory(
        self,
        relative: str,
        *,
        maximum_entries: int = MAX_REQUIRED_FILES,
    ) -> DirectorySnapshot:
        """Observe one bounded directory inventory without following symlinks."""

        existing = self._directories.get(relative)
        if existing is not None:
            return existing
        if validate_relative_path(relative) is None:
            snapshot = DirectorySnapshot(
                path=relative,
                exists=False,
                is_directory=False,
                is_symlink=False,
                observation_error=f"Unsafe project-relative path: {relative!r}",
            )
            self._directories[relative] = snapshot
            return snapshot
        path = self.root.joinpath(*PurePosixPath(relative).parts)
        try:
            ancestor_symlink = has_symlink_component(self.root, relative)
            exists = path.exists() or path.is_symlink()
            is_symlink = ancestor_symlink or path.is_symlink()
            is_directory = bool(exists and not is_symlink and path.is_dir())
            entries: list[DirectoryEntrySnapshot] = []
            if is_directory:
                for entry in heapq.nsmallest(
                    maximum_entries, path.iterdir(), key=lambda item: item.name
                ):
                    entry_is_symlink = has_symlink_component(path, entry.name)
                    metadata = entry.lstat()
                    entries.append(
                        DirectoryEntrySnapshot(
                            path=PurePosixPath(relative, entry.name).as_posix(),
                            name=entry.name,
                            byte_size=metadata.st_size,
                            is_file=bool(not entry_is_symlink and entry.is_file()),
                            is_directory=bool(not entry_is_symlink and entry.is_dir()),
                            is_symlink=entry_is_symlink,
                        )
                    )
            snapshot = DirectorySnapshot(
                path=relative,
                exists=exists,
                is_directory=is_directory,
                is_symlink=is_symlink,
                entries=tuple(entries),
            )
        except OSError as exc:
            snapshot = DirectorySnapshot(
                path=relative,
                exists=False,
                is_directory=False,
                is_symlink=False,
                observation_error=str(exc),
            )
        self._directories[relative] = snapshot
        return snapshot

    def file(self, relative: str) -> FileSnapshot | None:
        """Return an already observed file without performing another read."""

        return self._files.get(relative)

    @property
    def bytes_observed(self) -> int:
        return self._bytes_observed

    @property
    def files_opened(self) -> int:
        return len(self._files)

    def freeze(
        self,
        *,
        project_identity: Mapping[str, str] | None = None,
        git: GitSnapshot | None = None,
        bootstrap_state: Mapping[str, object] | None = None,
        manifest: Mapping[str, object] | None = None,
    ) -> ProjectSnapshot:
        return ProjectSnapshot(
            observed_at=self.observed_at,
            root=self.root,
            project_identity=MappingProxyType(dict(project_identity or {})),
            files=MappingProxyType(dict(self._files)),
            markdown=MappingProxyType(dict(self._markdown)),
            directories=MappingProxyType(dict(self._directories)),
            file_errors=MappingProxyType(dict(self._file_errors)),
            text_errors=MappingProxyType(dict(self._text_errors)),
            git=git or GitSnapshot(root=str(self.root)),
            bootstrap_state=_freeze_mapping(bootstrap_state or {}),
            manifest=_freeze_mapping(manifest or {}),
            observation_metrics=ObservationMetrics(
                files_opened=len(self._files),
                bytes_observed=self._bytes_observed,
                markdown_indexes=len(self._markdown),
                git_processes=(git.process_count if git is not None else 0),
                duplicate_git_processes=(
                    git.duplicate_processes if git is not None else 0
                ),
            ),
        )


class GitObserver:
    """Capture canonical, memoized read-only Git facts for one invocation."""

    def __init__(
        self,
        root: Path,
        *,
        resolve_git: Callable[[Path], str] | None = None,
        run: Callable[..., subprocess.CompletedProcess[bytes]] | None = None,
    ) -> None:
        self.root = root.resolve()
        self._resolve_git = resolve_git or resolve_trusted_git
        self._run = run or subprocess.run
        self._executable: str | None = None
        self._results: dict[GitQueryKey, GitQueryResult] = {}
        self._process_count = 0
        self._duplicate_requests = 0
        self._branch: str | None = None
        self._head_sha: str | None = None
        self._inside_work_tree: bool | None = None
        self._bare: bool | None = None
        self._tracked_changes: tuple[str, ...] = ()
        self._staged_changes: tuple[str, ...] = ()
        self._untracked_paths: tuple[str, ...] = ()

    def _execute(
        self, key: GitQueryKey, command_arguments: tuple[str, ...]
    ) -> GitQueryResult:
        existing = self._results.get(key)
        if existing is not None:
            self._duplicate_requests += 1
            return existing
        try:
            if self._executable is None:
                self._executable = self._resolve_git(self.root)
            self._process_count += 1
            completed = git_read(
                self.root,
                *command_arguments,
                resolve_git=lambda _root: str(self._executable),
                run=self._run,
            )
        except (GitObservationError, OSError, ValueError) as exc:
            result = GitQueryResult(
                key=key,
                returncode=-1,
                observation_error=str(exc),
            )
        else:
            stdout = completed.stdout
            stderr = completed.stderr
            result = GitQueryResult(
                key=key,
                returncode=completed.returncode,
                stdout=(
                    stdout
                    if isinstance(stdout, bytes)
                    else stdout.encode("utf-8", errors="surrogateescape")
                ),
                stderr=(
                    stderr
                    if isinstance(stderr, bytes)
                    else stderr.encode("utf-8", errors="surrogateescape")
                ),
            )
        self._results[key] = result
        return result

    def _record_synthetic(
        self,
        arguments: tuple[str, ...],
        *,
        returncode: int = 0,
        stdout: bytes = b"",
        stderr: bytes = b"",
        observation_error: str | None = None,
    ) -> GitQueryResult:
        key = GitQueryKey.from_arguments(arguments)
        existing = self._results.get(key)
        if existing is not None:
            return existing
        result = GitQueryResult(
            key=key,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            observation_error=observation_error,
        )
        self._results[key] = result
        return result

    def observe_repository_state(self) -> None:
        """Observe identity and dirty state in one lock-free Git process."""

        key = GitQueryKey("repository-status-v2")
        status = self._execute(
            key,
            ("status", "--porcelain=v2", "--branch", "-z", "--untracked-files=all"),
        )
        if status.observation_error is not None:
            for arguments in (
                ("rev-parse", "--is-inside-work-tree"),
                ("rev-parse", "--is-bare-repository"),
                ("rev-parse", "--verify", "HEAD"),
                ("rev-parse", "--verify", "HEAD^{commit}"),
            ):
                self._record_synthetic(
                    arguments,
                    returncode=-1,
                    observation_error=status.observation_error,
                )
            return
        if status.returncode != 0:
            for arguments in (
                ("rev-parse", "--is-inside-work-tree"),
                ("rev-parse", "--is-bare-repository"),
                ("rev-parse", "--verify", "HEAD"),
                ("rev-parse", "--verify", "HEAD^{commit}"),
            ):
                self._record_synthetic(
                    arguments,
                    returncode=status.returncode,
                    stderr=status.stderr,
                )
            return
        (
            self._branch,
            self._head_sha,
            tracked,
            staged,
            untracked,
        ) = _parse_porcelain_v2(status.stdout)
        self._inside_work_tree = True
        self._bare = False
        self._tracked_changes = tuple(sorted(tracked))
        self._staged_changes = tuple(sorted(staged))
        self._untracked_paths = tuple(sorted(untracked))
        self._record_synthetic(("rev-parse", "--is-inside-work-tree"), stdout=b"true\n")
        self._record_synthetic(("rev-parse", "--is-bare-repository"), stdout=b"false\n")
        if self._head_sha is not None:
            payload = self._head_sha.encode("ascii") + b"\n"
            self._record_synthetic(("rev-parse", "--verify", "HEAD"), stdout=payload)
            self._record_synthetic(
                ("rev-parse", "--verify", "HEAD^{commit}"), stdout=payload
            )
        tracked_payload = b"\0".join(
            path.encode("utf-8", errors="surrogateescape")
            for path in self._tracked_changes
        )
        if tracked_payload:
            tracked_payload += b"\0"
        untracked_payload = b"\0".join(
            path.encode("utf-8", errors="surrogateescape")
            for path in self._untracked_paths
        )
        if untracked_payload:
            untracked_payload += b"\0"
        self._record_synthetic(
            ("diff", "--name-only", "-z", "--relative", "HEAD", "--", "."),
            stdout=tracked_payload,
        )
        self._record_synthetic(
            ("ls-files", "--others", "--exclude-standard", "-z", "--", "."),
            stdout=untracked_payload,
        )

    def query(self, *arguments: str) -> GitQueryResult:
        """Return one canonical query result, executing it at most once."""

        normalized = tuple(arguments)
        key = GitQueryKey.from_arguments(normalized)
        existing = self._results.get(key)
        if existing is not None:
            self._duplicate_requests += 1
            return existing
        synthetic = self._synthetic_result(normalized)
        if synthetic is not None:
            return synthetic
        return self._execute(key, normalized)

    def _synthetic_result(self, arguments: tuple[str, ...]) -> GitQueryResult | None:
        """SAFETY: reuse only facts already proven by this immutable observation."""

        if arguments[:2] == ("rev-parse", "--verify") and len(arguments) == 3:
            reference = arguments[2].removesuffix("^{commit}")
            if reference == "HEAD" or reference == self._head_sha:
                if self._head_sha is None:
                    return None
                return self._record_synthetic(
                    arguments, stdout=self._head_sha.encode("ascii") + b"\n"
                )
        if arguments[:2] == ("merge-base", "--is-ancestor") and len(arguments) == 4:
            left = self._known_commit(arguments[2])
            right = self._known_commit(arguments[3])
            if left is not None and left == right:
                return self._record_synthetic(arguments)
        if arguments and arguments[0] == "diff":
            revision_range = next(
                (
                    item
                    for item in arguments
                    if ".." in item and not item.startswith("--")
                ),
                None,
            )
            if revision_range is not None:
                left_value, right_value = revision_range.split("..", 1)
                left = self._known_commit(left_value)
                right = self._known_commit(right_value)
                if left is not None and left == right:
                    return self._record_synthetic(arguments)
        return None

    def _known_commit(self, value: str) -> str | None:
        if value == "HEAD":
            return self._head_sha
        cleaned = value.removesuffix("^{commit}")
        if cleaned == self._head_sha:
            return self._head_sha
        result = self._results.get(GitQueryKey("resolve-commit", (value,)))
        if result is None:
            result = self._results.get(
                GitQueryKey("resolve-commit", (f"{cleaned}^{{commit}}",))
            )
        if result is None or result.returncode != 0 or result.observation_error:
            return None
        candidate = result.stdout.decode("ascii", errors="replace").strip()
        return candidate if re.fullmatch(r"[0-9a-fA-F]{40,64}", candidate) else None

    def freeze(
        self,
        *,
        baseline_sha: str | None = None,
        protected_dirty_paths: tuple[str, ...] = (),
    ) -> GitSnapshot:
        dirty = tuple(sorted(set(self._tracked_changes) | set(self._untracked_paths)))
        state = (
            "UNKNOWN"
            if self._inside_work_tree is None
            else ("DIRTY" if dirty else "CLEAN")
        )
        return GitSnapshot(
            executable=self._executable,
            root=str(self.root),
            branch=self._branch,
            head_sha=self._head_sha,
            baseline_sha=baseline_sha,
            inside_work_tree=self._inside_work_tree,
            bare=self._bare,
            working_tree_state=state,
            dirty_paths=dirty,
            tracked_changes=self._tracked_changes,
            staged_changes=self._staged_changes,
            untracked_paths=self._untracked_paths,
            protected_dirty_paths=protected_dirty_paths,
            query_results=MappingProxyType(dict(self._results)),
            process_count=self._process_count,
            duplicate_processes=0,
        )


def _parse_porcelain_v2(
    payload: bytes,
) -> tuple[str | None, str | None, set[str], set[str], set[str]]:
    branch: str | None = None
    head: str | None = None
    tracked: set[str] = set()
    staged: set[str] = set()
    untracked: set[str] = set()
    records = payload.split(b"\0")
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        if record.startswith(b"# branch.oid "):
            candidate = record.removeprefix(b"# branch.oid ").decode(
                "ascii", errors="replace"
            )
            if re.fullmatch(r"[0-9a-fA-F]{40,64}", candidate):
                head = candidate.lower()
            continue
        if record.startswith(b"# branch.head "):
            candidate = record.removeprefix(b"# branch.head ").decode(
                "utf-8", errors="replace"
            )
            branch = None if candidate == "(detached)" else candidate
            continue
        kind = record[:1]
        if kind == b"?" and record.startswith(b"? "):
            untracked.add(record[2:].decode("utf-8", errors="surrogateescape"))
            continue
        if kind not in {b"1", b"2", b"u"}:
            continue
        maximum = {b"1": 8, b"2": 9, b"u": 10}[kind]
        parts = record.split(b" ", maximum)
        if len(parts) <= maximum:
            continue
        xy = parts[1]
        path = parts[-1].decode("utf-8", errors="surrogateescape")
        tracked.add(path)
        if xy[:1] not in {b".", b" "}:
            staged.add(path)
        if kind == b"2" and index < len(records):
            index += 1
    return branch, head, tracked, staged, untracked


def has_symlink_component(root: Path, relative: str) -> bool:
    current = root
    for part in PurePosixPath(relative).parts:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode) or (
            getattr(metadata, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        ):
            return True
    return False


def git_read(
    root: Path,
    *arguments: str,
    resolve_git: Callable[[Path], str] | None = None,
    run: Callable[..., subprocess.CompletedProcess[bytes]] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """SAFETY: run one trusted, lock-free Git observation."""

    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    resolver = resolve_git or resolve_trusted_git
    runner = run or subprocess.run
    try:
        return runner(
            [
                resolver(root),
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.hooksPath=/dev/null",
                "-C",
                str(root),
                *arguments,
            ],
            check=False,
            capture_output=True,
            env=environment,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitObservationError(str(exc)) from exc


def inspect_git_baseline(
    root: Path,
    *,
    resolve_git: Callable[[Path], str] | None = None,
    run: Callable[..., subprocess.CompletedProcess[bytes]] | None = None,
) -> str:
    """SAFETY: observe the current commit without changing Git state."""

    try:
        result = git_read(
            root,
            "rev-parse",
            "--verify",
            "HEAD",
            resolve_git=resolve_git,
            run=run,
        )
    except GitObservationError:
        return "PENDING"
    if result.returncode != 0:
        return "PENDING"
    stdout = result.stdout
    commit = (
        stdout.decode("utf-8", errors="replace").strip()
        if isinstance(stdout, bytes)
        else stdout.strip()
    )
    return commit if re.fullmatch(r"[0-9a-fA-F]{40,64}", commit) else "PENDING"


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, list | tuple):
        return tuple(_freeze_value(item) for item in value)
    return value


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType({key: _freeze_value(item) for key, item in value.items()})
