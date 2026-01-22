import os
import sys
import json
import shutil
import struct
import argparse
from PIL import Image
import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator
import subprocess

def find_ggm_file(data_path):
    candidates = ["globalgamemanagers", "globalgamemanagers.assets", "data.unity3d"]
    candidates_resources = ["unity default resources", "unity_builtin_extra"]
    fls = []
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


def resolve_game_path(path):
    path = os.path.normpath(os.path.abspath(path))

    if path.lower().endswith("_data"):
        data_path = path
        game_path = os.path.dirname(path)
    else:
        game_path = path
        data_folders = [d for d in os.listdir(path) if d.lower().endswith("_data") and os.path.isdir(os.path.join(path, d))]

        if not data_folders:
            raise FileNotFoundError(f"'{path}'에서 _Data 폴더를 찾을 수 없습니다.")

        data_path = os.path.join(game_path, data_folders[0])

    ggm_path = find_ggm_file(data_path)
    if not ggm_path:
        raise FileNotFoundError(f"'{data_path}'에서 globalgamemanagers 파일을 찾을 수 없습니다.\n올바른 Unity 게임 폴더인지 확인해주세요.")

    return game_path, data_path


def get_data_path(game_path):
    data_folders = [i for i in os.listdir(game_path) if i.lower().endswith("_data")]
    if not data_folders:
        raise FileNotFoundError(f"'{game_path}'에서 _Data 폴더를 찾을 수 없습니다.")
    return os.path.join(game_path, data_folders[0])


def get_unity_version(game_path):
    data_path = get_data_path(game_path)
    ggm_path = find_ggm_file(data_path)
    return UnityPy.load(ggm_path).objects[0].assets_file.unity_version


def get_script_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def normalize_font_name(name):
    for ext in [".ttf", ".json", ".png"]:
        if name.lower().endswith(ext):
            name = name[:-len(ext)]
    if name.endswith(" SDF Atlas"):
        name = name[:-len(" SDF Atlas")]
    elif name.endswith(" SDF"):
        name = name[:-len(" SDF")]
    return name


def find_assets_files(game_path):
    data_path = get_data_path(game_path)
    assets_files = []
    exclude_exts = {".dll", ".manifest", ".exe", ".txt", ".json", ".xml", ".log", ".ini", ".cfg", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".wav", ".mp3", ".ogg", ".mp4", ".avi", ".mov"}
    for root, _, files in os.walk(data_path):
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in exclude_exts:
                assets_files.append(os.path.join(root, fn))
    return assets_files

def get_compile_method(datapath):
    if "Managed" in os.listdir(datapath):
        return "Mono"
    else:
        return "Il2cpp"

def scan_fonts(game_path):
    unity_version = get_unity_version(game_path)
    assets_files = find_assets_files(game_path)
    compile_method = get_compile_method(get_data_path(game_path))

    fonts = {
        "ttf": [],
        "sdf": []
    }

    for assets_file in assets_files:
        try:
            env = UnityPy.load(assets_file)
            generator = TypeTreeGenerator(unity_version)
            if compile_method == "Mono":
                generator.load_local_dll_folder(os.path.join(get_data_path(game_path), "Managed"))
            else:
                il2cpp_path = os.path.join(game_path, "GameAssembly.dll")
                with open(il2cpp_path, "rb") as f:
                    il2cpp = f.read()
                metadata_path = os.path.join(get_data_path(game_path), "il2cpp_data", "Metadata", "global-metadata.dat")
                with open(metadata_path, "rb") as f:
                    metadata = f.read()
                generator.load_il2cpp(il2cpp, metadata)
            env.typetree_generator = generator

        except Exception as e:
            print(f"[scan_fonts] UnityPy.load failed: {assets_file}")
            print(e)
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
                    is_font = False
                    try:
                        parse_obj = obj.parse_as_object()
                        if hasattr(parse_obj, 'get_type') and parse_obj.get_type() == "TMP_FontAsset":
                            is_font = True
                    except:
                        pass
                    if not is_font:
                        try:
                            parse_dict = obj.parse_as_dict()
                            if "m_AtlasTextures" in parse_dict and "m_FaceInfo" in parse_dict:
                                is_font = True
                        except:
                            pass
                    if is_font:
                        try:
                            parse_dict = obj.parse_as_dict()
                            atlas_textures = parse_dict.get("m_AtlasTextures", [])
                            glyph_count = len(parse_dict.get("m_GlyphTable", []))
                            if atlas_textures and atlas_textures[0].get("m_FileID", 0) != 0:
                                continue
                            if glyph_count == 0:
                                continue
                        except:
                            pass
                        fonts["sdf"].append({
                            "file": os.path.basename(assets_file),
                            "assets_name": obj.assets_file.name,
                            "name": obj.peek_name(),
                            "path_id": obj.path_id
                        })
            except Exception as e:
                print(e)
                pass

    return fonts


def parse_fonts(game_path):
    fonts = scan_fonts(game_path)
    game_name = os.path.basename(game_path)
    output_file = f"{game_name}.json"

    result = {}

    for font in fonts["ttf"]:
        key = f"{font['file']}|{font['assets_name']}|{font['name']}|TTF|{font['path_id']}"
        result[key] = {
            "Name": font["name"],
            "assets_name": font["assets_name"],
            "Path_ID": font["path_id"],
            "Type": "TTF",
            "File": font["file"],
            "Replace_to": ""
        }

    for font in fonts["sdf"]:
        key = f"{font['file']}|{font['assets_name']}|{font['name']}|SDF|{font['path_id']}"
        result[key] = {
            "Name": font["name"],
            "assets_name": font["assets_name"],
            "Path_ID": font["path_id"],
            "Type": "SDF",
            "File": font["file"],
            "Replace_to": ""
        }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4, ensure_ascii=False)

    print(f"폰트 정보가 '{output_file}'에 저장되었습니다.")
    print(f"  - TTF 폰트: {len(fonts['ttf'])}개")
    print(f"  - SDF 폰트: {len(fonts['sdf'])}개")
    return output_file


def load_font_assets(font_name):
    kr_assets = os.path.join(get_script_dir(), "KR_ASSETS")
    normalized = normalize_font_name(font_name)

    ttf_path = os.path.join(kr_assets, f"{normalized}.ttf")
    ttf_data = None
    if os.path.exists(ttf_path):
        with open(ttf_path, "rb") as f:
            ttf_data = list(f.read())

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


def replace_fonts_in_file(unity_version, game_path, assets_file, replacements, replace_ttf=True, replace_sdf=True):
    fn_without_path = os.path.basename(assets_file)
    data_path = get_data_path(game_path)
    tmp_path = os.path.join(data_path, "temp")
    compile_method = get_compile_method(data_path)

    if not os.path.exists(tmp_path):
        os.makedirs(tmp_path)
    else:
        shutil.rmtree(tmp_path)
        os.makedirs(tmp_path)

    env = UnityPy.load(assets_file)
    generator = TypeTreeGenerator(unity_version)
    if compile_method == "Mono":
        generator.load_local_dll_folder(os.path.join(data_path, "Managed"))
    else:
        il2cpp_path = os.path.join(game_path, "GameAssembly.dll")
        with open(il2cpp_path, "rb") as f:
            il2cpp = f.read()
        metadata_path = os.path.join(data_path, "il2cpp_data", "Metadata", "global-metadata.dat")
        with open(metadata_path, "rb") as f:
            metadata = f.read()
        generator.load_il2cpp(il2cpp, metadata)
    env.typetree_generator = generator

    texture_replacements = {}
    material_replacements = {}
    modified = False

    for obj in env.objects:
        assets_name = obj.assets_file.name
        if obj.type.name == "Font" and replace_ttf:
            font = obj.parse_as_object()
            font_name = font.m_Name
            font_pathid = obj.path_id
            
            replacement_font = None
            for key, info in replacements.items():
                if info.get("Type") == "TTF" and info.get("File") == fn_without_path and info.get("Path_ID") == font_pathid and info.get("assets_name") == assets_name:
                    if info.get("Replace_to"):
                        replacement_font = info["Replace_to"]
                        break

            if replacement_font:
                assets = load_font_assets(replacement_font)
                if assets["ttf_data"]:
                    print(f"TTF 폰트 교체: {assets_name} | {font_name} | (PathID: {font_pathid} -> {replacement_font})")
                    font.m_FontData = assets["ttf_data"]
                    font.save()
                    modified = True

        if obj.type.name == "MonoBehaviour" and replace_sdf:
            try:
                parse_dict = obj.parse_as_dict()
            except:
                continue
            if "m_FaceInfo" in parse_dict and "m_AtlasTextures" in parse_dict:
                # 폰트 참조만 있는 경우 건너뛰기 (실제 폰트 데이터가 아님)
                atlas_textures = parse_dict.get("m_AtlasTextures", [])
                glyph_count = len(parse_dict.get("m_GlyphTable", []))
                if atlas_textures and atlas_textures[0].get("m_FileID", 0) != 0:
                    continue
                if glyph_count == 0:
                    continue

                objname = obj.peek_name()
                pathid = obj.path_id

                replacement_font = None
                for key, info in replacements.items():
                    if info.get("Type") == "SDF" and info.get("File") == fn_without_path and info.get("Path_ID") == pathid and info.get("assets_name") == assets_name:
                        if info.get("Replace_to"):
                            replacement_font = info["Replace_to"]
                            break

                if replacement_font:
                    assets = load_font_assets(replacement_font)
                    if assets["sdf_data"] and assets["sdf_atlas"]:
                        print(f"SDF 폰트 교체: {assets_name} | {objname} | (PathID: {pathid}) -> {replacement_font}")

                        parse_dict = obj.parse_as_dict()
                        replace_data = assets["sdf_data"]

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

                        m_SourceFontFile_FileID = parse_dict["m_SourceFontFile"]["m_FileID"]
                        m_SourceFontFile_PathID = parse_dict["m_SourceFontFile"]["m_PathID"]
                        m_AtlasTextures_FileID = parse_dict["m_AtlasTextures"][0]["m_FileID"]
                        m_AtlasTextures_PathID = parse_dict["m_AtlasTextures"][0]["m_PathID"]

                        if "m_GlyphTable" in replace_data and type(replace_data["m_GlyphTable"]) == list:
                            for glyph in replace_data["m_GlyphTable"]:
                                glyph["m_ClassDefinitionType"] = 0

                        parse_dict["m_FaceInfo"] = replace_data["m_FaceInfo"]
                        parse_dict["m_GlyphTable"] = replace_data["m_GlyphTable"]
                        parse_dict["m_CharacterTable"] = replace_data["m_CharacterTable"]
                        parse_dict["m_AtlasTextures"] = replace_data["m_AtlasTextures"]
                        parse_dict["m_AtlasWidth"] = replace_data["m_AtlasWidth"]
                        parse_dict["m_AtlasHeight"] = replace_data["m_AtlasHeight"]
                        parse_dict["m_AtlasPadding"] = replace_data["m_AtlasPadding"]
                        parse_dict["m_AtlasRenderMode"] = replace_data["m_AtlasRenderMode"]
                        parse_dict["m_UsedGlyphRects"] = replace_data["m_UsedGlyphRects"]
                        parse_dict["m_FreeGlyphRects"] = replace_data["m_FreeGlyphRects"]
                        parse_dict["m_FontWeightTable"] = replace_data["m_FontWeightTable"]

                        def ensure_int(data, keys):
                            if not data:
                                return
                            for key in keys:
                                if key in data and data[key] is not None:
                                    data[key] = int(data[key])

                        if "m_FaceInfo" in parse_dict:
                            ensure_int(parse_dict["m_FaceInfo"], ["m_PointSize", "m_AtlasWidth", "m_AtlasHeight"])

                        if "m_CreationSettings" in parse_dict:
                            ensure_int(parse_dict["m_CreationSettings"], ["pointSize", "atlasWidth", "atlasHeight", "padding"])

                        if "m_GlyphTable" in parse_dict:
                            for glyph in parse_dict["m_GlyphTable"]:
                                ensure_int(glyph, ["m_Index", "m_AtlasIndex", "m_ClassDefinitionType"])
                                if "m_GlyphRect" in glyph:
                                    ensure_int(glyph["m_GlyphRect"], ["m_X", "m_Y", "m_Width", "m_Height"])

                        if "m_CharacterTable" in parse_dict:
                            for char in parse_dict["m_CharacterTable"]:
                                ensure_int(char, ["m_Unicode", "m_GlyphIndex", "m_ElementType"])

                        for rect_list_name in ["m_UsedGlyphRects", "m_FreeGlyphRects"]:
                            if rect_list_name in parse_dict:
                                for rect in parse_dict[rect_list_name]:
                                    ensure_int(rect, ["m_X", "m_Y", "m_Width", "m_Height"])

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

                        parse_dict["m_SourceFontFile"]["m_FileID"] = m_SourceFontFile_FileID
                        parse_dict["m_SourceFontFile"]["m_PathID"] = m_SourceFontFile_PathID
                        parse_dict["m_AtlasTextures"][0]["m_FileID"] = m_AtlasTextures_FileID
                        parse_dict["m_AtlasTextures"][0]["m_PathID"] = m_AtlasTextures_PathID
                        parse_dict["m_CreationSettings"]["characterSequence"] = ""
                        
                        texture_replacements[f"{assets_name}|{m_AtlasTextures_PathID}"] = assets["sdf_atlas"]
                        if m_Material_FileID == 0 and m_Material_PathID != 0:
                            gradient_scale = None
                            material_data = assets.get("sdf_materials")
                            if material_data:
                                material_props = material_data.get("m_SavedProperties", {})
                                float_properties = material_props.get("m_Floats", [])
                                for prop in float_properties:
                                    if prop[0] == "_GradientScale":
                                        gradient_scale = prop[1]
                                        break
                            material_replacements[f"{assets_name}|{m_Material_PathID}"] = {
                                "w": assets["sdf_atlas"].width,
                                "h": assets["sdf_atlas"].height,
                                "gs": gradient_scale
                            }
                        obj.patch(parse_dict)
                        modified = True

    for obj in env.objects:
        assets_name = obj.assets_file.name
        if obj.type.name == "Texture2D":
            if f"{assets_name}|{obj.path_id}" in texture_replacements:
                parse_dict = obj.parse_as_object()
                print(f"텍스처 교체: {obj.peek_name()} (PathID: {obj.path_id})")
                parse_dict.image = texture_replacements[f"{assets_name}|{obj.path_id}"]
                parse_dict.save()
                modified = True
        if obj.type.name == "Material":
            if f"{assets_name}|{obj.path_id}" in material_replacements:
                parse_dict = obj.parse_as_object()

                mat_info = material_replacements[f"{assets_name}|{obj.path_id}"]
                for i in range(len(parse_dict.m_SavedProperties.m_Floats)):
                    prop_name = parse_dict.m_SavedProperties.m_Floats[i][0]
                    if prop_name == '_TextureHeight':
                        parse_dict.m_SavedProperties.m_Floats[i] = ('_TextureHeight', float(mat_info["h"]))
                    elif prop_name == '_TextureWidth':
                        parse_dict.m_SavedProperties.m_Floats[i] = ('_TextureWidth', float(mat_info["w"]))
                    elif prop_name == '_GradientScale' and mat_info["gs"] is not None:
                        parse_dict.m_SavedProperties.m_Floats[i] = ('_GradientScale', float(mat_info["gs"]))
                parse_dict.save()

    if modified:
        print(f"'{fn_without_path}' 저장 중...")

        save_success = False

        def _save_env_file(packer=None):
            try:
                if packer is None:
                    return env.file.save()
                return env.file.save(packer=packer)
            except TypeError:
                # AssetsFile.save does not support packer; fall back to default
                return env.file.save()

        def _make_packer_with_flags(compression_flag):
            dataflags = getattr(env.file, "dataflags", None)
            if dataflags is None:
                return None
            try:
                data_flag = int(dataflags)
                block_info_flag = int(getattr(env.file, "_block_info_flags", 0))
            except Exception:
                return None
            # Preserve structure flags; only change compression bits.
            data_flag = (data_flag & ~0x3F) | int(compression_flag)
            block_info_flag = (block_info_flag & ~0x3F) | int(compression_flag)
            # Ensure only compression bits are set in block_info_flag (UnityFS expects 0x3F mask).
            block_info_flag &= 0x3F
            return (data_flag, block_info_flag)

        def _try_save(packer_label, log_label):
            nonlocal save_success
            try:
                sf = _save_env_file(packer_label)
                with open(f"{tmp_path}/{fn_without_path}", "wb") as f:
                    f.write(sf)
                save_success = True
                return True
            except (struct.error, Exception) as e:
                print(f"  저장 방법 {log_label} 실패: {e}")
                return False

        # Prefer preserving original bundle compression/layout when possible.
        original_packer = _make_packer_with_flags(int(getattr(env.file, "_block_info_flags", 0)) & 0x3F)
        if not _try_save(original_packer or "original", "1"):
            lz4_packer = _make_packer_with_flags(2)
            print("  lz4 압축 모드로 재시도...")
            if not _try_save(lz4_packer or "lz4", "2"):
                none_packer = _make_packer_with_flags(0)
                print("  비압축 모드로 재시도...")
                _try_save(none_packer or "none", "3")

        if save_success:
            def _close_reader(obj):
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

            def _close_env(environment):
                if not environment:
                    return
                stack = []
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
                print(f"  저장 완료 (크기: {saved_size} bytes)")
            else:
                print(f"  경고: 저장된 파일을 찾을 수 없습니다")
                save_success = False

        if not save_success:
            print("  오류: 파일 저장에 실패했습니다.")

    if os.path.exists(tmp_path):
        shutil.rmtree(tmp_path)

    return modified


def create_batch_replacements(game_path, font_name, replace_ttf=True, replace_sdf=True):
    fonts = scan_fonts(game_path)
    replacements = {}

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


def exit_with_error(message):
    print(f"오류: {message}")
    input("\n엔터를 눌러 종료...")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Unity 게임의 폰트를 한글 폰트로 교체합니다.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  %(prog)s --gamepath "D:\\Games\\Muck" --parse
  %(prog)s --gamepath "D:\\Games\\Muck" --mulmaru
  %(prog)s --gamepath "D:\\Games\\Muck" --nanumgothic --sdfonly
  %(prog)s --gamepath "D:\\Games\\Muck" --list Muck.json
        """
    )

    parser.add_argument("--gamepath", type=str, help="게임의 루트 경로 (예: D:\\Games\\Muck)")
    parser.add_argument("--parse", action="store_true", help="폰트 정보를 JSON으로 출력")
    parser.add_argument("--mulmaru", action="store_true", help="모든 폰트를 Mulmaru로 일괄 교체")
    parser.add_argument("--nanumgothic", action="store_true", help="모든 폰트를 NanumGothic으로 일괄 교체")
    parser.add_argument("--sdfonly", action="store_true", help="SDF 폰트만 교체")
    parser.add_argument("--ttfonly", action="store_true", help="TTF 폰트만 교체")
    parser.add_argument("--list", type=str, metavar="JSON_FILE", help="JSON 파일을 읽어서 폰트 교체")

    args = parser.parse_args()
    input_path = args.gamepath
    if not input_path:
        input_path = input("게임 경로를 입력하세요: ").strip()
        if not input_path:
            exit_with_error("게임 경로가 필요합니다.")

    if not os.path.isdir(input_path):
        exit_with_error(f"'{input_path}'는 유효한 디렉토리가 아닙니다.")

    try:
        game_path, data_path = resolve_game_path(input_path)
        compile_method = get_compile_method(data_path)
        print(f"게임 경로: {game_path}")
        print(f"데이터 경로: {data_path}")
        print(f"컴파일 방식: {compile_method}")
    except FileNotFoundError as e:
        exit_with_error(str(e))
    if os.path.exists(os.path.join(data_path, "temp")):
        shutil.rmtree(os.path.join(data_path, "temp"))
    replace_ttf = not args.sdfonly
    replace_sdf = not args.ttfonly

    if args.sdfonly and args.ttfonly:
        exit_with_error("--sdfonly와 --ttfonly를 동시에 사용할 수 없습니다.")

    replacements = None
    mode = None

    if args.parse:
        mode = "parse"
    elif args.mulmaru:
        mode = "mulmaru"
    elif args.nanumgothic:
        mode = "nanumgothic"
    elif args.list:
        mode = "list"
    else:
        print("작업을 선택하세요:")
        print("  1. 폰트 정보 추출 (JSON 파일 생성)")
        print("  2. JSON 파일로 폰트 교체")
        print("  3. Mulmaru(물마루체)로 일괄 교체")
        print("  4. NanumGothic(나눔고딕)으로 일괄 교체")
        print()
        choice = input("선택 (1-4): ").strip()

        if choice == "1":
            mode = "parse"
        elif choice == "2":
            mode = "list"
            args.list = input("JSON 파일 경로를 입력하세요: ").strip()
            if not args.list:
                exit_with_error("JSON 파일 경로가 필요합니다.")
        elif choice == "3":
            mode = "mulmaru"
        elif choice == "4":
            mode = "nanumgothic"
        else:
            exit_with_error("잘못된 선택입니다.")

    if compile_method == "Il2cpp" and os.path.exists(os.path.join(data_path, "Managed")) == False:
        binary_path = os.path.join(game_path, "GameAssembly.dll")
        metadata_path = os.path.join(data_path, "il2cpp_data", "Metadata", "global-metadata.dat")
        if not os.path.exists(binary_path) or not os.path.exists(metadata_path):
            exit_with_error("Il2cpp 게임의 경우 'Managed' 폴더 또는 'GameAssembly.dll'과 'global-metadata.dat' 파일이 필요합니다.\n올바른 Unity 게임 폴더인지 확인해주세요.")
        dumper_path = os.path.join(get_script_dir(), "Il2CppDumper", "Il2CppDumper.exe")
        target_path = os.path.join(get_data_path(game_path), "Managed_")
        os.makedirs(target_path, exist_ok=True)
        command = [os.path.abspath(dumper_path), os.path.abspath(binary_path), os.path.abspath(metadata_path), os.path.abspath(target_path)]
        print("Il2cpp 게임을 위한 Managed 폴더를 생성합니다...")
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
                encoding='utf-8'
            )

            if process.returncode == 0:
                print(process.stdout)
                shutil.move(os.path.join(get_data_path(game_path), "Managed_", "DummyDll"), os.path.join(get_data_path(game_path), "Managed"))
                shutil.rmtree(os.path.join(get_data_path(game_path), "Managed_"))
                print("더미 DLL 생성에 성공했습니다!")
            else:
                print(process.stderr)
                exit_with_error("Il2cpp 더미 DLL 생성 실패")

        except Exception as e:
            print(f"실행 중 예외 발생: {e}")


    if mode == "parse":
        parse_fonts(game_path)
        input("\n엔터를 눌러 종료...")
        return
    elif mode == "mulmaru":
        print("Mulmaru 폰트로 일괄 교체합니다...")
        replacements = create_batch_replacements(game_path, "Mulmaru", replace_ttf, replace_sdf)
        print(f"발견된 폰트: TTF {sum(1 for v in replacements.values() if v['Type'] == 'TTF')}개, SDF {sum(1 for v in replacements.values() if v['Type'] == 'SDF')}개")
    elif mode == "nanumgothic":
        print("NanumGothic 폰트로 일괄 교체합니다...")
        replacements = create_batch_replacements(game_path, "NanumGothic", replace_ttf, replace_sdf)
        print(f"발견된 폰트: TTF {sum(1 for v in replacements.values() if v['Type'] == 'TTF')}개, SDF {sum(1 for v in replacements.values() if v['Type'] == 'SDF')}개")
    elif mode == "list":
        if not os.path.exists(args.list):
            exit_with_error(f"'{args.list}' 파일을 찾을 수 없습니다.")

        print(f"'{args.list}' 파일을 읽어서 교체합니다...")
        with open(args.list, "r", encoding="utf-8") as f:
            replacements = json.load(f)

        for key, info in replacements.items():
            if info.get("Replace_to"):
                info["Replace_to"] = normalize_font_name(info["Replace_to"])

    unity_version = get_unity_version(game_path)
    assets_files = find_assets_files(game_path)

    files_to_process = set()
    for key, info in replacements.items():
        if info.get("Replace_to"):
            files_to_process.add(info["File"])

    modified_count = 0
    for assets_file in assets_files:
        fn = os.path.basename(assets_file)
        if fn in files_to_process:
            print(f"\n처리 중: {fn}")
            if replace_fonts_in_file(unity_version, game_path, assets_file, replacements, replace_ttf, replace_sdf):
                modified_count += 1

    print(f"\n완료! {modified_count}개의 파일이 수정되었습니다.")
    input("\n엔터를 눌러 종료...")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        print(f"\n예상치 못한 오류가 발생했습니다: {e}")
        traceback.print_exc()
        input("\n엔터를 눌러 종료...")
        sys.exit(1)
