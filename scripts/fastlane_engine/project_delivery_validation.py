"""Pure task-command validation against Design and construction boundaries."""

from __future__ import annotations

from collections.abc import Sequence

from .design import (
    Design8Extension,
    command_matches_prefix,
    dependency_command_allowed,
    is_dependency_acquisition_command,
    validation_commands,
)


def task_command_boundary_issues(
    task_id: str,
    validation_text: str,
    command_prefixes: Sequence[str],
    design_schema_version: int,
    design_extension: Design8Extension,
) -> list[tuple[str, str]]:
    """Return ordered command-prefix and dependency-acquisition diagnostics."""

    issues: list[tuple[str, str]] = []
    try:
        commands = validation_commands(validation_text, task_id)
    except ValueError as exc:
        return [("TASK_COMMAND_BOUNDARY", str(exc))]
    for command in commands:
        if not any(
            command_matches_prefix(command, prefix) for prefix in command_prefixes
        ):
            issues.append(
                (
                    "TASK_COMMAND_BOUNDARY",
                    f"{task_id} command {command!r} is outside AUTH",
                )
            )
        if (
            design_schema_version >= 8
            and is_dependency_acquisition_command(command)
            and not dependency_command_allowed(design_extension, command)
        ):
            issues.append(
                (
                    "TASK_DEPENDENCY_ACQUISITION_BOUNDARY",
                    f"{task_id} command {command!r} is not an exact current "
                    "Design 8 dependency-policy addition; an allowed local command "
                    "prefix cannot override dependency denial",
                )
            )
    return issues


__all__ = ("task_command_boundary_issues",)
