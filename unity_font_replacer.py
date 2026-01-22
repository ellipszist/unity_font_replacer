import os
import sys
import json
import shutil
import argparse
from PIL import Image
import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator


def resolve_game_path(path):
    path = os.path.normpath(os.path.abspath(path))

    if path.endswith("_Data"):
        data_path = path
        game_path = os.path.dirname(path)
    else:
        game_path = path
        data_folders = [d for d in os.listdir(path) if d.endswith("_Data") and os.path.isdir(os.path.join(path, d))]

        if not data_folders:
            raise FileNotFoundError(f"'{path}'에서 _Data 폴더를 찾을 수 없습니다.")

        data_path = os.path.join(game_path, data_folders[0])

    ggm_path = os.path.join(data_path, "globalgamemanagers")
    if not os.path.exists(ggm_path):
        raise FileNotFoundError(f"'{data_path}'에서 globalgamemanagers 파일을 찾을 수 없습니다.")

    return game_path, data_path


def get_data_path(game_path):
    data_folders = [i for i in os.listdir(game_path) if i.endswith("_Data")]
    if not data_folders:
        raise FileNotFoundError(f"'{game_path}'에서 _Data 폴더를 찾을 수 없습니다.")
    return os.path.join(game_path, data_folders[0])


def get_unity_version(game_path):
    data_path = get_data_path(game_path)
    ggm_path = os.path.join(data_path, "globalgamemanagers")
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
    for fn in os.listdir(data_path):
        if fn.endswith(".assets") or fn == "resources.assets":
            assets_files.append(os.path.join(data_path, fn))
    return assets_files


def scan_fonts(game_path):
    unity_version = get_unity_version(game_path)
    assets_files = find_assets_files(game_path)

    fonts = {
        "ttf": [],
        "sdf": []
    }

    for assets_file in assets_files:
        try:
            env = UnityPy.load(assets_file)
            generator = TypeTreeGenerator(unity_version)
            generator.load_local_game(game_path)
            env.typetree_generator = generator

            for obj in env.objects:
                if obj.type.name == "Font":
                    font = obj.parse_as_object()
                    fonts["ttf"].append({
                        "file": os.path.basename(assets_file),
                        "name": font.m_Name,
                        "path_id": obj.path_id
                    })
                elif obj.type.name == "MonoBehaviour":
                    parse_obj = obj.parse_as_object()
                    if parse_obj.get_type() == "TMP_FontAsset":
                        fonts["sdf"].append({
                            "file": os.path.basename(assets_file),
                            "name": obj.peek_name(),
                            "path_id": obj.path_id
                        })
        except Exception as e:
            print(f"경고: '{assets_file}' 처리 중 오류 발생: {e}")

    return fonts


def parse_fonts(game_path):
    fonts = scan_fonts(game_path)
    game_name = os.path.basename(game_path)
    output_file = f"{game_name}.json"

    result = {}

    for font in fonts["ttf"]:
        key = f"{font['file']}|TTF|{font['path_id']}"
        result[key] = {
            "Name": font["name"],
            "Path_ID": font["path_id"],
            "Type": "TTF",
            "File": font["file"],
            "Replace_to": ""
        }

    for font in fonts["sdf"]:
        key = f"{font['file']}|SDF|{font['path_id']}"
        result[key] = {
            "Name": font["name"],
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

    return {
        "ttf_data": ttf_data,
        "sdf_data": sdf_data,
        "sdf_atlas": sdf_atlas
    }


def replace_fonts_in_file(unity_version, game_path, assets_file, replacements, replace_ttf=True, replace_sdf=True):
    fn_without_path = os.path.basename(assets_file)
    data_path = get_data_path(game_path)
    tmp_path = os.path.join(data_path, "temp")

    if not os.path.exists(tmp_path):
        os.makedirs(tmp_path)
    else:
        shutil.rmtree(tmp_path)
        os.makedirs(tmp_path)

    env = UnityPy.load(assets_file)
    generator = TypeTreeGenerator(unity_version)
    generator.load_local_game(game_path)
    env.typetree_generator = generator

    texture_replacements = {}
    modified = False

    for obj in env.objects:
        if obj.type.name == "Font" and replace_ttf:
            font = obj.parse_as_object()
            font_name = font.m_Name
            font_pathid = obj.path_id

            replacement_font = None
            for key, info in replacements.items():
                if info.get("Type") == "TTF" and info.get("File") == fn_without_path and info.get("Path_ID") == font_pathid:
                    if info.get("Replace_to"):
                        replacement_font = info["Replace_to"]
                        break

            if replacement_font:
                assets = load_font_assets(replacement_font)
                if assets["ttf_data"]:
                    print(f"TTF 폰트 교체: {font_name} (PathID: {font_pathid}) -> {replacement_font}")
                    font.m_FontData = assets["ttf_data"]
                    font.save()
                    modified = True

        if obj.type.name == "MonoBehaviour" and replace_sdf:
            parse_obj = obj.parse_as_object()
            if parse_obj.get_type() == "TMP_FontAsset":
                objname = obj.peek_name()
                pathid = obj.path_id

                replacement_font = None
                for key, info in replacements.items():
                    if info.get("Type") == "SDF" and info.get("File") == fn_without_path and info.get("Path_ID") == pathid:
                        if info.get("Replace_to"):
                            replacement_font = info["Replace_to"]
                            break

                if replacement_font:
                    assets = load_font_assets(replacement_font)
                    if assets["sdf_data"] and assets["sdf_atlas"]:
                        print(f"SDF 폰트 교체: {objname} (PathID: {pathid}) -> {replacement_font}")

                        parse_dict = obj.parse_as_dict()
                        test_data = assets["sdf_data"]

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

                        if "m_GlyphTable" in test_data and type(test_data["m_GlyphTable"]) == list:
                            for glyph in test_data["m_GlyphTable"]:
                                glyph["m_ClassDefinitionType"] = 0

                        parse_dict["m_FaceInfo"] = test_data["m_FaceInfo"]
                        parse_dict["m_GlyphTable"] = test_data["m_GlyphTable"]
                        parse_dict["m_CharacterTable"] = test_data["m_CharacterTable"]
                        parse_dict["m_AtlasTextures"] = test_data["m_AtlasTextures"]
                        parse_dict["m_AtlasWidth"] = test_data["m_AtlasWidth"]
                        parse_dict["m_AtlasHeight"] = test_data["m_AtlasHeight"]
                        parse_dict["m_AtlasPadding"] = test_data["m_AtlasPadding"]
                        parse_dict["m_AtlasRenderMode"] = test_data["m_AtlasRenderMode"]
                        parse_dict["m_UsedGlyphRects"] = test_data["m_UsedGlyphRects"]
                        parse_dict["m_FreeGlyphRects"] = test_data["m_FreeGlyphRects"]
                        parse_dict["m_FontWeightTable"] = test_data["m_FontWeightTable"]

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

                        texture_replacements[m_AtlasTextures_PathID] = assets["sdf_atlas"]
                        obj.patch(parse_dict)
                        modified = True

    for obj in env.objects:
        if obj.type.name == "Texture2D":
            if obj.path_id in texture_replacements:
                parse_obj = obj.parse_as_object()
                print(f"텍스처 교체: {obj.peek_name()} (PathID: {obj.path_id})")
                parse_obj.image = texture_replacements[obj.path_id]
                parse_obj.save()
                modified = True

    if modified:
        print(f"'{fn_without_path}' 저장 중...")
        env.save(out_path=tmp_path)
        shutil.move(os.path.join(tmp_path, fn_without_path), assets_file)

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
        print(f"게임 경로: {game_path}")
        print(f"데이터 경로: {data_path}")
        print()
    except FileNotFoundError as e:
        exit_with_error(str(e))

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
        print(f"\n예상치 못한 오류가 발생했습니다: {e}")
        input("\n엔터를 눌러 종료...")
        sys.exit(1)
