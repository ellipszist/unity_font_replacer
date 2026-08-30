"""Length-preserving updates for legacy Addressables JSON catalogs."""

from __future__ import annotations

import base64
import json
import os
import re
import struct
from typing import Any, Iterable, Mapping


_JSON_OBJECT_TYPE = 7
_ENTRY_FIELD_COUNT = 7
_CRC_PATTERN = re.compile(r'("m_Crc"\s*:\s*)-?\d+')
_BUNDLE_SIZE_PATTERN = re.compile(r'("m_BundleSize"\s*:\s*)-?\d+')


def _read_i32(data: bytes | bytearray, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise ValueError(f"catalog int32 offset is out of range: {offset}")
    return struct.unpack_from("<i", data, offset)[0]


def _read_json_record(
    extra_data: bytes | bytearray,
    offset: int,
) -> dict[str, Any] | None:
    if offset < 0 or offset >= len(extra_data):
        raise ValueError(f"catalog extra-data offset is out of range: {offset}")
    cursor = offset
    object_type = extra_data[cursor]
    cursor += 1
    if object_type != _JSON_OBJECT_TYPE:
        return None

    if cursor >= len(extra_data):
        raise ValueError("truncated catalog assembly-name length")
    assembly_length = extra_data[cursor]
    cursor += 1
    assembly_end = cursor + assembly_length
    if assembly_end > len(extra_data):
        raise ValueError("truncated catalog assembly name")
    assembly_name = bytes(extra_data[cursor:assembly_end]).decode("ascii")
    cursor = assembly_end

    if cursor >= len(extra_data):
        raise ValueError("truncated catalog class-name length")
    class_length = extra_data[cursor]
    cursor += 1
    class_end = cursor + class_length
    if class_end > len(extra_data):
        raise ValueError("truncated catalog class name")
    class_name = bytes(extra_data[cursor:class_end]).decode("ascii")
    cursor = class_end

    json_length = _read_i32(extra_data, cursor)
    cursor += 4
    if json_length < 0 or json_length % 2 != 0:
        raise ValueError(f"invalid UTF-16 catalog JSON length: {json_length}")
    json_end = cursor + json_length
    if json_end > len(extra_data):
        raise ValueError("truncated catalog JSON payload")
    json_text = bytes(extra_data[cursor:json_end]).decode("utf-16-le")
    try:
        value = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid catalog JSON object at offset {offset}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"catalog JSON object is not a dictionary at offset {offset}")
    return {
        "offset": offset,
        "assembly_name": assembly_name,
        "class_name": class_name,
        "json_start": cursor,
        "json_length": json_length,
        "json_text": json_text,
        "value": value,
    }


def _catalog_extra_data_references(entry_data: bytes) -> dict[int, set[int]]:
    entry_count = _read_i32(entry_data, 0)
    if entry_count < 0:
        raise ValueError(f"negative Addressables entry count: {entry_count}")
    expected_size = 4 + entry_count * _ENTRY_FIELD_COUNT * 4
    if expected_size > len(entry_data):
        raise ValueError(
            "truncated Addressables entry data: "
            f"expected at least {expected_size}, got {len(entry_data)}"
        )
    references: dict[int, set[int]] = {}
    for entry_index in range(entry_count):
        base = 4 + entry_index * _ENTRY_FIELD_COUNT * 4
        internal_id_index = _read_i32(entry_data, base)
        data_offset = _read_i32(entry_data, base + 4 * 4)
        if data_offset < 0:
            continue
        references.setdefault(data_offset, set()).add(internal_id_index)
    return references


def inspect_addressables_bundle_options(catalog_bytes: bytes) -> list[dict[str, Any]]:
    """Parse AssetBundleRequestOptions records from a legacy JSON catalog."""
    try:
        catalog = json.loads(catalog_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid Addressables catalog JSON: {exc}") from exc
    if not isinstance(catalog, dict):
        raise ValueError("Addressables catalog root must be an object")
    try:
        entry_data = base64.b64decode(catalog["m_EntryDataString"], validate=True)
        extra_data = base64.b64decode(catalog["m_ExtraDataString"], validate=True)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("catalog is missing valid compact entry/extra data") from exc

    internal_ids = catalog.get("m_InternalIds", [])
    if not isinstance(internal_ids, list):
        internal_ids = []
    records: list[dict[str, Any]] = []
    for offset, internal_id_indices in _catalog_extra_data_references(
        entry_data
    ).items():
        record = _read_json_record(extra_data, offset)
        if record is None:
            continue
        value = record["value"]
        if not (
            str(record["class_name"]).endswith("AssetBundleRequestOptions")
            or ("m_BundleName" in value and "m_Crc" in value)
        ):
            continue
        record["internal_ids"] = [
            str(internal_ids[index])
            for index in sorted(internal_id_indices)
            if 0 <= index < len(internal_ids)
        ]
        records.append(record)
    return records


def patch_addressables_catalog_bytes(
    catalog_bytes: bytes,
    bundle_sizes: Mapping[str, int],
) -> tuple[bytes, list[str]]:
    """Set CRC to zero and synchronize size without changing compact offsets."""
    normalized_sizes: dict[str, int] = {}
    for bundle_name, bundle_size in bundle_sizes.items():
        normalized_name = os.path.basename(str(bundle_name).replace("\\", "/")).casefold()
        if not normalized_name:
            continue
        size = int(bundle_size)
        if size < 0:
            raise ValueError(f"negative bundle size for {bundle_name}: {size}")
        previous = normalized_sizes.get(normalized_name)
        if previous is not None and previous != size:
            raise ValueError(f"ambiguous bundle size for duplicate name: {bundle_name}")
        normalized_sizes[normalized_name] = size

    try:
        catalog = json.loads(catalog_bytes.decode("utf-8-sig"))
        old_extra_string = catalog["m_ExtraDataString"]
        entry_data = base64.b64decode(catalog["m_EntryDataString"], validate=True)
        extra_data = bytearray(base64.b64decode(old_extra_string, validate=True))
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid compact Addressables catalog: {exc}") from exc

    internal_ids = catalog.get("m_InternalIds", [])
    if not isinstance(internal_ids, list):
        internal_ids = []
    patched_names: list[str] = []
    for offset, internal_id_indices in _catalog_extra_data_references(
        entry_data
    ).items():
        record = _read_json_record(extra_data, offset)
        if record is None:
            continue
        value = record["value"]
        serialized_bundle_name = os.path.basename(
            str(value.get("m_BundleName", "")).replace("\\", "/")
        )
        candidate_names = {serialized_bundle_name.casefold()}
        for internal_id_index in internal_id_indices:
            if 0 <= internal_id_index < len(internal_ids):
                candidate_names.add(
                    os.path.basename(
                        str(internal_ids[internal_id_index]).replace("\\", "/")
                    ).casefold()
                )
        matching_names = sorted(candidate_names & normalized_sizes.keys())
        if not matching_names:
            continue
        matching_sizes = {normalized_sizes[name] for name in matching_names}
        if len(matching_sizes) != 1:
            raise ValueError(
                "one catalog record matched multiple bundle sizes: "
                + ", ".join(matching_names)
            )
        normalized_name = matching_names[0]
        bundle_name = normalized_name
        if "m_Crc" not in value or "m_BundleSize" not in value:
            raise ValueError(
                f"bundle options record lacks CRC/size fields: {bundle_name}"
            )

        json_text = str(record["json_text"])
        patched_text, crc_count = _CRC_PATTERN.subn(r"\g<1>0", json_text, count=1)
        patched_text, size_count = _BUNDLE_SIZE_PATTERN.subn(
            lambda match: f"{match.group(1)}{normalized_sizes[normalized_name]}",
            patched_text,
            count=1,
        )
        if crc_count != 1 or size_count != 1:
            raise ValueError(f"could not patch bundle options JSON: {bundle_name}")

        patched_json = patched_text.encode("utf-16-le")
        original_length = int(record["json_length"])
        if len(patched_json) > original_length:
            raise ValueError(
                "updated bundle options do not fit the fixed catalog record; "
                f"preserve bundle compression for {bundle_name}"
            )
        remaining = original_length - len(patched_json)
        if remaining % 2 != 0:
            raise ValueError("catalog UTF-16 padding length is not aligned")
        patched_json += " ".encode("utf-16-le") * (remaining // 2)
        json_start = int(record["json_start"])
        extra_data[json_start : json_start + original_length] = patched_json
        patched_names.extend(matching_names)

    if not patched_names:
        return catalog_bytes, []

    new_extra_string = base64.b64encode(extra_data).decode("ascii")
    if len(new_extra_string) != len(old_extra_string):
        raise ValueError("length-preserving catalog update changed base64 length")
    old_extra_bytes = old_extra_string.encode("ascii")
    if catalog_bytes.count(old_extra_bytes) != 1:
        raise ValueError("catalog extra-data string was not uniquely identifiable")
    patched_catalog = catalog_bytes.replace(
        old_extra_bytes,
        new_extra_string.encode("ascii"),
        1,
    )

    verified_records = inspect_addressables_bundle_options(patched_catalog)
    verified_by_name: dict[str, dict[str, Any]] = {}
    for record in verified_records:
        value = record["value"]
        names = [str(value.get("m_BundleName", "")), *record.get("internal_ids", [])]
        for name in names:
            normalized_name = os.path.basename(name.replace("\\", "/")).casefold()
            if normalized_name:
                verified_by_name[normalized_name] = value
    for patched_name in patched_names:
        verified = verified_by_name.get(patched_name.casefold())
        if not isinstance(verified, dict):
            raise ValueError(f"patched catalog record disappeared: {patched_name}")
        if int(verified.get("m_Crc", -1)) != 0:
            raise ValueError(f"catalog CRC verification failed: {patched_name}")
        if int(verified.get("m_BundleSize", -1)) != normalized_sizes[
            patched_name.casefold()
        ]:
            raise ValueError(f"catalog bundle-size verification failed: {patched_name}")
    return patched_catalog, patched_names


def validate_local_addressables_bundle_load(
    catalog_path: str,
    catalog_bytes: bytes,
    bundle_names: Iterable[str],
) -> None:
    """Prove that matched bundles use Addressables' local-file load path.

    Local standalone bundles are loaded with ``AssetBundle.LoadFromFileAsync``;
    their catalog hash is not a content-integrity input.  Remote, archive-backed,
    and forced-UWR bundles use different cache/hash contracts and are refused.
    """
    settings_path = os.path.join(os.path.dirname(catalog_path), "settings.json")
    try:
        with open(settings_path, "r", encoding="utf-8-sig") as stream:
            settings = json.load(stream)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"could not read Addressables settings next to catalog: {settings_path}"
        ) from exc
    if not isinstance(settings, dict):
        raise ValueError(f"Addressables settings root must be an object: {settings_path}")
    build_target = str(
        settings.get("m_buildTarget", settings.get("m_BuildTarget", ""))
    ).strip()
    if not build_target.casefold().startswith("standalone"):
        raise ValueError(
            "Addressables catalog rewriting is limited to proven local standalone "
            f"loads; build target is {build_target or '<missing>'}"
        )

    normalized_names = {
        os.path.basename(str(name).replace("\\", "/")).casefold()
        for name in bundle_names
        if os.path.basename(str(name).replace("\\", "/"))
    }
    matched_names: set[str] = set()
    runtime_prefix = (
        "{unityengine.addressableassets.addressables.runtimepath}/"
    )
    for record in inspect_addressables_bundle_options(catalog_bytes):
        value = record["value"]
        serialized_name = os.path.basename(
            str(value.get("m_BundleName", "")).replace("\\", "/")
        ).casefold()
        internal_ids = [str(item) for item in record.get("internal_ids", [])]
        candidate_names = {serialized_name}
        candidate_names.update(
            os.path.basename(value.replace("\\", "/")).casefold()
            for value in internal_ids
        )
        record_matches = candidate_names & normalized_names
        if not record_matches:
            continue
        matched_names.update(record_matches)

        use_uwr = value.get(
            "m_UseUnityWebRequestForLocalBundles",
            value.get("m_UseUWRForLocalBundles", False),
        )
        if use_uwr is True or str(use_uwr).strip().casefold() in {"1", "true"}:
            raise ValueError(
                "Addressables bundle forces UnityWebRequest for local files; its "
                "hash/cache contract cannot be updated safely"
            )
        matching_internal_ids = [
            internal_id
            for internal_id in internal_ids
            if os.path.basename(internal_id.replace("\\", "/")).casefold()
            in record_matches
        ]
        if not matching_internal_ids:
            raise ValueError(
                "Addressables bundle record has no matching internal ID; local-file "
                "loading cannot be proven"
            )
        for internal_id in matching_internal_ids:
            normalized_id = internal_id.replace("\\", "/").strip().casefold()
            if not normalized_id.startswith(runtime_prefix):
                raise ValueError(
                    "Addressables bundle does not use the local RuntimePath contract: "
                    f"{internal_id}"
                )

    missing_names = sorted(normalized_names - matched_names)
    if missing_names:
        raise ValueError(
            "Addressables local-file contract was not found for bundle(s): "
            + ", ".join(missing_names)
        )


def find_addressables_catalogs(data_path: str) -> list[str]:
    """Find local Addressables JSON catalogs under a game's Data directory."""
    catalogs: list[str] = []
    for root, _dirs, files in os.walk(data_path):
        normalized_files = {filename.casefold() for filename in files}
        if "settings.json" not in normalized_files:
            continue
        for filename in files:
            if filename.casefold() == "catalog.json":
                catalogs.append(os.path.join(root, filename))
    return sorted(catalogs)
