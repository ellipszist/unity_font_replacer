from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Literal, NoReturn

import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator


Language = Literal["ko", "en"]
JsonDict = dict[str, Any]


def _debug_parse_enabled() -> bool:
    """KR: TMP 파싱 디버그 로그 출력 여부를 반환합니다.
    EN: Return whether TMP parsing debug logging is enabled.
    """
    return os.environ.get("UFR_DEBUG_PARSE", "").strip() == "1"


def _debug_parse_log(message: str) -> None:
    """KR: 디버그 모드일 때만 메시지를 출력합니다.
    EN: Print a debug message only when debug mode is enabled.
    """
    if _debug_parse_enabled():
        print(message)


def exit_with_error(lang: Language, message: str) -> NoReturn:
    """KR: 로컬라이즈된 오류를 출력하고 종료합니다.
    EN: Print a localized error and terminate the process.
    """
    if lang == "ko":
        print(f"오류: {message}")
        input("\n엔터를 눌러 종료...")
    else:
        print(f"Error: {message}")
        input("\nPress Enter to exit...")
    sys.exit(1)


def find_ggm_file(data_path: str) -> str | None:
    """KR: 데이터 폴더에서 globalgamemanagers 계열 파일을 찾습니다.
    EN: Find a globalgamemanagers-like file under the data folder.
    """
    candidates = [
        "globalgamemanagers",
        "globalgamemanagers.assets",
        "data.unity3d",
    ]
    for candidate in candidates:
        ggm_path = os.path.join(data_path, candidate)
        if os.path.exists(ggm_path):
            return ggm_path
    return None


def resolve_game_path(lang: Language, path: str | None = None) -> tuple[str, str]:
    """KR: 입력 경로를 게임 루트/데이터 폴더 경로로 정규화합니다.
    EN: Normalize an input path into game-root and data-folder paths.
    """
    if path is None:
        path = os.getcwd()

    path = os.path.normpath(os.path.abspath(path))

    if path.lower().endswith("_data"):
        data_path = path
        game_path = os.path.dirname(path)
    else:
        game_path = path
        data_folders = [
            d
            for d in os.listdir(path)
            if d.lower().endswith("_data") and os.path.isdir(os.path.join(path, d))
        ]
        if not data_folders:
            if lang == "ko":
                exit_with_error(lang, f"'{path}'에서 _Data 폴더를 찾을 수 없습니다.\n게임 루트 폴더 또는 _Data 폴더에서 실행해주세요.")
            else:
                exit_with_error(lang, f"Could not find the _Data folder in '{path}'.\nRun this from the game root folder or the _Data folder.")
        data_path = os.path.join(game_path, data_folders[0])

    ggm_path = find_ggm_file(data_path)
    if not ggm_path:
        if lang == "ko":
            exit_with_error(lang, f"'{data_path}'에서 globalgamemanagers 파일을 찾을 수 없습니다.\n올바른 Unity 게임 폴더인지 확인해주세요.")
        else:
            exit_with_error(lang, f"Could not find the globalgamemanagers file in '{data_path}'.\nPlease check that this is a valid Unity game folder.")

    return game_path, data_path


def get_unity_version(data_path: str) -> str:
    """KR: 데이터 폴더의 Unity 버전을 반환합니다.
    EN: Return the Unity version detected from the data folder.
    """
    ggm_path = find_ggm_file(data_path)
    if not ggm_path:
        raise FileNotFoundError(f"globalgamemanagers not found in '{data_path}'")
    return str(UnityPy.load(ggm_path).objects[0].assets_file.unity_version)


def find_assets_files(data_path: str) -> list[str]:
    """KR: 교체/추출 대상이 될 에셋 파일 목록을 수집합니다.
    EN: Collect candidate asset files for replacement/export.
    """
    assets_files: list[str] = []
    exclude_exts = {
        ".dll",
        ".manifest",
        ".exe",
        ".txt",
        ".json",
        ".xml",
        ".log",
        ".ini",
        ".cfg",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".wav",
        ".mp3",
        ".ogg",
        ".mp4",
        ".avi",
        ".mov",
    }
    for root, _, files in os.walk(data_path):
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in exclude_exts:
                assets_files.append(os.path.join(root, fn))
    return assets_files


def get_compile_method(data_path: str) -> str:
    """KR: Managed 폴더 존재 여부로 Mono/Il2cpp를 판별합니다.
    EN: Detect Mono/Il2cpp based on the Managed folder presence.
    """
    return "Mono" if os.path.exists(os.path.join(data_path, "Managed")) else "Il2cpp"


def create_generator(
    unity_version: str,
    game_path: str,
    data_path: str,
    compile_method: str,
    lang: Language,
) -> TypeTreeGenerator:
    """KR: Unity 타입트리 생성기를 초기화하고 메타데이터를 로드합니다.
    EN: Initialize a Unity typetree generator and load metadata.
    """
    try:
        generator = TypeTreeGenerator(unity_version)
    except ImportError:
        if lang == "ko":
            raise RuntimeError(
                "TypeTreeGeneratorAPI가 설치되지 않아 TMP 폰트 타입트리를 생성할 수 없습니다.\n"
                "`pip install TypeTreeGeneratorAPI`를 실행해 주세요."
            )
        raise RuntimeError(
            "TypeTreeGeneratorAPI is required to generate TMP typetrees.\n"
            "Install it with: `pip install TypeTreeGeneratorAPI`."
        )

    if compile_method == "Mono":
        managed_dir = os.path.join(data_path, "Managed")
        for fn in os.listdir(managed_dir):
            if not fn.endswith(".dll"):
                continue
            try:
                with open(os.path.join(managed_dir, fn), "rb") as f:
                    generator.load_dll(f.read())
            except Exception as e:  # pragma: no cover
                if lang == "ko":
                    print(f"경고: DLL 로드 실패 '{fn}': {e}")
                else:
                    print(f"Warning: failed to load DLL '{fn}': {e}")
    else:
        il2cpp_path = os.path.join(game_path, "GameAssembly.dll")
        metadata_path = os.path.join(data_path, "il2cpp_data", "Metadata", "global-metadata.dat")
        if not os.path.exists(il2cpp_path) or not os.path.exists(metadata_path):
            if lang == "ko":
                raise RuntimeError("Il2cpp 감지됨. 'GameAssembly.dll'과 'global-metadata.dat'가 필요합니다.")
            raise RuntimeError("Detected Il2cpp. 'GameAssembly.dll' and 'global-metadata.dat' are required.")
        with open(il2cpp_path, "rb") as f:
            il2cpp = f.read()
        with open(metadata_path, "rb") as f:
            metadata = f.read()
        generator.load_il2cpp(il2cpp, metadata)

    return generator


def detect_tmp_version(data: JsonDict) -> Literal["new", "old"]:
    """KR: TMP 폰트 데이터가 신형/구형 포맷인지 판별합니다.
    EN: Detect whether TMP font data uses new or old schema.
    """
    has_new_glyphs = len(data.get("m_GlyphTable", [])) > 0
    has_old_glyphs = len(data.get("m_glyphInfoList", [])) > 0
    if has_new_glyphs:
        return "new"
    if has_old_glyphs:
        return "old"
    if "m_FaceInfo" in data:
        return "new"
    if "m_fontInfo" in data:
        return "old"
    return "new"


def is_tmp_font_asset(obj: Any) -> bool:
    """KR: MonoBehaviour 객체가 TMP 폰트 에셋인지 판별합니다.
    EN: Determine whether a MonoBehaviour object is a TMP font asset.
    """
    try:
        parse_obj = obj.parse_as_object()
        if hasattr(parse_obj, "get_type") and parse_obj.get_type() == "TMP_FontAsset":
            return True
    except Exception as e:  # pragma: no cover
        _debug_parse_log(f"[export_fonts] parse_as_object failed (PathID: {obj.path_id}): {e}")

    try:
        parse_dict = obj.parse_as_dict()
    except Exception as e:  # pragma: no cover
        _debug_parse_log(f"[export_fonts] parse_as_dict failed (PathID: {obj.path_id}): {e}")
        return False

    version = detect_tmp_version(parse_dict)
    has_new_face = "m_FaceInfo" in parse_dict or "m_GlyphTable" in parse_dict
    has_old_face = "m_fontInfo" in parse_dict or "m_glyphInfoList" in parse_dict
    has_new_atlas = "m_AtlasTextures" in parse_dict
    has_old_atlas = "atlas" in parse_dict

    if version == "new":
        return has_new_face and (has_new_atlas or has_old_atlas)
    return has_old_face and (has_old_atlas or has_new_atlas)


def extract_tmp_refs(parse_dict: JsonDict) -> dict[str, int] | None:
    """KR: TMP 폰트 데이터에서 atlas/material PathID를 추출합니다.
    EN: Extract atlas/material PathIDs from TMP font data.
    """
    tmp_version = detect_tmp_version(parse_dict)

    new_glyph_count = len(parse_dict.get("m_GlyphTable", []))
    old_glyph_count = len(parse_dict.get("m_glyphInfoList", []))

    if tmp_version == "new":
        glyph_count = new_glyph_count if new_glyph_count > 0 else old_glyph_count
        atlas_ref: Any = None
        atlas_list = parse_dict.get("m_AtlasTextures", [])
        if isinstance(atlas_list, list) and atlas_list:
            atlas_ref = atlas_list[0]
        elif isinstance(parse_dict.get("atlas"), dict):
            atlas_ref = parse_dict.get("atlas")
    else:
        glyph_count = old_glyph_count if old_glyph_count > 0 else new_glyph_count
        atlas_ref = parse_dict.get("atlas") if isinstance(parse_dict.get("atlas"), dict) else None
        if atlas_ref is None:
            atlas_list = parse_dict.get("m_AtlasTextures", [])
            if isinstance(atlas_list, list) and atlas_list:
                atlas_ref = atlas_list[0]

    if glyph_count == 0 or not isinstance(atlas_ref, dict):
        return None

    file_id = int(atlas_ref.get("m_FileID", 0) or 0)
    path_id = int(atlas_ref.get("m_PathID", 0) or 0)

    # KR: 외부 참조 stub(FileID!=0, PathID=0)은 실제 텍스처를 가리키지 않으므로 제외합니다.
    # EN: Skip external stubs (FileID!=0, PathID=0) because they do not point to a real texture.
    if file_id != 0 and path_id == 0:
        return None

    material_ref = parse_dict.get("m_Material")
    if not isinstance(material_ref, dict):
        alt_material = parse_dict.get("material")
        material_ref = alt_material if isinstance(alt_material, dict) else {}
    material_path_id = int(material_ref.get("m_PathID", 0) or 0)

    creation_settings = parse_dict.get("m_CreationSettings")
    if isinstance(creation_settings, dict):
        # KR: 교체/추출 시 문자열 시퀀스 잡음을 방지하기 위해 빈 문자열로 정규화합니다.
        # EN: Normalize characterSequence to empty to avoid noisy serialized diffs.
        creation_settings["characterSequence"] = ""

    return {
        "atlas_path_id": path_id,
        "material_path_id": material_path_id,
    }


def export_fonts(
    game_path: str,
    data_path: str,
    output_dir: str | None = None,
    lang: Language = "ko",
) -> int:
    """KR: 게임 내 TMP SDF 폰트 JSON/PNG를 추출합니다.
    EN: Export TMP SDF font JSON/PNG assets from a game.
    """
    if output_dir is None:
        output_dir = os.getcwd()

    unity_version = get_unity_version(data_path)
    assets_files = find_assets_files(data_path)
    compile_method = get_compile_method(data_path)
    generator = create_generator(unity_version, game_path, data_path, compile_method, lang)

    if lang == "ko":
        print(f"게임 경로: {game_path}")
        print(f"데이터 경로: {data_path}")
        print(f"Unity 버전: {unity_version}")
        print(f"컴파일 방식: {compile_method}")
        print(f"출력 폴더: {output_dir}")
    else:
        print(f"Game path: {game_path}")
        print(f"Data path: {data_path}")
        print(f"Unity version: {unity_version}")
        print(f"Compile method: {compile_method}")
        print(f"Output folder: {output_dir}")
    print()

    exported_count = 0

    for assets_file in assets_files:
        try:
            env = UnityPy.load(assets_file)
            env.typetree_generator = generator
        except Exception as e:  # pragma: no cover
            if lang == "ko":
                print(f"경고: 파일 로드 실패 '{os.path.basename(assets_file)}': {e}")
            else:
                print(f"Warning: failed to load '{os.path.basename(assets_file)}': {e}")
            continue

        texture_pointers: dict[int, str] = {}
        material_pointers: set[int] = set()

        for obj in env.objects:
            if obj.type.name != "MonoBehaviour":
                continue
            try:
                if not is_tmp_font_asset(obj):
                    continue
                parse_dict = obj.parse_as_dict()
                refs = extract_tmp_refs(parse_dict)
                if not refs:
                    continue

                objname = obj.peek_name() or f"TMP_FontAsset_{obj.path_id}"
                if lang == "ko":
                    print(f"SDF 폰트 발견: {objname} (PathID: {obj.path_id})")
                    print(f"  Atlas 텍스처 PathID: {refs['atlas_path_id']}")
                    print(f"  머티리얼 PathID: {refs['material_path_id']}")
                else:
                    print(f"SDF font found: {objname} (PathID: {obj.path_id})")
                    print(f"  Atlas texture PathID: {refs['atlas_path_id']}")
                    print(f"  Material PathID: {refs['material_path_id']}")

                texture_pointers[refs["atlas_path_id"]] = objname.replace(" SDF", " SDF Atlas")
                if refs["material_path_id"]:
                    material_pointers.add(refs["material_path_id"])

                json_path = os.path.join(output_dir, f"{objname}.json")
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(parse_dict, indent=4, ensure_ascii=False, fp=f)
                if lang == "ko":
                    print(f"  -> {objname}.json 저장됨")
                else:
                    print(f"  -> {objname}.json saved")
                exported_count += 1
            except Exception as e:  # pragma: no cover
                if lang == "ko":
                    print(f"경고: TMP 파싱 실패 (파일: {os.path.basename(assets_file)}, PathID: {obj.path_id}): {e}")
                else:
                    print(f"Warning: TMP parse failed (file: {os.path.basename(assets_file)}, PathID: {obj.path_id}): {e}")

        for obj in env.objects:
            try:
                if obj.type.name == "Texture2D" and obj.path_id in texture_pointers:
                    tex = obj.parse_as_object()
                    image = tex.image
                    objname = texture_pointers.get(obj.path_id, obj.peek_name() or str(obj.path_id))
                    if lang == "ko":
                        print(f"텍스처 추출: {objname} (PathID: {obj.path_id})")
                    else:
                        print(f"Extracting texture: {objname} (PathID: {obj.path_id})")
                    png_path = os.path.join(output_dir, f"{objname}.png")
                    image.save(png_path)
                    if lang == "ko":
                        print(f"  -> {objname}.png 저장됨")
                    else:
                        print(f"  -> {objname}.png saved")
                elif obj.type.name == "Material" and obj.path_id in material_pointers:
                    mat = obj.parse_as_dict()
                    mat_name = obj.peek_name() or f"Material_{obj.path_id}"
                    mat_path = os.path.join(output_dir, f"{mat_name}.json")
                    with open(mat_path, "w", encoding="utf-8") as f:
                        json.dump(mat, f, indent=4, ensure_ascii=False)
            except Exception as e:  # pragma: no cover
                if lang == "ko":
                    print(f"경고: 추출 중 오류 (파일: {os.path.basename(assets_file)}, PathID: {obj.path_id}): {e}")
                else:
                    print(f"Warning: export error (file: {os.path.basename(assets_file)}, PathID: {obj.path_id}): {e}")

    return exported_count


def main_cli(lang: Language = "ko") -> None:
    """KR: SDF 폰트 추출 CLI 진입점입니다.
    EN: CLI entry point for SDF font export.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Unity 게임에서 TMP SDF 폰트를 추출합니다."
            if lang == "ko"
            else "Export TMP SDF fonts from a Unity game."
        )
    )
    parser.add_argument(
        "gamepath",
        nargs="?",
        help=(
            "게임 루트 경로 또는 _Data 경로 (예: D:\\Games\\Muck)"
            if lang == "ko"
            else "Game root path or _Data path (e.g. D:\\Games\\Muck)"
        ),
    )
    args = parser.parse_args()

    if lang == "ko":
        print("=== Unity SDF 폰트 추출기 ===")
    else:
        print("=== Unity SDF Font Exporter ===")
    print()

    input_path = args.gamepath
    if not input_path:
        if lang == "ko":
            input_path = input("게임 경로를 입력하세요: ").strip()
            if not input_path:
                exit_with_error(lang, "게임 경로가 필요합니다.")
        else:
            input_path = input("Enter game path: ").strip()
            if not input_path:
                exit_with_error(lang, "Game path is required.")

    if not os.path.isdir(input_path):
        if lang == "ko":
            exit_with_error(lang, f"'{input_path}'는 유효한 디렉토리가 아닙니다.")
        else:
            exit_with_error(lang, f"'{input_path}' is not a valid directory.")

    try:
        game_path, data_path = resolve_game_path(lang, input_path)
        exported_count = export_fonts(game_path, data_path, lang=lang)
    except Exception as e:
        exit_with_error(lang, str(e))

    print()
    if lang == "ko":
        print(f"완료! {exported_count}개의 SDF 폰트가 추출되었습니다.")
        input("\n엔터를 눌러 종료...")
    else:
        print(f"Done! Exported {exported_count} SDF font(s).")
        input("\nPress Enter to exit...")
