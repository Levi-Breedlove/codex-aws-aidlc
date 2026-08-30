from __future__ import annotations

import ast
import base64
import copy
import hashlib
import inspect
import json
import struct
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zlib
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import mock

from scripts import bootstrap_doctor as doctor
from scripts import fastlane_adr
from scripts.fastlane_engine import api as engine_api
from scripts.fastlane_engine import design
from scripts.fastlane_engine.define.models import RequirementsContract
from scripts.fastlane_engine.design import adr as design_adr
from scripts.fastlane_engine.design import architecture_board as board_contracts
from scripts.fastlane_engine.design import diagrams as design_diagrams
from scripts.fastlane_engine.design.relationship_semantics import (
    diagram_relation_category,
)
from scripts.fastlane_engine.design.models import (
    ArchitectureSelection,
    ProjectDesignContract,
)
from tests import test_adr_rationale as adr_fixtures
from tests import test_bootstrap_doctor as doctor_fixtures


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DESIGN_PACKAGE = REPOSITORY_ROOT / "scripts/fastlane_engine/design"


EXPECTED_ARCHITECTURE_BOARD_QA_TILES = (
    "qa-tiles/qa-01-r1-c1.png",
    "qa-tiles/qa-02-r1-c2.png",
    "qa-tiles/qa-03-r1-c3.png",
    "qa-tiles/qa-04-r1-c4.png",
    "qa-tiles/qa-05-r2-c1.png",
    "qa-tiles/qa-06-r2-c2.png",
    "qa-tiles/qa-07-r2-c3.png",
    "qa-tiles/qa-08-r2-c4.png",
    "qa-tiles/qa-09-r3-c1.png",
    "qa-tiles/qa-10-r3-c2.png",
    "qa-tiles/qa-11-r3-c3.png",
    "qa-tiles/qa-12-r3-c4.png",
)
EXPECTED_ARCHITECTURE_BOARD_OUTPUTS = (
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
    *EXPECTED_ARCHITECTURE_BOARD_QA_TILES,
)
EXPECTED_ARCHITECTURE_BOARD_VALIDATION_CHECKS = frozenset(
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
EXPECTED_ARCHITECTURE_BOARD_VISUAL_CHECKS = (
    "text_clear",
    "connectors_clear",
    "arrowheads_clear",
    "labels_above_connectors",
    "boundary_label_masks_clear",
    "boundary_anchors_clear",
    "boundaries_clear",
    "callouts_match_notes",
)
EXPECTED_ARCHITECTURE_BOARD_LAYERS = (
    "background",
    "boundary-shapes",
    "edge-paths",
    "boundary-labels",
    "outer-labels",
    "nodes",
    "edge-labels",
    "annotations",
)
EXPECTED_ARCHITECTURE_BOARD_CONTRACT_ID = "aws-architecture-diagrams/v1.3"
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NAMESPACE)
OFFICIAL_ACTOR_ICON = base64.b64decode(
    "PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiPz4KPHN2ZyB3aWR0aD0iNDhweCIgaGVpZ2h0PSI0OHB4IiB2aWV3"
    "Qm94PSIwIDAgNDggNDgiIHZlcnNpb249IjEuMSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIiB4bWxuczp4bGlu"
    "az0iaHR0cDovL3d3dy53My5vcmcvMTk5OS94bGluayI+CiAgICA8dGl0bGU+SWNvbi1SZXNvdXJjZS9HZW5lcmFsLVJlc291cmNl"
    "L1Jlc19Vc2VyXzQ4X0xpZ2h0PC90aXRsZT4KICAgIDxnIGlkPSJJY29uLVJlc291cmNlL0dlbmVyYWwtUmVzb3VyY2UvUmVzX1Vz"
    "ZXJfNDgiIHN0cm9rZT0ibm9uZSIgc3Ryb2tlLXdpZHRoPSIxIiBmaWxsPSJub25lIiBmaWxsLXJ1bGU9ImV2ZW5vZGQiPgogICAg"
    "ICAgIDxwYXRoIGQ9Ik02LjAyNSw0NCBDNi41MjQsMzQuMDg1IDE0LjM5NSwyNi4xNzggMjQsMjYuMTc4IEMyNy4yNDgsMjYuMTc4"
    "IDMwLjQzLDI3LjA5MiAzMy4yMDUsMjguODIyIEMzOC4zNTQsMzIuMDMzIDQxLjY1MywzNy43ODMgNDEuOTc0LDQ0IEw2LjAyNSw0"
    "NCBaIE0xNC4xOTIsMTMuODc4IEMxNC4xOTIsOC40MzIgMTguNTkyLDQgMjQuMDAxLDQgQzI5LjQwOCw0IDMzLjgwNyw4LjQzMiAz"
    "My44MDcsMTMuODc4IEMzMy44MDcsMTkuMzI1IDI5LjQwOCwyMy43NTcgMjQuMDAxLDIzLjc1NyBDMTguNTkyLDIzLjc1NyAxNC4x"
    "OTIsMTkuMzI1IDE0LjE5MiwxMy44NzggTDE0LjE5MiwxMy44NzggWiBNMzQuMjYzLDI3LjEyNSBDMzIuNTMsMjYuMDQ0IDMwLjY1"
    "LDI1LjI2IDI4LjY5OCwyNC43NzEgQzMyLjg3NywyMi45MzkgMzUuODA3LDE4Ljc0OSAzNS44MDcsMTMuODc4IEMzNS44MDcsNy4z"
    "MjkgMzAuNTEsMiAyNC4wMDEsMiBDMTcuNDg5LDIgMTIuMTkyLDcuMzI5IDEyLjE5MiwxMy44NzggQzEyLjE5MiwxOC43NTUgMTUu"
    "MTMsMjIuOTUgMTkuMzE3LDI0Ljc3OCBDMTAuNTQ1LDI2Ljk4MSA0LDM1LjIgNCw0NSBDNCw0NS41NTIgNC40NDcsNDYgNSw0NiBM"
    "NDMsNDYgQzQzLjU1Miw0NiA0NCw0NS41NTIgNDQsNDUgQzQ0LDM3LjcxOSA0MC4yNjksMzAuODcgMzQuMjYzLDI3LjEyNSBMMzQu"
    "MjYzLDI3LjEyNSBaIiBpZD0iRmlsbC0xIiBmaWxsPSIjMjQyRjNFIj48L3BhdGg+CiAgICA8L2c+Cjwvc3ZnPg=="
)
OFFICIAL_API_GATEWAY_ICON = base64.b64decode(
    "PHN2ZyB3aWR0aD0iODAiIGhlaWdodD0iODAiIHZpZXdCb3g9IjAgMCA4MCA4MCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93"
    "d3cudzMub3JnLzIwMDAvc3ZnIj4KPGcgaWQ9Ikljb24tQXJjaGl0ZWN0dXJlLzY0L0FyY2hfQW1hem9uLUFQSS1HYXRld2F5XzY0"
    "Ij4KPGcgaWQ9Ikljb24tQXJjaGl0ZWN0dXJlLUJHLzY0L05ldHdvcmtpbmctQ29udGVudC1EZWxpdmVyeSI+CjxyZWN0IGlkPSJS"
    "ZWN0YW5nbGUiIHdpZHRoPSI4MCIgaGVpZ2h0PSI4MCIgZmlsbD0iIzhDNEZGRiIvPgo8L2c+CjxnIGlkPSJJY29uLVNlcnZpY2Uv"
    "NjQvQW1hem9uLUFQSS1HYXRld2F5XzY0Ij4KPHBhdGggaWQ9IkFtYXpvbi1BUEktR2F0ZXdheV9JY29uXzY0X1NxdWlkIiBmaWxs"
    "LXJ1bGU9ImV2ZW5vZGQiIGNsaXAtcnVsZT0iZXZlbm9kZCIgZD0iTTM0LjA2NSA1NS42MzI0SDM3VjUzLjYxNTNIMzQuMDY1VjU1"
    "LjYzMjRaTTM5IDU1LjYzMjRINDJWNTMuNjE1M0gzOVY1NS42MzI0Wk0yNyAxNC42Mjk1TDE0IDIxLjA4MjFWNjEuMTkzNEwyNyA2"
    "NS41ODk2VjE0LjYyOTVaTTI5IDI3LjM5MzRWNTMuNjE1M0gzMlY1NS42MzI0SDI5VjY2Ljk5MTVDMjkgNjcuMzE2MiAyOC44NDUg"
    "NjcuNjIwOCAyOC41ODQgNjcuODEwNEMyOC40MTIgNjcuOTM1NSAyOC4yMDcgNjggMjggNjhDMjcuODk0IDY4IDI3Ljc4NiA2Ny45"
    "ODI5IDI3LjY4MiA2Ny45NDc2TDEyLjY4MiA2Mi44NzU2QzEyLjI3NCA2Mi43Mzc1IDEyIDYyLjM1MjIgMTIgNjEuOTE5NlYyMC40"
    "NTM3QzEyIDIwLjA3MDUgMTIuMjE3IDE5LjcxODUgMTIuNTU5IDE5LjU0OTFMMjcuNTU5IDEyLjEwNDFDMjcuODY4IDExLjk0OTgg"
    "MjguMjM1IDExLjk2NzkgMjguNTI4IDEyLjE1MjVDMjguODIxIDEyLjMzNjEgMjkgMTIuNjU5OCAyOSAxMy4wMDg3VjI1LjM3NjRI"
    "MzJWMjcuMzkzNEgyOVpNNDQgNTUuNjMyNEg0N1Y1My42MTUzSDQ0VjU1LjYzMjRaTTQ0LjA2NSAyNy4zOTM0SDQ3VjI1LjM3NjRI"
    "NDQuMDY1VjI3LjM5MzRaTTM5LjA2NSAyNy4zOTM0SDQyVjI1LjM3NjRIMzkuMDY1VjI3LjM5MzRaTTM0LjA2NSAyNy4zOTM0SDM3"
    "VjI1LjM3NjRIMzQuMDY1VjI3LjM5MzRaTTY2IDIxLjA4MjFMNTMgMTQuNjI5NVY2NS41ODk2TDY2IDYxLjE5MzRWMjEuMDgyMVpN"
    "NjggNjEuOTE5NkM2OCA2Mi4zNTIyIDY3LjcyNiA2Mi43Mzc1IDY3LjMxOCA2Mi44NzU2TDUyLjMxOCA2Ny45NDc2QzUyLjIxNCA2"
    "Ny45ODI5IDUyLjEwNiA2OCA1MiA2OEM1MS43OTMgNjggNTEuNTg4IDY3LjkzNTUgNTEuNDE2IDY3LjgxMDRDNTEuMTU1IDY3LjYy"
    "MDggNTEgNjcuMzE2MiA1MSA2Ni45OTE1VjU1LjYzMjRINDkuMDY1VjUzLjYxNTNINTFWMjcuMzkzNEg0OS4wNjVWMjUuMzc2NEg1"
    "MVYxMy4wMDg3QzUxIDEyLjY1OTggNTEuMTc5IDEyLjMzNjEgNTEuNDcyIDEyLjE1MjVDNTEuNzY1IDExLjk2NzkgNTIuMTMxIDEx"
    "Ljk0OTggNTIuNDQxIDEyLjEwNDFMNjcuNDQxIDE5LjU0OTFDNjcuNzgzIDE5LjcxODUgNjggMjAuMDcwNSA2OCAyMC40NTM3VjYx"
    "LjkxOTZaTTQyLjkzNCAzMy44MDY3TDQxLjA2NiAzMy4wODI2TDM2LjA2NiA0Ni4xOTM1TDM3LjkzNCA0Ni45MTc2TDQyLjkzNCAz"
    "My44MDY3Wk00OS43MDcgNDAuMjA4OUM1MC4wOTggMzkuODE0NSA1MC4wOTggMzkuMTc2MSA0OS43MDcgMzguNzgyOEw0NS43MDcg"
    "MzQuNzQ4N0w0NC4yOTMgMzYuMTc0N0w0Ny41ODYgMzkuNDk1OEw0NC4yOTMgNDIuODE2OUw0NS43MDcgNDQuMjQzTDQ5LjcwNyA0"
    "MC4yMDg5Wk0zNC4yOTMgNDQuMjQzTDMwLjI5MyA0MC4yMDg5QzI5LjkwMiAzOS44MTQ1IDI5LjkwMiAzOS4xNzYxIDMwLjI5MyAz"
    "OC43ODI4TDM0LjI5MyAzNC43NDg3TDM1LjcwNyAzNi4xNzQ3TDMyLjQxNCAzOS40OTU4TDM1LjcwNyA0Mi44MTY5TDM0LjI5MyA0"
    "NC4yNDNaIiBmaWxsPSJ3aGl0ZSIvPgo8L2c+CjwvZz4KPC9zdmc+Cg=="
)


def _board_json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _board_canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _board_sha256(raw: bytes, *, prefixed: bool = True) -> str:
    digest = hashlib.sha256(raw).hexdigest()
    return "sha256:" + digest if prefixed else digest


def _board_png(width: int, height: int, rgba: bytes = b"\xef\xf6\xff\xff") -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    row = b"\x00" + rgba * width
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(row * height, 9))
        + chunk(b"IEND", b"")
    )


def _board_presentation_sha256(root: ET.Element, kind: str) -> str:
    normalized = ET.fromstring(ET.tostring(root, encoding="utf-8"))
    if kind == "svg":
        for key in (
            "data-contract-id",
            "data-source-model-sha256",
            "data-source-mermaid-sha256",
            "data-inventory-sha256",
        ):
            normalized.attrib.pop(key, None)
        for child in list(normalized):
            if child.tag.rsplit("}", 1)[-1] in {"title", "desc", "metadata", "defs"}:
                normalized.remove(child)
    else:
        graph = normalized.find(".//mxGraphModel")
        assert graph is not None
        for key in (
            "contractId",
            "sourceModelSha256",
            "sourceMermaidSha256",
            "inventorySha256",
        ):
            graph.attrib.pop(key, None)
    return _board_sha256(ET.tostring(normalized, encoding="utf-8"))


_BOARD_DASHED_RELATIONS = frozenset(
    {
        "defines changes for",
        "deploys",
        "emits operational signals to",
        "emits signals to",
        "protects",
        "protects code, data, and secrets posture for",
        "provides token issuer trust to",
        "restores",
    }
)


def _architecture_board_report_fixture(*, schema_version: int = 7) -> dict[str, object]:
    report = copy.deepcopy(
        json.loads(
            (REPOSITORY_ROOT / "tests/fixtures/engine_parity_v1.json").read_text(
                encoding="utf-8"
            )
        )["report_cases"]["gate_b_approved"]["report"]
    )
    design_contract = report["design_contract"]
    project_contract = design_contract["project_contract"]
    design_contract["schema_version"] = schema_version
    project_contract["schema_version"] = schema_version
    if schema_version == 8:
        project_contract["design_v8"] = {"schema_version": 8, "status": "READY"}
    records = design_contract["diagram_contract"]["records"]
    groups = {
        "DIAGRAM-0001": [
            ["ACT-001"],
            ["API-001", "ARCH-0001", "BOUNDARY-001", "TECH-0001", "TECH-0002"],
            ["TECH-0004", "TECH-0008", "TECH-0009", "TECH-0014", "TECH-0015"],
            ["TECH-0010", "TECH-0013"],
            ["TECH-0011"],
        ],
        "DIAGRAM-0008": [
            ["ARCH-0001", "TECH-0001", "TECH-0002"],
            ["TECH-0004", "TECH-0008", "TECH-0009", "TECH-0014", "TECH-0015"],
            ["TECH-0010", "TECH-0013"],
            ["TECH-0011"],
        ],
    }
    for record in records:
        diagram_id = record["diagram_id"]
        if diagram_id not in groups:
            continue
        record["semantic_relationships"] = [
            {
                **edge,
                "edge_kind": (
                    "DASHED" if edge["relation"] in _BOARD_DASHED_RELATIONS else "SOLID"
                ),
            }
            for edge in record["relationships"]
        ]
        record["containment"] = [
            sorted(record["referenced_ids"]),
            *groups[diagram_id],
        ]
    return report


def _board_edge_projection() -> dict[str, object]:
    return {
        "id": "EDGE-001",
        "representation": "DIRECT",
        "source_relationship_ids": ["REL-001"],
        "source_records": ["ACT-001"],
        "target_records": ["TECH-0013"],
        "source_terminal_record": "ACT-001",
        "target_terminal_record": "TECH-0013",
        "visible_label": "sends a review request through",
        "arrow_mode": "FORWARD",
        "stroke_color": "#4A5568",
        "stroke_width": 2,
        "dashed": False,
        "points": [[300, 350], [900, 350]],
        "label_at": [600, 330],
    }


def _board_model_rows(
    mermaid_sha256: str,
) -> tuple[dict[str, object], dict[str, bytes]]:
    icon_assets = {
        "actor": OFFICIAL_ACTOR_ICON,
        "api_gateway": OFFICIAL_API_GATEWAY_ICON,
    }
    model: dict[str, object] = {
        "schema_version": 2,
        "source": {
            "kind": "MERMAID",
            "path": "architecture-source.mmd",
            "sha256": mermaid_sha256,
        },
        "icon_package": {
            "assets": {key: _board_sha256(value) for key, value in icon_assets.items()},
            "name": "AWS Architecture Icons Q2 2026",
            "release": "2026-04-30",
            "source": "AWS Architecture Icons",
        },
        "render_contract": {
            "boundary_anchors": [],
            "canvas": {"height": 800, "width": 1280},
            "drawio_presentation_sha256": "sha256:" + "0" * 64,
            "svg_layer_order": list(EXPECTED_ARCHITECTURE_BOARD_LAYERS),
            "svg_presentation_sha256": "sha256:" + "0" * 64,
        },
        "boundaries": [
            {
                "boundary_type": "AWS_REGION",
                "dashed": False,
                "fill_color": "#F7FAFC",
                "geometry": {"x": 100, "y": 120, "width": 1080, "height": 520},
                "icon_key": None,
                "id": "BOUNDARY-001",
                "parent": None,
                "rendered": True,
                "stroke_color": "#A0AEC0",
                "subtitle": "us-west-2",
                "title": "AWS Region",
                "title_size": 18,
            }
        ],
        "components": [
            {
                "boundary": "BOUNDARY-001",
                "component_class": "ACTOR",
                "icon_key": "actor",
                "label": "Development user",
                "qualifiers": [],
                "mermaid_label": "Development user",
                "record_id": "ACT-001",
                "render_geometry": {"size": 96, "x": 220, "y": 300},
                "render_purpose": ["Sends an approved review request."],
                "render_title": ["Development user"],
                "scope": "PROJECT",
                "semantic_key": "ACT-001",
            },
            {
                "boundary": "BOUNDARY-001",
                "component_class": "AWS_SERVICE",
                "icon_key": "api_gateway",
                "label": "Amazon API Gateway",
                "qualifiers": ["regional HTTPS endpoint"],
                "mermaid_label": "Amazon API Gateway regional HTTPS endpoint",
                "record_id": "TECH-0013",
                "render_geometry": {"size": 96, "x": 900, "y": 300},
                "render_purpose": ["Accepts the planned regional HTTPS request."],
                "render_title": ["Amazon API Gateway"],
                "scope": "PROJECT",
                "semantic_key": "TECH-0013",
            },
        ],
        "relationships": [
            {
                "cadence": "SYNCHRONOUS",
                "class": "request",
                "failure": "The request fails closed.",
                "id": "REL-001",
                "security": ["TLS"],
                "source_id": "ACT-001",
                "source_text": "sends a review request through",
                "target_id": "TECH-0013",
            }
        ],
        "presentation": {
            "edges": [
                {
                    "arrow_mode": "FORWARD",
                    "dashed": False,
                    "id": "EDGE-001",
                    "label_at": [600, 330],
                    "points": [[300, 350], [900, 350]],
                    "relationship_ids": ["REL-001"],
                    "representation": "DIRECT",
                    "source_terminal": "ACT-001",
                    "stroke_color": "#4A5568",
                    "stroke_width": 2,
                    "target_terminal": "TECH-0013",
                    "visible_label": "sends a review request through",
                }
            ],
            "notes": [
                {
                    "body": f"Planned design note {step}.",
                    "relationship_ids": [],
                    "step": step,
                    "title": f"Design note {step}",
                }
                for step in range(1, 7)
            ],
        },
        "mermaid": {
            "dashed_relationship_ids": [],
            "decorative_edges": [],
            "decorative_nodes": [],
        },
    }
    return model, icon_assets


def _board_svg_tree(
    model: dict[str, object], icon_assets: dict[str, bytes]
) -> ET.Element:
    svg = ET.Element(
        f"{{{SVG_NAMESPACE}}}svg",
        {"width": "1280", "height": "800", "viewBox": "0 0 1280 800"},
    )
    defs = ET.SubElement(svg, f"{{{SVG_NAMESPACE}}}defs")
    marker = ET.SubElement(
        defs,
        f"{{{SVG_NAMESPACE}}}marker",
        {"id": "arrow", "markerWidth": "10", "markerHeight": "10"},
    )
    ET.SubElement(
        marker,
        f"{{{SVG_NAMESPACE}}}path",
        {"d": "M 0 0 L 10 5 L 0 10 z", "fill": "#4A5568"},
    )
    layers = {
        name: ET.SubElement(svg, f"{{{SVG_NAMESPACE}}}g", {"data-layer": name})
        for name in EXPECTED_ARCHITECTURE_BOARD_LAYERS
    }
    ET.SubElement(
        layers["background"],
        f"{{{SVG_NAMESPACE}}}rect",
        {"x": "0", "y": "0", "width": "1280", "height": "800", "fill": "#FFFFFF"},
    )
    boundary = ET.SubElement(
        layers["boundary-shapes"],
        f"{{{SVG_NAMESPACE}}}g",
        {"data-boundary-shape": "BOUNDARY-001"},
    )
    ET.SubElement(
        boundary,
        f"{{{SVG_NAMESPACE}}}rect",
        {
            "x": "100",
            "y": "120",
            "width": "1080",
            "height": "520",
            "fill": "#F7FAFC",
            "stroke": "#A0AEC0",
        },
    )
    edge = ET.SubElement(
        layers["edge-paths"],
        f"{{{SVG_NAMESPACE}}}g",
        {
            "data-edge": "EDGE-001",
            "data-contract": _board_canonical_bytes(_board_edge_projection())
            .decode()
            .strip(),
        },
    )
    ET.SubElement(
        edge,
        f"{{{SVG_NAMESPACE}}}path",
        {
            "d": "M 300 350 L 900 350",
            "fill": "none",
            "stroke": "#4A5568",
            "marker-end": "url(#arrow)",
        },
    )
    ET.SubElement(
        layers["boundary-labels"],
        f"{{{SVG_NAMESPACE}}}text",
        {"x": "120", "y": "155"},
    ).text = "AWS Region — us-west-2"
    components = model["components"]
    assert isinstance(components, list)
    for row in components:
        assert isinstance(row, dict)
        geometry = row["render_geometry"]
        assert isinstance(geometry, dict)
        encoded_icon = base64.b64encode(icon_assets[str(row["icon_key"])]).decode(
            "ascii"
        )
        group = ET.SubElement(
            layers["nodes"],
            f"{{{SVG_NAMESPACE}}}g",
            {
                "data-record": str(row["record_id"]),
                "data-contract": _board_canonical_bytes(row).decode().strip(),
            },
        )
        ET.SubElement(
            group,
            f"{{{SVG_NAMESPACE}}}image",
            {
                "x": str(geometry["x"]),
                "y": str(geometry["y"]),
                "width": str(geometry["size"]),
                "height": str(geometry["size"]),
                "href": "data:image/svg+xml;base64," + encoded_icon,
            },
        )
        ET.SubElement(
            group,
            f"{{{SVG_NAMESPACE}}}text",
            {"x": str(geometry["x"]), "y": str(int(geometry["y"]) + 120)},
        ).text = str(row["label"])
    ET.SubElement(
        layers["edge-labels"],
        f"{{{SVG_NAMESPACE}}}text",
        {"x": "475", "y": "330", "data-edge-label": "EDGE-001"},
    ).text = "sends a review request through"
    ET.SubElement(
        layers["annotations"],
        f"{{{SVG_NAMESPACE}}}text",
        {"x": "40", "y": "40"},
    ).text = "PLANNED ARCHITECTURE"
    ET.SubElement(
        layers["annotations"],
        f"{{{SVG_NAMESPACE}}}text",
        {"x": "40", "y": "70"},
    ).text = "Not deployment or authorization evidence"
    return svg


def _board_drawio_tree(
    model: dict[str, object], icon_assets: dict[str, bytes]
) -> tuple[ET.Element, ET.Element]:
    drawio = ET.Element("mxfile")
    diagram = ET.SubElement(drawio, "diagram", {"id": "board", "name": "Architecture"})
    graph = ET.SubElement(
        diagram,
        "mxGraphModel",
        {"pageWidth": "1280", "pageHeight": "800"},
    )
    root = ET.SubElement(graph, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})
    boundary = ET.SubElement(
        root,
        "mxCell",
        {
            "id": "boundary-BOUNDARY-001",
            "parent": "1",
            "value": "AWS Region — us-west-2",
            "vertex": "1",
        },
    )
    ET.SubElement(
        boundary,
        "mxGeometry",
        {"x": "100", "y": "120", "width": "1080", "height": "520", "as": "geometry"},
    )
    components = model["components"]
    assert isinstance(components, list)
    for row in components:
        assert isinstance(row, dict)
        geometry = row["render_geometry"]
        assert isinstance(geometry, dict)
        encoded_icon = base64.b64encode(icon_assets[str(row["icon_key"])]).decode(
            "ascii"
        )
        cell = ET.SubElement(
            root,
            "mxCell",
            {
                "id": "node-" + str(row["record_id"]),
                "parent": "boundary-BOUNDARY-001",
                "value": str(row["label"]),
                "vertex": "1",
                "componentRecord": str(row["record_id"]),
                "contract": _board_canonical_bytes(row).decode().strip(),
                "style": (
                    "shape=image;image=data:image/svg+xml;base64,"
                    + encoded_icon
                    + ";imageAspect=0;aspect=fixed;html=1;strokeColor=none;"
                    "fillColor=none;"
                ),
            },
        )
        ET.SubElement(
            cell,
            "mxGeometry",
            {
                "x": str(geometry["x"]),
                "y": str(geometry["y"]),
                "width": str(geometry["size"]),
                "height": str(geometry["size"]),
                "as": "geometry",
            },
        )
    edge = ET.SubElement(
        root,
        "mxCell",
        {
            "id": "edge-EDGE-001",
            "parent": "1",
            "source": "node-ACT-001",
            "target": "node-TECH-0013",
            "edge": "1",
            "style": "edgeStyle=orthogonalEdgeStyle;endArrow=block;",
            "contract": _board_canonical_bytes(_board_edge_projection())
            .decode()
            .strip(),
        },
    )
    ET.SubElement(edge, "mxGeometry", {"relative": "1", "as": "geometry"})
    label = ET.SubElement(
        root,
        "mxCell",
        {
            "id": "edge-label-EDGE-001",
            "parent": "edge-EDGE-001",
            "value": "sends a review request through",
            "vertex": "1",
        },
    )
    ET.SubElement(label, "mxGeometry", {"relative": "1", "as": "geometry"})
    status = ET.SubElement(
        root,
        "mxCell",
        {
            "id": "status",
            "parent": "1",
            "value": "Separate AWS approval required",
            "vertex": "1",
        },
    )
    ET.SubElement(
        status,
        "mxGeometry",
        {"x": "40", "y": "720", "width": "320", "height": "40", "as": "geometry"},
    )
    return drawio, graph


def _board_artifacts(
    mermaid_sha256: str,
) -> tuple[dict[str, object], bytes, bytes, bytes]:
    model, icon_assets = _board_model_rows(mermaid_sha256)
    svg = _board_svg_tree(model, icon_assets)
    drawio, graph = _board_drawio_tree(model, icon_assets)
    render = model["render_contract"]
    assert isinstance(render, dict)
    render["svg_presentation_sha256"] = _board_presentation_sha256(svg, "svg")
    render["drawio_presentation_sha256"] = _board_presentation_sha256(drawio, "drawio")
    inventory_sha256 = _board_sha256(
        _board_canonical_bytes(
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
    )
    source_model_raw = _board_json_bytes(model)
    source_model_sha256 = _board_sha256(source_model_raw)
    svg.attrib.update(
        {
            "data-contract-id": EXPECTED_ARCHITECTURE_BOARD_CONTRACT_ID,
            "data-source-model-sha256": source_model_sha256,
            "data-source-mermaid-sha256": mermaid_sha256,
            "data-inventory-sha256": inventory_sha256,
        }
    )
    graph.attrib.update(
        {
            "contractId": EXPECTED_ARCHITECTURE_BOARD_CONTRACT_ID,
            "sourceModelSha256": source_model_sha256,
            "sourceMermaidSha256": mermaid_sha256,
            "inventorySha256": inventory_sha256,
        }
    )
    return (
        model,
        source_model_raw,
        ET.tostring(svg, encoding="utf-8"),
        ET.tostring(drawio, encoding="utf-8"),
    )


def _board_markdown(model: dict[str, object], mermaid_raw: bytes) -> bytes:
    source = mermaid_raw.decode("utf-8").rstrip("\n")
    source_row = model["source"]
    assert isinstance(source_row, dict)
    ticks = chr(96) * 3
    tick = chr(96)
    return (
        "# Planned AWS architecture board\n\n"
        "> **PLANNED ARCHITECTURE \u2014 Not deployment or authorization evidence.**\n\n"
        f"Semantic source: {tick}{source_row['path']}{tick}  \n"
        f"Contract: {tick}{EXPECTED_ARCHITECTURE_BOARD_CONTRACT_ID}{tick}  \n"
        f"Source SHA-256: {tick}{source_row['sha256']}{tick}\n\n"
        f"{ticks}mermaid\n{source}\n{ticks}\n"
    ).encode("utf-8")


def _board_tile_geometry(
    sequence: int, width: int = 2560, height: int = 1600
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


def _board_fixture_paths(packet: dict[str, object]) -> tuple[str, ...]:
    manifest = packet["manifest"]
    assert isinstance(manifest, dict)
    output = manifest["output"]
    assert isinstance(output, dict)
    output_root = str(output["directory"])
    return tuple(
        sorted(
            {
                str(packet["manifest_path"]),
                str(packet["mermaid_path"]),
                str(packet["source_model_path"]),
                *(
                    f"{output_root}/{relative}"
                    for relative in EXPECTED_ARCHITECTURE_BOARD_OUTPUTS
                ),
            }
        )
    )


def write_architecture_board_completion_fixture(
    root: Path,
    report: dict[str, object],
    packet: dict[str, object],
) -> dict[str, object]:
    """Write one independently authored, fully observed board bundle."""

    manifest = packet["manifest"]
    assert isinstance(manifest, dict)
    output = manifest["output"]
    project = manifest["project"]
    assert isinstance(output, dict)
    assert isinstance(project, dict)
    output_root = str(output["directory"])

    def write(relative: str, content: bytes) -> None:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    def digest(relative: str, *, prefixed: bool = True) -> str:
        return _board_sha256((root / relative).read_bytes(), prefixed=prefixed)

    manifest_path = str(packet["manifest_path"])
    mermaid_path = str(packet["mermaid_path"])
    source_model_path = str(packet["source_model_path"])
    mermaid_raw = str(packet["mermaid_text"]).encode("utf-8")
    mermaid_sha256 = _board_sha256(mermaid_raw)
    model, source_model_raw, svg_raw, drawio_raw = _board_artifacts(mermaid_sha256)
    write(manifest_path, str(packet["manifest_text"]).encode("utf-8"))
    write(mermaid_path, mermaid_raw)
    write(source_model_path, source_model_raw)
    write(f"{output_root}/architecture-board.mmd", mermaid_raw)
    write(f"{output_root}/architecture-board.md", _board_markdown(model, mermaid_raw))
    write(f"{output_root}/architecture-board.svg", svg_raw)
    write(f"{output_root}/architecture-board.drawio", drawio_raw)
    write(f"{output_root}/architecture-board.png", _board_png(2560, 1600))
    qa_rows: list[dict[str, object]] = []
    visual_tiles: list[dict[str, object]] = []
    for sequence, relative in enumerate(EXPECTED_ARCHITECTURE_BOARD_QA_TILES, 1):
        row, column, left, top, width, height = _board_tile_geometry(sequence)
        write(f"{output_root}/{relative}", _board_png(width, height))
        name = relative.removeprefix("qa-tiles/")
        tile_sha = digest(f"{output_root}/{relative}", prefixed=False)
        qa_rows.append(
            {
                "sequence": sequence,
                "row": row,
                "column": column,
                "file": name,
                "left": left,
                "top": top,
                "width": width,
                "height": height,
                "sha256": tile_sha,
            }
        )
        visual_tiles.append(
            {
                "sequence": sequence,
                "file": name,
                "sha256": tile_sha,
                "status": "PASS",
                "notes": f"QA tile {sequence} was inspected at original resolution.",
            }
        )
    render = model["render_contract"]
    icon_package = model["icon_package"]
    assert isinstance(render, dict)
    assert isinstance(icon_package, dict)
    inventory_sha256 = _board_sha256(
        _board_canonical_bytes(
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
    )
    artifact_manifest = {
        "artifact": "architecture-board",
        "boundary_anchors": [],
        "boundary_label_collisions": [],
        "canonical_relationships": 1,
        "canvas": {"height": 800, "width": 1280},
        "contract_id": EXPECTED_ARCHITECTURE_BOARD_CONTRACT_ID,
        "derived_sources": {
            "mermaid": {
                "file": "architecture-board.mmd",
                "sha256": digest(f"{output_root}/architecture-board.mmd"),
            },
            "markdown": {
                "file": "architecture-board.md",
                "sha256": digest(f"{output_root}/architecture-board.md"),
            },
        },
        "disclaimer": "Not deployment or authorization evidence.",
        "edge_labels": 1,
        "flow_notes": 6,
        "model": {
            "contract_id": EXPECTED_ARCHITECTURE_BOARD_CONTRACT_ID,
            "source_model_path": "source-model.json",
            "source_model_sha256": digest(source_model_path),
            "source_mermaid_sha256": digest(mermaid_path),
            "inventory_sha256": inventory_sha256,
            "source_model": model,
            "edges": [_board_edge_projection()],
            "note_relationships": [],
        },
        "nodes": 2,
        "official_icons": {
            "package": icon_package["name"],
            "release_date": icon_package["release"],
            "embedded": True,
        },
        "precision_contract": "1.3.0",
        "provenance": "Derived locally from the current approved Mermaid source.",
        "records": ["ACT-001", "TECH-0013"],
        "region": project["region"],
        "relationships": 1,
        "status": "planned architecture",
        "svg_layer_order": list(EXPECTED_ARCHITECTURE_BOARD_LAYERS),
    }
    write(
        f"{output_root}/architecture-board-manifest.json",
        _board_json_bytes(artifact_manifest),
    )
    render_receipt = {
        "schema_version": 1,
        "renderer": "sharp",
        "density": 144,
        "source": "architecture-board.svg",
        "source_sha256": digest(f"{output_root}/architecture-board.svg"),
        "target": "architecture-board.png",
        "target_sha256": digest(f"{output_root}/architecture-board.png"),
        "width": 2560,
        "height": 1600,
    }
    write(
        f"{output_root}/architecture-board-render.json",
        _board_json_bytes(render_receipt),
    )
    qa_manifest = {
        "schema_version": "1.0",
        "source_png": "architecture-board.png",
        "source_png_sha256": digest(
            f"{output_root}/architecture-board.png", prefixed=False
        ),
        "source_dimensions": {"width": 2560, "height": 1600},
        "grid": {"columns": 4, "rows": 3, "overlap_px": 80},
        "expected_tile_count": 12,
        "tiles": qa_rows,
    }
    write(
        f"{output_root}/qa-tiles/qa-tiles-manifest.json",
        _board_json_bytes(qa_manifest),
    )
    bundle_names = (
        "architecture-board-manifest.json",
        "architecture-board-render.json",
        "architecture-board.drawio",
        "architecture-board.md",
        "architecture-board.mmd",
        "architecture-board.svg",
        "source-model.json",
        "architecture-source.mmd",
    )
    source_paths = {
        "source-model.json": source_model_path,
        "architecture-source.mmd": mermaid_path,
    }
    visual_receipt = {
        "schema_version": "1.0",
        "status": "PASS",
        "png": {
            "file": "architecture-board.png",
            "sha256": digest(f"{output_root}/architecture-board.png", prefixed=False),
            "width": 2560,
            "height": 1600,
        },
        "tiles_manifest": {
            "file": "qa-tiles/qa-tiles-manifest.json",
            "sha256": digest(
                f"{output_root}/qa-tiles/qa-tiles-manifest.json", prefixed=False
            ),
        },
        "bundle": [
            {
                "file": name,
                "sha256": digest(
                    source_paths.get(name, f"{output_root}/{name}"),
                    prefixed=False,
                ),
            }
            for name in bundle_names
        ],
        "full_canvas": {
            "status": "PASS",
            "notes": "The full canvas was inspected at original resolution.",
        },
        "checks": [
            {
                "id": name,
                "status": "PASS",
                "notes": f"The {name} visual check passed inspection.",
            }
            for name in EXPECTED_ARCHITECTURE_BOARD_VISUAL_CHECKS
        ],
        "tiles": visual_tiles,
        "completion_rule": "All full-canvas, visual, and tile checks passed.",
    }
    write(
        f"{output_root}/visual-review-receipt.json",
        _board_json_bytes(visual_receipt),
    )
    validation_names = (
        "architecture-board.svg",
        "architecture-board.png",
        "architecture-board.drawio",
        "architecture-board.mmd",
        "architecture-board.md",
        "architecture-board-manifest.json",
        "architecture-board-render.json",
    )
    validation_report = {
        "status": "PASS",
        "contract_id": EXPECTED_ARCHITECTURE_BOARD_CONTRACT_ID,
        "checks": {
            name: True for name in EXPECTED_ARCHITECTURE_BOARD_VALIDATION_CHECKS
        },
        "errors": [],
        "counts": {
            "canonical_components": 2,
            "canonical_relationships": 1,
            "visible_edges": 1,
            "note_relationships": 0,
            "embedded_icon_instances": 2,
            "external_image_dependencies": 0,
            "flow_notes": 6,
        },
        "inventory_sha256": inventory_sha256,
        "png": {
            "width": 2560,
            "height": 1600,
            "sha256": digest(f"{output_root}/architecture-board.png"),
        },
        "routing": {
            "missing_svg_arrowheads": [],
            "missing_drawio_arrowheads": [],
            "duplicate_arrowhead_endpoints": [],
            "overlapping_terminal_segments": [],
        },
        "layering": {
            "svg_layers": list(EXPECTED_ARCHITECTURE_BOARD_LAYERS),
            "text_before_connector_layer": [],
            "unmasked_svg_edge_labels": [],
            "early_drawio_text_cells": [],
            "labeled_drawio_edge_cells": [],
            "svg_edge_label_count": 1,
            "drawio_edge_label_count": 1,
        },
        "boundary_label_collisions": [],
        "boundary_anchor_failures": [],
        "visual_review": {
            "status": "PASS",
            "receipt": "visual-review-receipt.json",
            "png_sha256": digest(
                f"{output_root}/architecture-board.png", prefixed=False
            ),
            "tile_count": 12,
            "findings": [],
        },
        "sha256": {name: digest(f"{output_root}/{name}") for name in validation_names},
    }
    write(
        f"{output_root}/architecture-board-validation.json",
        _board_json_bytes(validation_report),
    )
    return engine_api.capture_architecture_board_completion(root, report, packet)


def _capture_board_snapshot(root: Path, packet: dict[str, object]):
    return engine_api.capture_project_snapshot(root, _board_fixture_paths(packet))


def _mutate_board_json(path: Path, mutate) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_bytes(_board_json_bytes(document))


class EngineDesignTests(unittest.TestCase):
    def test_architecture_board_handoff_is_current_bound_and_non_authorizing(
        self,
    ) -> None:
        report = _architecture_board_report_fixture()
        original = json.dumps(report, sort_keys=True)
        self.assertIn(
            "DIAGRAM_OUTPUT_NOT_AUTHORIZED",
            engine_api.derive_architecture_board_handoff(report)["issues"],
        )
        report["write_authority"]["approved_write_roots"].append("dist/architecture/**")
        handoff = engine_api.derive_architecture_board_handoff(report)
        semantic = report["design_contract"]["diagram_contract"]["records"][0][
            "semantic_sha256"
        ][7:]
        self.assertTrue(handoff["eligible"])
        self.assertEqual(
            handoff["output_root"], f"dist/architecture/DES-0001-{semantic}"
        )
        self.assertEqual(handoff["source"]["diagram_id"], "DIAGRAM-0001")
        self.assertEqual(handoff["cross_check"]["diagram_id"], "DIAGRAM-0008")
        self.assertEqual(
            (handoff["aws_authority"], handoff["external_authority"]),
            ("NONE", "NONE"),
        )
        report["write_authority"]["approved_write_roots"].pop()
        self.assertEqual(json.dumps(report, sort_keys=True), original)

        current = _architecture_board_report_fixture(schema_version=8)
        current["write_authority"]["approved_write_roots"].append(
            "dist/architecture/**"
        )
        self.assertTrue(
            engine_api.derive_architecture_board_handoff(current)["eligible"]
        )

    def test_architecture_board_handoff_fails_closed_without_changing_route(
        self,
    ) -> None:
        fixture = _architecture_board_report_fixture()
        fixture["write_authority"]["approved_write_roots"].append(
            "dist/architecture/**"
        )
        cases = {
            "stale-gate": lambda row: row["gates"].update(gate_b="STALE"),
            "unapproved-design-7": lambda row: row["gates"].update(
                gate_b="PENDING_OWNER_APPROVAL"
            ),
            "partial-design-7": lambda row: row["design_contract"][
                "project_contract"
            ].update(status="MIGRATION_REQUIRED"),
            "unsupported-schema": lambda row: (
                row["design_contract"].update(schema_version=6),
                row["design_contract"]["project_contract"].update(schema_version=6),
            ),
            "mismatched-schema": lambda row: row["design_contract"][
                "project_contract"
            ].update(schema_version=8),
            "incomplete-design-8": lambda row: (
                row["design_contract"].update(schema_version=8),
                row["design_contract"]["project_contract"].update(schema_version=8),
            ),
            "legacy": lambda row: row["design_contract"]["diagram_contract"].update(
                grandfathered_schema5=True
            ),
            "active-task": lambda row: row["write_authority"].update(
                active_task="TASK-0001"
            ),
            "excluded": lambda row: row["write_authority"]["exclusions"].append(
                "dist/**"
            ),
            "protected": lambda row: row["write_authority"]["protected_paths"].append(
                "dist/architecture/**"
            ),
            "no-aws-view": lambda row: row["design_contract"]["diagram_contract"][
                "records"
            ][7].update(status="NOT_APPLICABLE"),
            "bad-digest": lambda row: row["design_contract"]["diagram_contract"][
                "records"
            ][0].update(semantic_sha256="sha256:bad"),
            "empty-relationships": lambda row: row["design_contract"][
                "diagram_contract"
            ]["records"][0].update(relationships=[]),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                candidate = json.loads(json.dumps(fixture))
                route = candidate["next_prompt"]
                mutate(candidate)
                self.assertFalse(
                    engine_api.derive_architecture_board_handoff(candidate)["eligible"]
                )
                self.assertEqual(candidate["next_prompt"], route)

        conflict = json.loads(json.dumps(fixture))
        diagrams = conflict["design_contract"]["diagram_contract"]
        diagrams["records"][7]["referenced_ids"].append("ACT-001")
        diagrams["records"][7]["relationships"] = [
            {"from_id": "TECH-0013", "relation": "reverses", "to_id": "ACT-001"}
        ]
        diagrams["records"][7]["semantic_relationships"] = [
            {
                "from_id": "TECH-0013",
                "edge_kind": "SOLID",
                "relation": "reverses",
                "to_id": "ACT-001",
            }
        ]
        handoff = engine_api.derive_architecture_board_handoff(conflict)
        self.assertEqual(handoff["status"], "SEMANTIC_CONFLICT")
        self.assertEqual(handoff["failure_route"], "DESIGN-10")

        redirect = json.loads(json.dumps(fixture))
        redirect["design_contract"]["diagram_contract"]["records"][7]["relationships"][
            0
        ]["to_id"] = "TECH-0009"
        redirect["design_contract"]["diagram_contract"]["records"][7][
            "semantic_relationships"
        ][0]["to_id"] = "TECH-0009"
        handoff = engine_api.derive_architecture_board_handoff(redirect)
        self.assertEqual(handoff["status"], "SEMANTIC_CONFLICT")
        self.assertEqual(handoff["failure_route"], "DESIGN-10")

    def test_architecture_board_cross_check_requires_semantic_path_parity(
        self,
    ) -> None:
        fixture = _architecture_board_report_fixture()
        fixture["write_authority"]["approved_write_roots"].append(
            "dist/architecture/**"
        )

        def board_records(candidate: dict[str, object]) -> tuple[dict, dict]:
            records = candidate["design_contract"]["diagram_contract"]["records"]
            return records[0], records[7]

        def reverse_direction(candidate: dict[str, object]) -> None:
            _primary, cross = board_records(candidate)
            for key in ("relationships", "semantic_relationships"):
                edge = cross[key][0]
                edge["from_id"], edge["to_id"] = edge["to_id"], edge["from_id"]

        def change_relation(candidate: dict[str, object]) -> None:
            _primary, cross = board_records(candidate)
            for key in ("relationships", "semantic_relationships"):
                cross[key][0]["relation"] = "deploys"

        def use_uncontrolled_relation(candidate: dict[str, object]) -> None:
            _primary, cross = board_records(candidate)
            for key in ("relationships", "semantic_relationships"):
                cross[key][0]["relation"] = "passes through"

        def change_edge_kind(candidate: dict[str, object]) -> None:
            _primary, cross = board_records(candidate)
            cross["semantic_relationships"][0]["edge_kind"] = "SOLID"

        def change_containment(candidate: dict[str, object]) -> None:
            _primary, cross = board_records(candidate)
            cross["containment"][2].remove("TECH-0008")
            cross["containment"][4].append("TECH-0008")

        def add_ambiguous_path(candidate: dict[str, object]) -> None:
            primary, _cross = board_records(candidate)
            additions = (
                ("ARCH-0001", "TECH-0004"),
                ("TECH-0004", "TECH-0011"),
            )
            for source, target in additions:
                primary["relationships"].append(
                    {
                        "from_id": source,
                        "relation": "reads and writes",
                        "to_id": target,
                    }
                )
                primary["semantic_relationships"].append(
                    {
                        "from_id": source,
                        "edge_kind": "SOLID",
                        "relation": "reads and writes",
                        "to_id": target,
                    }
                )

        for name, mutate in {
            "reversed-direction": reverse_direction,
            "wrong-relation-family": change_relation,
            "uncontrolled-relation": use_uncontrolled_relation,
            "wrong-edge-kind": change_edge_kind,
            "wrong-containment": change_containment,
            "ambiguous-path": add_ambiguous_path,
        }.items():
            with self.subTest(name=name):
                candidate = copy.deepcopy(fixture)
                mutate(candidate)
                handoff = engine_api.derive_architecture_board_handoff(candidate)
                self.assertEqual(handoff["status"], "SEMANTIC_CONFLICT")
                self.assertEqual(handoff["failure_route"], "DESIGN-10")

    def test_architecture_board_accepts_controlled_non_fixture_relation_alias(
        self,
    ) -> None:
        fixture = _architecture_board_report_fixture()
        fixture["write_authority"]["approved_write_roots"].append(
            "dist/architecture/**"
        )
        records = fixture["design_contract"]["diagram_contract"]["records"]
        cross = records[7]
        for key in ("relationships", "semantic_relationships"):
            edge = next(
                item
                for item in cross[key]
                if item["from_id"] == "ARCH-0001" and item["to_id"] == "TECH-0014"
            )
            edge["relation"] = "publishes telemetry to"

        handoff = engine_api.derive_architecture_board_handoff(fixture)

        self.assertEqual(
            diagram_relation_category("publishes telemetry to"), "OBSERVABILITY"
        )
        self.assertEqual(diagram_relation_category("sends metrics to"), "OBSERVABILITY")
        self.assertEqual(
            diagram_relation_category("publishes order event to"), "MESSAGING"
        )
        self.assertEqual(
            diagram_relation_category("sends order message to"), "MESSAGING"
        )
        self.assertEqual(
            diagram_relation_category("publishes telemetry event to"),
            "OBSERVABILITY",
        )
        self.assertIsNone(diagram_relation_category("sends request event to"))
        self.assertIsNone(diagram_relation_category("passes through"))
        self.assertTrue(handoff["eligible"], handoff["issues"])

    def test_architecture_board_records_require_canonical_semantic_projection(
        self,
    ) -> None:
        fixture = _architecture_board_report_fixture()
        fixture["write_authority"]["approved_write_roots"].append(
            "dist/architecture/**"
        )

        def duplicate_relationship(candidate: dict[str, object]) -> None:
            record = candidate["design_contract"]["diagram_contract"]["records"][0]
            record["semantic_relationships"].append(
                copy.deepcopy(record["semantic_relationships"][0])
            )

        def duplicate_containment(candidate: dict[str, object]) -> None:
            record = candidate["design_contract"]["diagram_contract"]["records"][0]
            record["containment"].append(copy.deepcopy(record["containment"][1]))

        for name, mutate in {
            "duplicate-relationship": duplicate_relationship,
            "duplicate-containment": duplicate_containment,
        }.items():
            with self.subTest(name=name):
                candidate = copy.deepcopy(fixture)
                mutate(candidate)
                handoff = engine_api.derive_architecture_board_handoff(candidate)
                self.assertEqual(handoff["status"], "INELIGIBLE")
                self.assertIn("SYSTEM_CONTEXT_DIAGRAM_REQUIRED", handoff["issues"])
                self.assertIsNone(handoff["failure_route"])

    def test_architecture_board_unique_path_check_is_bounded_on_dense_graphs(
        self,
    ) -> None:
        nodes = [f"NODE-{index:03d}" for index in range(30)]
        edges = [
            {
                "from_id": source,
                "edge_kind": "SOLID",
                "relation": "invokes",
                "to_id": target,
            }
            for source_index, source in enumerate(nodes)
            for target in nodes[source_index + 1 :]
        ]
        edges.append(
            {
                "from_id": nodes[0],
                "edge_kind": "SOLID",
                "relation": "invokes",
                "to_id": "TARGET",
            }
        )

        path = board_contracts._unique_directed_path(edges, nodes[0], "TARGET")

        self.assertIsNotNone(path)
        self.assertEqual(len(path), 1)

    def test_architecture_board_source_is_exactly_the_approved_mermaid(self) -> None:
        source = (
            "# Record\n\n## Proposed system at a glance\n\n"
            "```mermaid\nflowchart TB\n    A --> B\n```\n\n## Next\n"
        )
        rendered = b"```mermaid\nflowchart TB\n    A --> B\n```\n"
        handoff = {
            "eligible": True,
            "source": {
                "anchor": "proposed-system-at-a-glance",
                "rendered_sha256": "sha256:" + hashlib.sha256(rendered).hexdigest(),
            },
        }
        self.assertEqual(
            engine_api.architecture_board_mermaid_source(source, handoff),
            "flowchart TB\n    A --> B\n",
        )
        handoff["source"]["rendered_sha256"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ValueError, "presentation digest changed"):
            engine_api.architecture_board_mermaid_source(source, handoff)

    def test_architecture_board_request_packet_is_exact_and_fail_closed(self) -> None:
        report = _architecture_board_report_fixture()
        report["write_authority"]["approved_write_roots"].append("dist/architecture/**")
        prd_text = doctor_fixtures.complete_design_contract(
            (REPOSITORY_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        )
        current_design, design_issues = doctor.derive_design_contract(
            prd_text, "DES-0001", required=True
        )
        self.assertEqual(design_issues, [])
        report["design_contract"]["diagram_contract"] = (
            current_design.diagram_contract.to_dict()
        )
        identity = {
            **engine_api.ARCHITECTURE_DIAGRAM_SKILL_IDENTITY,
            "valid": True,
            "issues": [],
        }
        original = json.dumps(report, sort_keys=True)
        packet = engine_api.derive_architecture_board_request_packet(
            report,
            prd_text,
            identity,
            owner_request=engine_api.ARCHITECTURE_BOARD_OWNER_REQUEST,
            source_model_target_exists=False,
        )
        manifest = json.loads(packet["manifest_text"])
        root = engine_api.derive_architecture_board_handoff(report)["output_root"]
        self.assertEqual(packet["manifest"], manifest)
        self.assertEqual(packet["status"], "READY")
        self.assertEqual(packet["resume_route"], "TASK-10")
        self.assertEqual(
            (packet["aws_authority"], packet["external_authority"]),
            ("NONE", "NONE"),
        )
        self.assertEqual(
            packet["manifest_path"],
            f"{root}/architecture-board-task-manifest.json",
        )
        self.assertEqual(packet["mermaid_path"], f"{root}/architecture-source.mmd")
        self.assertEqual(packet["source_model_path"], f"{root}/source-model.json")
        self.assertEqual(
            manifest["approved_mermaid"]["sha256"],
            "sha256:"
            + hashlib.sha256(packet["mermaid_text"].encode("utf-8")).hexdigest(),
        )
        self.assertEqual(
            manifest["authority"],
            {
                "construction_authorization_id": "AUTH-0001",
                "permitted_output_boundary": f"{root}/**",
                "aws": "NONE",
                "external": "NONE",
            },
        )
        self.assertEqual(
            manifest["source_model"],
            {
                "mode": "NEW_DERIVATION",
                "state": "PENDING_DERIVATION",
                "schema_version": 2,
                "target_path": f"{root}/source-model.json",
                "target_must_be_absent": True,
            },
        )
        self.assertEqual(
            manifest["skill"], engine_api.ARCHITECTURE_DIAGRAM_SKILL_IDENTITY
        )
        self.assertNotIn("expected_sha256", packet["manifest_text"])
        self.assertNotIn("source_model_sha256", packet["manifest_text"])
        self.assertEqual(json.dumps(report, sort_keys=True), original)

        failures = (
            (
                "exact owner request",
                report,
                identity,
                "not the exact request",
                False,
            ),
            (
                "skill identity",
                report,
                {**identity, "version": "1.3.0"},
                engine_api.ARCHITECTURE_BOARD_OWNER_REQUEST,
                False,
            ),
            (
                "absent source-model",
                report,
                identity,
                engine_api.ARCHITECTURE_BOARD_OWNER_REQUEST,
                True,
            ),
            (
                "not currently eligible",
                {
                    **report,
                    "write_authority": {
                        **report["write_authority"],
                        "approved_write_roots": ["app/**", "tests/**"],
                    },
                },
                identity,
                engine_api.ARCHITECTURE_BOARD_OWNER_REQUEST,
                False,
            ),
            (
                "project identity",
                {**report, "project": {}},
                identity,
                engine_api.ARCHITECTURE_BOARD_OWNER_REQUEST,
                False,
            ),
        )
        for message, candidate, receipt, request, target_exists in failures:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    engine_api.derive_architecture_board_request_packet(
                        candidate,
                        prd_text,
                        receipt,
                        owner_request=request,
                        source_model_target_exists=target_exists,
                    )

        self.assertEqual(
            engine_api.ARCHITECTURE_BOARD_REQUIRED_OUTPUTS,
            EXPECTED_ARCHITECTURE_BOARD_OUTPUTS,
        )
        self.assertEqual(
            engine_api.ARCHITECTURE_BOARD_QA_TILES,
            EXPECTED_ARCHITECTURE_BOARD_QA_TILES,
        )
        self.assertEqual(
            engine_api._ARCHITECTURE_BOARD_VALIDATION_CHECKS,
            EXPECTED_ARCHITECTURE_BOARD_VALIDATION_CHECKS,
        )
        self.assertEqual(
            engine_api._ARCHITECTURE_BOARD_VISUAL_CHECKS,
            frozenset(EXPECTED_ARCHITECTURE_BOARD_VISUAL_CHECKS),
        )

        with tempfile.TemporaryDirectory() as directory:
            board_root = Path(directory)
            observed = write_architecture_board_completion_fixture(
                board_root, report, packet
            )
            snapshot = _capture_board_snapshot(board_root, packet)
            self.assertEqual(
                engine_api.validate_architecture_board_completion(
                    report, packet, snapshot
                ),
                observed,
            )
            self.assertEqual(len(observed["artifacts"]), 25)
            self.assertEqual(observed["status"], "COMPLETE")
            self.assertEqual(
                observed["evidence_boundary"],
                {
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
                        "contract_id": "aws-architecture-diagrams/v1.3",
                        "reported_check_count": 20,
                        "reported_render_reproduced": True,
                        "status": "PASS_REPORTED_EXECUTION_NOT_AUTHENTICATED",
                    },
                    "icon_provenance": (
                        "DECLARED_PACKAGE_NOT_INDEPENDENTLY_AUTHENTICATED"
                    ),
                },
            )
            self.assertEqual(
                observed["canonical_sha256"],
                engine_api.architecture_board_completion_digest(observed),
            )
            self.assertEqual(
                observed["artifacts"][packet["mermaid_path"]],
                observed["artifacts"][f"{root}/architecture-board.mmd"],
            )

            forged_mermaid = copy.deepcopy(packet)
            forged_mermaid["mermaid_text"] = "flowchart TB\n    WRONG --> BOARD\n"
            forged_manifest = forged_mermaid["manifest"]
            assert isinstance(forged_manifest, dict)
            approved = forged_manifest["approved_mermaid"]
            assert isinstance(approved, dict)
            approved["sha256"] = _board_sha256(
                str(forged_mermaid["mermaid_text"]).encode("utf-8")
            )
            forged_mermaid["manifest_text"] = (
                json.dumps(forged_manifest, indent=2, sort_keys=True) + "\n"
            )
            with self.assertRaisesRegex(ValueError, "request packet is stale"):
                engine_api.validate_architecture_board_completion(
                    report, forged_mermaid, snapshot
                )

            for label, path, value in (
                (
                    "mandatory cross-check",
                    ("mandatory_cross_check", "semantic_sha256"),
                    "sha256:" + "0" * 64,
                ),
                ("skill identity", ("skill", "version"), "0.0.0"),
                ("project identity", ("project", "region"), "eu-west-1"),
                (
                    "source-model target",
                    ("source_model", "target_path"),
                    "../outside/source-model.json",
                ),
            ):
                with self.subTest(packet_binding=label):
                    candidate = copy.deepcopy(packet)
                    candidate_manifest = candidate["manifest"]
                    assert isinstance(candidate_manifest, dict)
                    target: object = candidate_manifest
                    for key in path[:-1]:
                        assert isinstance(target, dict)
                        target = target[key]
                    assert isinstance(target, dict)
                    target[path[-1]] = value
                    candidate["manifest_text"] = (
                        json.dumps(candidate_manifest, indent=2, sort_keys=True) + "\n"
                    )
                    with self.assertRaisesRegex(ValueError, "request packet is stale"):
                        engine_api.validate_architecture_board_completion(
                            report, candidate, snapshot
                        )

            stale_report = copy.deepcopy(report)
            stale_report["gates"]["gate_b"] = "STALE"
            with self.assertRaisesRegex(ValueError, "request packet is not current"):
                engine_api.validate_architecture_board_completion(
                    stale_report, packet, snapshot
                )

            paths = _board_fixture_paths(packet)
            missing = engine_api.capture_project_snapshot(board_root, paths[:-1])
            with self.assertRaisesRegex(ValueError, "observation is incomplete"):
                engine_api.validate_architecture_board_completion(
                    report, packet, missing
                )
            extra_path = f"{root}/unexpected-output.txt"
            (board_root / extra_path).write_text("unexpected\n", encoding="utf-8")
            extra = engine_api.capture_project_snapshot(
                board_root, (*paths, extra_path)
            )
            with self.assertRaisesRegex(ValueError, "observation is incomplete"):
                engine_api.validate_architecture_board_completion(report, packet, extra)

            def changed_json(raw: bytes, mutate) -> bytes:
                document = json.loads(raw.decode("utf-8"))
                mutate(document)
                return _board_json_bytes(document)

            def assert_invalid_artifact(
                relative: str,
                mutate,
                message: str,
            ) -> None:
                target = board_root / relative
                original = target.read_bytes()
                try:
                    target.write_bytes(mutate(original))
                    candidate_snapshot = _capture_board_snapshot(board_root, packet)
                    with self.assertRaisesRegex(ValueError, message):
                        engine_api.validate_architecture_board_completion(
                            report, packet, candidate_snapshot
                        )
                finally:
                    target.write_bytes(original)

            source_model_relative = f"{root}/source-model.json"
            assert_invalid_artifact(
                source_model_relative,
                lambda raw: changed_json(
                    raw, lambda document: document.pop("presentation")
                ),
                "source model schema is invalid",
            )

            def reverse_relationship(document: dict[str, object]) -> None:
                relationships = document["relationships"]
                presentation = document["presentation"]
                assert isinstance(relationships, list)
                assert isinstance(presentation, dict)
                relationship = relationships[0]
                edges = presentation["edges"]
                assert isinstance(relationship, dict)
                assert isinstance(edges, list)
                edge = edges[0]
                assert isinstance(edge, dict)
                relationship["source_id"], relationship["target_id"] = (
                    relationship["target_id"],
                    relationship["source_id"],
                )
                edge["source_terminal"], edge["target_terminal"] = (
                    edge["target_terminal"],
                    edge["source_terminal"],
                )

            assert_invalid_artifact(
                source_model_relative,
                lambda raw: changed_json(raw, reverse_relationship),
                "Mermaid relationship binding changed",
            )
            assert_invalid_artifact(
                source_model_relative,
                lambda raw: changed_json(
                    raw,
                    lambda document: document["presentation"]["edges"][0]["points"][
                        -1
                    ].__setitem__(0, 1281),
                ),
                "edge route is invalid",
            )
            assert_invalid_artifact(
                source_model_relative,
                lambda raw: changed_json(
                    raw,
                    lambda document: document["presentation"]["edges"][0].update(
                        label_at=[600, 801]
                    ),
                ),
                "edge label is invalid",
            )
            assert_invalid_artifact(
                source_model_relative,
                lambda raw: changed_json(
                    raw,
                    lambda document: document["presentation"]["edges"][0].update(
                        source_terminal="TECH-0013"
                    ),
                ),
                "direct edge terminals are invalid",
            )
            assert_invalid_artifact(
                source_model_relative,
                lambda raw: changed_json(
                    raw,
                    lambda document: document["icon_package"].update(
                        source="unverified icon collection"
                    ),
                ),
                "icon package identity is invalid",
            )
            for field, value in (
                ("name", "unverified icon collection"),
                ("release", "not-an-iso-date"),
            ):
                with self.subTest(icon_package_field=field):
                    assert_invalid_artifact(
                        source_model_relative,
                        lambda raw, field=field, value=value: changed_json(
                            raw,
                            lambda document: document["icon_package"].update(
                                {field: value}
                            ),
                        ),
                        "icon package identity is invalid",
                    )
            assert_invalid_artifact(
                f"{root}/architecture-board.svg",
                lambda _raw: b"<svg",
                "SVG XML is invalid",
            )
            assert_invalid_artifact(
                f"{root}/architecture-board.drawio",
                lambda _raw: b"<mxfile",
                "Draw.io XML is invalid",
            )

            def swap_svg_component_icons(raw: bytes) -> bytes:
                svg = ET.fromstring(raw)
                images = [
                    group.find(f"{{{SVG_NAMESPACE}}}image")
                    for group in svg.findall(f".//{{{SVG_NAMESPACE}}}g[@data-record]")
                ]
                self.assertEqual(len(images), 2)
                first, second = images
                self.assertIsNotNone(first)
                self.assertIsNotNone(second)
                assert first is not None and second is not None
                first_href, second_href = first.get("href"), second.get("href")
                self.assertIsNotNone(first_href)
                self.assertIsNotNone(second_href)
                first.set("href", str(second_href))
                second.set("href", str(first_href))
                return ET.tostring(svg, encoding="utf-8")

            assert_invalid_artifact(
                f"{root}/architecture-board.svg",
                swap_svg_component_icons,
                "embedded icon binding changed",
            )

            def swap_drawio_component_icons(raw: bytes) -> bytes:
                drawio = ET.fromstring(raw)
                cells = [
                    item
                    for item in drawio.findall(".//mxCell[@vertex='1']")
                    if item.get("componentRecord")
                ]
                self.assertEqual(len(cells), 2)
                first, second = cells
                first_style, second_style = first.get("style"), second.get("style")
                self.assertIsNotNone(first_style)
                self.assertIsNotNone(second_style)
                first.set("style", str(second_style))
                second.set("style", str(first_style))
                return ET.tostring(drawio, encoding="utf-8")

            assert_invalid_artifact(
                f"{root}/architecture-board.drawio",
                swap_drawio_component_icons,
                "embedded icon binding changed",
            )
            assert_invalid_artifact(
                f"{root}/architecture-board.png",
                lambda _raw: b"not-a-png",
                "is not a PNG",
            )

            def oversized_png_header(raw: bytes) -> bytes:
                oversized = bytearray(raw)
                self.assertEqual(oversized[12:16], b"IHDR")
                oversized[16:24] = struct.pack(">II", 5_000, 5_000)
                oversized[29:33] = struct.pack(
                    ">I", zlib.crc32(oversized[12:29]) & 0xFFFFFFFF
                )
                return bytes(oversized)

            assert_invalid_artifact(
                f"{root}/architecture-board.png",
                oversized_png_header,
                "PNG structure is invalid",
            )

            def overexpanded_png_payload(raw: bytes) -> bytes:
                width, height = struct.unpack(">II", raw[16:24])
                scanline = b"\x00" + b"\xef\xf6\xff\xff" * width
                compressed = zlib.compress(scanline * height + b"\x00", level=9)

                def chunk(kind: bytes, data: bytes) -> bytes:
                    checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
                    return (
                        struct.pack(">I", len(data))
                        + kind
                        + data
                        + struct.pack(">I", checksum)
                    )

                return (
                    b"\x89PNG\r\n\x1a\n"
                    + chunk(b"IHDR", raw[16:29])
                    + chunk(b"IDAT", compressed)
                    + chunk(b"IEND", b"")
                )

            assert_invalid_artifact(
                f"{root}/architecture-board.png",
                overexpanded_png_payload,
                "PNG pixels are invalid",
            )

            def alter_svg_identity(raw: bytes) -> bytes:
                svg = ET.fromstring(raw)
                svg.set("data-source-model-sha256", "sha256:" + "0" * 64)
                return ET.tostring(svg, encoding="utf-8")

            assert_invalid_artifact(
                f"{root}/architecture-board.svg",
                alter_svg_identity,
                "artifact root identity changed",
            )

            def alter_svg_presentation(raw: bytes) -> bytes:
                svg = ET.fromstring(raw)
                ET.SubElement(
                    svg,
                    f"{{{SVG_NAMESPACE}}}circle",
                    {"cx": "20", "cy": "20", "r": "5", "fill": "#000000"},
                )
                return ET.tostring(svg, encoding="utf-8")

            assert_invalid_artifact(
                f"{root}/architecture-board.svg",
                alter_svg_presentation,
                "visible presentation digest changed",
            )
            assert_invalid_artifact(
                f"{root}/qa-tiles/qa-tiles-manifest.json",
                lambda raw: changed_json(
                    raw,
                    lambda document: document["tiles"][0].update(left=999999),
                ),
                "QA tile evidence is invalid",
            )
            for label, mutate in (
                (
                    "missing validation check",
                    lambda document: document["checks"].pop("canvas_png"),
                ),
                (
                    "extra validation check",
                    lambda document: document["checks"].update(unexpected_check=True),
                ),
                (
                    "failed validation check",
                    lambda document: document["checks"].update(canvas_png=False),
                ),
            ):
                with self.subTest(validation_receipt=label):
                    assert_invalid_artifact(
                        f"{root}/architecture-board-validation.json",
                        lambda raw, mutation=mutate: changed_json(raw, mutation),
                        "validation report is not PASS",
                    )
            for label, mutate, message in (
                (
                    "missing bundle row",
                    lambda document: document["bundle"].pop(),
                    "visual review receipt is invalid",
                ),
                (
                    "extra bundle row",
                    lambda document: document["bundle"].append(
                        {"file": "extra.txt", "sha256": "0" * 64}
                    ),
                    "visual review receipt is invalid",
                ),
                (
                    "bundle hash mismatch",
                    lambda document: document["bundle"][0].update(sha256="0" * 64),
                    "visual review receipt is invalid",
                ),
                (
                    "failed visual status",
                    lambda document: document.update(status="FAIL"),
                    "visual review receipt is invalid",
                ),
                (
                    "empty full-canvas notes",
                    lambda document: document["full_canvas"].update(notes=""),
                    "full-canvas notes is invalid",
                ),
                (
                    "empty visual-check notes",
                    lambda document: document["checks"][0].update(notes=""),
                    "visual check notes is invalid",
                ),
                (
                    "empty tile notes",
                    lambda document: document["tiles"][0].update(notes=""),
                    "visual tile notes is invalid",
                ),
            ):
                with self.subTest(visual_receipt=label):
                    assert_invalid_artifact(
                        f"{root}/visual-review-receipt.json",
                        lambda raw, mutation=mutate: changed_json(raw, mutation),
                        message,
                    )

            tile_relative = f"{root}/{EXPECTED_ARCHITECTURE_BOARD_QA_TILES[0]}"
            qa_relative = f"{root}/qa-tiles/qa-tiles-manifest.json"
            visual_relative = f"{root}/visual-review-receipt.json"
            originals = {
                relative: (board_root / relative).read_bytes()
                for relative in (tile_relative, qa_relative, visual_relative)
            }

            def assert_rebound_tile_invalid(wrong_tile: bytes) -> None:
                (board_root / tile_relative).write_bytes(wrong_tile)
                wrong_sha = _board_sha256(wrong_tile, prefixed=False)
                qa_document = json.loads(
                    (board_root / qa_relative).read_text(encoding="utf-8")
                )
                qa_document["tiles"][0]["sha256"] = wrong_sha
                (board_root / qa_relative).write_bytes(_board_json_bytes(qa_document))
                visual_document = json.loads(
                    (board_root / visual_relative).read_text(encoding="utf-8")
                )
                visual_document["tiles"][0]["sha256"] = wrong_sha
                visual_document["tiles_manifest"]["sha256"] = _board_sha256(
                    (board_root / qa_relative).read_bytes(), prefixed=False
                )
                (board_root / visual_relative).write_bytes(
                    _board_json_bytes(visual_document)
                )
                with self.assertRaisesRegex(ValueError, "QA tile evidence is invalid"):
                    engine_api.validate_architecture_board_completion(
                        report, packet, _capture_board_snapshot(board_root, packet)
                    )
                for relative, raw in originals.items():
                    (board_root / relative).write_bytes(raw)

            for label, wrong_tile in (
                ("wrong dimensions", _board_png(721, 613)),
                (
                    "same-size pixel tampering",
                    _board_png(720, 613, rgba=b"\x10\x20\x30\xff"),
                ),
            ):
                with self.subTest(qa_tile=label):
                    try:
                        assert_rebound_tile_invalid(wrong_tile)
                    finally:
                        for relative, raw in originals.items():
                            (board_root / relative).write_bytes(raw)

    def test_mermaid_claim_guard_allows_real_verified_names_and_states(self) -> None:
        for value in (
            "AWS Verified Access",
            "Amazon Verified Permissions",
            "Verified Permissions",
            "Amazon Verified<br/>Permissions",
            "Amazon Verified Permissions<br/>policy evaluation",
            "AWS Verified Access<br/>application access",
            "Amazon API Gateway",
            "AWS Lambda function",
            "Amazon Relational Database Service",
            "AWS CloudFormation stack",
            "Application Load Balancer",
            "AWS Systems Manager",
            "AWS CodeBuild",
            "AWS Config",
            "VERIFIED",
            "AWS SAM CLI deployment and change sets",
            "Infrastructure as code",
            "Recovery path",
            "Recovery plan",
            "Production environment",
            "Release review",
            "Construction envelope",
            "AWS account boundary",
            "Planned deployment path",
            "Account access scope",
            "Proposed account architecture",
            "Deployment validation strategy",
            "Planned deployment and recovery flow",
            "Tests exercise the planned recovery path",
            "Deployment requires separate authorization",
            "Construction permission pending",
            "Gate B approval required",
            "No deployment has occurred",
            "Tests not yet run",
            "Recovery not observed",
            "Recovery not yet observed",
            "AWS access requires owner authorization",
            "Deployment not authorized",
            "No AWS account was accessed",
            "AWS access is not authorized",
            "AWS account access boundary",
            "Deployment will be validated before release",
            "System will be live after deployment",
            "Tests must pass before release",
            "Tests should pass before release",
            "Recovery must be validated",
            "Infrastructure is to be provisioned",
            "AWS access will be authorized separately",
            "Gate B must be approved by the owner",
            "Cloud resources may be created later",
            "Application should remain ready",
            "AWS Budgets",
            "AWS Cost Explorer",
            "AWS Billing and Cost Management",
            "Cost alerts",
            "Monthly cost cap",
            "Budget threshold",
            "Spending limit",
            "Billing boundary",
            "Approval required",
            "Authorization pending",
            "Permission boundary",
            "Consent required",
            "Sign-off pending",
            "Access boundary",
            "Access path",
            "Access request",
            "Access not authorized",
            "Access will be granted",
            "Quality gate required",
            "Authority boundary",
            "Signoff pending",
            "Go-ahead required",
            "Green light pending",
            "R&amp;D boundary",
            "Documented deployment plan",
            "Deployment plan documented",
            "Documented consent workflow",
            "Consent workflow documented",
            "Documented approval path",
            "Approval path documented",
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    design_diagrams._unsafe_visible_mermaid_issues(
                        "DIAGRAM-0001",
                        "node label",
                        value,
                        allow_breaks="<br" in value,
                    ),
                    [],
                )

        for value in (
            "The architecture was deployed and verified",
            "The owner granted AWS access",
            "AWS access was granted",
            "The system is live in AWS",
            "Deployment successful",
            "AWS access confirmed",
            "Gate B passed",
            "Owner consented to AWS deployment",
            "Production operational",
            "AWS account connected",
            "Construction permission active",
            "AWS access enabled",
            "AWS access established",
            "Gate B accepted",
            "Gate B cleared",
            "Owner gave permission for AWS deployment",
            "Deployment worked",
            "Deployment finished",
            "Released to production",
            "AWS resources provisioned",
            "Infrastructure created in AWS",
            "AWS deployment complete",
            "Construction greenlit",
            "Owner signed off AWS deployment",
            "Tests pass",
            "Recovery proven",
            "AWS access available",
            "AWS account linked",
            "Gate B signed off",
            "Owner okayed AWS deployment",
            "Deployment done",
            "Released successfully",
            "Tests green",
            "Recovery validated",
            "Infrastructure ready",
            "Production healthy",
            "AWS session authenticated",
            "Deployment validated",
            "Gate B complete",
            "AWS access ready",
            "Cloud resources running",
            "Planned deployment was successful",
            "Proposed system is live in AWS",
            "Planned AWS access was granted",
            "Proposed Gate B accepted",
            "Planned infrastructure was created in AWS",
            "Planned tests pass",
            "The request was deployed and verified through the runtime",
            "Successful planned deployment",
            "Deployed architecture",
            "Verified architecture",
            "Running cloud resources",
            "Passed tests",
            "Created AWS resources",
            "Gate B approval recorded",
            "Owner approval received",
            "Deployment successful pending review",
            "Tests passed, approval pending",
            "System live while deployment not authorized",
            "AWS access pending and active",
            "Gate B pending and accepted",
            "Deployment not authorized and successful",
            "No AWS access and connected",
            "Architecture and deployed",
            "The architecture is stable and deployed",
            "Planned deployment and successful",
            "AWS access granted while owner approval pending",
            "Deployment was successful without evidence",
            "Deployment was not only successful but verified",
            "AWS access was not only granted but active",
            "No deployment needed because system is live",
            "Deployment complete proposed architecture",
            "Gate B complete planned deployment",
            "AWS access complete proposed state",
            "Deployment not authorized yet successful",
            "Tests not run yet system live",
            "Deployment will fail yet system live",
            "Deployment not authorized though tests passed",
            "Deployment not authorized whereas tests passed",
            "Deployment not authorized nevertheless tests passed",
            "No deployment nonetheless AWS access granted",
            "Deployment not authorized even though tests passed",
            "AWS access verified",
            "AWS access validated",
            "AWS session operational",
            "AWS account verified",
            "AWS credentials active",
            "Cloud account connected",
            "Implementation built",
            "Deployment configured",
            "Application launched",
            "Service started",
            "Production serving traffic",
            "System responding",
            "Application reachable",
            "Service accessible",
            "System functioning",
            "Deployment working",
            "Tests passing",
            "System recovered",
            "Recovery restored",
            "Deployment rolled back",
            "Release published",
            "Infrastructure applied",
            "AWS resources allocated",
            "AWS stack created",
            "Stack deployed",
            "Lambda deployed",
            "API live",
            "Website live",
            "Database ready",
            "Deployment validated result",
            "Tests validated result",
            "System validated result",
            "Deployment validated stack",
            "Recovery validated stack",
            "AWS spend observed",
            "Monthly spending verified",
            "Budget approved",
            "Costs confirmed",
            "AWS charges incurred",
            "Bill paid",
            "Budget available",
            "Cost controls active",
            "Spending reconciled",
            "Approval granted",
            "Authorization confirmed",
            "Permission received",
            "Consent recorded",
            "Sign-off obtained",
            "Owner agreed to deployment",
            "Owner endorsed deployment",
            "Owner signed the approval",
            "Owner permission given",
            "Owner approval documented",
            "Gate B finalized",
            "Owner selected deployment",
            "Owner chose the architecture",
            "Owner waived the restriction",
            "Owner acknowledged approval",
            "Owner-selected deployment mechanism",
            "Owner's selected deployment mechanism",
            "Owner’s selected deployment mechanism",
            "Access granted",
            "Access authorized",
            "Access available",
            "Amazon Cognito<br/>access granted",
            "AWS Verified Access<br/>access granted",
            "Amazon Verified Permissions<br/>access granted",
            "Gate approved",
            "Quality gate passed",
            "Authority granted",
            "Authority confirmed",
            "Signoff obtained",
            "Signoff granted",
            "Go-ahead received",
            "Green light given",
            "Proposed deployment l&#105;ve in AWS",
            "Proposed deployment li\u200bve in AWS",
            "Proposed deployment \uff4c\uff49\uff56\uff45 in AWS",
            "Amazon Verified Permissions AWS access granted",
            "AWS Verified Access deployment successful",
        ):
            with self.subTest(value=value):
                self.assertTrue(
                    design_diagrams._unsafe_visible_mermaid_issues(
                        "DIAGRAM-0001",
                        "node label",
                        value,
                        allow_breaks="<br" in value,
                    )
                )

        for value in (
            "Deployment<br/>successful",
            "AWS access<br/>granted",
            "System<br/>live in AWS",
            "Tests<br/>pass",
            "Recovery<br/>validated",
            "Cloud resources<br/>running",
            "The architecture<br/>was deployed and verified",
            "No deployment<br/>AWS access granted",
            "Deployment not authorized<br/>Tests passed",
            "Recovery not observed<br/>Deployment successful",
            "Tests not run<br/>System live",
            "Deployment will be tested<br/>System live",
            "Tests must pass<br/>AWS access granted",
        ):
            with self.subTest(value=value):
                self.assertTrue(
                    design_diagrams._unsafe_visible_mermaid_issues(
                        "DIAGRAM-0001",
                        "node label",
                        value,
                        allow_breaks=True,
                    )
                )

    def test_digest_neutral_presentation_fields_preserve_1234_positional_models(
        self,
    ) -> None:
        requirements_bytes = b"legacy requirements bytes\n"
        requirements = RequirementsContract(
            "1.4",
            "READY",
            ("ACT-001",),
            ("FR-001",),
            ("JOURNEY-001",),
            ("AC-FR-001",),
            (),
            (),
            (),
            None,
            (),
            (),
            "sha256:" + "a" * 64,
            False,
            requirements_bytes,
        )
        self.assertEqual(requirements.canonical_bytes, requirements_bytes)
        self.assertEqual(requirements.presentation_labels, ())

        project_bytes = b"legacy project design bytes\n"
        project = ProjectDesignContract(
            7,
            "READY",
            None,
            ("API-001",),
            ("BOUNDARY-001",),
            (),
            None,
            None,
            (),
            "sha256:" + "b" * 64,
            False,
            False,
            False,
            project_bytes,
        )
        self.assertEqual(project.canonical_bytes, project_bytes)
        self.assertEqual(project.presentation_labels, ())

    def test_pre_aws_diagram_payload_preserves_exact_1234_shape(self) -> None:
        legacy = design_diagrams._diagram_semantic_payload(
            "SYSTEM_CONTEXT",
            ("ARCH-0001", "FR-001"),
            ("ACT-001", "ARCH-0001"),
            (
                ("ARCH-0001", "DASHED", "serves", "ACT-001"),
                ("ACT-001", "DASHED", "uses", "ARCH-0001"),
                ("ACT-001", "SOLID", "uses", "ARCH-0001"),
            ),
            "flowchart LR\nACT-001 -->|uses| ARCH-0001",
            modern_contract=False,
        )
        self.assertEqual(
            legacy,
            {
                "kind": "SYSTEM_CONTEXT",
                "basis_ids": ["ARCH-0001", "FR-001"],
                "referenced_ids": ["ACT-001", "ARCH-0001"],
                "relationships": [
                    {
                        "from_id": "ACT-001",
                        "relation": "uses",
                        "to_id": "ARCH-0001",
                    },
                ],
            },
        )
        self.assertNotIn("containment", legacy)
        self.assertNotIn("edge_kind", legacy["relationships"][0])
        canonical = (
            json.dumps(
                legacy,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
        self.assertEqual(
            hashlib.sha256(canonical).hexdigest(),
            "2287bc06dffd89d05c847c96c6e336714f984135bd3a19bdecc7567c624a820c",
        )

    def test_legacy_diagram_contract_ignores_dashed_edges_and_keeps_row_order(
        self,
    ) -> None:
        source = """## Document status

| Field | Value |
|---|---|
| Project mode | greenfield |

### Project diagram contract

| Diagram ID | Kind | Applicability | Status | Anchor | Basis IDs | Referenced IDs |
|---|---|---|---|---|---|---|
| DIAGRAM-0002 | PRIMARY_OUTCOME | REQUIRED | CURRENT | primary-view | ARCH-0001 | ACT-001, ARCH-0001 |
| DIAGRAM-0001 | SYSTEM_CONTEXT | REQUIRED | CURRENT | system-view | ARCH-0001 | ACT-001, ARCH-0001 |

### Primary view

```mermaid
flowchart LR
ACT-001 -->|uses| ARCH-0001
ARCH-0001 -. "trusts" .-> ACT-001
```

### System view

```mermaid
flowchart LR
ARCH-0001 -->|serves| ACT-001
ACT-001 -. "trusts" .-> ARCH-0001
```
"""
        architecture = design.ArchitectureContract(
            selection=ArchitectureSelection(
                architecture_id="ARCH-0001",
                selected_candidate="CAND-0001",
                requirement_and_driver_basis="FR-001",
                rationale="Selected legacy design",
                rejected_alternatives="NONE",
                risks="NONE",
                mitigations="NONE",
                security_impact="NONE",
                reliability_impact="NONE",
                operational_burden="NONE",
                cost_effect="NONE",
                breakpoints="NONE",
                migration_path="NONE",
                revisit_triggers="NONE",
                validation="NONE",
            )
        )
        contract, issues = design.derive_diagram_contract(
            source,
            architecture,
            RequirementsContract(requirement_ids=("FR-001",)),
            doctor.CoverageContract(work_kind="NEW_BUILD"),
            required=True,
            grandfathered_schema5=False,
        )

        self.assertEqual(issues, [])
        self.assertEqual(contract.status, "CURRENT")
        self.assertEqual(
            [record.diagram_id for record in contract.records],
            ["DIAGRAM-0002", "DIAGRAM-0001"],
        )
        self.assertEqual(
            contract.records[0].relationships,
            (("ACT-001", "uses", "ARCH-0001"),),
        )
        self.assertEqual(
            contract.records[1].relationships,
            (("ARCH-0001", "serves", "ACT-001"),),
        )
        self.assertEqual(
            [row[0] for row in json.loads(contract.canonical_bytes or b"[]")],
            ["DIAGRAM-0002", "DIAGRAM-0001"],
        )

    def test_migration_diagram_requires_preservation_basis_and_real_design_roles(
        self,
    ) -> None:
        context = design_diagrams._DiagramPresentationContext(
            architecture_id="ARCH-0001",
            requirement_ids=("FR-001",),
            actor_ids=("ACT-001",),
            journey_ids=("JOURNEY-001",),
            use_case_ids=(),
            interface_ids=("API-001",),
            boundary_ids=("BOUNDARY-001",),
            state_ids=(),
            all_aws_ids=frozenset({"TECH-0004", "TECH-0014"}),
            applicable_aws_ids=frozenset({"TECH-0004", "TECH-0014"}),
            current_ids=frozenset(
                {
                    "ARCH-0001",
                    "BOUNDARY-001",
                    "PRES-001",
                    "TECH-0004",
                    "TECH-0014",
                }
            ),
            labels_by_id={},
            styles_by_id={},
            technology_ids_by_concern={},
        )
        unrelated = design_diagrams._diagram_kind_semantic_issues(
            "DIAGRAM-0005",
            "MIGRATION",
            ("PRES-001",),
            {"TECH-0004", "TECH-0014"},
            context,
        )
        self.assertEqual(
            unrelated,
            [
                "DIAGRAM-0005: MIGRATION must show a project boundary",
                "DIAGRAM-0005: MIGRATION must show the selected architecture",
            ],
        )
        self.assertEqual(
            design_diagrams._diagram_kind_semantic_issues(
                "DIAGRAM-0005",
                "MIGRATION",
                ("PRES-001",),
                {"BOUNDARY-001", "ARCH-0001"},
                context,
            ),
            [],
        )

    def test_truthful_long_canonical_label_is_not_an_impossible_gate_blocker(
        self,
    ) -> None:
        label = (
            "Amazon service selected under an owner constraint with a deliberately "
            "long but truthful canonical technical description"
        )
        normalized, issues = design_diagrams._mermaid_label_issues(
            "DIAGRAM-0008", "TECH-0001", label
        )
        self.assertEqual(normalized, label)
        self.assertEqual(issues, [])

        _normalized, issues = design_diagrams._mermaid_label_issues(
            "DIAGRAM-0004",
            "STATE-001",
            "DRAFT<br/>VALIDATED<br/>PUBLISHED<br/>EXPIRED",
        )
        self.assertTrue(any("at most three visual lines" in issue for issue in issues))

        issues = design_diagrams._mermaid_relationship_issues(
            "DIAGRAM-0004",
            (
                "STATE-001 -->|permits only<br/>recorded publication<br/>transitions| STATE-001",
            ),
            presentation_only=True,
        )
        self.assertTrue(
            any("at most two visual lines" in issue for issue in issues),
            issues,
        )

    def test_visible_text_distinguishes_standards_and_plain_colons_from_uris(
        self,
    ) -> None:
        current_ids = ("ACT-001", "TECH-0001")
        for label in (
            "ISO-27001 reviewer",
            "RFC-7231 response handling",
            "Data: owner records",
            "File: upload owner",
            "JavaScript: framework guidance",
        ):
            with self.subTest(safe=label):
                normalized, issues = design_diagrams._mermaid_label_issues(
                    "DIAGRAM-0001",
                    "ACT-001",
                    label,
                    current_ids,
                )
                self.assertEqual(normalized, label)
                self.assertEqual(issues, [])

        for label in (
            "https://example.invalid/track",
            "file:/private/path",
            "javascript:alert(1)",
            "data:text/html,unsafe",
            "www.example.invalid",
        ):
            with self.subTest(unsafe=label):
                _normalized, issues = design_diagrams._mermaid_label_issues(
                    "DIAGRAM-0001",
                    "ACT-001",
                    label,
                    current_ids,
                )
                self.assertTrue(
                    any("external or active URI" in issue for issue in issues),
                    issues,
                )

        _normalized, issues = design_diagrams._mermaid_label_issues(
            "DIAGRAM-0001",
            "ACT-001",
            "Current TECH-0001 runtime",
            current_ids,
        )
        self.assertTrue(any("canonical record ID" in issue for issue in issues))

    def test_public_diagram_evaluator_preserves_1234_call_contract(self) -> None:
        signature = inspect.signature(design.derive_diagram_contract)
        self.assertEqual(
            tuple(signature.parameters),
            (
                "text",
                "architecture",
                "requirements",
                "coverage",
                "required",
                "grandfathered_schema5",
            ),
        )
        contract, issues = design.derive_diagram_contract(
            (REPOSITORY_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8"),
            design.ArchitectureContract(),
            doctor.RequirementsContract(),
            doctor.CoverageContract(),
            required=False,
            grandfathered_schema5=False,
        )
        self.assertEqual(issues, [])
        self.assertEqual(contract.status, "TEMPLATE")

    def test_doctor_facade_delegates_complete_design_to_pure_engine(self) -> None:
        source = doctor_fixtures.complete_design_contract(
            (REPOSITORY_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        )
        captured: dict[str, object] = {}
        evaluator = doctor._derive_design_contract_core

        def capture(*args: object, **kwargs: object):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return evaluator(*args, **kwargs)

        with mock.patch.object(
            doctor, "_derive_design_contract_core", side_effect=capture
        ):
            facade_contract, facade_issues = doctor.derive_design_contract(
                source, "DES-0001", required=True
            )

        core_contract, core_issues = evaluator(
            *captured["args"],
            **captured["kwargs"],  # type: ignore[arg-type]
        )
        self.assertEqual(facade_issues, [])
        self.assertEqual(core_issues, facade_issues)
        self.assertEqual(core_contract.to_dict(), facade_contract.to_dict())
        self.assertIs(evaluator, design.derive_design_contract)
        with self.assertRaises(FrozenInstanceError):
            facade_contract.status = "BLOCKED"  # type: ignore[misc]

    def test_adr_facade_and_observed_source_evaluator_are_exactly_equal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adr_directory = root / "docs/adr"
            adr_directory.mkdir(parents=True)
            (adr_directory / "0001-runtime.md").write_text(
                adr_fixtures.adr_text(), encoding="utf-8"
            )
            contract = adr_fixtures.design_contract()
            facade = fastlane_adr.derive_adr_rationale(root, contract, "")
            inventory, inventory_issues = fastlane_adr._safe_adr_inventory(root)
            sources: dict[str, str] = {}
            source_issues: dict[str, dict[str, str]] = {}
            for relative in inventory.values():
                text, issue = fastlane_adr._read_adr(root, relative)
                if issue is not None:
                    source_issues[relative] = issue
                elif text is not None:
                    sources[relative] = text
            pure = design_adr.derive_adr_rationale(
                contract,
                "",
                inventory,
                sources,
                inventory_issues=inventory_issues,
                source_issues=source_issues,
            )
        self.assertEqual(pure, facade)
        self.assertEqual(pure[0]["status"], "CURRENT")
        self.assertFalse(pure[0]["authoritative"])

    def test_design_domain_has_no_observation_or_sibling_domain_imports(self) -> None:
        forbidden_imports = {
            "boto3",
            "os",
            "requests",
            "socket",
            "subprocess",
            "urllib",
        }
        forbidden_calls = {
            "open",
            "iterdir",
            "read_bytes",
            "read_text",
            "stat",
            "write_bytes",
            "write_text",
        }
        sibling_domains = {"authority", "aws", "define", "deliver"}
        failures: list[str] = []
        for path in sorted(DESIGN_PACKAGE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] in forbidden_imports:
                            failures.append(f"{path.name}: imports {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module.split(".")[0] in forbidden_imports:
                        failures.append(f"{path.name}: imports {module}")
                    if any(part in sibling_domains for part in module.split(".")):
                        failures.append(f"{path.name}: imports sibling {module}")
                elif isinstance(node, ast.Call):
                    if (
                        isinstance(node.func, ast.Name)
                        and node.func.id in forbidden_calls
                    ):
                        failures.append(f"{path.name}: calls {node.func.id}")
                    elif (
                        isinstance(node.func, ast.Attribute)
                        and node.func.attr in forbidden_calls
                    ):
                        failures.append(f"{path.name}: calls {node.func.attr}")
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
