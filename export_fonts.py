import os
import sys
import json
import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator
from PIL import Image


def exit_with_error(message):
    print(f"오류: {message}")
    input("\n엔터를 눌러 종료...")
    sys.exit(1)


def find_ggm_file(data_path):
    candidates = ["globalgamemanagers", "globalgamemanagers.assets", "data.unity3d"]
    for candidate in candidates:
        ggm_path = os.path.join(data_path, candidate)
        if os.path.exists(ggm_path):
            return ggm_path
    return None


def resolve_game_path(path=None):
    if path is None:
        path = os.getcwd()

    path = os.path.normpath(os.path.abspath(path))

    if path.endswith("_Data"):
        data_path = path
        game_path = os.path.dirname(path)
    else:
        game_path = path
        data_folders = [d for d in os.listdir(path) if d.endswith("_Data") and os.path.isdir(os.path.join(path, d))]

        if not data_folders:
            exit_with_error(f"'{path}'에서 _Data 폴더를 찾을 수 없습니다.\n게임 루트 폴더 또는 _Data 폴더에서 실행해주세요.")

        data_path = os.path.join(game_path, data_folders[0])

    ggm_path = find_ggm_file(data_path)
    if not ggm_path:
        exit_with_error(f"'{data_path}'에서 globalgamemanagers 파일을 찾을 수 없습니다.\n올바른 Unity 게임 폴더인지 확인해주세요.")

    return game_path, data_path


def get_unity_version(data_path):
    ggm_path = find_ggm_file(data_path)
    return UnityPy.load(ggm_path).objects[0].assets_file.unity_version


def find_assets_files(data_path):
    assets_files = []
    exclude_exts = {".dll", ".manifest", ".exe", ".txt", ".json", ".xml", ".log", ".ini", ".cfg", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".wav", ".mp3", ".ogg", ".mp4", ".avi", ".mov"}
    for root, _, files in os.walk(data_path):
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in exclude_exts:
                assets_files.append(os.path.join(root, fn))
    return assets_files


def export_fonts(game_path, data_path, output_dir=None):
    if output_dir is None:
        output_dir = os.getcwd()

    unity_version = get_unity_version(data_path)
    assets_files = find_assets_files(data_path)

    print(f"게임 경로: {game_path}")
    print(f"데이터 경로: {data_path}")
    print(f"Unity 버전: {unity_version}")
    print(f"출력 폴더: {output_dir}")
    print()

    exported_count = 0

    for assets_file in assets_files:
        try:
            env = UnityPy.load(assets_file)
            generator = TypeTreeGenerator(unity_version)
            generator.load_local_game(game_path)
            env.typetree_generator = generator
        except Exception as e:
            print(f"경고: '{os.path.basename(assets_file)}' 로드 중 오류: {e}")
            continue

        texture_pointers = []
        texture_names = {}

        for obj in env.objects:
            try:
                if obj.type.name == "MonoBehaviour":
                    parse_obj = obj.parse_as_object()
                    if parse_obj.get_type() == "TMP_FontAsset":
                        objname = obj.peek_name()
                        pathid = obj.path_id
                        parse_dict = obj.parse_as_dict()
                        m_AtlasTextures_PathID = parse_dict["m_AtlasTextures"][0]["m_PathID"]

                        print(f"SDF 폰트 발견: {objname} (PathID: {pathid})")
                        print(f"  Atlas 텍스처 PathID: {m_AtlasTextures_PathID}")

                        texture_pointers.append(m_AtlasTextures_PathID)
                        texture_names[m_AtlasTextures_PathID] = objname.replace(" SDF", " SDF Atlas")

                        json_path = os.path.join(output_dir, f"{objname}.json")
                        with open(json_path, "w", encoding="utf-8") as f:
                            json.dump(parse_dict, indent=4, ensure_ascii=False, fp=f)
                        print(f"  -> {objname}.json 저장됨")
                        exported_count += 1
            except Exception as e:
                pass

        for obj in env.objects:
            try:
                if obj.path_id in texture_pointers:
                    if obj.type.name == "Texture2D":
                        tex = obj.read()
                        image = tex.image
                        objname = texture_names.get(obj.path_id, obj.peek_name())

                        print(f"텍스처 추출: {objname} (PathID: {obj.path_id})")

                        png_path = os.path.join(output_dir, f"{objname}.png")
                        image.save(png_path)
                        print(f"  -> {objname}.png 저장됨")
            except Exception as e:
                print(f"경고: 텍스처 추출 중 오류 (PathID: {obj.path_id}): {e}")

    return exported_count


def main():
    print("=== Unity SDF 폰트 추출기 ===")
    print()

    game_path, data_path = resolve_game_path()

    exported_count = export_fonts(game_path, data_path)

    print()
    print(f"완료! {exported_count}개의 SDF 폰트가 추출되었습니다.")
    input("\n엔터를 눌러 종료...")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n예상치 못한 오류가 발생했습니다: {e}")
        input("\n엔터를 눌러 종료...")
        sys.exit(1)
