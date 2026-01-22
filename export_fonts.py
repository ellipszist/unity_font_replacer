import os
import sys
import json
import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator
from PIL import Image


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
            print(f"오류: '{path}'에서 _Data 폴더를 찾을 수 없습니다.")
            print("게임 루트 폴더 또는 _Data 폴더에서 실행해주세요.")
            sys.exit(1)

        data_path = os.path.join(game_path, data_folders[0])

    ggm_path = os.path.join(data_path, "globalgamemanagers")
    if not os.path.exists(ggm_path):
        print(f"오류: '{data_path}'에서 globalgamemanagers 파일을 찾을 수 없습니다.")
        print("올바른 Unity 게임 폴더인지 확인해주세요.")
        sys.exit(1)

    return game_path, data_path


def get_unity_version(data_path):
    ggm_path = os.path.join(data_path, "globalgamemanagers")
    return UnityPy.load(ggm_path).objects[0].assets_file.unity_version


def find_assets_files(data_path):
    assets_files = []
    for fn in os.listdir(data_path):
        if fn.endswith(".assets") or fn == "resources.assets":
            assets_files.append(os.path.join(data_path, fn))
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

            texture_pointers = []

            for obj in env.objects:
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

                        json_path = os.path.join(output_dir, f"{objname}.json")
                        with open(json_path, "w", encoding="utf-8") as f:
                            json.dump(parse_dict, indent=4, ensure_ascii=False, fp=f)
                        print(f"  -> {objname}.json 저장됨")
                        exported_count += 1

            for obj in env.objects:
                if obj.path_id in texture_pointers:
                    if obj.type.name == "Texture2D":
                        tex = obj.read()
                        image = tex.image
                        objname = obj.peek_name()

                        print(f"텍스처 추출: {objname} (PathID: {obj.path_id})")

                        png_path = os.path.join(output_dir, f"{objname}.png")
                        image.save(png_path)
                        print(f"  -> {objname}.png 저장됨")

        except Exception as e:
            print(f"경고: '{os.path.basename(assets_file)}' 처리 중 오류: {e}")

    return exported_count


def main():
    print("=== Unity SDF 폰트 추출기 ===")
    print()

    game_path, data_path = resolve_game_path()

    exported_count = export_fonts(game_path, data_path)

    print()
    print(f"완료! {exported_count}개의 SDF 폰트가 추출되었습니다.")


if __name__ == "__main__":
    main()
