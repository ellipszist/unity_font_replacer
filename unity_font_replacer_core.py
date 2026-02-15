from __future__ import annotations

import argparse
import inspect
import io
import json
import os
import shutil
import subprocess
import sys
import traceback as tb_module
from functools import lru_cache
from typing import Any, Callable, Iterable, Literal, NoReturn, cast

import UnityPy
from PIL import Image, ImageStat
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator


Language = Literal["ko", "en"]
JsonDict = dict[str, Any]


class TeeWriter:
    """KR: stdout/stderr를 콘솔과 파일에 동시에 기록합니다.
    EN: Mirror stdout/stderr to both console and file.
    """

    def __init__(self, file: io.TextIOBase, original_stream: io.TextIOBase) -> None:
        """KR: 출력 대상 파일과 원본 스트림을 저장합니다.
        EN: Store target file stream and original stream.
        """
        self.file = file
        self.original = original_stream

    def write(self, data: str) -> int:
        """KR: 문자열을 두 스트림에 동시에 기록합니다.
        EN: Write text to both streams.
        """
        self.original.write(data)
        self.file.write(data)
        self.file.flush()
        return len(data)

    def flush(self) -> None:
        """KR: 두 스트림 버퍼를 모두 비웁니다.
        EN: Flush both stream buffers.
        """
        self.original.flush()
        self.file.flush()

    def fileno(self) -> int:
        """KR: 원본 스트림 파일 디스크립터를 반환합니다.
        EN: Return original stream file descriptor.
        """
        return self.original.fileno()

    @property
    def encoding(self) -> str:
        """KR: 원본 스트림 인코딩을 반환합니다.
        EN: Return encoding of the original stream.
        """
        return self.original.encoding


def find_ggm_file(data_path: str) -> str | None:
    """KR: 데이터 폴더에서 globalgamemanagers 계열 파일 경로를 찾습니다.
    EN: Find a globalgamemanagers-like file inside the data folder.
    """
    candidates = ["globalgamemanagers", "globalgamemanagers.assets", "data.unity3d"]
    candidates_resources = ["unity default resources", "unity_builtin_extra"]
    fls: list[str] = []
    for candidate in candidates_resources:
        ggm_path = os.path.join(data_path, "Resources", candidate)
        if os.path.exists(ggm_path):
            fls.append(ggm_path)
    for candidate in candidates:
        ggm_path = os.path.join(data_path, candidate)
        if os.path.exists(ggm_path):
            fls.append(ggm_path)
    if fls:
        return fls[0]
    return None


def resolve_game_path(path: str, lang: Language = "ko") -> tuple[str, str]:
    """KR: 입력 경로를 게임 루트와 _Data 경로로 정규화합니다.
    EN: Normalize input path to game root and _Data folder path.
    """
    path = os.path.normpath(os.path.abspath(path))

    if path.lower().endswith("_data"):
        data_path = path
        game_path = os.path.dirname(path)
    else:
        game_path = path
        data_folders = [d for d in os.listdir(path) if d.lower().endswith("_data") and os.path.isdir(os.path.join(path, d))]

        if not data_folders:
            if lang == "ko":
                raise FileNotFoundError(f"'{path}'에서 _Data 폴더를 찾을 수 없습니다.")
            raise FileNotFoundError(f"Could not find _Data folder in '{path}'.")

        data_path = os.path.join(game_path, data_folders[0])

    ggm_path = find_ggm_file(data_path)
    if not ggm_path:
        if lang == "ko":
            raise FileNotFoundError(
                f"'{data_path}'에서 globalgamemanagers 파일을 찾을 수 없습니다.\n올바른 Unity 게임 폴더인지 확인해주세요."
            )
        raise FileNotFoundError(
            f"Could not find a globalgamemanagers file in '{data_path}'.\nPlease verify this is a valid Unity game folder."
        )

    return game_path, data_path


def get_data_path(game_path: str, lang: Language = "ko") -> str:
    """KR: 게임 루트에서 _Data 폴더 경로를 반환합니다.
    EN: Return _Data folder path from game root.
    """
    data_folders = [i for i in os.listdir(game_path) if i.lower().endswith("_data")]
    if not data_folders:
        if lang == "ko":
            raise FileNotFoundError(f"'{game_path}'에서 _Data 폴더를 찾을 수 없습니다.")
        raise FileNotFoundError(f"Could not find _Data folder in '{game_path}'.")
    return os.path.join(game_path, data_folders[0])


def get_unity_version(game_path: str, lang: Language = "ko") -> str:
    """KR: 게임 경로에서 Unity 버전을 읽어 반환합니다.
    EN: Read and return Unity version from the game path.
    """
    data_path = get_data_path(game_path, lang=lang)
    ggm_path = find_ggm_file(data_path)
    if not ggm_path:
        if lang == "ko":
            raise FileNotFoundError(
                f"'{data_path}'에서 globalgamemanagers 파일을 찾을 수 없습니다.\n올바른 Unity 게임 폴더인지 확인해주세요."
            )
        raise FileNotFoundError(
            f"Could not find a globalgamemanagers file in '{data_path}'.\nPlease verify this is a valid Unity game folder."
        )
    return str(UnityPy.load(ggm_path).objects[0].assets_file.unity_version)


def get_script_dir() -> str:
    """KR: 실행 기준 디렉터리(스크립트/배포 바이너리)를 반환합니다.
    EN: Return runtime directory for script or frozen executable.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def normalize_font_name(name: str) -> str:
    """KR: 확장자/SDF 접미사를 제거해 폰트 기본 이름으로 정규화합니다.
    EN: Normalize font name by removing extension and SDF suffixes.
    """
    for ext in [".ttf", ".json", ".png"]:
        if name.lower().endswith(ext):
            name = name[:-len(ext)]
    if name.endswith(" SDF Atlas"):
        name = name[:-len(" SDF Atlas")]
    elif name.endswith(" SDF"):
        name = name[:-len(" SDF")]
    return name


def warn_unitypy_version(
    expected_major_minor: tuple[int, int] = (1, 24),
    lang: Language = "ko",
) -> None:
    """KR: UnityPy 버전을 점검하고 권장 버전과 다르면 경고합니다.
    EN: Check UnityPy version and print warning when it differs from recommendation.
    """
    version = getattr(UnityPy, "__version__", "")
    try:
        parts = version.split(".")
        major = int(parts[0])
        minor = int(parts[1])
    except (ValueError, IndexError, AttributeError):
        if lang == "ko":
            print(f"[경고] UnityPy 버전을 확인할 수 없습니다: '{version}'")
        else:
            print(f"[Warning] Could not determine UnityPy version: '{version}'")
        return

    if (major, minor) != expected_major_minor:
        expected = f"{expected_major_minor[0]}.{expected_major_minor[1]}.x"
        if lang == "ko":
            print(f"[경고] 현재 UnityPy {version} 사용 중입니다. 권장 검증 버전은 {expected}입니다.")
        else:
            print(f"[Warning] Using UnityPy {version}. Recommended validated version is {expected}.")


def build_replacement_lookup(
    replacements: dict[str, JsonDict],
) -> tuple[dict[tuple[str, str, str, int], str], set[str]]:
    """KR: 교체 JSON을 빠른 조회용 룩업 테이블로 변환합니다.
    EN: Build fast lookup structures from replacement JSON data.
    """
    lookup: dict[tuple[str, str, str, int], str] = {}
    files_to_process: set[str] = set()

    for info in replacements.values():
        replace_to = info.get("Replace_to")
        if not replace_to:
            continue

        file_name_raw = info.get("File")
        assets_name_raw = info.get("assets_name")
        path_id_raw = info.get("Path_ID")
        type_name_raw = info.get("Type")

        if not isinstance(file_name_raw, str) or not file_name_raw:
            continue
        if not isinstance(assets_name_raw, str) or not assets_name_raw:
            continue
        if not isinstance(type_name_raw, str) or not type_name_raw:
            continue
        if path_id_raw is None:
            continue

        try:
            path_id = int(path_id_raw)
        except (TypeError, ValueError):
            continue

        normalized_target = normalize_font_name(str(replace_to))
        lookup[(type_name_raw, file_name_raw, assets_name_raw, path_id)] = normalized_target
        files_to_process.add(file_name_raw)

    return lookup, files_to_process


def debug_parse_enabled() -> bool:
    """KR: 디버그 파싱 로그 활성화 여부를 반환합니다.
    EN: Return whether parse debug logging is enabled.
    """
    return os.environ.get("UFR_DEBUG_PARSE", "").strip() == "1"


def debug_parse_log(message: str) -> None:
    """KR: 디버그 모드일 때만 파싱 로그를 출력합니다.
    EN: Print parsing debug message only when enabled.
    """
    if debug_parse_enabled():
        print(message)


def ensure_int(data: JsonDict | None, keys: Iterable[str]) -> None:
    """KR: 딕셔너리의 지정 키 값을 int로 강제 변환합니다.
    EN: Force-convert specified dictionary keys to integers.
    """
    if not data:
        return
    for key in keys:
        if key in data and data[key] is not None:
            data[key] = int(data[key])


def detect_tmp_version(data: JsonDict) -> Literal["new", "old"]:
    """KR: SDF TMP 데이터가 신형/구형 포맷인지 판별합니다.
    EN: Detect whether SDF TMP data uses new or old schema.
    """
    has_new_glyphs = len(data.get("m_GlyphTable", [])) > 0
    has_old_glyphs = len(data.get("m_glyphInfoList", [])) > 0

    # KR: 두 포맷 키가 동시에 있어도 실제 글리프가 있는 쪽을 우선합니다.
    # EN: When both schema keys exist, prefer the side that has real glyph data.
    if has_new_glyphs:
        return "new"
    if has_old_glyphs:
        return "old"

    # KR: 글리프가 비어 있으면 필드 존재 여부로 포맷을 추정합니다.
    # EN: If glyphs are empty, infer format by field presence.
    if "m_FaceInfo" in data:
        return "new"
    if "m_fontInfo" in data:
        return "old"

    return "new"


def convert_face_info_new_to_old(
    face_info: JsonDict,
    atlas_padding: int = 0,
    atlas_width: int = 0,
    atlas_height: int = 0,
) -> JsonDict:
    """KR: 신형 m_FaceInfo를 구형 m_fontInfo 구조로 변환합니다.
    EN: Convert new m_FaceInfo to old m_fontInfo schema.
    """
    return {
        "Name": face_info.get("m_FamilyName", ""),
        "PointSize": face_info.get("m_PointSize", 0),
        "Scale": face_info.get("m_Scale", 1.0),
        "CharacterCount": 0,
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
    EN: Convert old m_fontInfo to new m_FaceInfo schema.
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
    EN: Normalize new TMP glyph rect to integer coordinates/sizes.
    """
    x = int(round(float(rect.get("m_X", 0))))
    y = int(round(float(rect.get("m_Y", 0))))
    w = max(1, int(round(float(rect.get("m_Width", 0)))))
    h = max(1, int(round(float(rect.get("m_Height", 0)))))
    return x, y, w, h


def detect_new_glyph_y_flip(
    glyph_table: list[JsonDict],
    char_table: list[JsonDict],
    atlas_image: Image.Image | None,
    sample_limit: int = 256,
) -> bool:
    """KR: 신형 TMP glyph Y축이 구형 TMP 기준으로 반전되어 있는지 추정합니다.
    EN: Estimate whether new TMP glyph Y coordinates must be flipped for old TMP.
    """
    if atlas_image is None or not glyph_table or not char_table:
        return False

    glyph_by_index: dict[int, JsonDict] = {}
    for glyph in glyph_table:
        glyph_by_index[int(glyph.get("m_Index", 0))] = glyph

    # KR: 문자 테이블 순서를 따라 샘플을 뽑아 실제 렌더와 가까운 분포를 사용합니다.
    # EN: Sample in character-table order to match runtime usage distribution.
    rect_samples: list[tuple[int, int, int, int]] = []
    seen_indices: set[int] = set()
    for char in char_table:
        glyph_idx = int(char.get("m_GlyphIndex", -1))
        if glyph_idx in seen_indices:
            continue
        seen_indices.add(glyph_idx)
        glyph = glyph_by_index.get(glyph_idx)
        if not glyph:
            continue
        rect = glyph.get("m_GlyphRect", {})
        x, y, w, h = _new_glyph_rect_to_int(rect)
        if w <= 1 or h <= 1:
            continue
        rect_samples.append((x, y, w, h))

    if not rect_samples:
        return False

    if len(rect_samples) > sample_limit:
        step = max(1, len(rect_samples) // sample_limit)
        rect_samples = rect_samples[::step][:sample_limit]

    if "A" in atlas_image.getbands():
        alpha = atlas_image.getchannel("A")
    else:
        alpha = atlas_image.convert("L")

    atlas_w, atlas_h = alpha.size

    def _score(flip_y: bool) -> tuple[int, float, int]:
        non_zero_count = 0
        mean_sum = 0.0
        valid_rects = 0

        for x, y, w, h in rect_samples:
            yy = atlas_h - y - h if flip_y else y
            x0 = max(0, min(atlas_w - 1, x))
            y0 = max(0, min(atlas_h - 1, yy))
            x1 = max(x0 + 1, min(atlas_w, x0 + w))
            y1 = max(y0 + 1, min(atlas_h, y0 + h))

            if x1 <= x0 or y1 <= y0:
                continue

            region = alpha.crop((x0, y0, x1, y1))
            stats = ImageStat.Stat(region)
            mean_sum += float(stats.mean[0]) if stats.mean else 0.0
            if region.getbbox() is not None:
                non_zero_count += 1
            valid_rects += 1

        return non_zero_count, mean_sum, valid_rects

    direct_non_zero, direct_mean, direct_valid = _score(False)
    flipped_non_zero, flipped_mean, flipped_valid = _score(True)

    valid_count = min(direct_valid, flipped_valid)
    if valid_count == 0:
        return False

    non_zero_margin = max(2, valid_count // 20)  # 5%
    return (
        flipped_non_zero > direct_non_zero + non_zero_margin
        or (flipped_non_zero >= direct_non_zero and flipped_mean > (direct_mean * 1.2))
    )


def convert_glyphs_new_to_old(
    glyph_table: list[JsonDict],
    char_table: list[JsonDict],
    atlas_height: int | None = None,
    flip_y: bool = False,
) -> list[JsonDict]:
    """KR: 신형 글리프/문자 테이블을 구형 m_glyphInfoList로 변환합니다.
    EN: Convert new glyph/character tables into old m_glyphInfoList.
    """
    glyph_by_index: dict[int, JsonDict] = {}
    for g in glyph_table:
        glyph_by_index[int(g.get("m_Index", 0))] = g
    result: list[JsonDict] = []
    for char in char_table:
        unicode_val = char.get("m_Unicode", 0)
        glyph_idx = char.get("m_GlyphIndex", 0)
        g = glyph_by_index.get(glyph_idx, {})
        metrics = g.get("m_Metrics", {})
        rect = g.get("m_GlyphRect", {})
        rect_y = float(rect.get("m_Y", 0))
        rect_h = float(rect.get("m_Height", 0))
        if flip_y and atlas_height:
            rect_y = float(atlas_height) - rect_y - rect_h
        result.append({
            "id": int(unicode_val),
            "x": float(rect.get("m_X", 0)),
            "y": rect_y,
            "width": float(metrics.get("m_Width", 0)),
            "height": float(metrics.get("m_Height", 0)),
            "xOffset": float(metrics.get("m_HorizontalBearingX", 0)),
            "yOffset": float(metrics.get("m_HorizontalBearingY", 0)),
            "xAdvance": float(metrics.get("m_HorizontalAdvance", 0)),
            "scale": float(g.get("m_Scale", 1.0)),
        })
    return result


def convert_glyphs_old_to_new(glyph_info_list: list[JsonDict]) -> tuple[list[JsonDict], list[JsonDict]]:
    """KR: 구형 m_glyphInfoList를 신형 테이블 구조로 변환합니다.
    EN: Convert old m_glyphInfoList into new glyph/character tables.
    """
    glyph_table: list[JsonDict] = []
    char_table: list[JsonDict] = []
    glyph_idx = 0
    for glyph in glyph_info_list:
        uid = glyph.get("id", 0)
        glyph_table.append({
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
                "m_Y": int(glyph.get("y", 0)),
                "m_Width": int(glyph.get("width", 0)),
                "m_Height": int(glyph.get("height", 0)),
            },
            "m_Scale": glyph.get("scale", 1.0),
            "m_AtlasIndex": 0,
            "m_ClassDefinitionType": 0,
        })
        char_table.append({
            "m_ElementType": 1,
            "m_Unicode": int(uid),
            "m_GlyphIndex": glyph_idx,
            "m_Scale": 1.0,
        })
        glyph_idx += 1
    return glyph_table, char_table


def normalize_sdf_data(data: JsonDict) -> JsonDict:
    """KR: SDF 교체 데이터를 신형 TMP 형식으로 정규화해 반환합니다.
    EN: Normalize SDF replacement data into the new TMP schema.
    """
    import copy

    result: JsonDict = copy.deepcopy(data)
    version = detect_tmp_version(result)

    if version == "old":
        font_info = result.get("m_fontInfo", {})
        glyph_info_list = result.get("m_glyphInfoList", [])
        atlas_padding = font_info.get("Padding", 0)
        atlas_width = font_info.get("AtlasWidth", 0)
        atlas_height = font_info.get("AtlasHeight", 0)

        # KR: 구형 face/glyph 구조를 신형 TMP 필드로 승격합니다.
        # EN: Upgrade old face/glyph structures to new TMP fields.
        result["m_FaceInfo"] = convert_face_info_old_to_new(font_info)

        glyph_table, char_table = convert_glyphs_old_to_new(glyph_info_list)
        result["m_GlyphTable"] = glyph_table
        result["m_CharacterTable"] = char_table

        # KR: 구형 atlas 참조를 신형 atlas 배열 필드로 보정합니다.
        # EN: Normalize old atlas reference into new atlas-list field.
        if "m_AtlasTextures" not in result or not result["m_AtlasTextures"]:
            atlas_ref = result.get("atlas", {"m_FileID": 0, "m_PathID": 0})
            result["m_AtlasTextures"] = [atlas_ref]
        result.setdefault("m_AtlasWidth", int(atlas_width))
        result.setdefault("m_AtlasHeight", int(atlas_height))
        result.setdefault("m_AtlasPadding", int(atlas_padding))
        result.setdefault("m_AtlasRenderMode", 4118)
        result.setdefault("m_UsedGlyphRects", [])
        result.setdefault("m_FreeGlyphRects", [])

        # KR: 구형 데이터에 누락된 weight table은 기본값으로 채웁니다.
        # EN: Fill missing weight table in old data with a safe default.
        if "m_FontWeightTable" not in result:
            font_weights = result.get("fontWeights", [])
            result["m_FontWeightTable"] = font_weights if font_weights else []

    return result


def find_assets_files(game_path: str, lang: Language = "ko") -> list[str]:
    """KR: 게임에서 처리 대상 에셋 파일 목록을 수집합니다.
    EN: Collect candidate asset files from the game.
    """
    data_path = get_data_path(game_path, lang=lang)
    assets_files: list[str] = []
    exclude_exts = {".dll", ".manifest", ".exe", ".txt", ".json", ".xml", ".log", ".ini", ".cfg", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".wav", ".mp3", ".ogg", ".mp4", ".avi", ".mov"}
    for root, _, files in os.walk(data_path):
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in exclude_exts:
                assets_files.append(os.path.join(root, fn))
    return assets_files

def get_compile_method(datapath: str) -> str:
    """KR: 데이터 폴더의 컴파일 방식을 Mono/Il2cpp로 판별합니다.
    EN: Detect compile method as Mono or Il2cpp.
    """
    if "Managed" in os.listdir(datapath):
        return "Mono"
    else:
        return "Il2cpp"


def _create_generator(
    unity_version: str,
    game_path: str,
    data_path: str,
    compile_method: str,
    lang: Language = "ko",
) -> TypeTreeGenerator:
    """KR: 타입트리 생성기를 구성하고 Mono/Il2cpp 메타데이터를 로드합니다.
    EN: Build typetree generator and load Mono/Il2cpp metadata.
    """
    generator = TypeTreeGenerator(unity_version)
    if compile_method == "Mono":
        managed_dir = os.path.join(data_path, "Managed")
        for fn in os.listdir(managed_dir):
            if not fn.endswith(".dll"):
                continue
            try:
                with open(os.path.join(managed_dir, fn), "rb") as f:
                    generator.load_dll(f.read())
            except Exception as e:
                if lang == "ko":
                    print(f"[generator] DLL 로드 실패: {fn} ({e})")
                else:
                    print(f"[generator] Failed to load DLL: {fn} ({e})")
    else:
        il2cpp_path = os.path.join(game_path, "GameAssembly.dll")
        with open(il2cpp_path, "rb") as f:
            il2cpp = f.read()
        metadata_path = os.path.join(data_path, "il2cpp_data", "Metadata", "global-metadata.dat")
        with open(metadata_path, "rb") as f:
            metadata = f.read()
        generator.load_il2cpp(il2cpp, metadata)
    return generator


def scan_fonts(game_path: str, lang: Language = "ko") -> dict[str, list[JsonDict]]:
    """KR: 게임 에셋을 스캔해 TTF/SDF 폰트 목록을 반환합니다.
    EN: Scan game assets and return TTF/SDF font entries.
    """
    data_path = get_data_path(game_path, lang=lang)
    unity_version = get_unity_version(game_path, lang=lang)
    assets_files = find_assets_files(game_path, lang=lang)
    compile_method = get_compile_method(data_path)
    generator = _create_generator(unity_version, game_path, data_path, compile_method, lang=lang)

    fonts: dict[str, list[JsonDict]] = {
        "ttf": [],
        "sdf": [],
    }

    for assets_file in assets_files:
        try:
            env = UnityPy.load(assets_file)
            env.typetree_generator = generator

        except Exception as e:
            if lang == "ko":
                print(f"[scan_fonts] UnityPy.load 실패: {assets_file} ({e})")
            else:
                print(f"[scan_fonts] UnityPy.load failed: {assets_file} ({e})")
            continue

        for obj in env.objects:
            try:
                if obj.type.name == "Font":
                    font = obj.parse_as_object()
                    fonts["ttf"].append({
                        "file": os.path.basename(assets_file),
                        "assets_name": obj.assets_file.name,
                        "name": font.m_Name,
                        "path_id": obj.path_id
                    })
                elif obj.type.name == "MonoBehaviour":
                    parse_dict = None
                    is_font = False
                    try:
                        parse_obj = obj.parse_as_object()
                        if hasattr(parse_obj, 'get_type') and parse_obj.get_type() == "TMP_FontAsset":
                            is_font = True
                    except Exception:
                        if lang == "ko":
                            debug_parse_log(f"[scan_fonts] parse_as_object 실패: {os.path.basename(assets_file)} | PathID {obj.path_id}")
                        else:
                            debug_parse_log(f"[scan_fonts] parse_as_object failed: {os.path.basename(assets_file)} | PathID {obj.path_id}")
                    if not is_font:
                        try:
                            parse_dict = obj.parse_as_dict()
                            # KR: TMP 스키마 판별: 신형(m_FaceInfo/m_AtlasTextures) 또는 구형(m_fontInfo/atlas)
                            # EN: Detect TMP schema: new(m_FaceInfo/m_AtlasTextures) or old(m_fontInfo/atlas)
                            if ("m_AtlasTextures" in parse_dict and "m_FaceInfo" in parse_dict) or \
                               ("atlas" in parse_dict and "m_fontInfo" in parse_dict):
                                is_font = True
                        except Exception:
                            if lang == "ko":
                                debug_parse_log(f"[scan_fonts] parse_as_dict 실패: {os.path.basename(assets_file)} | PathID {obj.path_id}")
                            else:
                                debug_parse_log(f"[scan_fonts] parse_as_dict failed: {os.path.basename(assets_file)} | PathID {obj.path_id}")
                    if is_font:
                        try:
                            if parse_dict is None:
                                parse_dict = obj.parse_as_dict()
                            # KR: 신형/구형 TMP 모두에서 유효 글리프를 확인합니다.
                            # EN: Validate effective glyph presence across new/old TMP schemas.
                            atlas_textures = parse_dict.get("m_AtlasTextures", [])
                            glyph_count = len(parse_dict.get("m_GlyphTable", []))
                            if not atlas_textures and "atlas" in parse_dict:
                                atlas_textures = []
                            if glyph_count == 0:
                                glyph_count = len(parse_dict.get("m_glyphInfoList", []))
                            if atlas_textures:
                                first_atlas = atlas_textures[0]
                                file_id = first_atlas.get("m_FileID", 0)
                                path_id = first_atlas.get("m_PathID", 0)
                                # KR: 외부 참조 stub(FileID!=0, PathID=0)은 실제 교체 대상이 아닙니다.
                                # EN: External stubs (FileID!=0, PathID=0) are not valid replacement targets.
                                if file_id != 0 and path_id == 0:
                                    continue
                            if glyph_count == 0:
                                continue
                        except Exception:
                            if lang == "ko":
                                debug_parse_log(f"[scan_fonts] SDF 필드 검사 실패: {os.path.basename(assets_file)} | PathID {obj.path_id}")
                            else:
                                debug_parse_log(f"[scan_fonts] SDF field check failed: {os.path.basename(assets_file)} | PathID {obj.path_id}")
                        fonts["sdf"].append({
                            "file": os.path.basename(assets_file),
                            "assets_name": obj.assets_file.name,
                            "name": obj.peek_name(),
                            "path_id": obj.path_id
                        })
            except Exception as e:
                if lang == "ko":
                    print(f"[scan_fonts] 오브젝트 처리 실패: {os.path.basename(assets_file)} | PathID {obj.path_id} ({e})")
                else:
                    print(f"[scan_fonts] Object processing failed: {os.path.basename(assets_file)} | PathID {obj.path_id} ({e})")
                continue

    return fonts


def parse_fonts(game_path: str, lang: Language = "ko") -> str:
    """KR: 스캔한 폰트를 JSON으로 저장하고 결과 파일 경로를 반환합니다.
    EN: Save scanned fonts to JSON and return output file path.
    """
    fonts = scan_fonts(game_path, lang=lang)
    game_name = os.path.basename(game_path)
    output_file = os.path.join(get_script_dir(), f"{game_name}.json")

    result: dict[str, JsonDict] = {}

    for font in fonts["ttf"]:
        key = f"{font['file']}|{font['assets_name']}|{font['name']}|TTF|{font['path_id']}"
        result[key] = {
            "File": font["file"],
            "assets_name": font["assets_name"],
            "Path_ID": font["path_id"],
            "Type": "TTF",
            "Name": font["name"],
            "Replace_to": ""
        }

    for font in fonts["sdf"]:
        key = f"{font['file']}|{font['assets_name']}|{font['name']}|SDF|{font['path_id']}"
        result[key] = {
            "File": font["file"],
            "assets_name": font["assets_name"],
            "Path_ID": font["path_id"],
            "Type": "SDF",
            "Name": font["name"],
            "Replace_to": ""
        }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4, ensure_ascii=False)

    if lang == "ko":
        print(f"폰트 정보가 '{output_file}'에 저장되었습니다.")
        print(f"  - TTF 폰트: {len(fonts['ttf'])}개")
        print(f"  - SDF 폰트: {len(fonts['sdf'])}개")
    else:
        print(f"Font information saved to '{output_file}'.")
        print(f"  - TTF fonts: {len(fonts['ttf'])}")
        print(f"  - SDF fonts: {len(fonts['sdf'])}")
    return output_file


@lru_cache(maxsize=64)
def _load_font_assets_cached(script_dir: str, normalized: str) -> JsonDict:
    """KR: KR_ASSETS에서 폰트 리소스를 읽어 캐시에 저장합니다.
    EN: Load and cache font resources from KR_ASSETS.
    """
    kr_assets = os.path.join(script_dir, "KR_ASSETS")

    ttf_path = os.path.join(kr_assets, f"{normalized}.ttf")
    ttf_data = None
    if os.path.exists(ttf_path):
        with open(ttf_path, "rb") as f:
            ttf_data = f.read()

    sdf_json_path = os.path.join(kr_assets, f"{normalized} SDF.json")
    sdf_data = None
    if os.path.exists(sdf_json_path):
        with open(sdf_json_path, "r", encoding="utf-8") as f:
            sdf_data = json.load(f)

    sdf_atlas_path = os.path.join(kr_assets, f"{normalized} SDF Atlas.png")
    sdf_atlas = None
    if os.path.exists(sdf_atlas_path):
        with open(sdf_atlas_path, "rb") as f:
            sdf_atlas = Image.open(f)
            sdf_atlas.load()

    sdf_material_path = os.path.join(kr_assets, f"{normalized} SDF Material.json")
    sdf_material_data = None
    if os.path.exists(sdf_material_path):
        with open(sdf_material_path, "r", encoding="utf-8") as f:
            sdf_material_data = json.load(f)

    return {
        "ttf_data": ttf_data,
        "sdf_data": sdf_data,
        "sdf_atlas": sdf_atlas,
        "sdf_materials": sdf_material_data
    }


def load_font_assets(font_name: str) -> JsonDict:
    """KR: 지정 폰트명의 교체용 리소스(TTF/SDF/Atlas/Material)를 로드합니다.
    EN: Load replacement assets (TTF/SDF/Atlas/Material) for a font name.
    """
    normalized = normalize_font_name(font_name)
    cached_assets = _load_font_assets_cached(get_script_dir(), normalized)
    atlas = cached_assets["sdf_atlas"]
    return {
        "ttf_data": cached_assets["ttf_data"],
        "sdf_data": cached_assets["sdf_data"],
        "sdf_atlas": atlas.copy() if atlas is not None else None,
        "sdf_materials": cached_assets["sdf_materials"],
    }


def replace_fonts_in_file(
    unity_version: str,
    game_path: str,
    assets_file: str,
    replacements: dict[str, JsonDict],
    replace_ttf: bool = True,
    replace_sdf: bool = True,
    use_game_mat: bool = False,
    generator: TypeTreeGenerator | None = None,
    replacement_lookup: dict[tuple[str, str, str, int], str] | None = None,
    lang: Language = "ko",
) -> bool:
    """KR: 단일 assets 파일의 TTF/SDF 폰트를 교체하고 저장합니다.
    EN: Replace TTF/SDF fonts in one assets file and save changes.
    """
    fn_without_path = os.path.basename(assets_file)
    data_path = get_data_path(game_path, lang=lang)
    tmp_path = os.path.join(data_path, "temp")

    if not os.path.exists(tmp_path):
        os.makedirs(tmp_path)
    else:
        shutil.rmtree(tmp_path)
        os.makedirs(tmp_path)

    env = UnityPy.load(assets_file)
    if generator is None:
        compile_method = get_compile_method(data_path)
        generator = _create_generator(unity_version, game_path, data_path, compile_method, lang=lang)
    env.typetree_generator = generator
    if replacement_lookup is None:
        replacement_lookup, _ = build_replacement_lookup(replacements)

    texture_replacements: dict[str, Any] = {}
    material_replacements: dict[str, JsonDict] = {}
    modified = False

    for obj in env.objects:
        assets_name = obj.assets_file.name
        if obj.type.name == "Font" and replace_ttf:
            font_pathid = obj.path_id
            replacement_font = replacement_lookup.get(("TTF", fn_without_path, assets_name, font_pathid))

            if replacement_font:
                assets = load_font_assets(replacement_font)
                if assets["ttf_data"]:
                    font = obj.parse_as_object()
                    if lang == "ko":
                        print(f"TTF 폰트 교체: {assets_name} | {font.m_Name} | (PathID: {font_pathid} -> {replacement_font})")
                    else:
                        print(f"TTF font replaced: {assets_name} | {font.m_Name} | (PathID: {font_pathid} -> {replacement_font})")
                    font.m_FontData = assets["ttf_data"]
                    font.save()
                    modified = True

        if obj.type.name == "MonoBehaviour" and replace_sdf:
            try:
                parse_dict = obj.parse_as_dict()
            except Exception:
                if lang == "ko":
                    debug_parse_log(f"[replace_fonts] MonoBehaviour parse_as_dict 실패: {fn_without_path} | PathID {obj.path_id}")
                else:
                    debug_parse_log(f"[replace_fonts] MonoBehaviour parse_as_dict failed: {fn_without_path} | PathID {obj.path_id}")
                continue
            has_new_keys = "m_FaceInfo" in parse_dict and "m_AtlasTextures" in parse_dict
            has_old_keys = "m_fontInfo" in parse_dict and "atlas" in parse_dict
            if has_new_keys or has_old_keys:
                target_version = detect_tmp_version(parse_dict)
                is_new_tmp = (target_version == "new")
                is_old_tmp = (target_version == "old")
                # KR: 외부 참조 stub만 제외하고 실제 TMP 폰트만 처리합니다.
                # EN: Skip external stubs and process only concrete TMP font assets.
                if is_new_tmp:
                    atlas_textures = parse_dict.get("m_AtlasTextures", [])
                    glyph_count = len(parse_dict.get("m_GlyphTable", []))
                else:
                    atlas_textures = []
                    glyph_count = len(parse_dict.get("m_glyphInfoList", []))
                if atlas_textures:
                    first_atlas = atlas_textures[0]
                    if first_atlas.get("m_FileID", 0) != 0 and first_atlas.get("m_PathID", 0) == 0:
                        continue
                if glyph_count == 0:
                    continue

                objname = obj.peek_name()
                pathid = obj.path_id
                replacement_font = replacement_lookup.get(("SDF", fn_without_path, assets_name, pathid))

                if replacement_font:
                    assets = load_font_assets(replacement_font)
                    if assets["sdf_data"] and assets["sdf_atlas"]:
                        if lang == "ko":
                            print(f"SDF 폰트 교체: {assets_name} | {objname} | (PathID: {pathid}) -> {replacement_font}")
                        else:
                            print(f"SDF font replaced: {assets_name} | {objname} | (PathID: {pathid}) -> {replacement_font}")

                        # KR: 입력 JSON이 신형/구형이어도 내부 교체는 신형 TMP 스키마로 통일합니다.
                        # EN: Normalize replacement JSON to the new TMP schema regardless of input format.
                        replace_data = normalize_sdf_data(assets["sdf_data"])

                        # KR: GameObject/Script/Material/Atlas 참조는 기존 PathID를 유지해야 런타임 연결이 깨지지 않습니다.
                        # EN: Preserve original GameObject/Script/Material/Atlas references to keep runtime links intact.
                        m_GameObject_FileID = parse_dict["m_GameObject"]["m_FileID"]
                        m_GameObject_PathID = parse_dict["m_GameObject"]["m_PathID"]
                        m_Script_FileID = parse_dict["m_Script"]["m_FileID"]
                        m_Script_PathID = parse_dict["m_Script"]["m_PathID"]

                        if parse_dict.get("m_Material") is not None:
                            m_Material_FileID = parse_dict["m_Material"]["m_FileID"]
                            m_Material_PathID = parse_dict["m_Material"]["m_PathID"]
                        else:
                            m_Material_FileID = parse_dict["material"]["m_FileID"]
                            m_Material_PathID = parse_dict["material"]["m_PathID"]

                        if is_old_tmp:
                            # KR: 대상이 구형 TMP면 교체 데이터도 구형 필드로 역변환해 적용합니다.
                            # EN: For old TMP targets, convert replacement data back to old schema before patching.
                            atlas_ref = parse_dict["atlas"]
                            m_AtlasTextures_FileID = atlas_ref["m_FileID"]
                            m_AtlasTextures_PathID = atlas_ref["m_PathID"]

                            old_font_info = convert_face_info_new_to_old(
                                replace_data["m_FaceInfo"],
                                replace_data.get("m_AtlasPadding", 0),
                                replace_data.get("m_AtlasWidth", 0),
                                replace_data.get("m_AtlasHeight", 0)
                            )
                            replacement_atlas = assets.get("sdf_atlas")
                            atlas_height = int(
                                replace_data.get(
                                    "m_AtlasHeight",
                                    replacement_atlas.height if replacement_atlas is not None else 0,
                                )
                            )
                            flip_new_glyph_y = detect_new_glyph_y_flip(
                                replace_data.get("m_GlyphTable", []),
                                replace_data.get("m_CharacterTable", []),
                                replacement_atlas if isinstance(replacement_atlas, Image.Image) else None,
                            )
                            if flip_new_glyph_y:
                                if lang == "ko":
                                    print("  구형 TMP 좌표계 보정(Y-flip) 적용")
                                else:
                                    print("  Applying old TMP coordinate fix (Y-flip)")
                            old_glyph_list = convert_glyphs_new_to_old(
                                replace_data.get("m_GlyphTable", []),
                                replace_data.get("m_CharacterTable", []),
                                atlas_height=atlas_height,
                                flip_y=flip_new_glyph_y,
                            )
                            old_font_info["CharacterCount"] = len(old_glyph_list)
                            parse_dict["m_fontInfo"] = old_font_info
                            parse_dict["m_glyphInfoList"] = old_glyph_list

                            if "m_CreationSettings" in parse_dict:
                                cs = parse_dict["m_CreationSettings"]
                                cs["atlasWidth"] = int(replace_data.get("m_AtlasWidth", cs.get("atlasWidth", 0)))
                                cs["atlasHeight"] = int(replace_data.get("m_AtlasHeight", cs.get("atlasHeight", 0)))
                                cs["pointSize"] = int(old_font_info["PointSize"])
                                cs["padding"] = int(old_font_info["Padding"])
                                cs["characterSequence"] = ""

                        else:
                            # KR: 대상이 신형 TMP면 정규화된 신형 필드를 그대로 적용합니다.
                            # EN: For new TMP targets, apply normalized new-schema fields directly.
                            m_SourceFontFile_FileID = parse_dict["m_SourceFontFile"]["m_FileID"]
                            m_SourceFontFile_PathID = parse_dict["m_SourceFontFile"]["m_PathID"]
                            m_AtlasTextures_FileID = parse_dict["m_AtlasTextures"][0]["m_FileID"]
                            m_AtlasTextures_PathID = parse_dict["m_AtlasTextures"][0]["m_PathID"]

                            if "m_GlyphTable" in replace_data and isinstance(replace_data["m_GlyphTable"], list):
                                for glyph in replace_data["m_GlyphTable"]:
                                    glyph["m_ClassDefinitionType"] = 0

                            parse_dict["m_FaceInfo"] = replace_data["m_FaceInfo"]
                            parse_dict["m_GlyphTable"] = replace_data["m_GlyphTable"]
                            parse_dict["m_CharacterTable"] = replace_data["m_CharacterTable"]
                            parse_dict["m_AtlasTextures"] = replace_data["m_AtlasTextures"]
                            parse_dict["m_AtlasWidth"] = replace_data["m_AtlasWidth"]
                            parse_dict["m_AtlasHeight"] = replace_data["m_AtlasHeight"]
                            parse_dict["m_AtlasPadding"] = replace_data["m_AtlasPadding"]
                            parse_dict["m_AtlasRenderMode"] = replace_data.get("m_AtlasRenderMode", 4118)
                            parse_dict["m_UsedGlyphRects"] = replace_data.get("m_UsedGlyphRects", [])
                            parse_dict["m_FreeGlyphRects"] = replace_data.get("m_FreeGlyphRects", [])
                            parse_dict["m_FontWeightTable"] = replace_data.get("m_FontWeightTable", [])

                            ensure_int(parse_dict["m_FaceInfo"], ["m_PointSize", "m_AtlasWidth", "m_AtlasHeight"])

                            if "m_CreationSettings" in parse_dict:
                                ensure_int(parse_dict["m_CreationSettings"], ["pointSize", "atlasWidth", "atlasHeight", "padding"])

                            for glyph in parse_dict["m_GlyphTable"]:
                                ensure_int(glyph, ["m_Index", "m_AtlasIndex", "m_ClassDefinitionType"])
                                if "m_GlyphRect" in glyph:
                                    ensure_int(glyph["m_GlyphRect"], ["m_X", "m_Y", "m_Width", "m_Height"])

                            for char in parse_dict["m_CharacterTable"]:
                                ensure_int(char, ["m_Unicode", "m_GlyphIndex", "m_ElementType"])

                            for rect_list_name in ["m_UsedGlyphRects", "m_FreeGlyphRects"]:
                                if rect_list_name in parse_dict:
                                    for rect in parse_dict[rect_list_name]:
                                        ensure_int(rect, ["m_X", "m_Y", "m_Width", "m_Height"])

                            parse_dict["m_SourceFontFile"]["m_FileID"] = m_SourceFontFile_FileID
                            parse_dict["m_SourceFontFile"]["m_PathID"] = m_SourceFontFile_PathID
                            parse_dict["m_AtlasTextures"][0]["m_FileID"] = m_AtlasTextures_FileID
                            parse_dict["m_AtlasTextures"][0]["m_PathID"] = m_AtlasTextures_PathID
                            if "m_CreationSettings" in parse_dict:
                                parse_dict["m_CreationSettings"]["characterSequence"] = ""

                        # KR: 포맷 분기 후 공통 참조를 원래 값으로 되돌립니다.
                        # EN: Restore shared references to original values after schema-specific patching.
                        parse_dict["m_GameObject"]["m_FileID"] = m_GameObject_FileID
                        parse_dict["m_GameObject"]["m_PathID"] = m_GameObject_PathID
                        parse_dict["m_Script"]["m_FileID"] = m_Script_FileID
                        parse_dict["m_Script"]["m_PathID"] = m_Script_PathID

                        if parse_dict.get("m_Material") is not None:
                            parse_dict["m_Material"]["m_FileID"] = m_Material_FileID
                            parse_dict["m_Material"]["m_PathID"] = m_Material_PathID
                        else:
                            parse_dict["material"]["m_FileID"] = m_Material_FileID
                            parse_dict["material"]["m_PathID"] = m_Material_PathID

                        if is_old_tmp:
                            parse_dict["atlas"]["m_FileID"] = m_AtlasTextures_FileID
                            parse_dict["atlas"]["m_PathID"] = m_AtlasTextures_PathID

                        texture_replacements[f"{assets_name}|{m_AtlasTextures_PathID}"] = assets["sdf_atlas"]
                        if m_Material_FileID == 0 and m_Material_PathID != 0:
                            gradient_scale = None
                            apply_replacement_material = not use_game_mat
                            float_overrides: dict[str, float] = {}
                            material_data = assets.get("sdf_materials")
                            if material_data and apply_replacement_material:
                                material_props = material_data.get("m_SavedProperties", {})
                                float_properties = material_props.get("m_Floats", [])
                                for prop in float_properties:
                                    if not isinstance(prop, (list, tuple)) or len(prop) < 2:
                                        continue
                                    key = str(prop[0])
                                    try:
                                        value = float(prop[1])
                                    except (TypeError, ValueError):
                                        continue
                                    float_overrides[key] = value
                                gradient_scale = float_overrides.get("_GradientScale")
                            material_replacements[f"{assets_name}|{m_Material_PathID}"] = {
                                "w": assets["sdf_atlas"].width,
                                "h": assets["sdf_atlas"].height,
                                "gs": gradient_scale,
                                "float_overrides": float_overrides,
                            }
                        obj.patch(parse_dict)
                        modified = True

    for obj in env.objects:
        assets_name = obj.assets_file.name
        if obj.type.name == "Texture2D":
            if f"{assets_name}|{obj.path_id}" in texture_replacements:
                parse_dict = obj.parse_as_object()
                if lang == "ko":
                    print(f"텍스처 교체: {obj.peek_name()} (PathID: {obj.path_id})")
                else:
                    print(f"Texture replaced: {obj.peek_name()} (PathID: {obj.path_id})")
                parse_dict.image = texture_replacements[f"{assets_name}|{obj.path_id}"]
                parse_dict.save()
                modified = True
        if obj.type.name == "Material":
            if f"{assets_name}|{obj.path_id}" in material_replacements:
                parse_dict = obj.parse_as_object()

                mat_info = material_replacements[f"{assets_name}|{obj.path_id}"]
                float_overrides = mat_info.get("float_overrides", {})
                for i in range(len(parse_dict.m_SavedProperties.m_Floats)):
                    prop_name = parse_dict.m_SavedProperties.m_Floats[i][0]
                    if prop_name in float_overrides:
                        parse_dict.m_SavedProperties.m_Floats[i] = (prop_name, float(float_overrides[prop_name]))
                    elif prop_name == '_TextureHeight':
                        parse_dict.m_SavedProperties.m_Floats[i] = ('_TextureHeight', float(mat_info["h"]))
                    elif prop_name == '_TextureWidth':
                        parse_dict.m_SavedProperties.m_Floats[i] = ('_TextureWidth', float(mat_info["w"]))
                    elif prop_name == '_GradientScale' and mat_info["gs"] is not None:
                        parse_dict.m_SavedProperties.m_Floats[i] = ('_GradientScale', float(mat_info["gs"]))
                parse_dict.save()

    if modified:
        if lang == "ko":
            print(f"'{fn_without_path}' 저장 중...")
        else:
            print(f"Saving '{fn_without_path}'...")

        save_success = False

        def _save_env_file(packer: Any = None) -> bytes:
            """KR: 지정 packer로 env.file.save를 호출합니다.
            EN: Call env.file.save with an optional packer.
            """
            save_fn = getattr(env.file, "save", None)
            if not callable(save_fn):
                raise AttributeError("UnityPy environment file object has no callable save().")
            typed_save = cast(Callable[..., bytes], save_fn)
            # KR: save() 시그니처를 기준으로 packer 지원 여부를 판별해 내부 TypeError를 가리지 않도록 합니다.
            # EN: Detect packer support from save() signature so we don't swallow internal TypeError.
            try:
                supports_packer = "packer" in inspect.signature(typed_save).parameters
            except (TypeError, ValueError):
                supports_packer = False

            if packer is None or not supports_packer:
                return typed_save()
            return typed_save(packer=packer)

        def _validate_saved_blob(saved_blob: bytes) -> bool:
            """KR: 저장 결과 blob이 Unity bundle로 다시 열리는지 검증합니다.
            EN: Validate saved blob by attempting to reload with UnityPy.
            """
            signature = getattr(env.file, "signature", None)
            if signature not in {"UnityFS", "UnityWeb", "UnityRaw"}:
                return True
            try:
                UnityPy.load(saved_blob)
                return True
            except Exception as e:
                if lang == "ko":
                    print(f"  저장 검증 실패: {e}")
                else:
                    print(f"  Save validation failed: {e}")
                return False

        def _try_save(packer_label: Any, log_label: str) -> bool:
            """KR: 단일 저장 전략을 시도하고 성공 여부를 반환합니다.
            EN: Try one save strategy and return success status.
            """
            nonlocal save_success
            try:
                sf = _save_env_file(packer_label)
                if not _validate_saved_blob(sf):
                    return False
                with open(f"{tmp_path}/{fn_without_path}", "wb") as f:
                    f.write(sf)
                save_success = True
                return True
            except Exception as e:
                if lang == "ko":
                    print(f"  저장 방법 {log_label} 실패 [{type(e).__name__}]: {e!r}")
                else:
                    print(f"  Save method {log_label} failed [{type(e).__name__}]: {e!r}")
                if debug_parse_enabled():
                    tb_module.print_exc()
                return False

        # KR: 저장 안정성을 위해 original -> lz4 -> safe-none 순서로 저장을 재시도합니다.
        # EN: For save stability, retry packers in order: original -> lz4 -> safe-none.
        if not _try_save("original", "1"):
            if lang == "ko":
                print("  lz4 압축 모드로 재시도...")
            else:
                print("  Retrying with lz4 packer...")
            if not _try_save("lz4", "2"):
                dataflags = getattr(env.file, "dataflags", None)
                safe_none_packer = (int(dataflags), 0) if dataflags is not None else "none"
                if lang == "ko":
                    print("  비압축 계열 모드로 재시도...")
                else:
                    print("  Retrying with uncompressed-style packer...")
                if not _try_save(safe_none_packer, "3") and dataflags is not None:
                    legacy_none_packer = ((int(dataflags) & ~0x3F), 0)
                    if lang == "ko":
                        print("  레거시 비트마스크 모드로 재시도...")
                    else:
                        print("  Retrying with legacy bitmask packer...")
                    _try_save(legacy_none_packer, "4")

        if save_success:
            def _close_reader(obj: Any) -> None:
                """KR: UnityPy 내부 reader/객체를 안전하게 dispose합니다.
                EN: Safely dispose UnityPy internal reader/object resources.
                """
                reader = getattr(obj, "reader", None)
                if reader is not None and hasattr(reader, "dispose"):
                    try:
                        reader.dispose()
                    except Exception:
                        pass
                if hasattr(obj, "dispose"):
                    try:
                        obj.dispose()
                    except Exception:
                        pass

            def _close_env(environment: Any) -> None:
                """KR: Environment에 연결된 파일 리소스를 순회 종료합니다.
                EN: Walk and close file resources attached to environment.
                """
                if not environment:
                    return
                stack: list[Any] = []
                files = getattr(environment, "files", None)
                if isinstance(files, dict):
                    stack.extend(files.values())
                while stack:
                    item = stack.pop()
                    _close_reader(item)
                    sub_files = getattr(item, "files", None)
                    if isinstance(sub_files, dict):
                        stack.extend(sub_files.values())

            _close_env(env)

            saved_file_path = os.path.join(tmp_path, fn_without_path)
            if os.path.exists(saved_file_path):
                saved_size = os.path.getsize(saved_file_path)
                shutil.move(saved_file_path, assets_file)
                if lang == "ko":
                    print(f"  저장 완료 (크기: {saved_size} bytes)")
                else:
                    print(f"  Save complete (size: {saved_size} bytes)")
            else:
                if lang == "ko":
                    print("  경고: 저장된 파일을 찾을 수 없습니다")
                else:
                    print("  Warning: saved file was not found")
                save_success = False

        if not save_success:
            if lang == "ko":
                print("  오류: 파일 저장에 실패했습니다.")
            else:
                print("  Error: failed to save file.")

    if os.path.exists(tmp_path):
        shutil.rmtree(tmp_path)

    return save_success if modified else False


def create_batch_replacements(
    game_path: str,
    font_name: str,
    replace_ttf: bool = True,
    replace_sdf: bool = True,
    lang: Language = "ko",
) -> dict[str, JsonDict]:
    """KR: 게임 내 모든 폰트를 지정 폰트로 치환하는 배치 매핑을 생성합니다.
    EN: Create batch replacement mapping for all fonts in a game.
    """
    fonts = scan_fonts(game_path, lang=lang)
    replacements: dict[str, JsonDict] = {}

    if replace_ttf:
        for font in fonts["ttf"]:
            key = f"{font['file']}|TTF|{font['path_id']}"
            replacements[key] = {
                "Name": font["name"],
                "assets_name": font["assets_name"],
                "Path_ID": font["path_id"],
                "Type": "TTF",
                "File": font["file"],
                "Replace_to": font_name
            }

    if replace_sdf:
        for font in fonts["sdf"]:
            key = f"{font['file']}|SDF|{font['path_id']}"
            replacements[key] = {
                "Name": font["name"],
                "assets_name": font["assets_name"],
                "Path_ID": font["path_id"],
                "Type": "SDF",
                "File": font["file"],
                "Replace_to": font_name
            }

    return replacements


def exit_with_error(message: str, lang: Language = "ko") -> NoReturn:
    """KR: 로컬라이즈된 오류 메시지를 출력하고 종료합니다.
    EN: Print localized error message and terminate the process.
    """
    if lang == "ko":
        print(f"오류: {message}")
    else:
        print(f"Error: {message}")
    if lang == "ko":
        input("\n엔터를 눌러 종료...")
    else:
        input("\nPress Enter to exit...")
    sys.exit(1)


def exit_with_error_en(message: str) -> NoReturn:
    """KR: 영문 오류 메시지를 출력하고 종료합니다.
    EN: Print English error message and terminate the process.
    """
    exit_with_error(message, lang="en")


def main_cli(lang: Language = "ko") -> None:
    """KR: 언어별 공통 CLI 진입점입니다.
    EN: Shared CLI entrypoint parameterized by language.
    """
    is_ko = lang == "ko"

    if is_ko:
        description = "Unity 게임의 폰트를 한글 폰트로 교체합니다."
        epilog = """
예시:
  %(prog)s --gamepath "D:\\Games\\Muck" --parse
  %(prog)s --gamepath "D:\\Games\\Muck" --mulmaru
  %(prog)s --gamepath "D:\\Games\\Muck" --nanumgothic --sdfonly
  %(prog)s --gamepath "D:\\Games\\Muck" --list Muck.json
        """
        gamepath_help = "게임의 루트 경로 (예: D:\\Games\\Muck)"
        parse_help = "폰트 정보를 JSON으로 출력"
        mulmaru_help = "모든 폰트를 Mulmaru로 일괄 교체"
        nanum_help = "모든 폰트를 NanumGothic으로 일괄 교체"
        sdf_help = "SDF 폰트만 교체"
        ttf_help = "TTF 폰트만 교체"
        list_help = "JSON 파일을 읽어서 폰트 교체"
        game_mat_help = "SDF 교체 시 게임 원본 Material 파라미터를 유지"
        verbose_help = "모든 로그를 verbose.txt 파일로 저장"
    else:
        description = "Replace Unity game fonts with Korean fonts."
        epilog = """
Examples:
  %(prog)s --gamepath "D:\\Games\\Muck" --parse
  %(prog)s --gamepath "D:\\Games\\Muck" --mulmaru
  %(prog)s --gamepath "D:\\Games\\Muck" --nanumgothic --sdfonly
  %(prog)s --gamepath "D:\\Games\\Muck" --list Muck.json
        """
        gamepath_help = "Game root path (e.g. D:\\Games\\Muck)"
        parse_help = "Export font info to JSON"
        mulmaru_help = "Replace all fonts with Mulmaru"
        nanum_help = "Replace all fonts with NanumGothic"
        sdf_help = "Replace SDF fonts only"
        ttf_help = "Replace TTF fonts only"
        list_help = "Replace fonts using a JSON file"
        game_mat_help = "Keep original in-game Material parameters for SDF replacement"
        verbose_help = "Save all logs to verbose.txt"

    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog,
    )
    parser.add_argument("--gamepath", type=str, help=gamepath_help)
    parser.add_argument("--parse", action="store_true", help=parse_help)
    parser.add_argument("--mulmaru", action="store_true", help=mulmaru_help)
    parser.add_argument("--nanumgothic", action="store_true", help=nanum_help)
    parser.add_argument("--sdfonly", action="store_true", help=sdf_help)
    parser.add_argument("--ttfonly", action="store_true", help=ttf_help)
    parser.add_argument("--list", type=str, metavar="JSON_FILE", help=list_help)
    parser.add_argument("--use-game-mat", action="store_true", help=game_mat_help)
    parser.add_argument("--verbose", action="store_true", help=verbose_help)

    args = parser.parse_args()
    warn_unitypy_version(lang=lang)

    verbose_file = None
    if args.verbose:
        verbose_path = os.path.join(get_script_dir(), "verbose.txt")
        verbose_file = open(verbose_path, "w", encoding="utf-8")
        original_stdout = sys.__stdout__
        original_stderr = sys.__stderr__
        if original_stdout is None or original_stderr is None:
            if is_ko:
                exit_with_error("표준 출력 스트림을 사용할 수 없습니다.", lang=lang)
            else:
                exit_with_error("Standard output streams are unavailable.", lang=lang)
        sys.stdout = TeeWriter(verbose_file, original_stdout)
        sys.stderr = TeeWriter(verbose_file, original_stderr)
        if is_ko:
            print(f"[verbose] 로그를 '{verbose_path}'에 저장합니다.")
        else:
            print(f"[verbose] Saving logs to '{verbose_path}'.")

    input_path = args.gamepath
    if not input_path:
        if is_ko:
            input_path = input("게임 경로를 입력하세요: ").strip()
            if not input_path:
                exit_with_error("게임 경로가 필요합니다.", lang=lang)
        else:
            input_path = input("Enter game path: ").strip()
            if not input_path:
                exit_with_error("Game path is required.", lang=lang)

    if not os.path.isdir(input_path):
        if is_ko:
            exit_with_error(f"'{input_path}'는 유효한 디렉토리가 아닙니다.", lang=lang)
        else:
            exit_with_error(f"'{input_path}' is not a valid directory.", lang=lang)

    try:
        game_path, data_path = resolve_game_path(input_path, lang=lang)
        compile_method = get_compile_method(data_path)
        if is_ko:
            print(f"게임 경로: {game_path}")
            print(f"데이터 경로: {data_path}")
            print(f"컴파일 방식: {compile_method}")
        else:
            print(f"Game path: {game_path}")
            print(f"Data path: {data_path}")
            print(f"Compile method: {compile_method}")
    except FileNotFoundError as e:
        exit_with_error(str(e), lang=lang)

    if os.path.exists(os.path.join(data_path, "temp")):
        shutil.rmtree(os.path.join(data_path, "temp"))

    replace_ttf = not args.sdfonly
    replace_sdf = not args.ttfonly
    if args.sdfonly and args.ttfonly:
        if is_ko:
            exit_with_error("--sdfonly와 --ttfonly를 동시에 사용할 수 없습니다.", lang=lang)
        else:
            exit_with_error("Cannot use --sdfonly and --ttfonly at the same time.", lang=lang)

    replacements: dict[str, JsonDict] | None = None
    mode: str | None = None
    if args.parse:
        mode = "parse"
    elif args.mulmaru:
        mode = "mulmaru"
    elif args.nanumgothic:
        mode = "nanumgothic"
    elif args.list:
        mode = "list"
    else:
        if is_ko:
            print("작업을 선택하세요:")
            print("  1. 폰트 정보 추출 (JSON 파일 생성)")
            print("  2. JSON 파일로 폰트 교체")
            print("  3. Mulmaru(물마루체)로 일괄 교체")
            print("  4. NanumGothic(나눔고딕)으로 일괄 교체")
            print()
            choice = input("선택 (1-4): ").strip()
        else:
            print("Select a task:")
            print("  1. Export font info (create JSON)")
            print("  2. Replace fonts using JSON")
            print("  3. Bulk replace with Mulmaru")
            print("  4. Bulk replace with NanumGothic")
            print()
            choice = input("Choose (1-4): ").strip()

        if choice == "1":
            mode = "parse"
        elif choice == "2":
            mode = "list"
            if is_ko:
                args.list = input("JSON 파일 경로를 입력하세요: ").strip()
                if not args.list:
                    exit_with_error("JSON 파일 경로가 필요합니다.", lang=lang)
            else:
                args.list = input("Enter JSON file path: ").strip()
                if not args.list:
                    exit_with_error("JSON file path is required.", lang=lang)
        elif choice == "3":
            mode = "mulmaru"
        elif choice == "4":
            mode = "nanumgothic"
        else:
            if is_ko:
                exit_with_error("잘못된 선택입니다.", lang=lang)
            else:
                exit_with_error("Invalid selection.", lang=lang)

    if compile_method == "Il2cpp" and not os.path.exists(os.path.join(data_path, "Managed")):
        binary_path = os.path.join(game_path, "GameAssembly.dll")
        metadata_path = os.path.join(data_path, "il2cpp_data", "Metadata", "global-metadata.dat")
        if not os.path.exists(binary_path) or not os.path.exists(metadata_path):
            if is_ko:
                exit_with_error(
                    "Il2cpp 게임의 경우 'Managed' 폴더 또는 'GameAssembly.dll'과 'global-metadata.dat' 파일이 필요합니다.\n올바른 Unity 게임 폴더인지 확인해주세요.",
                    lang=lang,
                )
            else:
                exit_with_error(
                    "For Il2cpp games, the 'Managed' folder or 'GameAssembly.dll' and 'global-metadata.dat' files are required.\nPlease check that this is a valid Unity game folder.",
                    lang=lang,
                )

        dumper_path = os.path.join(get_script_dir(), "Il2CppDumper", "Il2CppDumper.exe")
        target_path = os.path.join(data_path, "Managed_")
        os.makedirs(target_path, exist_ok=True)
        command = [os.path.abspath(dumper_path), os.path.abspath(binary_path), os.path.abspath(metadata_path), os.path.abspath(target_path)]
        if is_ko:
            print("Il2cpp 게임을 위한 Managed 폴더를 생성합니다...")
        else:
            print("Creating Managed folder for Il2cpp game...")
        print(os.path.abspath(target_path))

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                startupinfo=startupinfo,
                encoding="utf-8",
            )
            if process.returncode == 0:
                print(process.stdout)
                shutil.move(os.path.join(data_path, "Managed_", "DummyDll"), os.path.join(data_path, "Managed"))
                shutil.rmtree(os.path.join(data_path, "Managed_"))
                if is_ko:
                    print("더미 DLL 생성에 성공했습니다!")
                else:
                    print("Dummy DLL generated successfully!")
                compile_method = get_compile_method(data_path)
                if is_ko:
                    print(f"컴파일 방식 재감지: {compile_method}")
                else:
                    print(f"Compile method re-detected: {compile_method}")
            else:
                print(process.stderr)
                if is_ko:
                    exit_with_error("Il2cpp 더미 DLL 생성 실패", lang=lang)
                else:
                    exit_with_error("Failed to generate Il2cpp dummy DLL", lang=lang)
        except Exception as e:
            if is_ko:
                exit_with_error(f"Il2CppDumper 실행 중 예외 발생: {e}", lang=lang)
            else:
                exit_with_error(f"Exception while running Il2CppDumper: {e}", lang=lang)

    if mode == "parse":
        parse_fonts(game_path, lang=lang)
        if is_ko:
            input("\n엔터를 눌러 종료...")
        else:
            input("\nPress Enter to exit...")
        return

    if mode == "mulmaru":
        if is_ko:
            print("Mulmaru 폰트로 일괄 교체합니다...")
        else:
            print("Bulk replacing with Mulmaru...")
        replacements = create_batch_replacements(game_path, "Mulmaru", replace_ttf, replace_sdf, lang=lang)
        ttf_count = sum(1 for v in replacements.values() if v["Type"] == "TTF")
        sdf_count = sum(1 for v in replacements.values() if v["Type"] == "SDF")
        if is_ko:
            print(f"발견된 폰트: TTF {ttf_count}개, SDF {sdf_count}개")
        else:
            print(f"Found fonts: TTF {ttf_count}, SDF {sdf_count}")
    elif mode == "nanumgothic":
        if is_ko:
            print("NanumGothic 폰트로 일괄 교체합니다...")
        else:
            print("Bulk replacing with NanumGothic...")
        replacements = create_batch_replacements(game_path, "NanumGothic", replace_ttf, replace_sdf, lang=lang)
        ttf_count = sum(1 for v in replacements.values() if v["Type"] == "TTF")
        sdf_count = sum(1 for v in replacements.values() if v["Type"] == "SDF")
        if is_ko:
            print(f"발견된 폰트: TTF {ttf_count}개, SDF {sdf_count}개")
        else:
            print(f"Found fonts: TTF {ttf_count}, SDF {sdf_count}")
    elif mode == "list":
        if not args.list or not os.path.exists(args.list):
            if is_ko:
                exit_with_error(f"'{args.list}' 파일을 찾을 수 없습니다.", lang=lang)
            else:
                exit_with_error(f"File not found: '{args.list}'", lang=lang)

        if is_ko:
            print(f"'{args.list}' 파일을 읽어서 교체합니다...")
        else:
            print(f"Replacing using '{args.list}'...")
        with open(args.list, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            if is_ko:
                exit_with_error("JSON 루트는 객체(dict)여야 합니다.", lang=lang)
            else:
                exit_with_error("JSON root must be an object (dict).", lang=lang)
        replacements = cast(dict[str, JsonDict], loaded)

    if replacements is None:
        if is_ko:
            exit_with_error("교체 정보가 생성되지 않았습니다.", lang=lang)
        else:
            exit_with_error("Replacement mapping was not generated.", lang=lang)

    unity_version = get_unity_version(game_path, lang=lang)
    assets_files = find_assets_files(game_path, lang=lang)
    generator = _create_generator(unity_version, game_path, data_path, compile_method, lang=lang)
    replacement_lookup, files_to_process = build_replacement_lookup(replacements)

    modified_count = 0
    for assets_file in assets_files:
        fn = os.path.basename(assets_file)
        if fn in files_to_process:
            if is_ko:
                print(f"\n처리 중: {fn}")
            else:
                print(f"\nProcessing: {fn}")
            # KR: 대형 SDF Atlas 다건 교체 시 UnityPy 저장 단계에서 메모리 피크가 커질 수 있어 파일 단위로 분할 저장합니다.
            # EN: Split save per file when many SDF atlas replacements exist to reduce UnityPy memory peak.
            file_replacements = {
                key: value
                for key, value in replacements.items()
                if isinstance(value, dict)
                and value.get("File") == fn
                and value.get("Replace_to")
            }
            file_ttf_replacements = {
                key: value
                for key, value in file_replacements.items()
                if value.get("Type") == "TTF"
            }
            file_sdf_replacements = {
                key: value
                for key, value in file_replacements.items()
                if value.get("Type") == "SDF"
            }

            file_modified = False
            use_split_sdf_save = replace_sdf and len(file_sdf_replacements) > 1

            if use_split_sdf_save:
                if is_ko:
                    print(
                        f"  SDF 대상 {len(file_sdf_replacements)}건 감지: 메모리 안정성을 위해 분할 저장 모드로 진행합니다..."
                    )
                else:
                    print(
                        f"  Detected {len(file_sdf_replacements)} SDF targets: using split-save mode for memory stability..."
                    )

                if replace_ttf and file_ttf_replacements:
                    file_ttf_lookup, _ = build_replacement_lookup(file_ttf_replacements)
                    if replace_fonts_in_file(
                        unity_version,
                        game_path,
                        assets_file,
                        file_ttf_replacements,
                        replace_ttf=True,
                        replace_sdf=False,
                        use_game_mat=args.use_game_mat,
                        generator=generator,
                        replacement_lookup=file_ttf_lookup,
                        lang=lang,
                    ):
                        file_modified = True

                if replace_sdf:
                    for key, value in file_sdf_replacements.items():
                        single_sdf = {key: value}
                        single_sdf_lookup, _ = build_replacement_lookup(single_sdf)
                        if replace_fonts_in_file(
                            unity_version,
                            game_path,
                            assets_file,
                            single_sdf,
                            replace_ttf=False,
                            replace_sdf=True,
                            use_game_mat=args.use_game_mat,
                            generator=generator,
                            replacement_lookup=single_sdf_lookup,
                            lang=lang,
                        ):
                            file_modified = True
            else:
                if replace_fonts_in_file(
                    unity_version,
                    game_path,
                    assets_file,
                    replacements,
                    replace_ttf,
                    replace_sdf,
                    use_game_mat=args.use_game_mat,
                    generator=generator,
                    replacement_lookup=replacement_lookup,
                    lang=lang,
                ):
                    file_modified = True

            if file_modified:
                modified_count += 1

    if is_ko:
        print(f"\n완료! {modified_count}개의 파일이 수정되었습니다.")
        input("\n엔터를 눌러 종료...")
    else:
        print(f"\nDone! Modified {modified_count} file(s).")
        input("\nPress Enter to exit...")


def main() -> None:
    """KR: 한국어 CLI 진입점입니다.
    EN: Korean CLI entrypoint.
    """
    main_cli(lang="ko")


def main_en() -> None:
    """KR: 영어 CLI 진입점입니다.
    EN: English CLI entrypoint.
    """
    main_cli(lang="en")


def _restore_tee_streams() -> None:
    """KR: TeeWriter로 교체된 stdout/stderr를 원상복구합니다.
    EN: Restore stdout/stderr replaced by TeeWriter.
    """
    if isinstance(sys.stdout, TeeWriter):
        sys.stdout.file.close()
        sys.stdout = sys.__stdout__
    if isinstance(sys.stderr, TeeWriter):
        sys.stderr.file.close()
        sys.stderr = sys.__stderr__


def run_main_ko() -> None:
    """KR: 한국어 실행 진입점을 예외 처리와 함께 실행합니다.
    EN: Run Korean entrypoint with top-level exception handling.
    """
    try:
        main()
    except Exception as e:
        print(f"\n예상치 못한 오류가 발생했습니다: {e}")
        tb_module.print_exc()
        input("\n엔터를 눌러 종료...")
        sys.exit(1)
    finally:
        _restore_tee_streams()


def run_main_en() -> None:
    """KR: 영어 실행 진입점을 예외 처리와 함께 실행합니다.
    EN: Run English entrypoint with top-level exception handling.
    """
    try:
        main_en()
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        tb_module.print_exc()
        input("\nPress Enter to exit...")
        sys.exit(1)
    finally:
        _restore_tee_streams()


if __name__ == "__main__":
    try:
        run_main_ko()
    except Exception as e:
        print(f"\n예상치 못한 오류가 발생했습니다: {e}")
        tb_module.print_exc()
        input("\n엔터를 눌러 종료...")
        sys.exit(1)
