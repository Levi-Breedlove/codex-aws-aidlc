"""Pure binary and XML validation for planned architecture-board artifacts."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import struct
import xml.etree.ElementTree as ET
import zlib
from collections.abc import Mapping
from typing import Any


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _xml(raw: bytes, label: str) -> ET.Element:
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError(f"architecture board {label} XML is unsafe")
    try:
        return ET.fromstring(raw.decode("utf-8"))
    except (UnicodeError, ET.ParseError) as exc:
        raise ValueError(f"architecture board {label} XML is invalid") from exc


def _presentation_sha256(root: ET.Element, kind: str) -> str:
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
            if _local_name(child) in {"title", "desc", "metadata", "defs"}:
                normalized.remove(child)
    else:
        graph = normalized.find(".//mxGraphModel")
        if graph is None:
            raise ValueError("architecture board Draw.io graph is invalid")
        for key in (
            "contractId",
            "sourceModelSha256",
            "sourceMermaidSha256",
            "inventorySha256",
        ):
            graph.attrib.pop(key, None)
    return _sha256(ET.tostring(normalized, encoding="utf-8"))


def _embedded_icon_digest(value: str) -> str:
    prefix = "data:image/svg+xml;base64,"
    if not value.startswith(prefix):
        raise ValueError("architecture board icon is not embedded")
    try:
        raw = base64.b64decode(value.removeprefix(prefix), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("architecture board embedded icon is invalid") from exc
    return _sha256(raw)


def _mermaid_edge_matches(
    line: str, source: str, target: str, label: str, arrow: str
) -> bool:
    edge = re.fullmatch(
        r"([A-Za-z][A-Za-z0-9_-]*)\s*(-->|-\.->)\s*"
        r'(?:\|"?([\s\S]*?)"?\|)?\s*([A-Za-z][A-Za-z0-9_-]*)\s*;?',
        line,
    )
    return bool(
        edge
        and edge.group(1) == source
        and edge.group(2) == arrow
        and " ".join((edge.group(3) or "").split()) == " ".join(label.split())
        and edge.group(4) == target
    )


def _validated_xml_roots(
    svg_raw: bytes,
    drawio_raw: bytes,
    source_model_sha: str,
    source_sha: str,
    model_state: Mapping[str, Any],
    *,
    contract_id: str,
) -> tuple[ET.Element, ET.Element, list[str]]:
    svg = _xml(svg_raw, "SVG")
    drawio = _xml(drawio_raw, "Draw.io")
    graph = drawio.find(".//mxGraphModel")
    render = model_state["render"]
    canvas = render["canvas"]
    if (
        _local_name(svg) != "svg"
        or _local_name(drawio) != "mxfile"
        or graph is None
        or svg.get("data-contract-id") != contract_id
        or graph.get("contractId") != contract_id
        or svg.get("data-source-model-sha256") != source_model_sha
        or graph.get("sourceModelSha256") != source_model_sha
        or svg.get("data-source-mermaid-sha256") != source_sha
        or graph.get("sourceMermaidSha256") != source_sha
        or svg.get("data-inventory-sha256") != model_state["inventory_sha256"]
        or graph.get("inventorySha256") != model_state["inventory_sha256"]
    ):
        raise ValueError("architecture board artifact root identity changed")
    if (
        svg.get("width") != str(canvas["width"])
        or svg.get("height") != str(canvas["height"])
        or svg.get("viewBox") != f"0 0 {canvas['width']} {canvas['height']}"
        or graph.get("pageWidth") != str(canvas["width"])
        or graph.get("pageHeight") != str(canvas["height"])
    ):
        raise ValueError("architecture board artifact canvas changed")
    if any(
        _local_name(item) in {"script", "style", "foreignObject"}
        or bool((item.get("style") or "").strip())
        for item in svg.iter()
    ):
        raise ValueError("architecture board SVG contains unsafe visual content")
    svg_layers = [
        child.get("data-layer") for child in list(svg) if child.get("data-layer")
    ]
    if svg_layers != render["svg_layer_order"]:
        raise ValueError("architecture board SVG layers changed")
    return svg, drawio, svg_layers


def _artifact_inventory(
    svg: ET.Element, drawio: ET.Element
) -> dict[str, list[ET.Element]]:
    return {
        "svg_nodes": [item for item in svg.iter() if item.get("data-record")],
        "draw_nodes": [
            item
            for item in drawio.findall(".//mxCell[@vertex='1']")
            if item.get("componentRecord")
        ],
        "svg_edges": [item for item in svg.iter() if item.get("data-edge")],
        "draw_edges": list(drawio.findall(".//mxCell[@edge='1']")),
        "svg_boundaries": [
            item for item in svg.iter() if item.get("data-boundary-shape")
        ],
        "draw_boundaries": [
            item
            for item in drawio.findall(".//mxCell[@vertex='1']")
            if str(item.get("id", "")).startswith("boundary-")
            and not str(item.get("id", "")).startswith(
                ("boundary-label-", "boundary-icon-")
            )
        ],
    }


def _validate_inventory_membership(
    inventory: Mapping[str, list[ET.Element]], model_state: Mapping[str, Any]
) -> None:
    component_ids = set(model_state["components"])
    edge_ids = {str(row["id"]) for row in model_state["edges"]}
    boundary_ids = {
        key for key, row in model_state["boundaries"].items() if row["rendered"]
    }
    if (
        {str(item.get("data-record")) for item in inventory["svg_nodes"]}
        != component_ids
        or {str(item.get("componentRecord")) for item in inventory["draw_nodes"]}
        != component_ids
        or {str(item.get("data-edge")) for item in inventory["svg_edges"]} != edge_ids
        or {
            str(item.get("id", "")).removeprefix("edge-")
            for item in inventory["draw_edges"]
        }
        != edge_ids
        or {
            str(item.get("data-boundary-shape")) for item in inventory["svg_boundaries"]
        }
        != boundary_ids
        or {
            str(item.get("id", "")).removeprefix("boundary-")
            for item in inventory["draw_boundaries"]
        }
        != boundary_ids
    ):
        raise ValueError("architecture board visible inventory changed")


def _validate_component_bindings(
    inventory: Mapping[str, list[ET.Element]], model_state: Mapping[str, Any]
) -> None:
    for item in inventory["svg_nodes"]:
        record = str(item.get("data-record"))
        expected = _canonical_bytes(model_state["components"][record]).decode().strip()
        if item.get("data-contract") != expected:
            raise ValueError("architecture board SVG component binding changed")
    for item in inventory["draw_nodes"]:
        record = str(item.get("componentRecord"))
        expected = _canonical_bytes(model_state["components"][record]).decode().strip()
        if item.get("contract") != expected:
            raise ValueError("architecture board Draw.io component binding changed")


def _validate_edge_bindings(
    inventory: Mapping[str, list[ET.Element]], model_state: Mapping[str, Any]
) -> None:
    edge_map = {str(row["id"]): row for row in model_state["edges"]}
    for group in inventory["svg_edges"]:
        edge_id = str(group.get("data-edge"))
        expected = _canonical_bytes(edge_map[edge_id]).decode().strip()
        path = next((item for item in group if _local_name(item) == "path"), None)
        if (
            group.get("data-contract") != expected
            or path is None
            or not path.get("marker-end")
        ):
            raise ValueError("architecture board SVG edge binding changed")
    for cell in inventory["draw_edges"]:
        edge_id = str(cell.get("id", "")).removeprefix("edge-")
        expected = _canonical_bytes(edge_map[edge_id]).decode().strip()
        if cell.get("contract") != expected or "endArrow=block" not in str(
            cell.get("style", "")
        ):
            raise ValueError("architecture board Draw.io edge binding changed")


def _validate_icons_and_status(
    svg: ET.Element, drawio: ET.Element, model_state: Mapping[str, Any]
) -> int:
    components = model_state["components"]
    boundaries = model_state["boundaries"]
    assets = model_state["icons"]["assets"]
    images = [item for item in svg.iter() if _local_name(item) == "image"]
    draw_images = _drawio_images(drawio)
    expected_icons = len(components) + sum(
        bool(row.get("icon_key")) for row in boundaries.values()
    )
    if len(images) != expected_icons or len(draw_images) != expected_icons:
        raise ValueError("architecture board embedded icon inventory changed")
    _validate_source_icon_bindings(svg, draw_images, components, boundaries, assets)
    _validate_planned_status(svg, drawio)
    return len(images)


def _drawio_images(drawio: ET.Element) -> list[ET.Element]:
    return [
        item
        for item in drawio.findall(".//mxCell[@vertex='1']")
        if _style(item.get("style", "")).get("shape") == "image"
    ]


def _validate_planned_status(svg: ET.Element, drawio: ET.Element) -> None:
    visible = " ".join(" ".join(svg.itertext()).split())
    draw_values = " ".join(
        str(item.get("value", "")) for item in drawio.findall(".//mxCell")
    )
    if (
        "PLANNED ARCHITECTURE" not in visible
        or "Not deployment or authorization evidence" not in visible
        or "Separate AWS approval required" not in draw_values
    ):
        raise ValueError("architecture board planned-status evidence is missing")


def _validate_source_icon_bindings(
    svg: ET.Element,
    draw_images: list[ET.Element],
    components: Mapping[str, Any],
    boundaries: Mapping[str, Any],
    assets: Mapping[str, Any],
) -> None:
    svg_components = _keyed_elements(svg.iter(), "data-record")
    draw_components = _keyed_elements(draw_images, "componentRecord")
    svg_boundaries = _keyed_elements(svg.iter(), "data-boundary-label")
    draw_boundaries = _keyed_elements(draw_images, "boundaryRecord")
    href_key = "{http://www.w3.org/1999/xlink}href"
    for record, component in components.items():
        _validate_icon_pair(
            svg_components.get(record),
            draw_components.get(record),
            str(assets[component["icon_key"]]),
            href_key,
        )
    for record, boundary in boundaries.items():
        if boundary.get("icon_key"):
            _validate_icon_pair(
                svg_boundaries.get(record),
                draw_boundaries.get(record),
                str(assets[boundary["icon_key"]]),
                href_key,
            )


def _keyed_elements(elements: Any, attribute: str) -> dict[str, ET.Element]:
    return {str(item.get(attribute)): item for item in elements if item.get(attribute)}


def _style(value: str) -> dict[str, str]:
    parts = value.split(";")
    result: dict[str, str] = {}
    index = 0
    while index < len(parts):
        part = parts[index].strip()
        separator = "=" if "=" in part else ":" if ":" in part else None
        if separator is None:
            index += 1
            continue
        key, item = (field.strip() for field in part.split(separator, 1))
        if key == "image" and item == "data:image/svg+xml" and index + 1 < len(parts):
            item += ";" + parts[index + 1]
            index += 1
        result[key] = item
        index += 1
    return result


def _validate_icon_pair(
    svg_group: ET.Element | None,
    draw_cell: ET.Element | None,
    expected_digest: str,
    href_key: str,
) -> None:
    svg_images = (
        [item for item in svg_group if _local_name(item) == "image"]
        if svg_group is not None
        else []
    )
    draw_uri = (
        _style(draw_cell.get("style", "")).get("image", "")
        if draw_cell is not None
        else ""
    )
    if (
        len(svg_images) != 1
        or draw_cell is None
        or _embedded_icon_digest(
            svg_images[0].get("href") or svg_images[0].get(href_key) or ""
        )
        != expected_digest
        or _embedded_icon_digest(draw_uri) != expected_digest
    ):
        raise ValueError("architecture board embedded icon binding changed")


def _validate_actual_xml(
    svg_raw: bytes,
    drawio_raw: bytes,
    source_model_sha: str,
    source_sha: str,
    model_state: Mapping[str, Any],
    *,
    contract_id: str,
) -> dict[str, Any]:
    svg, drawio, svg_layers = _validated_xml_roots(
        svg_raw,
        drawio_raw,
        source_model_sha,
        source_sha,
        model_state,
        contract_id=contract_id,
    )
    inventory = _artifact_inventory(svg, drawio)
    _validate_inventory_membership(inventory, model_state)
    _validate_component_bindings(inventory, model_state)
    _validate_edge_bindings(inventory, model_state)
    icon_count = _validate_icons_and_status(svg, drawio, model_state)
    render = model_state["render"]
    if (
        _presentation_sha256(svg, "svg") != render["svg_presentation_sha256"]
        or _presentation_sha256(drawio, "drawio")
        != render["drawio_presentation_sha256"]
    ):
        raise ValueError("architecture board visible presentation digest changed")
    return {
        "svg": svg,
        "drawio": drawio,
        "icon_count": icon_count,
        "svg_layers": svg_layers,
        "svg_edge_labels": len(
            [item for item in svg.iter() if item.get("data-edge-label")]
        ),
        "drawio_edge_labels": len(
            [
                item
                for item in drawio.findall(".//mxCell")
                if str(item.get("id", "")).startswith("edge-label-")
            ]
        ),
    }


def _png_payload(raw: bytes, label: str) -> tuple[int, int, bytes]:
    if len(raw) < 45 or raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"architecture board {label} is not a PNG")
    offset = 8
    chunks: list[bytes] = []
    compressed = bytearray()
    width = height = 0
    header: tuple[int, ...] | None = None
    while offset + 12 <= len(raw):
        length = struct.unpack(">I", raw[offset : offset + 4])[0]
        kind = raw[offset + 4 : offset + 8]
        end = offset + 12 + length
        if end > len(raw):
            raise ValueError(f"architecture board {label} PNG is truncated")
        data = raw[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", raw[offset + 8 + length : end])[0]
        if zlib.crc32(kind + data) & 0xFFFFFFFF != expected_crc:
            raise ValueError(f"architecture board {label} PNG checksum is invalid")
        chunks.append(kind)
        if kind == b"IHDR":
            if length != 13 or chunks != [b"IHDR"]:
                raise ValueError(f"architecture board {label} PNG header is invalid")
            header = struct.unpack(">IIBBBBB", data)
            width, height = header[:2]
        elif kind == b"IDAT":
            compressed.extend(data)
        offset = end
        if kind == b"IEND":
            break
    if (
        offset != len(raw)
        or chunks[-1:] != [b"IEND"]
        or b"IDAT" not in chunks
        or width <= 0
        or height <= 0
        or width * height > 20_000_000
        or header is None
        or header[2:] != (8, 6, 0, 0, 0)
    ):
        raise ValueError(f"architecture board {label} PNG structure is invalid")
    return width, height, bytes(compressed)


def _png_rgba(raw: bytes, label: str) -> tuple[int, int, bytes]:
    width, height, compressed = _png_payload(raw, label)
    stride = width * 4
    expected_size = height * (stride + 1)
    decoder = zlib.decompressobj()
    try:
        scanlines = decoder.decompress(compressed, expected_size + 1)
    except zlib.error as exc:
        raise ValueError(f"architecture board {label} PNG pixels are invalid") from exc
    if (
        len(scanlines) != expected_size
        or decoder.unconsumed_tail
        or decoder.unused_data
        or not decoder.eof
    ):
        raise ValueError(f"architecture board {label} PNG pixels are invalid")
    return width, height, _decoded_png_pixels(scanlines, width, height, label)


def _decoded_png_pixels(scanlines: bytes, width: int, height: int, label: str) -> bytes:
    stride = width * 4
    pixels = bytearray()
    previous = bytearray(stride)
    for row_index in range(height):
        start = row_index * (stride + 1)
        filter_type = scanlines[start]
        row = bytearray(scanlines[start + 1 : start + stride + 1])
        _unfilter_png_row(row, previous, filter_type, label)
        pixels.extend(row)
        previous = row
    return bytes(pixels)


def _unfilter_png_row(
    row: bytearray, previous: bytearray, filter_type: int, label: str
) -> None:
    if filter_type == 0:
        return
    if filter_type not in {1, 2, 3, 4}:
        raise ValueError(f"architecture board {label} PNG filter is invalid")
    for index, value in enumerate(row):
        left = row[index - 4] if index >= 4 else 0
        above = previous[index]
        upper_left = previous[index - 4] if index >= 4 else 0
        if filter_type == 1:
            predictor = left
        elif filter_type == 2:
            predictor = above
        elif filter_type == 3:
            predictor = (left + above) // 2
        else:
            estimate = left + above - upper_left
            distances = (
                abs(estimate - left),
                abs(estimate - above),
                abs(estimate - upper_left),
            )
            predictor = (left, above, upper_left)[distances.index(min(distances))]
        row[index] = (value + predictor) & 0xFF


def _png_dimensions(raw: bytes, label: str) -> tuple[int, int]:
    width, height, _pixels = _png_rgba(raw, label)
    return width, height


def _rgba_crop(
    pixels: bytes,
    source_width: int,
    left: int,
    top: int,
    width: int,
    height: int,
) -> bytes:
    return b"".join(
        pixels[
            ((top + row) * source_width + left) * 4 : (
                (top + row) * source_width + left + width
            )
            * 4
        ]
        for row in range(height)
    )


def _markdown_bytes(
    model: Mapping[str, Any], mermaid_raw: bytes, *, contract_id: str
) -> bytes:
    source = mermaid_raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    source = source.rstrip("\n")
    notice = "PLANNED ARCHITECTURE — Not deployment or authorization evidence."
    return (
        "# Planned AWS architecture board\n\n"
        f"> **{notice}**\n\n"
        f"Semantic source: `{model['source']['path']}`  \n"
        f"Contract: `{contract_id}`  \n"
        f"Source SHA-256: `{model['source']['sha256']}`\n\n"
        "```mermaid\n"
        f"{source}\n"
        "```\n"
    ).encode("utf-8")


__all__ = (
    "_markdown_bytes",
    "_mermaid_edge_matches",
    "_png_dimensions",
    "_png_rgba",
    "_rgba_crop",
    "_validate_actual_xml",
)
