"""Bounded, immutable, single-observation project snapshots.

Canonical inputs are repository-relative regular files observed from one root.
The observer returns frozen file and Markdown snapshots. It performs bounded
read-only filesystem access only; it never writes, invokes Git/subprocesses,
accesses a network, validates lifecycle state, or grants authority.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from .digests import lf_normalized_text, sha256_hex
from .ids import validate_relative_path
from .markdown_index import MarkdownDocumentIndex


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
class GitSnapshot:
    executable: str | None = None
    root: str | None = None
    branch: str | None = None
    head: str | None = None
    baseline: str | None = None
    tracked_changes: tuple[str, ...] = ()
    staged_changes: tuple[str, ...] = ()
    untracked_paths: tuple[str, ...] = ()
    protected_dirty_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class ObservationMetrics:
    files_opened: int
    bytes_observed: int
    markdown_indexes: int


@dataclass(frozen=True)
class ProjectSnapshot:
    observed_at: datetime
    root: Path
    project_identity: Mapping[str, str]
    files: Mapping[str, FileSnapshot]
    markdown: Mapping[str, MarkdownDocumentIndex]
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
            git=git or GitSnapshot(root=str(self.root)),
            bootstrap_state=_freeze_mapping(bootstrap_state or {}),
            manifest=_freeze_mapping(manifest or {}),
            observation_metrics=ObservationMetrics(
                files_opened=len(self._files),
                bytes_observed=self._bytes_observed,
                markdown_indexes=len(self._markdown),
            ),
        )


def has_symlink_component(root: Path, relative: str) -> bool:
    current = root
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, list | tuple):
        return tuple(_freeze_value(item) for item in value)
    return value


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType({key: _freeze_value(item) for key, item in value.items()})
