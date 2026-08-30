import copy
import math
import re
from collections.abc import Iterable
from functools import lru_cache
from typing import Any, Literal, cast

JsonDict = dict[str, Any]

# KR: Unity-Runtime-Libraries reports/sdf_font 분석 기준 경계 버전
#     구 스키마(old)만 지원하는 마지막 버전
# EN: Unity-Runtime-Libraries reports/sdf_font analysis boundary versions
#     Last version supporting only old schema
_TMP_OLD_ONLY_LAST = (2018, 3, 14)
# KR: 신 스키마(new)가 처음 도입된 버전
# EN: First version introducing new schema
_TMP_NEW_SCHEMA_FIRST = (2018, 4, 2)
# KR: TMP 폰트 에셋 생성 설정 키 (버전별로 다른 이름 사용)
# EN: TMP font asset creation settings key (different names per version)
_TMP_CREATION_SETTINGS_KEYS = (
    "fontCreationSettings",
    "m_CreationSettings",
    "m_FontAssetCreationSettings",
    "m_fontAssetCreationEditorSettings",
)


def ensure_int(data: JsonDict | None, keys: Iterable[str]) -> None:
    """KR: 딕셔너리의 지정 키 값을 int로 강제 변환합니다.
    EN: Force-converts the specified key values in a dictionary to int.
    """
    if not data:
        return
    for key in keys:
        if key in data and data[key] is not None:
            data[key] = int(data[key])


@lru_cache(maxsize=256)
def _parse_unity_version_triplet(version_text: str) -> tuple[int, int, int] | None:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", version_text or "")
    if not match:
        return None
    try:
        return int(match.group(1)), int(match.group(2)), int(match.group(3))
    except Exception:
        return None


def _resolve_creation_settings_key(
    data: JsonDict, unity_version: str | None = None
) -> str | None:
    """KR: 타겟 딕셔너리에서 creation settings 키를 판별합니다.
    EN: Identifies the creation settings key in the target dictionary.
    """
    for key in _TMP_CREATION_SETTINGS_KEYS:
        if isinstance(data.get(key), dict):
            return key
    # TMP_Info is analysis evidence, not a runtime dependency. The parsed key
    # shape is authoritative and avoids loading the multi-megabyte report.
    return None


def _sync_creation_settings_payload(
    creation_settings: JsonDict,
    atlas_width: int,
    atlas_height: int,
    padding: int,
    point_size: int,
    render_mode: int | None = None,
) -> None:
    """KR: creation settings 내부 키 패턴을 감지해 atlas/pointSize를 동기화합니다.
    EN: Detects key patterns inside creation settings and syncs atlas/pointSize.
    """
    for key in list(creation_settings.keys()):
        normalized = key.replace("_", "").lower()
        if "atlaswidth" in normalized:
            creation_settings[key] = int(atlas_width)
        elif "atlasheight" in normalized:
            creation_settings[key] = int(atlas_height)
        elif normalized.endswith("padding") or normalized == "padding":
            creation_settings[key] = int(padding)
        elif normalized.endswith("pointsize") or normalized in {
            "pointsize",
            "fontsize",
        }:
            creation_settings[key] = int(point_size)
        elif render_mode is not None and normalized.endswith("rendermode"):
            creation_settings[key] = int(render_mode)


def _sync_existing_record_table(target: Any, replacement: Any) -> None:
    """Sync only existing record-list fields, clearing stale glyph references."""
    if not isinstance(target, dict):
        return
    replacement_dict = replacement if isinstance(replacement, dict) else {}
    for key in list(target.keys()):
        current_value = target.get(key)
        replacement_value = replacement_dict.get(key)
        if isinstance(current_value, list):
            target[key] = (
                copy.deepcopy(replacement_value)
                if isinstance(replacement_value, list)
                else []
            )
        elif isinstance(current_value, dict) and isinstance(replacement_value, dict):
            _sync_existing_record_table(current_value, replacement_value)


def _legacy_value_record(value: Any, *, x_advance: float = 0.0) -> JsonDict:
    """Return the union shape used by every serialized legacy TMP value record."""
    record = copy.deepcopy(value) if isinstance(value, dict) else {}
    record.setdefault("xPlacement", 0.0)
    record.setdefault("yPlacement", 0.0)
    record.setdefault("xAdvance", float(x_advance))
    record.setdefault("yAdvance", 0.0)
    return record


def _modern_value_record(value: Any) -> JsonDict:
    """Fill zero-valued TextCore fields commonly omitted from YAML fixtures."""
    record = copy.deepcopy(value) if isinstance(value, dict) else {}
    record.setdefault("m_XPlacement", 0.0)
    record.setdefault("m_YPlacement", 0.0)
    record.setdefault("m_XAdvance", 0.0)
    record.setdefault("m_YAdvance", 0.0)
    return record


def _coerce_serialized_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1"}:
            return True
        if normalized in {"false", "0"}:
            return False
    raise ValueError(f"Invalid serialized boolean for {field_name}: {value!r}")


def _coerce_matching_alias(pair: JsonDict, old_key: str, new_key: str) -> int:
    old_present = old_key in pair
    new_present = new_key in pair
    try:
        old_value = int(pair[old_key]) if old_present else None
        new_value = int(pair[new_key]) if new_present else None
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"Invalid TMP kerning glyph alias: {old_key}/{new_key}") from exc
    if old_value is not None and new_value is not None and old_value != new_value:
        raise ValueError(
            f"Conflicting TMP kerning glyph aliases: {old_key}={old_value}, "
            f"{new_key}={new_value}"
        )
    resolved = old_value if old_value is not None else new_value
    if resolved is None or resolved < 0:
        raise ValueError(f"Missing or invalid TMP kerning glyph: {old_key}/{new_key}")
    pair[old_key] = resolved
    pair[new_key] = resolved
    return resolved


def _normalize_legacy_kerning_pair(value: Any) -> JsonDict:
    """Canonicalize the 3-field and expanded TMP KerningPair generations."""
    if not isinstance(value, dict):
        raise ValueError("TMP kerning pair must be an object")
    pair = copy.deepcopy(value)
    _coerce_matching_alias(pair, "AscII_Left", "m_FirstGlyph")
    _coerce_matching_alias(pair, "AscII_Right", "m_SecondGlyph")

    first_adjustments = pair.get("m_FirstGlyphAdjustments")
    adjustment_advance: float | None = None
    if isinstance(first_adjustments, dict) and "xAdvance" in first_adjustments:
        try:
            adjustment_advance = float(first_adjustments["xAdvance"])
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Invalid TMP legacy first-glyph xAdvance") from exc
    try:
        legacy_advance = (
            float(pair["XadvanceOffset"])
            if "XadvanceOffset" in pair
            else None
        )
        migrated_advance = float(pair["xOffset"]) if "xOffset" in pair else None
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Invalid TMP legacy kerning advance") from exc

    candidates = (
        ("XadvanceOffset", legacy_advance),
        ("xOffset", migrated_advance),
        ("m_FirstGlyphAdjustments.xAdvance", adjustment_advance),
    )
    nonzero_candidates = [
        (name, candidate)
        for name, candidate in candidates
        if candidate not in (None, 0.0)
    ]
    if nonzero_candidates:
        resolved_advance = float(nonzero_candidates[0][1])
        for name, candidate in nonzero_candidates[1:]:
            assert candidate is not None
            if not math.isclose(
                resolved_advance,
                float(candidate),
                rel_tol=0.0,
                abs_tol=1e-6,
            ):
                raise ValueError(
                    "Conflicting TMP legacy kerning advances: "
                    f"{nonzero_candidates[0][0]}={resolved_advance}, "
                    f"{name}={candidate}"
                )
    else:
        resolved_advance = float(
            next(
                (candidate for _, candidate in candidates if candidate is not None),
                0.0,
            )
        )

    # TMP 1.0.25 promoted XadvanceOffset into xOffset and then into the first
    # value record at runtime. Keep all generations coherent so whichever
    # subset the target TypeTree serializes carries the same adjustment.
    pair["XadvanceOffset"] = resolved_advance
    pair["xOffset"] = resolved_advance
    normalized_first = _legacy_value_record(
        first_adjustments,
        x_advance=resolved_advance,
    )
    normalized_first["xAdvance"] = resolved_advance
    pair["m_FirstGlyphAdjustments"] = normalized_first
    pair["m_SecondGlyphAdjustments"] = _legacy_value_record(
        pair.get("m_SecondGlyphAdjustments")
    )
    pair["m_IgnoreSpacingAdjustments"] = _coerce_serialized_bool(
        pair.get("m_IgnoreSpacingAdjustments", False),
        "m_IgnoreSpacingAdjustments",
    )
    return pair


def _normalize_font_feature_payload(data: JsonDict) -> None:
    """Normalize official TMP record deltas and migrate legacy pairs when needed."""
    legacy_pairs: list[JsonDict] = []
    normalized_legacy_tables: dict[str, JsonDict] = {}
    for table_key in ("m_KerningTable", "m_kerningInfo"):
        table = data.get(table_key)
        if table is None:
            continue
        if not isinstance(table, dict):
            raise ValueError(f"{table_key} must be an object")
        pairs = table.get("kerningPairs")
        if pairs is None:
            pairs = []
        if not isinstance(pairs, list):
            raise ValueError(f"{table_key}.kerningPairs must be a list")
        normalized_pairs = [_normalize_legacy_kerning_pair(pair) for pair in pairs]
        table["kerningPairs"] = normalized_pairs
        normalized_legacy_tables[table_key] = table
        if normalized_pairs and not legacy_pairs:
            legacy_pairs = normalized_pairs

    if len(normalized_legacy_tables) == 1:
        present_key, present_table = next(iter(normalized_legacy_tables.items()))
        missing_key = (
            "m_kerningInfo" if present_key == "m_KerningTable" else "m_KerningTable"
        )
        mirrored_table = copy.deepcopy(present_table)
        data[missing_key] = mirrored_table
        normalized_legacy_tables[missing_key] = mirrored_table
    elif len(normalized_legacy_tables) == 2:
        modern_alias_pairs = normalized_legacy_tables["m_KerningTable"][
            "kerningPairs"
        ]
        old_alias_pairs = normalized_legacy_tables["m_kerningInfo"]["kerningPairs"]
        if modern_alias_pairs != old_alias_pairs:
            raise ValueError(
                "Conflicting TMP legacy kerning tables: "
                "m_KerningTable and m_kerningInfo"
            )

    feature_table = data.get("m_FontFeatureTable")
    if feature_table is not None and not isinstance(feature_table, dict):
        raise ValueError("m_FontFeatureTable must be an object")
    if isinstance(feature_table, dict):
        modern_pairs = feature_table.get("m_GlyphPairAdjustmentRecords")
        if isinstance(modern_pairs, list):
            for pair in modern_pairs:
                if not isinstance(pair, dict):
                    raise ValueError("TMP glyph-pair adjustment record must be an object")
                try:
                    lookup_flags = int(pair.get("m_FeatureLookupFlags", 0))
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ValueError("Invalid TMP feature lookup flags") from exc
                if lookup_flags < 0:
                    raise ValueError("TMP feature lookup flags cannot be negative")
                pair["m_FeatureLookupFlags"] = lookup_flags
                for adjustment_key in (
                    "m_FirstAdjustmentRecord",
                    "m_SecondAdjustmentRecord",
                ):
                    adjustment = pair.get(adjustment_key)
                    if not isinstance(adjustment, dict):
                        raise ValueError(
                            f"TMP glyph-pair record is missing {adjustment_key}"
                        )
                    try:
                        glyph_index = int(adjustment["m_GlyphIndex"])
                    except (KeyError, TypeError, ValueError, OverflowError) as exc:
                        raise ValueError(
                            f"Invalid TMP glyph index in {adjustment_key}"
                        ) from exc
                    if glyph_index < 0:
                        raise ValueError("TMP glyph indexes cannot be negative")
                    adjustment["m_GlyphIndex"] = glyph_index
                    adjustment["m_GlyphValueRecord"] = _modern_value_record(
                        adjustment.get("m_GlyphValueRecord")
                    )
            if modern_pairs:
                return

    if not legacy_pairs:
        return
    character_table = data.get("m_CharacterTable")
    if not isinstance(character_table, list):
        return
    glyph_by_unicode: dict[int, int] = {}
    for character in character_table:
        if not isinstance(character, dict):
            continue
        try:
            glyph_by_unicode[int(character["m_Unicode"])] = int(
                character["m_GlyphIndex"]
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            continue

    migrated_by_glyphs: dict[tuple[int, int], JsonDict] = {}
    advances_by_glyphs: dict[tuple[int, int], float] = {}
    for pair in legacy_pairs:
        left = glyph_by_unicode.get(int(pair["AscII_Left"]))
        right = glyph_by_unicode.get(int(pair["AscII_Right"]))
        if left is None or right is None:
            continue
        first_value = pair["m_FirstGlyphAdjustments"]
        second_value = pair["m_SecondGlyphAdjustments"]
        advance = float(first_value.get("xAdvance", 0.0))
        glyph_key = (left, right)
        previous_advance = advances_by_glyphs.get(glyph_key)
        if previous_advance is not None and previous_advance != advance:
            raise ValueError(
                "Conflicting legacy kerning values map to one TMP glyph pair: "
                f"{glyph_key}"
            )
        advances_by_glyphs[glyph_key] = advance
        ignore_spacing = bool(pair.get("m_IgnoreSpacingAdjustments", False))
        migrated_by_glyphs[glyph_key] = {
            "m_FirstAdjustmentRecord": {
                "m_GlyphIndex": left,
                "m_GlyphValueRecord": {
                    "m_XPlacement": float(first_value.get("xPlacement", 0.0)),
                    "m_YPlacement": float(first_value.get("yPlacement", 0.0)),
                    "m_XAdvance": advance,
                    "m_YAdvance": float(first_value.get("yAdvance", 0.0)),
                },
            },
            "m_SecondAdjustmentRecord": {
                "m_GlyphIndex": right,
                "m_GlyphValueRecord": {
                    "m_XPlacement": float(second_value.get("xPlacement", 0.0)),
                    "m_YPlacement": float(second_value.get("yPlacement", 0.0)),
                    "m_XAdvance": float(second_value.get("xAdvance", 0.0)),
                    "m_YAdvance": float(second_value.get("yAdvance", 0.0)),
                },
            },
            "m_FeatureLookupFlags": 0x100 if ignore_spacing else 0,
        }

    if not migrated_by_glyphs:
        return
    if not isinstance(feature_table, dict):
        feature_table = {}
        data["m_FontFeatureTable"] = feature_table
    feature_table.setdefault("m_MultipleSubstitutionRecords", [])
    feature_table.setdefault("m_LigatureSubstitutionRecords", [])
    feature_table["m_GlyphPairAdjustmentRecords"] = [
        migrated_by_glyphs[key] for key in sorted(migrated_by_glyphs)
    ]
    feature_table.setdefault("m_MarkToBaseAdjustmentRecords", [])
    feature_table.setdefault("m_MarkToMarkAdjustmentRecords", [])


def _tmp_version_hint(unity_version: str | None) -> Literal["new", "old"] | None:
    if not unity_version:
        return None
    triplet = _parse_unity_version_triplet(str(unity_version))
    if triplet is None:
        return None
    if triplet <= _TMP_OLD_ONLY_LAST:
        return "old"
    if triplet >= _TMP_NEW_SCHEMA_FIRST:
        return "new"
    return None


def _safe_list_len(value: Any) -> int:
    """KR: 리스트이면 길이를 반환하고, 아니면 0을 반환합니다.
    EN: Returns the length if it is a list, otherwise returns 0.
    """
    return len(value) if isinstance(value, list) else 0


def _first_atlas_ref(value: Any) -> JsonDict | None:
    """KR: 아틀라스 텍스처 리스트에서 첫 번째 딕셔너리 참조를 반환합니다.
    EN: Returns the first dictionary reference from the atlas texture list.
    """
    if not isinstance(value, list):
        return None
    for item in value:
        if isinstance(item, dict):
            return cast(JsonDict, item)
    return None


def _atlas_ref_ids(ref: Any) -> tuple[int, int]:
    """KR: 아틀라스 참조 딕셔너리에서 (m_FileID, m_PathID) 튜플을 추출합니다.
    EN: Extracts the (m_FileID, m_PathID) tuple from an atlas reference dictionary.
    """
    if not isinstance(ref, dict):
        return 0, 0
    try:
        file_id = int(ref.get("m_FileID", 0) or 0)
    except Exception:
        file_id = 0
    try:
        path_id = int(ref.get("m_PathID", 0) or 0)
    except Exception:
        path_id = 0
    return file_id, path_id


def _has_real_atlas_path(ref: Any) -> bool:
    """KR: 아틀라스 참조의 PathID가 0이 아닌지(실제 유효한 경로인지) 확인합니다.
    EN: Checks whether the atlas reference PathID is nonzero (i.e. actually valid).
    """
    _, path_id = _atlas_ref_ids(ref)
    return path_id != 0


def _first_valid_atlas_ref(value: Any) -> JsonDict | None:
    """KR: 아틀라스 텍스처 리스트에서 유효한 PathID를 가진 첫 번째 참조를 반환합니다.
    EN: Returns the first reference with a valid PathID from the atlas texture list.
    """
    if not isinstance(value, list):
        return None
    for item in value:
        if isinstance(item, dict) and _has_real_atlas_path(item):
            return cast(JsonDict, item)
    return None


def _all_valid_atlas_refs(data: JsonDict) -> list[JsonDict]:
    """Return every unique non-null atlas PPtr present in the target shape."""
    refs: list[JsonDict] = []
    seen: set[tuple[int, int]] = set()
    candidates: list[Any] = []
    atlas_textures = data.get("m_AtlasTextures")
    if isinstance(atlas_textures, list):
        candidates.extend(atlas_textures)
    candidates.extend((data.get("m_AtlasTexture"), data.get("atlas")))
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        ids = _atlas_ref_ids(candidate)
        if ids[1] == 0 or ids in seen:
            continue
        seen.add(ids)
        refs.append(copy.deepcopy(candidate))
    return refs


def _best_atlas_ref(
    data: JsonDict,
    *,
    prefer_new: bool,
) -> JsonDict | None:
    """KR: 신형/구형 아틀라스 참조 중 가장 적합한 것을 선택합니다. prefer_new에 따라 우선순위가 달라집니다.
    EN: Selects the best atlas reference from new/old variants. Priority changes based on prefer_new.
    """
    new_any = _first_atlas_ref(data.get("m_AtlasTextures"))
    new_valid = _first_valid_atlas_ref(data.get("m_AtlasTextures"))
    singular_any = (
        cast(JsonDict | None, data.get("m_AtlasTexture"))
        if isinstance(data.get("m_AtlasTexture"), dict)
        else None
    )
    singular_valid = singular_any if _has_real_atlas_path(singular_any) else None
    old_any = (
        cast(JsonDict | None, data.get("atlas"))
        if isinstance(data.get("atlas"), dict)
        else None
    )
    old_valid = old_any if _has_real_atlas_path(old_any) else None

    ordered = (
        (new_valid, singular_valid, old_valid, new_any, singular_any, old_any)
        if prefer_new
        else (old_valid, new_valid, singular_valid, old_any, new_any, singular_any)
    )
    for ref in ordered:
        if isinstance(ref, dict):
            return ref
    return None


def detect_tmp_version(
    data: JsonDict, unity_version: str | None = None
) -> Literal["new", "old"]:
    """KR: SDF TMP 데이터가 신형/구형 포맷인지 판별합니다.
    EN: Determines whether SDF TMP data uses the new or old format.
    """
    new_glyph_count = _safe_list_len(data.get("m_GlyphTable"))
    old_glyph_count = _safe_list_len(data.get("m_glyphInfoList"))
    has_new_glyphs = new_glyph_count > 0
    has_old_glyphs = old_glyph_count > 0

    has_new_face = isinstance(data.get("m_FaceInfo"), dict)
    has_old_face = isinstance(data.get("m_fontInfo"), dict)
    has_new_atlas = _first_atlas_ref(
        data.get("m_AtlasTextures")
    ) is not None or isinstance(data.get("m_AtlasTexture"), dict)
    has_old_atlas = isinstance(data.get("atlas"), dict)

    # KR: 두 포맷 키가 동시에 있어도 실제 글리프가 있는 쪽을 우선합니다.
    # EN: Even if both format keys exist, the side with actual glyphs takes priority.
    if has_new_glyphs != has_old_glyphs:
        return "new" if has_new_glyphs else "old"
    if new_glyph_count != old_glyph_count:
        return "new" if new_glyph_count > old_glyph_count else "old"

    # KR: 글리프가 비슷하면 face/atlas 신호를 비교합니다.
    # EN: If glyph counts are similar, compare face/atlas signals.
    if has_new_face != has_old_face:
        return "new" if has_new_face else "old"
    if has_new_atlas != has_old_atlas:
        return "new" if has_new_atlas else "old"

    # KR: 실제 신형 필드가 있으면 Unity 버전 힌트보다 우선합니다.
    # EN: Actual new-schema fields take priority over the Unity version hint.
    if any(
        key in data
        for key in (
            "m_GlyphTable",
            "m_CharacterTable",
            "m_AtlasTextures",
            "m_AtlasTexture",
            "m_AtlasWidth",
        )
    ):
        return "new"

    # KR: Unity-Runtime-Libraries 기준 버전 힌트(2018.3.14 / 2018.4.2)를 사용합니다.
    # EN: Uses version hints based on Unity-Runtime-Libraries (2018.3.14 / 2018.4.2).
    hint = _tmp_version_hint(unity_version)
    if hint is not None:
        return hint

    # KR: 최종 폴백은 신형 우선입니다.
    # EN: Final fallback prefers the new format.
    if has_new_face or has_new_atlas or "m_CharacterTable" in data:
        return "new"
    if has_old_face or has_old_atlas:
        return "old"

    return "new"


def inspect_tmp_font_schema(
    data: JsonDict,
    unity_version: str | None = None,
) -> dict[str, Any]:
    """KR: TMP 스키마 판별과 glyph/atlas 핵심 메타를 공통 형태로 반환합니다.
    EN: Returns TMP schema detection and core glyph/atlas metadata in a common format.
    """
    target_version = detect_tmp_version(data, unity_version=unity_version)

    new_glyph_count = _safe_list_len(data.get("m_GlyphTable"))
    old_glyph_count = _safe_list_len(data.get("m_glyphInfoList"))
    has_new_face = isinstance(data.get("m_FaceInfo"), dict)
    has_old_face = isinstance(data.get("m_fontInfo"), dict)
    new_atlas_ref = _first_atlas_ref(data.get("m_AtlasTextures"))
    singular_atlas_ref = (
        cast(JsonDict | None, data.get("m_AtlasTexture"))
        if isinstance(data.get("m_AtlasTexture"), dict)
        else None
    )
    old_atlas_ref = (
        cast(JsonDict | None, data.get("atlas"))
        if isinstance(data.get("atlas"), dict)
        else None
    )

    # A single generic field such as m_FaceInfo or atlas is not sufficient to
    # identify a TMP FontAsset. Require a coherent serialized shape so an
    # unrelated MonoBehaviour cannot be offered as a font and then mutated.
    # List *presence* (including empty lists) intentionally keeps valid empty
    # or dynamic FontAssets discoverable.
    has_new_signature = bool(
        has_new_face
        and isinstance(data.get("m_GlyphTable"), list)
        and isinstance(data.get("m_CharacterTable"), list)
        and (
            isinstance(data.get("m_AtlasTextures"), list)
            or isinstance(data.get("m_AtlasTexture"), dict)
        )
    )
    has_old_signature = bool(
        has_old_face
        and isinstance(data.get("m_glyphInfoList"), list)
        and old_atlas_ref is not None
        and (
            isinstance(data.get("material"), dict)
            or isinstance(data.get("m_Material"), dict)
        )
    )

    if target_version == "new":
        glyph_count = new_glyph_count if new_glyph_count > 0 else old_glyph_count
        atlas_ref = _best_atlas_ref(data, prefer_new=True)
    else:
        glyph_count = old_glyph_count if old_glyph_count > 0 else new_glyph_count
        atlas_ref = _best_atlas_ref(data, prefer_new=False)

    atlas_file_id, atlas_path_id = _atlas_ref_ids(atlas_ref)

    is_tmp = has_new_signature or has_old_signature

    return {
        "version": target_version,
        "is_tmp": is_tmp,
        "glyph_count": int(glyph_count),
        "atlas_file_id": int(atlas_file_id),
        "atlas_path_id": int(atlas_path_id),
    }


def extract_tmp_atlas_padding(
    data: JsonDict,
    unity_version: str | None = None,
) -> float:
    """KR: TMP 에셋 데이터에서 아틀라스 패딩 값을 추출합니다. m_AtlasPadding, CreationSettings, m_fontInfo 순으로 탐색합니다.
    EN: Extracts the atlas padding value from TMP asset data. Searches m_AtlasPadding, CreationSettings, m_fontInfo in order.
    """
    candidates: list[Any] = [data.get("m_AtlasPadding")]
    creation_settings_key = _resolve_creation_settings_key(
        data,
        unity_version=unity_version,
    )
    if creation_settings_key and isinstance(data.get(creation_settings_key), dict):
        creation_settings = cast(JsonDict, data[creation_settings_key])
        for key, value in creation_settings.items():
            normalized = key.replace("_", "").lower()
            if normalized == "padding" or normalized.endswith("padding"):
                candidates.append(value)
    if isinstance(data.get("m_fontInfo"), dict):
        candidates.append(cast(JsonDict, data["m_fontInfo"]).get("Padding"))

    for candidate in candidates:
        try:
            numeric = float(candidate)
        except Exception:
            continue
        if numeric > 0:
            return numeric
    return 0.0


def convert_face_info_new_to_old(
    face_info: JsonDict,
    atlas_padding: int = 0,
    atlas_width: int = 0,
    atlas_height: int = 0,
    character_count: int = 0,
) -> JsonDict:
    """KR: 신형 m_FaceInfo를 구형 m_fontInfo 구조로 변환합니다.
    EN: Converts new-format m_FaceInfo to old-format m_fontInfo structure.
    """
    return {
        "Name": face_info.get("m_FamilyName", ""),
        "PointSize": face_info.get("m_PointSize", 0),
        "Scale": face_info.get("m_Scale", 1.0),
        "CharacterCount": int(character_count),
        "LineHeight": face_info.get("m_LineHeight", 0),
        "Baseline": face_info.get("m_Baseline", 0),
        "Ascender": face_info.get("m_AscentLine", 0),
        "CapHeight": face_info.get("m_CapLine", 0),
        "Descender": face_info.get("m_DescentLine", 0),
        "CenterLine": face_info.get("m_MeanLine", 0),
        "SuperscriptOffset": face_info.get("m_SuperscriptOffset", 0),
        "SubscriptOffset": face_info.get("m_SubscriptOffset", 0),
        "SubSize": face_info.get("m_SubscriptSize", 0.5),
        "Underline": face_info.get("m_UnderlineOffset", 0),
        "UnderlineThickness": face_info.get("m_UnderlineThickness", 0),
        "strikethrough": face_info.get("m_StrikethroughOffset", 0),
        "strikethroughThickness": face_info.get("m_StrikethroughThickness", 0),
        "TabWidth": face_info.get("m_TabWidth", 0),
        "Padding": atlas_padding,
        "AtlasWidth": atlas_width,
        "AtlasHeight": atlas_height,
    }


def convert_face_info_old_to_new(font_info: JsonDict) -> JsonDict:
    """KR: 구형 m_fontInfo를 신형 m_FaceInfo 구조로 변환합니다.
    EN: Converts old-format m_fontInfo to new-format m_FaceInfo structure.
    """
    return {
        "m_FaceIndex": 0,
        "m_FamilyName": font_info.get("Name", ""),
        "m_StyleName": "regular",
        "m_PointSize": font_info.get("PointSize", 0),
        "m_Scale": font_info.get("Scale", 1.0),
        "m_UnitsPerEM": 0,
        "m_LineHeight": font_info.get("LineHeight", 0),
        "m_AscentLine": font_info.get("Ascender", 0),
        "m_CapLine": font_info.get("CapHeight", 0),
        "m_MeanLine": font_info.get("CenterLine", 0),
        "m_Baseline": font_info.get("Baseline", 0),
        "m_DescentLine": font_info.get("Descender", 0),
        "m_SuperscriptOffset": font_info.get("SuperscriptOffset", 0),
        "m_SuperscriptSize": 0.5,
        "m_SubscriptOffset": font_info.get("SubscriptOffset", 0),
        "m_SubscriptSize": font_info.get("SubSize", 0.5),
        "m_UnderlineOffset": font_info.get("Underline", 0),
        "m_UnderlineThickness": font_info.get("UnderlineThickness", 0),
        "m_StrikethroughOffset": font_info.get("strikethrough", 0),
        "m_StrikethroughThickness": font_info.get("strikethroughThickness", 0),
        "m_TabWidth": font_info.get("TabWidth", 0),
    }


def _new_glyph_rect_to_int(rect: JsonDict) -> tuple[int, int, int, int]:
    """KR: 신형 TMP glyph rect를 정수 좌표/크기로 정규화합니다.
    EN: Normalizes a new-format TMP glyph rect to integer coordinates/dimensions.
    """
    x = int(round(float(rect.get("m_X", 0))))
    y = int(round(float(rect.get("m_Y", 0))))
    w = max(1, int(round(float(rect.get("m_Width", 0)))))
    h = max(1, int(round(float(rect.get("m_Height", 0)))))
    return x, y, w, h


def _tmp_flip_y_between_old_new(
    y_value: float, glyph_height: float, atlas_height: float | None
) -> float:
    """KR: TMP old(top-origin) <-> new(bottom-origin) Y 변환 공식을 적용합니다.
    EN: Applies the TMP old(top-origin) <-> new(bottom-origin) Y conversion formula.
    """
    if atlas_height is None:
        return float(y_value)
    try:
        atlas_h = float(atlas_height)
    except Exception:
        return float(y_value)
    if atlas_h <= 0:
        return float(y_value)
    return atlas_h - float(y_value) - float(glyph_height)


def convert_glyphs_new_to_old(
    glyph_table: list[JsonDict],
    char_table: list[JsonDict],
    atlas_height: int | None = None,
) -> list[JsonDict]:
    """KR: 신형 글리프/문자 테이블을 구형 m_glyphInfoList로 변환합니다.
    EN: Converts new-format glyph/character tables to old-format m_glyphInfoList.
    """
    glyph_by_index: dict[int, JsonDict] = {}
    for g in glyph_table:
        glyph_by_index[int(g.get("m_Index", 0))] = g
    result: list[JsonDict] = []
    for char in char_table:
        unicode_val = char.get("m_Unicode", 0)
        glyph_idx = int(char.get("m_GlyphIndex", 0) or 0)
        g = glyph_by_index.get(glyph_idx, {})
        metrics = g.get("m_Metrics", {})
        rect = g.get("m_GlyphRect", {})
        rect_h = float(rect.get("m_Height", 0))
        rect_y = _tmp_flip_y_between_old_new(
            float(rect.get("m_Y", 0)),
            rect_h,
            atlas_height,
        )
        result.append(
            {
                "id": int(unicode_val),
                "x": float(rect.get("m_X", 0)),
                "y": rect_y,
                # TMP legacy width/height describe the packed atlas rect, not
                # the advance/bearing metrics.
                "width": float(rect.get("m_Width", 0)),
                "height": float(rect.get("m_Height", 0)),
                "xOffset": float(metrics.get("m_HorizontalBearingX", 0)),
                "yOffset": float(metrics.get("m_HorizontalBearingY", 0)),
                "xAdvance": float(metrics.get("m_HorizontalAdvance", 0)),
                "scale": float(g.get("m_Scale", 1.0)),
            }
        )
    return result


def convert_glyphs_old_to_new(
    glyph_info_list: list[JsonDict],
    atlas_height: int | None = None,
) -> tuple[list[JsonDict], list[JsonDict]]:
    """KR: 구형 m_glyphInfoList를 신형 테이블 구조로 변환합니다.
    EN: Converts old-format m_glyphInfoList to new-format table structure.
    """
    glyph_table: list[JsonDict] = []
    char_table: list[JsonDict] = []
    glyph_idx = 0
    for glyph in glyph_info_list:
        uid = glyph.get("id", 0)
        old_rect_y = float(glyph.get("y", 0))
        glyph_h = float(glyph.get("height", 0))
        # Match TMP_FontAsset's legacy migration exactly.  Unity truncates X,
        # rounds Y/width/height by adding 0.5 before the integer cast, and
        # performs the Y cast before subtracting it from the atlas height.
        # Python's round() is banker's rounding, so it is not equivalent here.
        if atlas_height is None or int(atlas_height) <= 0:
            new_rect_y = int(old_rect_y + 0.5)
        else:
            new_rect_y = int(atlas_height) - int(old_rect_y + glyph_h + 0.5)
        glyph_table.append(
            {
                "m_Index": glyph_idx,
                "m_Metrics": {
                    "m_Width": glyph.get("width", 0),
                    "m_Height": glyph.get("height", 0),
                    "m_HorizontalBearingX": glyph.get("xOffset", 0),
                    "m_HorizontalBearingY": glyph.get("yOffset", 0),
                    "m_HorizontalAdvance": glyph.get("xAdvance", 0),
                },
                "m_GlyphRect": {
                    "m_X": int(glyph.get("x", 0)),
                    "m_Y": new_rect_y,
                    "m_Width": int(float(glyph.get("width", 0)) + 0.5),
                    "m_Height": int(glyph_h + 0.5),
                },
                "m_Scale": glyph.get("scale", 1.0),
                "m_AtlasIndex": 0,
                "m_ClassDefinitionType": 0,
            }
        )
        char_table.append(
            {
                "m_ElementType": 1,
                "m_Unicode": int(uid),
                "m_GlyphIndex": glyph_idx,
                "m_Scale": 1.0,
            }
        )
        glyph_idx += 1
    return glyph_table, char_table


def _default_font_weight_table() -> list[JsonDict]:
    return [
        {
            "regularTypeface": {"m_FileID": 0, "m_PathID": 0},
            "italicTypeface": {"m_FileID": 0, "m_PathID": 0},
        }
        for _ in range(10)
    ]


def normalize_sdf_data(data: JsonDict, deep_copy: bool = True) -> JsonDict:
    """KR: SDF 교체 데이터를 신형 TMP 형식으로 정규화해 반환합니다.
    deep_copy=True면 입력 데이터를 복사해 원본 변형을 방지합니다.
    EN: Normalizes SDF replacement data to new-format TMP and returns it.
    deep_copy=True copies input data to prevent mutation of the original.
    """
    result: JsonDict = copy.deepcopy(data) if deep_copy else data
    version = detect_tmp_version(result)

    if version == "old":
        font_info = result.get("m_fontInfo", {})
        glyph_info_list = result.get("m_glyphInfoList", [])
        atlas_padding = font_info.get("Padding", 0)
        atlas_width = font_info.get("AtlasWidth", 0)
        atlas_height = font_info.get("AtlasHeight", 0)

        # KR: 구형 face/glyph 구조를 신형 TMP 필드로 승격합니다.
        # EN: Promotes old-format face/glyph structures to new-format TMP fields.
        result["m_FaceInfo"] = convert_face_info_old_to_new(font_info)

        try:
            atlas_height_int = int(atlas_height) if atlas_height is not None else None
        except Exception:
            atlas_height_int = None
        glyph_table, char_table = convert_glyphs_old_to_new(
            glyph_info_list,
            atlas_height=atlas_height_int,
        )
        result["m_GlyphTable"] = glyph_table
        result["m_CharacterTable"] = char_table

        # KR: 구형 atlas 참조를 신형 atlas 배열 필드로 보정합니다.
        # EN: Adjusts old-format atlas references to new-format atlas array fields.
        if "m_AtlasTextures" not in result or not result["m_AtlasTextures"]:
            atlas_ref = _best_atlas_ref(result, prefer_new=False) or {
                "m_FileID": 0,
                "m_PathID": 0,
            }
            result["m_AtlasTextures"] = [atlas_ref]
        result.setdefault("m_AtlasWidth", int(atlas_width))
        result.setdefault("m_AtlasHeight", int(atlas_height))
        result.setdefault("m_AtlasPadding", int(atlas_padding))
        result.setdefault("m_AtlasRenderMode", 4169)
        result.setdefault("m_UsedGlyphRects", [])
        result.setdefault("m_FreeGlyphRects", [])

        # KR: 구형 데이터에 누락된 weight table은 기본값으로 채웁니다.
        # EN: Fills missing weight tables in old-format data with defaults.
        if "m_FontWeightTable" not in result:
            font_weights = result.get("fontWeights", [])
            result["m_FontWeightTable"] = (
                font_weights if font_weights else _default_font_weight_table()
            )

    # KR: 정규화 후 반복 사용을 위해 숫자 타입/기본값을 한 번만 정리합니다.
    # EN: Cleans up numeric types/defaults once after normalization for repeated use.
    try:
        result["m_AtlasWidth"] = int(result.get("m_AtlasWidth", 0) or 0)
        result["m_AtlasHeight"] = int(result.get("m_AtlasHeight", 0) or 0)
        result["m_AtlasPadding"] = int(result.get("m_AtlasPadding", 0) or 0)
    except Exception:
        pass
    result.setdefault("m_AtlasRenderMode", 4169)
    result.setdefault("m_UsedGlyphRects", [])
    result.setdefault("m_FreeGlyphRects", [])
    if not isinstance(result.get("m_FontWeightTable"), list) or not result.get(
        "m_FontWeightTable"
    ):
        result["m_FontWeightTable"] = _default_font_weight_table()

    face_info = result.get("m_FaceInfo")
    if isinstance(face_info, dict):
        # These fields were added to the serialized FaceInfo in later TMP /
        # TextCore generations. Their zero defaults preserve older exported
        # JSON while satisfying newer TypeTrees.
        face_info.setdefault("m_FaceIndex", 0)
        face_info.setdefault("m_UnitsPerEM", 0)
        ensure_int(
            face_info,
            [
                "m_FaceIndex",
                "m_PointSize",
                "m_UnitsPerEM",
                "m_AtlasWidth",
                "m_AtlasHeight",
            ],
        )

    # KR: Atlas 참조 목록은 공유 변형을 피하기 위해 독립 딕셔너리로 재구성합니다.
    # EN: Atlas reference list is rebuilt as independent dicts to avoid shared mutation.
    atlas_textures_raw = result.get("m_AtlasTextures", [])
    atlas_textures: list[JsonDict] = []
    if isinstance(atlas_textures_raw, list):
        for tex in atlas_textures_raw:
            if isinstance(tex, dict):
                atlas_textures.append(
                    {
                        "m_FileID": int(tex.get("m_FileID", 0) or 0),
                        "m_PathID": int(tex.get("m_PathID", 0) or 0),
                    }
                )
    if not atlas_textures:
        atlas_ref = _best_atlas_ref(result, prefer_new=True)
    else:
        atlas_ref = None
    if not atlas_textures and isinstance(atlas_ref, dict):
        atlas_textures.append(
            {
                "m_FileID": int(atlas_ref.get("m_FileID", 0) or 0),
                "m_PathID": int(atlas_ref.get("m_PathID", 0) or 0),
            }
        )
    result["m_AtlasTextures"] = atlas_textures

    glyph_table = result.get("m_GlyphTable")
    if isinstance(glyph_table, list):
        for glyph in glyph_table:
            if not isinstance(glyph, dict):
                continue
            glyph.setdefault("m_ClassDefinitionType", 0)
            ensure_int(glyph, ["m_Index", "m_AtlasIndex", "m_ClassDefinitionType"])
            rect = glyph.get("m_GlyphRect")
            if isinstance(rect, dict):
                ensure_int(rect, ["m_X", "m_Y", "m_Width", "m_Height"])

    char_table = result.get("m_CharacterTable")
    if isinstance(char_table, list):
        for char in char_table:
            if isinstance(char, dict):
                ensure_int(char, ["m_Unicode", "m_GlyphIndex", "m_ElementType"])

    for rect_list_name in ["m_UsedGlyphRects", "m_FreeGlyphRects"]:
        rect_list = result.get(rect_list_name)
        if isinstance(rect_list, list):
            for rect in rect_list:
                if isinstance(rect, dict):
                    ensure_int(rect, ["m_X", "m_Y", "m_Width", "m_Height"])

    creation_settings = result.get("m_CreationSettings")
    if isinstance(creation_settings, dict):
        ensure_int(
            creation_settings, ["pointSize", "atlasWidth", "atlasHeight", "padding"]
        )

    _normalize_font_feature_payload(result)

    return result


def _sync_single_atlas_state(
    data: JsonDict,
    file_id: int,
    path_id: int,
    *,
    reference_template: JsonDict | None = None,
) -> None:
    """Synchronize only existing TMP atlas fields for one baked atlas."""
    atlas_ref = copy.deepcopy(reference_template) if reference_template else {}
    atlas_ref["m_FileID"] = int(file_id)
    atlas_ref["m_PathID"] = int(path_id)
    if isinstance(data.get("m_AtlasTextures"), list):
        data["m_AtlasTextures"] = [copy.deepcopy(atlas_ref)]
    for singular_key in ("m_AtlasTexture", "atlas"):
        singular = data.get(singular_key)
        if isinstance(singular, dict):
            singular["m_FileID"] = int(file_id)
            singular["m_PathID"] = int(path_id)
    if "m_AtlasTextureIndex" in data:
        data["m_AtlasTextureIndex"] = 0
    if "m_IsMultiAtlasTexturesEnabled" in data:
        data["m_IsMultiAtlasTexturesEnabled"] = False
    if "m_AtlasPopulationMode" in data:
        data["m_AtlasPopulationMode"] = 0
    if "InternalDynamicOS" in data:
        data["InternalDynamicOS"] = False


def _get_tmp_material_reference(
    data: JsonDict,
) -> tuple[str | None, int, int]:
    """Return an optional TMP material PPtr without assuming either key exists."""
    key = next(
        (
            candidate
            for candidate in ("m_Material", "material")
            if isinstance(data.get(candidate), dict)
        ),
        None,
    )
    file_id, path_id = _atlas_ref_ids(data.get(key) if key else None)
    return key, file_id, path_id
