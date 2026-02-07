import os
import sys
import json
import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator
from PIL import Image


def exit_with_error(message):
    print(f"Error: {message}")
    input("\nPress Enter to exit...")
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
            exit_with_error(f"Could not find the _Data folder in '{path}'.\nRun this from the game root folder or the _Data folder.")

        data_path = os.path.join(game_path, data_folders[0])

    ggm_path = find_ggm_file(data_path)
    if not ggm_path:
        exit_with_error(f"Could not find the globalgamemanagers file in '{data_path}'.\nPlease check that this is a valid Unity game folder.")

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

    print(f"Game path: {game_path}")
    print(f"Data path: {data_path}")
    print(f"Unity version: {unity_version}")
    print(f"Output folder: {output_dir}")
    print()

    exported_count = 0

    for assets_file in assets_files:
        try:
            env = UnityPy.load(assets_file)
            generator = TypeTreeGenerator(unity_version)
            generator.load_local_game(game_path)
            env.typetree_generator = generator
        except Exception as e:
            print(f"Warning: failed to load '{os.path.basename(assets_file)}': {e}")
            continue

        texture_pointers = []
        texture_names = {}
        material_pointers = []

        for obj in env.objects:
            try:
                if obj.type.name == "MonoBehaviour":
                    parse_obj = obj.parse_as_object()
                    if parse_obj.get_type() == "TMP_FontAsset":
                        objname = obj.peek_name()
                        pathid = obj.path_id
                        parse_dict = obj.parse_as_dict()
                        m_AtlasTextures_PathID = parse_dict["m_AtlasTextures"][0]["m_PathID"]
                        if parse_dict.get("m_Material") is not None:
                            m_Material_PathID = parse_dict["m_Material"]["m_PathID"]
                        else:
                            m_Material_PathID = parse_dict["material"]["m_PathID"]
                        parse_dict["m_CreationSettings"]["characterSequence"] = ""
                        print(f"SDF font found: {objname} (PathID: {pathid})")
                        print(f"  Atlas texture PathID: {m_AtlasTextures_PathID}")
                        print(f"  Material PathID: {m_Material_PathID}")

                        texture_pointers.append(m_AtlasTextures_PathID)
                        texture_names[m_AtlasTextures_PathID] = objname.replace(" SDF", " SDF Atlas")
                        material_pointers.append(m_Material_PathID)

                        json_path = os.path.join(output_dir, f"{objname}.json")
                        with open(json_path, "w", encoding="utf-8") as f:
                            json.dump(parse_dict, indent=4, ensure_ascii=False, fp=f)
                        print(f"  -> {objname}.json saved")
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

                        print(f"Extracting texture: {objname} (PathID: {obj.path_id})")

                        png_path = os.path.join(output_dir, f"{objname}.png")
                        image.save(png_path)
                        print(f"  -> {objname}.png saved")
                elif obj.path_id in material_pointers:
                    if obj.type.name == "Material":
                        mat = obj.read_typetree()
                        mat_name = obj.peek_name()
                        mat_path = os.path.join(output_dir, f"{mat_name}.json")
                        with open(mat_path, "w", encoding="utf-8") as f:
                            json.dump(mat, f, indent=4, ensure_ascii=False)
            except Exception as e:
                print(f"Warning: error during export (PathID: {obj.path_id}): {e}")

    return exported_count


def main():
    print("=== Unity SDF Font Exporter ===")
    print()

    game_path, data_path = resolve_game_path()

    exported_count = export_fonts(game_path, data_path)

    print()
    print(f"Done! Exported {exported_count} SDF font(s).")
    input("\nPress Enter to exit...")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        input("\nPress Enter to exit...")
        sys.exit(1)
