"""Optional post-Gate-B architecture-board contracts and validation.

The module consumes immutable Engine reports and bounded snapshots. It performs
no project mutation, subprocess execution, network or AWS access, approval, or
authority expansion.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from ..core.contracts import path_boundaries_overlap, path_boundary_contains
from ..core.snapshot import ProjectSnapshot
from .architecture_board_validation import (
    _markdown_bytes as _validated_markdown_bytes,
    _mermaid_edge_matches,
    _png_dimensions,
    _png_rgba,
    _rgba_crop,
    _validate_actual_xml,
)

ARCHITECTURE_DIAGRAM_SKILL_IDENTITY = {
    "name": "aws-architecture-diagrams",
    "version": "1.3.1",
    "contract_id": "aws-architecture-diagrams/v1.3",
    "source_model_schema_version": 2,
    "tree_sha256": "sha256:3482ba7a5cb5f8b9db12f4eb25700f257e04f5fedb50eb2c8d64d5ff00062977",
    "release_sha256": "sha256:ffa17e5905bfb83ce7b302894760745b192a625eafa7ea7261613df9a0134d4",
}
ARCHITECTURE_BOARD_OWNER_REQUEST = "Generate the planned AWS architecture board."
ARCHITECTURE_BOARD_QA_TILES = tuple(
    f"qa-tiles/qa-{sequence:02d}-r{row}-c{column}.png"
    for sequence, (row, column) in enumerate(
        ((row, column) for row in range(1, 4) for column in range(1, 5)),
        start=1,
    )
)
ARCHITECTURE_BOARD_REQUIRED_OUTPUTS = (
    "architecture-board.drawio",
    "architecture-board.svg",
    "architecture-board.png",
    "architecture-board.mmd",
    "architecture-board.md",
    "architecture-board-manifest.json",
    "architecture-board-validation.json",
    "architecture-board-render.json",
    "visual-review-receipt.json",
    "qa-tiles/qa-tiles-manifest.json",
    *ARCHITECTURE_BOARD_QA_TILES,
)
_ARCHITECTURE_BOARD_VALIDATION_CHECKS = frozenset(
    {
        "xml_documents",
        "source_model",
        "artifact_bindings",
        "canvas_svg",
        "canvas_png",
        "visible_arrowheads",
        "unique_arrowhead_endpoints",
        "nonoverlapping_terminal_segments",
        "svg_layer_order",
        "svg_text_above_connectors",
        "opaque_svg_edge_label_masks",
        "drawio_text_above_connectors",
        "drawio_connector_labels_separate",
        "boundary_label_clearance",
        "boundary_anchor_clearance",
        "embedded_official_icons",
        "flow_note_count",
        "planned_disclaimer",
        "render_receipt",
        "render_reproduced",
    }
)
_ARCHITECTURE_BOARD_VISUAL_CHECKS = frozenset(
    {
        "text_clear",
        "connectors_clear",
        "arrowheads_clear",
        "labels_above_connectors",
        "boundary_label_masks_clear",
        "boundary_anchors_clear",
        "boundaries_clear",
        "callouts_match_notes",
    }
)

_BOARD_SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
_BOARD_RECORDS = {
    "DIAGRAM-0001": ("SYSTEM_CONTEXT", "proposed-system-at-a-glance"),
    "DIAGRAM-0008": ("AWS_IMPLEMENTATION", "aws-implementation-at-a-glance"),
}


def _architecture_board_record(
    diagrams: Mapping[str, Any], diagram_id: str
) -> dict[str, Any] | None:
    rows = [
        row
        for row in diagrams.get("records", [])
        if isinstance(row, Mapping) and row.get("diagram_id") == diagram_id
    ]
    if len(rows) != 1:
        return None
    row = rows[0]
    kind, anchor = _BOARD_RECORDS[diagram_id]
    valid = (
        row.get("kind") == kind
        and row.get("applicability") == "REQUIRED"
        and row.get("status") == "CURRENT"
        and row.get("anchor") == anchor
        and isinstance(row.get("relationships"), list)
        and bool(row["relationships"])
        and all(isinstance(edge, Mapping) for edge in row["relationships"])
        and all(
            _BOARD_SHA256.fullmatch(str(row.get(key, "")))
            for key in ("semantic_sha256", "rendered_sha256")
        )
    )
    return dict(row) if valid else None


def _architecture_board_report_current(
    report: Mapping[str, Any], parts: tuple[Any, ...]
) -> bool:
    if not all(isinstance(item, Mapping) for item in parts):
        return False
    gates, design, project, diagrams, authority, auth, external = parts
    return bool(
        report.get("schema_version") == 2
        and report.get("ok") is True
        and gates.get("gate_a") == "APPROVED_FOR_DESIGN"
        and gates.get("gate_b") == "APPROVED_FOR_CONSTRUCTION"
        and design.get("schema_version") == project.get("schema_version") == 7
        and design.get("status") == project.get("status") == "READY"
        and not any(project.get(f"grandfathered_v{version}") for version in (4, 5, 6))
        and diagrams.get("status") == "CURRENT"
        and diagrams.get("grandfathered_schema5") is False
        and authority.get("valid") is True
        and authority.get("active_task") == "NONE"
        and authority.get("authorization_id") == auth.get("construction")
        and auth.get("construction") != "NONE"
        and auth.get("aws") == "NONE"
        and external.get("kind") == external.get("validity") == "NONE"
    )


def _architecture_board_conflict(
    diagrams: Mapping[str, Any] | None,
    primary: Mapping[str, Any] | None,
    cross_check: Mapping[str, Any] | None,
) -> bool:
    if diagrams is None or primary is None or cross_check is None:
        return False

    primary_edges = {(e["from_id"], e["to_id"]) for e in primary["relationships"]}
    cross_edges = {(e["from_id"], e["to_id"]) for e in cross_check["relationships"]}

    def reaches(source: str, target: str) -> bool:
        frontier = {right for left, right in primary_edges if left == source}
        for _ in primary.get("referenced_ids", []):
            frontier |= {right for left, right in primary_edges if left in frontier}
        return target in frontier

    basis = diagrams.get("architecture_basis_id")
    return bool(
        basis not in primary.get("basis_ids", [])
        or basis not in cross_check.get("basis_ids", [])
        or not set(cross_check.get("referenced_ids", [])).issubset(
            primary.get("referenced_ids", [])
        )
        or any(not reaches(source, target) for source, target in cross_edges)
    )


def _architecture_board_output(
    design: Mapping[str, Any] | None,
    primary: Mapping[str, Any] | None,
    authority: Mapping[str, Any] | None,
) -> tuple[str | None, str | None, bool]:
    revision = str(design.get("design_revision", "")) if design else ""
    semantic = str(primary.get("semantic_sha256", "")) if primary else ""
    root = (
        f"dist/architecture/{revision}-{semantic[7:]}"
        if re.fullmatch(r"DES-\d{4,}", revision) and _BOARD_SHA256.fullmatch(semantic)
        else None
    )
    boundary = f"{root}/**" if root else None
    roots = authority.get("approved_write_roots", []) if authority else []
    blocked = [
        *(authority.get("exclusions", []) if authority else []),
        *(authority.get("protected_paths", []) if authority else []),
    ]
    authorized = bool(
        boundary
        and all(isinstance(path, str) for path in [*roots, *blocked])
        and any(path_boundary_contains(path, boundary) for path in roots)
        and not any(path_boundaries_overlap(path, boundary) for path in blocked)
    )
    return root, boundary, authorized


def derive_architecture_board_handoff(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return the request-scoped planned-board capability; never infer a plugin."""

    gates, design = report.get("gates"), report.get("design_contract")
    project = design.get("project_contract") if isinstance(design, Mapping) else None
    diagrams = design.get("diagram_contract") if isinstance(design, Mapping) else None
    authority, auth = report.get("write_authority"), report.get("authorizations")
    external = report.get("external_authority")
    parts = (gates, design, project, diagrams, authority, auth, external)
    current = _architecture_board_report_current(report, parts)
    if isinstance(diagrams, Mapping):
        primary = _architecture_board_record(diagrams, "DIAGRAM-0001")
        cross_check = _architecture_board_record(diagrams, "DIAGRAM-0008")
    else:
        primary = cross_check = None
    conflict = _architecture_board_conflict(diagrams, primary, cross_check)
    root, boundary, authorized = _architecture_board_output(
        design if isinstance(design, Mapping) else None,
        primary,
        authority if isinstance(authority, Mapping) else None,
    )
    issues = [
        *([] if current else ["CURRENT_GATE_B_REQUIRED"]),
        *([] if primary else ["SYSTEM_CONTEXT_DIAGRAM_REQUIRED"]),
        *([] if cross_check else ["AWS_IMPLEMENTATION_DIAGRAM_REQUIRED"]),
        *(["DIAGRAM_CROSS_CHECK_CONFLICT"] if conflict else []),
        *([] if root else ["DIAGRAM_OUTPUT_IDENTITY_INVALID"]),
        *([] if authorized else ["DIAGRAM_OUTPUT_NOT_AUTHORIZED"]),
    ]
    status = (
        "SEMANTIC_CONFLICT" if conflict else ("ELIGIBLE", "INELIGIBLE")[bool(issues)]
    )
    return {
        "status": status,
        "eligible": not issues,
        "issues": issues,
        "source_path": "docs/project/PRD.md",
        "source": primary,
        "cross_check": cross_check,
        "output_root": root,
        "failure_route": "DESIGN-10" if conflict else None,
        "aws_authority": "NONE",
        "external_authority": "NONE",
    }


def architecture_board_mermaid_source(text: str, handoff: Mapping[str, Any]) -> str:
    from .diagrams import _canonical_mermaid_block

    source = handoff.get("source")
    if handoff.get("eligible") is not True or not isinstance(source, Mapping):
        raise ValueError("architecture board handoff is not eligible")
    rendered_bytes, rendered = _canonical_mermaid_block(text, str(source.get("anchor")))
    observed = "sha256:" + hashlib.sha256(rendered_bytes).hexdigest()
    if observed != source.get("rendered_sha256"):
        raise ValueError("approved Mermaid presentation digest changed")
    return rendered.removeprefix("```mermaid\n").removesuffix("```\n")


def _architecture_board_request_manifest(
    handoff: Mapping[str, Any],
    design: Mapping[str, Any],
    project: Mapping[str, Any],
    construction: str,
    mermaid_path: str,
    mermaid_sha256: str,
    source_model_path: str,
) -> dict[str, Any]:
    source, cross_check = handoff["source"], handoff["cross_check"]
    output_root = str(handoff["output_root"])
    return {
        "schema_version": 1,
        "kind": "FASTLANE_ARCHITECTURE_BOARD_REQUEST",
        "request": ARCHITECTURE_BOARD_OWNER_REQUEST,
        "status": "CURRENT",
        "architecture_status": "PLANNED",
        "project": {"name": project.get("name"), "region": project.get("region")},
        "lifecycle": {"route": "TASK-10", "resume_route": "TASK-10"},
        "authority": {
            "construction_authorization_id": construction,
            "permitted_output_boundary": f"{output_root}/**",
            "aws": "NONE",
            "external": "NONE",
        },
        "design": {
            "revision": design.get("design_revision"),
            "canonical_sha256": design.get("canonical_sha256"),
        },
        "approved_mermaid": {
            "prd_path": handoff.get("source_path"),
            "anchor": source.get("anchor"),
            "diagram_id": source.get("diagram_id"),
            "semantic_sha256": source.get("semantic_sha256"),
            "rendered_sha256": source.get("rendered_sha256"),
            "target_path": mermaid_path,
            "sha256": mermaid_sha256,
        },
        "mandatory_cross_check": {
            "diagram_id": cross_check.get("diagram_id"),
            "semantic_sha256": cross_check.get("semantic_sha256"),
            "rendered_sha256": cross_check.get("rendered_sha256"),
        },
        "source_model": {
            "mode": "NEW_DERIVATION",
            "state": "PENDING_DERIVATION",
            "schema_version": 2,
            "target_path": source_model_path,
            "target_must_be_absent": True,
        },
        "skill": dict(ARCHITECTURE_DIAGRAM_SKILL_IDENTITY),
        "output": {
            "directory": output_root,
            "required": list(ARCHITECTURE_BOARD_REQUIRED_OUTPUTS),
        },
    }


def derive_architecture_board_request_packet(
    report: Mapping[str, Any],
    prd_text: str,
    skill_identity: Mapping[str, Any],
    *,
    owner_request: str,
    source_model_target_exists: bool,
) -> dict[str, Any]:
    """Derive one local DIAGRAM-10 request packet without writing project state."""

    expected_identity = {
        **ARCHITECTURE_DIAGRAM_SKILL_IDENTITY,
        "valid": True,
        "issues": [],
    }
    if owner_request != ARCHITECTURE_BOARD_OWNER_REQUEST:
        raise ValueError("architecture board requires the exact owner request")
    if dict(skill_identity) != expected_identity:
        raise ValueError("architecture diagram skill identity is not current")
    if source_model_target_exists is not False:
        raise ValueError("NEW_DERIVATION requires an absent source-model target")

    handoff = derive_architecture_board_handoff(report)
    interaction = report.get("interaction")
    if (
        handoff.get("eligible") is not True
        or report.get("next_prompt") != "TASK-10"
        or not isinstance(interaction, Mapping)
        or interaction.get("owner_action_required") is not False
        or interaction.get("automatic_continuation_allowed") is not True
    ):
        raise ValueError("architecture board request is not currently eligible")

    design = report.get("design_contract")
    authorizations = report.get("authorizations")
    project = report.get("project")
    source, cross_check = handoff.get("source"), handoff.get("cross_check")
    if not all(
        isinstance(item, Mapping)
        for item in (design, authorizations, project, source, cross_check)
    ):
        raise ValueError("architecture board request evidence is malformed")
    if any(
        not isinstance(project.get(field), str) or not project[field].strip()
        for field in ("name", "region")
    ):
        raise ValueError("architecture board project identity is malformed")
    construction = str(authorizations.get("construction", ""))
    if not _BOARD_SHA256.fullmatch(
        str(design.get("canonical_sha256", ""))
    ) or not re.fullmatch(r"AUTH-\d{4,}", construction):
        raise ValueError("architecture board authority binding is malformed")

    output_root = str(handoff["output_root"])
    manifest_path = f"{output_root}/architecture-board-task-manifest.json"
    mermaid_path = f"{output_root}/architecture-source.mmd"
    source_model_path = f"{output_root}/source-model.json"
    mermaid_text = architecture_board_mermaid_source(prd_text, handoff)
    mermaid_sha256 = (
        "sha256:" + hashlib.sha256(mermaid_text.encode("utf-8")).hexdigest()
    )
    manifest = _architecture_board_request_manifest(
        handoff,
        design,
        project,
        construction,
        mermaid_path,
        mermaid_sha256,
        source_model_path,
    )
    return {
        "status": "READY",
        "manifest_path": manifest_path,
        "manifest": manifest,
        "manifest_text": json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        "mermaid_path": mermaid_path,
        "mermaid_text": mermaid_text,
        "source_model_path": source_model_path,
        "resume_route": "TASK-10",
        "aws_authority": "NONE",
        "external_authority": "NONE",
    }


def architecture_board_completion_digest(completion: Mapping[str, Any]) -> str:
    """Bind one snapshot-derived DIAGRAM-10 completion projection."""

    bound = {
        key: value for key, value in completion.items() if key != "canonical_sha256"
    }
    canonical = json.dumps(bound, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _sha256(raw: bytes, *, prefixed: bool = True) -> str:
    digest = hashlib.sha256(raw).hexdigest()
    return "sha256:" + digest if prefixed else digest


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _object(value: object, keys: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError(f"architecture board {label} schema is invalid")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"architecture board {label} is invalid")
    return value.strip()


def _strings(
    value: object, label: str, *, allow_empty: bool = True
) -> list[str]:
    if (
        not isinstance(value, list)
        or (not allow_empty and not value)
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise ValueError(f"architecture board {label} is invalid")
    rows = [item.strip() for item in value]
    if len(rows) != len(set(rows)):
        raise ValueError(f"architecture board {label} contains duplicates")
    return rows


def _sha_value(value: object, label: str, *, prefixed: bool = True) -> str:
    text = _text(value, label)
    pattern = r"sha256:[0-9a-f]{64}" if prefixed else r"[0-9a-f]{64}"
    if re.fullmatch(pattern, text) is None:
        raise ValueError(f"architecture board {label} digest is invalid")
    return text


def _safe_relative_path(value: object, label: str) -> str:
    text = _text(value, label).replace("\\", "/")
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or path.as_posix() != text
        or any(part in {"", ".", ".."} for part in path.parts)
        or ":" in path.parts[0]
    ):
        raise ValueError(f"architecture board {label} path is invalid")
    return text


def _architecture_board_expected_paths(packet: Mapping[str, Any]) -> frozenset[str]:
    manifest = packet.get("manifest")
    output = manifest.get("output") if isinstance(manifest, Mapping) else None
    if not isinstance(output, Mapping):
        raise ValueError("architecture board request packet is not current")
    output_root = _safe_relative_path(output.get("directory"), "output")
    paths = {
        _safe_relative_path(packet.get("manifest_path"), "manifest"),
        _safe_relative_path(packet.get("mermaid_path"), "Mermaid"),
        _safe_relative_path(packet.get("source_model_path"), "source model"),
        *(f"{output_root}/{relative}" for relative in ARCHITECTURE_BOARD_REQUIRED_OUTPUTS),
    }
    if len(paths) != 25 or any(
        not path.startswith(output_root + "/") for path in paths
    ):
        raise ValueError("architecture board request artifact set is invalid")
    return frozenset(paths)


def _validated_request_context(
    report: Mapping[str, Any], packet: Mapping[str, Any]
) -> dict[str, Any]:
    packet_keys = {
        "status",
        "manifest_path",
        "manifest",
        "manifest_text",
        "mermaid_path",
        "mermaid_text",
        "source_model_path",
        "resume_route",
        "aws_authority",
        "external_authority",
    }
    manifest = packet.get("manifest")
    handoff = derive_architecture_board_handoff(report)
    design = report.get("design_contract")
    project = report.get("project")
    authorizations = report.get("authorizations")
    interaction = report.get("interaction")
    if (
        set(packet) != packet_keys
        or packet.get("status") != "READY"
        or packet.get("resume_route") != "TASK-10"
        or packet.get("aws_authority") != "NONE"
        or packet.get("external_authority") != "NONE"
        or report.get("next_prompt") != "TASK-10"
        or handoff.get("eligible") is not True
        or not all(
            isinstance(item, Mapping)
            for item in (manifest, design, project, authorizations, interaction)
        )
        or interaction.get("owner_action_required") is not False
        or interaction.get("automatic_continuation_allowed") is not True
    ):
        raise ValueError("architecture board request packet is not current")
    output_root = str(handoff.get("output_root", ""))
    manifest_path = f"{output_root}/architecture-board-task-manifest.json"
    mermaid_path = f"{output_root}/architecture-source.mmd"
    source_model_path = f"{output_root}/source-model.json"
    mermaid_text = packet.get("mermaid_text")
    construction = str(authorizations.get("construction", ""))
    if (
        re.fullmatch(r"dist/architecture/DES-\d{4,}-[0-9a-f]{64}", output_root)
        is None
        or packet.get("manifest_path") != manifest_path
        or packet.get("mermaid_path") != mermaid_path
        or packet.get("source_model_path") != source_model_path
        or not isinstance(mermaid_text, str)
        or not mermaid_text
        or "\x00" in mermaid_text
        or not re.fullmatch(r"AUTH-\d{4,}", construction)
    ):
        raise ValueError("architecture board request packet is stale")
    mermaid_raw = mermaid_text.encode("utf-8")
    mermaid_sha = _sha256(mermaid_raw)
    expected_manifest = _architecture_board_request_manifest(
        handoff,
        design,
        project,
        construction,
        mermaid_path,
        mermaid_sha,
        source_model_path,
    )
    source = handoff.get("source")
    fenced = b"\x60\x60\x60mermaid\n" + mermaid_raw + b"\x60\x60\x60\n"
    if (
        dict(manifest) != expected_manifest
        or packet.get("manifest_text")
        != json.dumps(expected_manifest, indent=2, sort_keys=True) + "\n"
        or not isinstance(source, Mapping)
        or _sha256(fenced) != source.get("rendered_sha256")
    ):
        raise ValueError("architecture board request packet is stale")
    return {
        "handoff": handoff,
        "manifest": expected_manifest,
        "output_root": output_root,
        "mermaid_raw": mermaid_raw,
        "mermaid_sha": mermaid_sha,
        "paths": _architecture_board_expected_paths(packet),
    }


def _snapshot_artifacts(
    snapshot: ProjectSnapshot, expected_paths: frozenset[str]
) -> dict[str, str]:
    if (
        set(snapshot.files) != set(expected_paths)
        or snapshot.observation_metrics.files_opened != len(expected_paths)
    ):
        raise ValueError("architecture board completion observation is incomplete")
    return {
        path: "sha256:" + snapshot.files[path].byte_sha256
        for path in sorted(expected_paths)
    }


def _json_document(snapshot: ProjectSnapshot, path: str) -> Mapping[str, Any]:
    observed = snapshot.file(path)
    if observed is None or b"\x00" in observed.raw_bytes:
        raise ValueError("architecture board completion artifact is missing")
    try:
        value = json.loads(observed.raw_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("architecture board completion JSON is malformed") from exc
    if not isinstance(value, Mapping):
        raise ValueError("architecture board completion JSON is malformed")
    return value


def _validate_icon_package(model: Mapping[str, Any]) -> Mapping[str, Any]:
    package = _object(
        model.get("icon_package"),
        {"assets", "name", "release", "source"},
        "icon package",
    )
    name = _text(package.get("name"), "icon package name")
    release = _text(package.get("release"), "icon package release")
    source = _text(package.get("source"), "icon package source")
    if (
        not name.startswith("AWS Architecture Icons ")
        or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", release)
        or source != "AWS Architecture Icons"
    ):
        raise ValueError("architecture board icon package identity is invalid")
    assets = package.get("assets")
    if not isinstance(assets, Mapping) or not assets:
        raise ValueError("architecture board icon package assets are invalid")
    for key, digest in assets.items():
        _text(key, "icon key")
        _sha_value(digest, f"icon {key}")
    return package


def _validate_render_contract(model: Mapping[str, Any]) -> Mapping[str, Any]:
    contract = _object(
        model.get("render_contract"),
        {
            "boundary_anchors",
            "canvas",
            "drawio_presentation_sha256",
            "svg_layer_order",
            "svg_presentation_sha256",
        },
        "render contract",
    )
    canvas = _object(contract.get("canvas"), {"height", "width"}, "canvas")
    if any(
        isinstance(canvas.get(key), bool)
        or not isinstance(canvas.get(key), int)
        or int(canvas[key]) <= 0
        for key in ("width", "height")
    ):
        raise ValueError("architecture board canvas is invalid")
    layers = _strings(
        contract.get("svg_layer_order"), "SVG layer order", allow_empty=False
    )
    expected_layers = [
        "background",
        "boundary-shapes",
        "edge-paths",
        "boundary-labels",
        "outer-labels",
        "nodes",
        "edge-labels",
        "annotations",
    ]
    if layers != expected_layers:
        raise ValueError("architecture board SVG layer order is invalid")
    _sha_value(contract.get("svg_presentation_sha256"), "SVG presentation")
    _sha_value(contract.get("drawio_presentation_sha256"), "Draw.io presentation")
    anchors = contract.get("boundary_anchors")
    if not isinstance(anchors, list):
        raise ValueError("architecture board boundary anchors are invalid")
    for row in anchors:
        anchor = _object(
            row,
            {"boundary", "clearance", "edge", "endpoint", "side"},
            "boundary anchor",
        )
        if (
            not isinstance(anchor.get("clearance"), int)
            or isinstance(anchor.get("clearance"), bool)
            or int(anchor["clearance"]) < 0
            or anchor.get("endpoint") not in {"start", "end"}
            or anchor.get("side") not in {"top", "right", "bottom", "left"}
        ):
            raise ValueError("architecture board boundary anchor is invalid")
        _text(anchor.get("boundary"), "boundary anchor boundary")
        _text(anchor.get("edge"), "boundary anchor edge")
    return contract


def _validate_boundary_geometry(
    row: Mapping[str, Any], canvas: Mapping[str, Any]
) -> None:
    if not row["rendered"]:
        if row.get("geometry") is not None or row.get("title_size") is not None:
            raise ValueError("architecture board non-rendered boundary is invalid")
        return
    geometry = _object(
        row.get("geometry"), {"height", "width", "x", "y"}, "boundary geometry"
    )
    values = [geometry.get(key) for key in ("x", "y", "width", "height")]
    invalid = (
        any(isinstance(item, bool) or not isinstance(item, int) for item in values)
        or min(int(item) for item in values) < 0
        or int(geometry["width"]) <= 0
        or int(geometry["height"]) <= 0
        or int(geometry["x"]) + int(geometry["width"]) > int(canvas["width"])
        or int(geometry["y"]) + int(geometry["height"]) > int(canvas["height"])
        or not isinstance(row.get("title_size"), int)
        or isinstance(row.get("title_size"), bool)
        or int(row["title_size"]) <= 0
    )
    if invalid:
        raise ValueError("architecture board boundary geometry is invalid")


def _validated_boundary_row(
    value: object, icons: Mapping[str, Any], canvas: Mapping[str, Any]
) -> tuple[str, Mapping[str, Any]]:
    row = _object(
        value,
        {
            "boundary_type",
            "dashed",
            "fill_color",
            "geometry",
            "icon_key",
            "id",
            "parent",
            "rendered",
            "stroke_color",
            "subtitle",
            "title",
            "title_size",
        },
        "boundary",
    )
    boundary_id = _text(row.get("id"), "boundary id")
    if not isinstance(row.get("rendered"), bool):
        raise ValueError("architecture board boundary identity is invalid")
    if row.get("icon_key") is not None and row.get("icon_key") not in icons["assets"]:
        raise ValueError("architecture board boundary icon is invalid")
    _validate_boundary_geometry(row, canvas)
    return boundary_id, row


def _validate_boundary_parents(
    result: Mapping[str, Mapping[str, Any]],
) -> None:
    for boundary_id, row in result.items():
        parent = row.get("parent")
        if parent is not None and parent not in result:
            raise ValueError("architecture board boundary parent is invalid")
        seen = {boundary_id}
        while parent is not None:
            if parent in seen:
                raise ValueError("architecture board boundary parent cycle exists")
            seen.add(str(parent))
            parent = result[str(parent)].get("parent")


def _validate_boundaries(
    model: Mapping[str, Any],
    icons: Mapping[str, Any],
    canvas: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    rows = model.get("boundaries")
    if not isinstance(rows, list) or not rows:
        raise ValueError("architecture board boundaries are invalid")
    result: dict[str, Mapping[str, Any]] = {}
    for value in rows:
        boundary_id, row = _validated_boundary_row(value, icons, canvas)
        if boundary_id in result:
            raise ValueError("architecture board boundary identity is invalid")
        result[boundary_id] = row
    _validate_boundary_parents(result)
    return result


def _validate_components(
    model: Mapping[str, Any],
    boundaries: Mapping[str, Mapping[str, Any]],
    icons: Mapping[str, Any],
    canvas: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    rows = model.get("components")
    if not isinstance(rows, list) or not rows:
        raise ValueError("architecture board components are invalid")
    result: dict[str, Mapping[str, Any]] = {}
    semantics: set[str] = set()
    for value in rows:
        row = _object(
            value,
            {
                "boundary",
                "component_class",
                "icon_key",
                "label",
                "qualifiers",
                "mermaid_label",
                "record_id",
                "render_geometry",
                "render_purpose",
                "render_title",
                "scope",
                "semantic_key",
            },
            "component",
        )
        record_id = _text(row.get("record_id"), "component record")
        semantic = _text(row.get("semantic_key"), "component semantic key")
        geometry = _object(
            row.get("render_geometry"), {"size", "x", "y"}, "component geometry"
        )
        values = [geometry.get(key) for key in ("x", "y", "size")]
        if (
            record_id in result
            or semantic in semantics
            or row.get("boundary") not in boundaries
            or row.get("icon_key") not in icons["assets"]
            or any(isinstance(item, bool) or not isinstance(item, int) for item in values)
            or min(int(item) for item in values) < 0
            or int(geometry["size"]) <= 0
            or int(geometry["x"]) + int(geometry["size"]) > int(canvas["width"])
            or int(geometry["y"]) + int(geometry["size"]) > int(canvas["height"])
        ):
            raise ValueError("architecture board component identity is invalid")
        _strings(row.get("qualifiers"), "component qualifiers")
        _strings(row.get("render_purpose"), "component purpose", allow_empty=False)
        _strings(row.get("render_title"), "component title", allow_empty=False)
        result[record_id] = row
        semantics.add(semantic)
    return result


def _validate_relationships(
    model: Mapping[str, Any], components: Mapping[str, Mapping[str, Any]]
) -> dict[str, Mapping[str, Any]]:
    rows = model.get("relationships")
    allowed = {
        "alert",
        "data",
        "event",
        "failure",
        "plan-only",
        "publication",
        "request",
        "schedule",
        "telemetry",
        "trust",
    }
    if not isinstance(rows, list) or not rows:
        raise ValueError("architecture board relationships are invalid")
    result: dict[str, Mapping[str, Any]] = {}
    semantics: set[tuple[str, str, str]] = set()
    for value in rows:
        row = _object(
            value,
            {
                "cadence",
                "class",
                "failure",
                "id",
                "security",
                "source_id",
                "source_text",
                "target_id",
            },
            "relationship",
        )
        relationship_id = _text(row.get("id"), "relationship id")
        semantic = (
            str(row.get("source_id")),
            str(row.get("source_text")),
            str(row.get("target_id")),
        )
        if (
            relationship_id in result
            or semantic in semantics
            or row.get("source_id") not in components
            or row.get("target_id") not in components
            or row.get("class") not in allowed
        ):
            raise ValueError("architecture board relationship identity is invalid")
        _strings(row.get("security"), "relationship security")
        result[relationship_id] = row
        semantics.add(semantic)
    return result


def _validated_edge_style(row: Mapping[str, Any]) -> str:
    representation = row.get("representation")
    expected_arrow = "BOTH" if representation == "BIDIRECTIONAL" else "FORWARD"
    invalid = (
        representation not in {"DIRECT", "BIDIRECTIONAL", "AGGREGATED"}
        or row.get("arrow_mode") != expected_arrow
        or not isinstance(row.get("dashed"), bool)
        or isinstance(row.get("stroke_width"), bool)
        or not isinstance(row.get("stroke_width"), (int, float))
        or float(row["stroke_width"]) <= 0
    )
    if invalid:
        raise ValueError("architecture board presentation edge is invalid")
    return str(representation)


def _validate_edge_cardinality(
    representation: str, selected: list[Mapping[str, Any]]
) -> None:
    if representation == "DIRECT" and len(selected) != 1:
        raise ValueError("architecture board direct edge cardinality is invalid")
    if representation == "BIDIRECTIONAL" and (
        len(selected) != 2
        or selected[0]["source_id"] != selected[1]["target_id"]
        or selected[0]["target_id"] != selected[1]["source_id"]
    ):
        raise ValueError("architecture board bidirectional edge is invalid")
    if representation == "AGGREGATED" and len(selected) < 2:
        raise ValueError("architecture board aggregated edge is invalid")


def _validated_edge_points(
    row: Mapping[str, Any], canvas: Mapping[str, Any]
) -> list[list[int | float]]:
    points = row.get("points")
    if not isinstance(points, list) or len(points) < 2:
        raise ValueError("architecture board presentation edge points are invalid")
    for point in points:
        if (
            not isinstance(point, list)
            or len(point) != 2
            or any(
                isinstance(item, bool) or not isinstance(item, (int, float))
                for item in point
            )
            or not 0 <= float(point[0]) <= int(canvas["width"])
            or not 0 <= float(point[1]) <= int(canvas["height"])
        ):
            raise ValueError("architecture board presentation edge route is invalid")
    if any(
        first[0] != second[0] and first[1] != second[1]
        for first, second in zip(points, points[1:])
    ):
        raise ValueError("architecture board presentation edge route is invalid")
    return points


def _validate_direct_terminals(
    representation: str,
    source_terminal: object,
    target_terminal: object,
    sources: list[str],
    targets: list[str],
) -> None:
    if representation == "DIRECT" and (
        source_terminal != sources[0] or target_terminal != targets[0]
    ):
        raise ValueError("architecture board direct edge terminals are invalid")


def _validate_presentation_edge(
    value: object,
    relationships: Mapping[str, Mapping[str, Any]],
    canvas: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    row = _object(
        value,
        {
            "arrow_mode",
            "dashed",
            "id",
            "label_at",
            "points",
            "relationship_ids",
            "representation",
            "source_terminal",
            "stroke_color",
            "stroke_width",
            "target_terminal",
            "visible_label",
        },
        "presentation edge",
    )
    edge_id = _text(row.get("id"), "presentation edge id")
    relationship_ids = _strings(
        row.get("relationship_ids"), "presentation relationships", allow_empty=False
    )
    selected = [relationships[item] for item in relationship_ids if item in relationships]
    if len(selected) != len(relationship_ids):
        raise ValueError("architecture board presentation references unknown relationships")
    representation = _validated_edge_style(row)
    _validate_edge_cardinality(representation, selected)
    _validated_edge_points(row, canvas)
    label_at = row.get("label_at")
    if (
        not isinstance(label_at, list)
        or len(label_at) != 2
        or any(
            isinstance(item, bool) or not isinstance(item, (int, float))
            for item in label_at
        )
        or not 0 <= float(label_at[0]) <= int(canvas["width"])
        or not 0 <= float(label_at[1]) <= int(canvas["height"])
    ):
        raise ValueError("architecture board presentation edge label is invalid")
    sources = sorted({str(item["source_id"]) for item in selected})
    targets = sorted({str(item["target_id"]) for item in selected})
    source_terminal = row.get("source_terminal")
    target_terminal = row.get("target_terminal")
    _validate_direct_terminals(
        representation, source_terminal, target_terminal, sources, targets
    )
    projection = {
        "id": edge_id,
        "representation": representation,
        "source_relationship_ids": relationship_ids,
        "source_records": sources,
        "target_records": targets,
        "source_terminal_record": source_terminal,
        "target_terminal_record": target_terminal,
        "visible_label": row.get("visible_label"),
        "arrow_mode": row.get("arrow_mode"),
        "stroke_color": row.get("stroke_color"),
        "stroke_width": row.get("stroke_width"),
        "dashed": row.get("dashed"),
        "points": row.get("points"),
        "label_at": row.get("label_at"),
    }
    return projection, relationship_ids


def _validate_presentation(
    model: Mapping[str, Any],
    relationships: Mapping[str, Mapping[str, Any]],
    canvas: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    presentation = _object(model.get("presentation"), {"edges", "notes"}, "presentation")
    values = presentation.get("edges")
    notes = presentation.get("notes")
    if not isinstance(values, list) or not isinstance(notes, list) or not 6 <= len(notes) <= 10:
        raise ValueError("architecture board presentation is invalid")
    edges: list[dict[str, Any]] = []
    covered: set[str] = set()
    edge_ids: set[str] = set()
    for value in values:
        edge, ids = _validate_presentation_edge(value, relationships, canvas)
        if edge["id"] in edge_ids or covered.intersection(ids):
            raise ValueError("architecture board presentation coverage is invalid")
        edge_ids.add(str(edge["id"]))
        covered.update(ids)
        edges.append(edge)
    note_rows: list[dict[str, Any]] = []
    for step, value in enumerate(notes, start=1):
        row = _object(
            value, {"body", "relationship_ids", "step", "title"}, "presentation note"
        )
        ids = _strings(row.get("relationship_ids"), "note relationships")
        if row.get("step") != step or any(item not in relationships for item in ids):
            raise ValueError("architecture board presentation note is invalid")
        _text(row.get("title"), "note title")
        _text(row.get("body"), "note body")
        if covered.intersection(ids):
            raise ValueError("architecture board relationship is multiply covered")
        covered.update(ids)
        if ids:
            note_rows.append({"note_step": step, "source_relationship_ids": ids})
    if covered != set(relationships):
        raise ValueError("architecture board relationships are not fully presented")
    return edges, note_rows


def _validate_mermaid(
    model: Mapping[str, Any],
    mermaid_raw: bytes,
    components: Mapping[str, Mapping[str, Any]],
    relationships: Mapping[str, Mapping[str, Any]],
) -> None:
    contract = _object(
        model.get("mermaid"),
        {"dashed_relationship_ids", "decorative_edges", "decorative_nodes"},
        "Mermaid contract",
    )
    _strings(contract.get("dashed_relationship_ids"), "dashed relationship ids")
    if not isinstance(contract.get("decorative_edges"), list) or not isinstance(
        contract.get("decorative_nodes"), list
    ):
        raise ValueError("architecture board Mermaid decorations are invalid")
    text = mermaid_raw.decode("utf-8")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    for component in components.values():
        semantic = str(component["semantic_key"])
        record_id = str(component["record_id"])
        if not any(semantic in line and record_id in line for line in lines):
            raise ValueError("architecture board Mermaid component binding changed")
    semantics = {key: str(row["semantic_key"]) for key, row in components.items()}
    dashed = set(contract["dashed_relationship_ids"])
    for relationship in relationships.values():
        source = semantics[str(relationship["source_id"])]
        target = semantics[str(relationship["target_id"])]
        label = str(relationship["source_text"])
        arrow = "-.->" if relationship["id"] in dashed else "-->"
        if not any(_mermaid_edge_matches(line, source, target, label, arrow) for line in lines):
            raise ValueError("architecture board Mermaid relationship binding changed")
def _validate_source_model(
    document: Mapping[str, Any], mermaid_raw: bytes, source_sha: str
) -> dict[str, Any]:
    model = _object(
        document,
        {
            "boundaries",
            "components",
            "icon_package",
            "mermaid",
            "presentation",
            "relationships",
            "render_contract",
            "schema_version",
            "source",
        },
        "source model",
    )
    source = _object(model.get("source"), {"kind", "path", "sha256"}, "source")
    if (
        model.get("schema_version") != 2
        or source.get("kind") != "MERMAID"
        or source.get("path") != "architecture-source.mmd"
        or source.get("sha256") != source_sha
    ):
        raise ValueError("architecture board source model binding changed")
    icons = _validate_icon_package(model)
    render = _validate_render_contract(model)
    canvas = render["canvas"]
    boundaries = _validate_boundaries(model, icons, canvas)
    components = _validate_components(model, boundaries, icons, canvas)
    relationships = _validate_relationships(model, components)
    edges, note_rows = _validate_presentation(model, relationships, canvas)
    _validate_mermaid(model, mermaid_raw, components, relationships)
    anchor_edges = {str(row["id"]) for row in edges}
    for anchor in render["boundary_anchors"]:
        if anchor["boundary"] not in boundaries or anchor["edge"] not in anchor_edges:
            raise ValueError("architecture board boundary anchor binding changed")
    return {
        "model": model,
        "icons": icons,
        "render": render,
        "boundaries": boundaries,
        "components": components,
        "relationships": relationships,
        "edges": edges,
        "note_rows": note_rows,
        "inventory_sha256": _sha256(
            _canonical_bytes(
                {
                    key: model[key]
                    for key in (
                        "boundaries",
                        "components",
                        "icon_package",
                        "mermaid",
                        "presentation",
                        "relationships",
                        "render_contract",
                    )
                }
            )
        ),
    }


def _markdown_bytes(model: Mapping[str, Any], mermaid_raw: bytes) -> bytes:
    return _validated_markdown_bytes(
        model,
        mermaid_raw,
        contract_id=ARCHITECTURE_DIAGRAM_SKILL_IDENTITY["contract_id"],
    )


def _validate_manifest_anchors(
    observations: object, model_state: Mapping[str, Any]
) -> None:
    expected_rows = model_state["render"]["boundary_anchors"]
    if not isinstance(observations, list) or len(observations) != len(expected_rows):
        raise ValueError("architecture board boundary anchor evidence changed")
    for expected, observed in zip(expected_rows, observations, strict=True):
        if not isinstance(observed, Mapping) or any(
            observed.get(key) != expected[key]
            for key in ("boundary", "edge", "endpoint", "side")
        ):
            raise ValueError("architecture board boundary anchor evidence changed")
        actual = observed.get("actual_clearance")
        if (
            isinstance(actual, bool)
            or not isinstance(actual, (int, float))
            or float(actual) < int(expected["clearance"])
        ):
            raise ValueError("architecture board boundary anchor evidence changed")


def _validate_manifest(
    document: Mapping[str, Any],
    context: Mapping[str, Any],
    artifacts: Mapping[str, str],
    model_state: Mapping[str, Any],
) -> None:
    keys = {
        "artifact",
        "boundary_anchors",
        "boundary_label_collisions",
        "canonical_relationships",
        "canvas",
        "contract_id",
        "derived_sources",
        "disclaimer",
        "edge_labels",
        "flow_notes",
        "model",
        "nodes",
        "official_icons",
        "precision_contract",
        "provenance",
        "records",
        "region",
        "relationships",
        "status",
        "svg_layer_order",
    }
    manifest = _object(document, keys, "artifact manifest")
    root = str(context["output_root"])
    source_model_path = f"{root}/source-model.json"
    source_path = f"{root}/architecture-source.mmd"
    derived = {
        "mermaid": {
            "file": "architecture-board.mmd",
            "sha256": artifacts[f"{root}/architecture-board.mmd"],
        },
        "markdown": {
            "file": "architecture-board.md",
            "sha256": artifacts[f"{root}/architecture-board.md"],
        },
    }
    expected_model = {
        "contract_id": ARCHITECTURE_DIAGRAM_SKILL_IDENTITY["contract_id"],
        "source_model_path": "source-model.json",
        "source_model_sha256": artifacts[source_model_path],
        "source_mermaid_sha256": artifacts[source_path],
        "inventory_sha256": model_state["inventory_sha256"],
        "source_model": model_state["model"],
        "edges": model_state["edges"],
        "note_relationships": model_state["note_rows"],
    }
    project = context["manifest"]["project"]
    expected_icons = {
        "package": model_state["icons"]["name"],
        "release_date": model_state["icons"]["release"],
        "embedded": True,
    }
    if (
        manifest.get("contract_id")
        != ARCHITECTURE_DIAGRAM_SKILL_IDENTITY["contract_id"]
        or manifest.get("artifact") != "architecture-board"
        or manifest.get("canvas") != model_state["render"]["canvas"]
        or str(manifest.get("status", "")).casefold() != "planned architecture"
        or manifest.get("region") != project["region"]
        or manifest.get("official_icons") != expected_icons
        or manifest.get("model") != expected_model
        or manifest.get("records") != list(model_state["components"])
        or manifest.get("nodes") != len(model_state["components"])
        or manifest.get("relationships") != len(model_state["edges"])
        or manifest.get("canonical_relationships")
        != len(model_state["relationships"])
        or manifest.get("edge_labels")
        != sum(bool(row["visible_label"]) for row in model_state["edges"])
        or manifest.get("flow_notes")
        != len(model_state["model"]["presentation"]["notes"])
        or manifest.get("svg_layer_order")
        != model_state["render"]["svg_layer_order"]
        or manifest.get("boundary_label_collisions") != []
        or manifest.get("precision_contract") != "1.3.0"
        or manifest.get("derived_sources") != derived
        or not _text(manifest.get("provenance"), "manifest provenance")
        or "not deployment or authorization evidence"
        not in _text(manifest.get("disclaimer"), "manifest disclaimer").casefold()
    ):
        raise ValueError("architecture board artifact manifest is not current")
    _validate_manifest_anchors(manifest.get("boundary_anchors"), model_state)


def _validate_render_receipt(
    document: Mapping[str, Any],
    root: str,
    artifacts: Mapping[str, str],
    canvas: Mapping[str, Any],
    png_dimensions: tuple[int, int],
) -> None:
    expected = {
        "schema_version": 1,
        "renderer": "sharp",
        "density": 144,
        "source": "architecture-board.svg",
        "source_sha256": artifacts[f"{root}/architecture-board.svg"],
        "target": "architecture-board.png",
        "target_sha256": artifacts[f"{root}/architecture-board.png"],
        "width": png_dimensions[0],
        "height": png_dimensions[1],
    }
    if (
        dict(document) != expected
        or png_dimensions
        != (int(canvas["width"]) * 2, int(canvas["height"]) * 2)
    ):
        raise ValueError("architecture board render receipt is invalid")


def _validate_validation_report(
    document: Mapping[str, Any],
    root: str,
    artifacts: Mapping[str, str],
    model_state: Mapping[str, Any],
    actual: Mapping[str, Any],
    png_dimensions: tuple[int, int],
) -> None:
    keys = {
        "boundary_anchor_failures",
        "boundary_label_collisions",
        "checks",
        "contract_id",
        "counts",
        "errors",
        "inventory_sha256",
        "layering",
        "png",
        "routing",
        "sha256",
        "status",
        "visual_review",
    }
    report = _object(document, keys, "validation report")
    checks = report.get("checks")
    expected_sha = {
        relative: artifacts[f"{root}/{relative}"]
        for relative in (
            "architecture-board.svg",
            "architecture-board.png",
            "architecture-board.drawio",
            "architecture-board.mmd",
            "architecture-board.md",
            "architecture-board-manifest.json",
            "architecture-board-render.json",
        )
    }
    expected_counts = {
        "canonical_components": len(model_state["components"]),
        "canonical_relationships": len(model_state["relationships"]),
        "visible_edges": len(model_state["edges"]),
        "note_relationships": sum(
            len(row["source_relationship_ids"]) for row in model_state["note_rows"]
        ),
        "embedded_icon_instances": actual["icon_count"],
        "external_image_dependencies": 0,
        "flow_notes": len(model_state["model"]["presentation"]["notes"]),
    }
    expected_routing = {
        "missing_svg_arrowheads": [],
        "missing_drawio_arrowheads": [],
        "duplicate_arrowhead_endpoints": [],
        "overlapping_terminal_segments": [],
    }
    expected_layering = {
        "svg_layers": actual["svg_layers"],
        "text_before_connector_layer": [],
        "unmasked_svg_edge_labels": [],
        "early_drawio_text_cells": [],
        "labeled_drawio_edge_cells": [],
        "svg_edge_label_count": actual["svg_edge_labels"],
        "drawio_edge_label_count": actual["drawio_edge_labels"],
    }
    expected_visual = {
        "status": "PASS",
        "receipt": "visual-review-receipt.json",
        "png_sha256": artifacts[f"{root}/architecture-board.png"].removeprefix(
            "sha256:"
        ),
        "tile_count": 12,
        "findings": [],
    }
    if (
        report.get("status") != "PASS"
        or report.get("contract_id")
        != ARCHITECTURE_DIAGRAM_SKILL_IDENTITY["contract_id"]
        or not isinstance(checks, Mapping)
        or set(checks) != _ARCHITECTURE_BOARD_VALIDATION_CHECKS
        or any(value is not True for value in checks.values())
        or report.get("errors") != []
        or report.get("counts") != expected_counts
        or report.get("inventory_sha256") != model_state["inventory_sha256"]
        or report.get("png")
        != {
            "width": png_dimensions[0],
            "height": png_dimensions[1],
            "sha256": artifacts[f"{root}/architecture-board.png"],
        }
        or report.get("routing") != expected_routing
        or report.get("layering") != expected_layering
        or report.get("boundary_label_collisions") != []
        or report.get("boundary_anchor_failures") != []
        or report.get("visual_review") != expected_visual
        or report.get("sha256") != expected_sha
    ):
        raise ValueError("architecture board validation report is not PASS")


def _tile_geometry(
    sequence: int, width: int, height: int
) -> tuple[int, int, int, int, int, int]:
    row = (sequence - 1) // 4
    column = (sequence - 1) % 4
    cell_left = (column * width) // 4
    cell_right = ((column + 1) * width) // 4
    cell_top = (row * height) // 3
    cell_bottom = ((row + 1) * height) // 3
    left = max(0, cell_left - 80)
    top = max(0, cell_top - 80)
    right = min(width, cell_right + 80)
    bottom = min(height, cell_bottom + 80)
    return row + 1, column + 1, left, top, right - left, bottom - top


def _validate_qa_manifest(
    document: Mapping[str, Any],
    snapshot: ProjectSnapshot,
    root: str,
    artifacts: Mapping[str, str],
    png_dimensions: tuple[int, int],
) -> dict[str, str]:
    manifest = _object(
        document,
        {
            "expected_tile_count",
            "grid",
            "schema_version",
            "source_dimensions",
            "source_png",
            "source_png_sha256",
            "tiles",
        },
        "QA tile manifest",
    )
    if (
        manifest.get("schema_version") != "1.0"
        or manifest.get("source_png") != "architecture-board.png"
        or manifest.get("source_png_sha256")
        != artifacts[f"{root}/architecture-board.png"].removeprefix("sha256:")
        or manifest.get("source_dimensions")
        != {"width": png_dimensions[0], "height": png_dimensions[1]}
        or manifest.get("grid") != {"columns": 4, "rows": 3, "overlap_px": 80}
        or manifest.get("expected_tile_count") != 12
        or not isinstance(manifest.get("tiles"), list)
        or len(manifest["tiles"]) != 12
    ):
        raise ValueError("architecture board QA tile manifest is invalid")
    main = snapshot.file(f"{root}/architecture-board.png")
    if main is None:
        raise ValueError("architecture board QA tile evidence is invalid")
    main_width, main_height, main_pixels = _png_rgba(
        main.raw_bytes, "architecture-board.png"
    )
    if (main_width, main_height) != png_dimensions:
        raise ValueError("architecture board QA tile evidence is invalid")
    result: dict[str, str] = {}
    for sequence, value in enumerate(manifest["tiles"], start=1):
        row, column, left, top, width, height = _tile_geometry(
            sequence, *png_dimensions
        )
        relative = ARCHITECTURE_BOARD_QA_TILES[sequence - 1]
        name = relative.removeprefix("qa-tiles/")
        expected = {
            "sequence": sequence,
            "row": row,
            "column": column,
            "file": name,
            "left": left,
            "top": top,
            "width": width,
            "height": height,
            "sha256": artifacts[f"{root}/{relative}"].removeprefix("sha256:"),
        }
        observed = snapshot.file(f"{root}/{relative}")
        tile = (
            _png_rgba(observed.raw_bytes, name) if observed is not None else None
        )
        if (
            not isinstance(value, Mapping)
            or dict(value) != expected
            or observed is None
            or tile is None
            or tile[:2] != (width, height)
            or tile[2]
            != _rgba_crop(main_pixels, main_width, left, top, width, height)
        ):
            raise ValueError("architecture board QA tile evidence is invalid")
        result[name] = str(expected["sha256"])
    return result


def _named_digests(rows: object) -> dict[str, str]:
    if not isinstance(rows, list):
        raise ValueError("architecture board visual receipt bundle is invalid")
    result: dict[str, str] = {}
    for value in rows:
        row = _object(value, {"file", "sha256"}, "visual receipt bundle row")
        name = _safe_relative_path(row.get("file"), "visual bundle")
        digest = _sha_value(row.get("sha256"), "visual bundle", prefixed=False)
        if name in result:
            raise ValueError("architecture board visual receipt has duplicate paths")
        result[name] = digest
    return result


def _validate_visual_checks(values: object) -> None:
    if not isinstance(values, list) or len(values) != 8:
        raise ValueError("architecture board visual checks are incomplete")
    observed: set[str] = set()
    for value in values:
        row = _object(value, {"id", "notes", "status"}, "visual check")
        check_id = _text(row.get("id"), "visual check id")
        if (
            check_id in observed
            or row.get("status") != "PASS"
            or not _text(row.get("notes"), "visual check notes")
        ):
            raise ValueError("architecture board visual checks are incomplete")
        observed.add(check_id)
    if observed != _ARCHITECTURE_BOARD_VISUAL_CHECKS:
        raise ValueError("architecture board visual checks are incomplete")


def _validate_visual_tiles(
    values: object, tile_digests: Mapping[str, str]
) -> None:
    if not isinstance(values, list) or len(values) != 12:
        raise ValueError("architecture board visual tile review is incomplete")
    for sequence, value in enumerate(values, start=1):
        row = _object(
            value, {"file", "notes", "sequence", "sha256", "status"}, "visual tile"
        )
        name = ARCHITECTURE_BOARD_QA_TILES[sequence - 1].removeprefix("qa-tiles/")
        if (
            row.get("sequence") != sequence
            or row.get("file") != name
            or row.get("sha256") != tile_digests[name]
            or row.get("status") != "PASS"
            or not _text(row.get("notes"), "visual tile notes")
        ):
            raise ValueError("architecture board visual tile review is incomplete")


def _validate_visual_receipt(
    document: Mapping[str, Any],
    root: str,
    artifacts: Mapping[str, str],
    tile_digests: Mapping[str, str],
    png_dimensions: tuple[int, int],
) -> None:
    receipt = _object(
        document,
        {
            "bundle",
            "checks",
            "completion_rule",
            "full_canvas",
            "png",
            "schema_version",
            "status",
            "tiles",
            "tiles_manifest",
        },
        "visual receipt",
    )
    expected_bundle = {
        "architecture-board-manifest.json": artifacts[
            f"{root}/architecture-board-manifest.json"
        ].removeprefix("sha256:"),
        "architecture-board-render.json": artifacts[
            f"{root}/architecture-board-render.json"
        ].removeprefix("sha256:"),
        "architecture-board.drawio": artifacts[
            f"{root}/architecture-board.drawio"
        ].removeprefix("sha256:"),
        "architecture-board.md": artifacts[f"{root}/architecture-board.md"].removeprefix(
            "sha256:"
        ),
        "architecture-board.mmd": artifacts[
            f"{root}/architecture-board.mmd"
        ].removeprefix("sha256:"),
        "architecture-board.svg": artifacts[
            f"{root}/architecture-board.svg"
        ].removeprefix("sha256:"),
        "source-model.json": artifacts[f"{root}/source-model.json"].removeprefix(
            "sha256:"
        ),
        "architecture-source.mmd": artifacts[
            f"{root}/architecture-source.mmd"
        ].removeprefix("sha256:"),
    }
    full = receipt.get("full_canvas")
    tiles_manifest = receipt.get("tiles_manifest")
    if (
        receipt.get("schema_version") != "1.0"
        or receipt.get("status") != "PASS"
        or receipt.get("png")
        != {
            "file": "architecture-board.png",
            "sha256": artifacts[f"{root}/architecture-board.png"].removeprefix(
                "sha256:"
            ),
            "width": png_dimensions[0],
            "height": png_dimensions[1],
        }
        or not isinstance(tiles_manifest, Mapping)
        or str(tiles_manifest.get("file", "")).replace("\\", "/")
        != "qa-tiles/qa-tiles-manifest.json"
        or tiles_manifest.get("sha256")
        != artifacts[f"{root}/qa-tiles/qa-tiles-manifest.json"].removeprefix(
            "sha256:"
        )
        or _named_digests(receipt.get("bundle")) != expected_bundle
        or not isinstance(full, Mapping)
        or full.get("status") != "PASS"
        or not _text(full.get("notes"), "full-canvas notes")
        or not _text(receipt.get("completion_rule"), "visual completion rule")
    ):
        raise ValueError("architecture board visual review receipt is invalid")
    _validate_visual_checks(receipt.get("checks"))
    _validate_visual_tiles(receipt.get("tiles"), tile_digests)


def _completion_projection(
    context: Mapping[str, Any],
    packet: Mapping[str, Any],
    artifacts: Mapping[str, str],
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    manifest = context["manifest"]
    design = manifest["design"]
    authority = manifest["authority"]
    source_model = manifest["source_model"]
    completion: dict[str, Any] = {
        "schema_version": 1,
        "status": "COMPLETE",
        "output_root": context["output_root"],
        "binding": {
            "design_revision": design["revision"],
            "design_sha256": design["canonical_sha256"],
            "construction_authorization_id": authority[
                "construction_authorization_id"
            ],
            "request_manifest_sha256": artifacts[str(packet["manifest_path"])],
            "approved_mermaid_sha256": manifest["approved_mermaid"]["sha256"],
            "source_model_mode": source_model["mode"],
        },
        "artifacts": dict(artifacts),
        "evidence": dict(evidence),
        "evidence_boundary": {
            "fastlane_independent_checks": [
                "CURRENT_REPORT_AND_REQUEST_BINDING",
                "MERMAID_AND_SOURCE_MODEL_SEMANTICS",
                "SVG_AND_DRAWIO_STRUCTURE_AND_BINDINGS",
                "ARTIFACT_HASH_GRAPH",
                "PNG_STRUCTURE_AND_DIMENSIONS",
                "PNG_TO_QA_TILE_PIXEL_REPRODUCTION",
                "RECEIPT_FILE_BINDINGS",
            ],
            "external_validator_report": {
                "contract_id": ARCHITECTURE_DIAGRAM_SKILL_IDENTITY["contract_id"],
                "reported_check_count": 20,
                "reported_render_reproduced": True,
                "status": "PASS_REPORTED_EXECUTION_NOT_AUTHENTICATED",
            },
            "icon_provenance": "DECLARED_PACKAGE_NOT_INDEPENDENTLY_AUTHENTICATED",
        },
        "resume_route": "TASK-10",
        "aws_authority": "NONE",
        "external_authority": "NONE",
        "issues": [],
    }
    completion["canonical_sha256"] = architecture_board_completion_digest(completion)
    return completion


def _captured_board_evidence(
    snapshot: ProjectSnapshot, root: str
) -> dict[str, Mapping[str, Any]]:
    names = {
        "source_model": "source-model.json",
        "artifact_manifest": "architecture-board-manifest.json",
        "render_receipt": "architecture-board-render.json",
        "validation_report": "architecture-board-validation.json",
        "qa_tiles_manifest": "qa-tiles/qa-tiles-manifest.json",
        "visual_review_receipt": "visual-review-receipt.json",
    }
    return {
        key: _json_document(snapshot, f"{root}/{relative}")
        for key, relative in names.items()
    }


def validate_architecture_board_completion(
    report: Mapping[str, Any],
    packet: Mapping[str, Any],
    snapshot: ProjectSnapshot,
) -> dict[str, Any]:
    """Derive completion only from one exact bounded artifact snapshot."""

    context = _validated_request_context(report, packet)
    root = str(context["output_root"])
    artifacts = _snapshot_artifacts(snapshot, context["paths"])
    manifest_file = snapshot.file(str(packet["manifest_path"]))
    mermaid_file = snapshot.file(str(packet["mermaid_path"]))
    if (
        manifest_file is None
        or mermaid_file is None
        or manifest_file.raw_bytes
        != str(packet["manifest_text"]).encode("utf-8")
        or mermaid_file.raw_bytes != context["mermaid_raw"]
    ):
        raise ValueError("architecture board request artifact binding changed")
    source_model = _json_document(snapshot, f"{root}/source-model.json")
    model_state = _validate_source_model(
        source_model, context["mermaid_raw"], context["mermaid_sha"]
    )
    source_model_file = snapshot.file(f"{root}/source-model.json")
    derived_mermaid = snapshot.file(f"{root}/architecture-board.mmd")
    markdown = snapshot.file(f"{root}/architecture-board.md")
    svg = snapshot.file(f"{root}/architecture-board.svg")
    drawio = snapshot.file(f"{root}/architecture-board.drawio")
    png = snapshot.file(f"{root}/architecture-board.png")
    if (
        source_model_file is None
        or derived_mermaid is None
        or markdown is None
        or svg is None
        or drawio is None
        or png is None
        or derived_mermaid.raw_bytes != context["mermaid_raw"]
        or markdown.raw_bytes
        != _markdown_bytes(model_state["model"], context["mermaid_raw"])
    ):
        raise ValueError("architecture board derived source binding changed")
    source_model_sha = artifacts[f"{root}/source-model.json"]
    actual = _validate_actual_xml(
        svg.raw_bytes,
        drawio.raw_bytes,
        source_model_sha,
        context["mermaid_sha"],
        model_state,
        contract_id=ARCHITECTURE_DIAGRAM_SKILL_IDENTITY["contract_id"],
    )
    png_dimensions = _png_dimensions(png.raw_bytes, "rendered board")
    evidence = _captured_board_evidence(snapshot, root)
    _validate_manifest(evidence["artifact_manifest"], context, artifacts, model_state)
    _validate_render_receipt(
        evidence["render_receipt"],
        root,
        artifacts,
        model_state["render"]["canvas"],
        png_dimensions,
    )
    tile_digests = _validate_qa_manifest(
        evidence["qa_tiles_manifest"],
        snapshot,
        root,
        artifacts,
        png_dimensions,
    )
    _validate_visual_receipt(
        evidence["visual_review_receipt"],
        root,
        artifacts,
        tile_digests,
        png_dimensions,
    )
    _validate_validation_report(
        evidence["validation_report"],
        root,
        artifacts,
        model_state,
        actual,
        png_dimensions,
    )
    return _completion_projection(context, packet, artifacts, evidence)
