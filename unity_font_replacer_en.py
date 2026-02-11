import os
import sys
import json
import shutil
import argparse
import io
import traceback as tb_module
from PIL import Image
import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator
import subprocess


class TeeWriter:
    """Writes to both console and file simultaneously"""
    def __init__(self, file, original_stream):
        self.file = file
        self.original = original_stream

    def write(self, data):
        self.original.write(data)
        self.file.write(data)
        self.file.flush()

    def flush(self):
        self.original.flush()
        self.file.flush()

    def fileno(self):
        return self.original.fileno()

    @property
    def encoding(self):
        return self.original.encoding

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
            raise FileNotFoundError(f"Could not find the _Data folder in '{path}'.")

        data_path = os.path.join(game_path, data_folders[0])

    ggm_path = find_ggm_file(data_path)
    if not ggm_path:
        raise FileNotFoundError(f"Could not find the globalgamemanagers file in '{data_path}'.\nPlease check that this is a valid Unity game folder.")

    return game_path, data_path


def get_data_path(game_path):
    data_folders = [i for i in os.listdir(game_path) if i.lower().endswith("_data")]
    if not data_folders:
        raise FileNotFoundError(f"Could not find the _Data folder in '{game_path}'.")
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


def ensure_int(data, keys):
    """Convert specified keys in dict to int"""
    if not data:
        return
    for key in keys:
        if key in data and data[key] is not None:
            data[key] = int(data[key])


def detect_tmp_version(data):
    """Detect whether SDF font data is new or legacy TMP format.

    Returns:
        "new" - New TMP (m_FaceInfo, m_GlyphTable, m_CharacterTable, m_AtlasTextures)
        "old" - Legacy TMP (m_fontInfo, m_glyphInfoList, atlas)
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


def convert_face_info_new_to_old(face_info, atlas_padding=0, atlas_width=0, atlas_height=0):
    """Convert new m_FaceInfo → legacy m_fontInfo"""
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


def convert_face_info_old_to_new(font_info):
    """Convert legacy m_fontInfo → new m_FaceInfo"""
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


def convert_glyphs_new_to_old(glyph_table, char_table):
    """Convert new m_GlyphTable + m_CharacterTable → legacy m_glyphInfoList"""
    glyph_by_index = {}
    for g in glyph_table:
        glyph_by_index[g["m_Index"]] = g
    result = []
    for char in char_table:
        unicode_val = char.get("m_Unicode", 0)
        glyph_idx = char.get("m_GlyphIndex", 0)
        g = glyph_by_index.get(glyph_idx, {})
        metrics = g.get("m_Metrics", {})
        rect = g.get("m_GlyphRect", {})
        result.append({
            "id": int(unicode_val),
            "x": float(rect.get("m_X", 0)),
            "y": float(rect.get("m_Y", 0)),
            "width": float(metrics.get("m_Width", 0)),
            "height": float(metrics.get("m_Height", 0)),
            "xOffset": float(metrics.get("m_HorizontalBearingX", 0)),
            "yOffset": float(metrics.get("m_HorizontalBearingY", 0)),
            "xAdvance": float(metrics.get("m_HorizontalAdvance", 0)),
            "scale": float(g.get("m_Scale", 1.0))
        })
    return result


def convert_glyphs_old_to_new(glyph_info_list):
    """Convert legacy m_glyphInfoList → new (m_GlyphTable, m_CharacterTable)"""
    glyph_table = []
    char_table = []
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


def normalize_sdf_data(data):
    """Normalize SDF replacement data to new TMP format.
    Handles both old and new format inputs, always outputs new format.
    Returns a new dict without modifying the original."""
    import copy
    result = copy.deepcopy(data)
    version = detect_tmp_version(result)

    if version == "old":
        font_info = result.get("m_fontInfo", {})
        glyph_info_list = result.get("m_glyphInfoList", [])
        atlas_padding = font_info.get("Padding", 0)
        atlas_width = font_info.get("AtlasWidth", 0)
        atlas_height = font_info.get("AtlasHeight", 0)

        result["m_FaceInfo"] = convert_face_info_old_to_new(font_info)

        glyph_table, char_table = convert_glyphs_old_to_new(glyph_info_list)
        result["m_GlyphTable"] = glyph_table
        result["m_CharacterTable"] = char_table

        if "m_AtlasTextures" not in result or not result["m_AtlasTextures"]:
            atlas_ref = result.get("atlas", {"m_FileID": 0, "m_PathID": 0})
            result["m_AtlasTextures"] = [atlas_ref]
        result.setdefault("m_AtlasWidth", int(atlas_width))
        result.setdefault("m_AtlasHeight", int(atlas_height))
        result.setdefault("m_AtlasPadding", int(atlas_padding))
        result.setdefault("m_AtlasRenderMode", 4118)
        result.setdefault("m_UsedGlyphRects", [])
        result.setdefault("m_FreeGlyphRects", [])

        if "m_FontWeightTable" not in result:
            font_weights = result.get("fontWeights", [])
            result["m_FontWeightTable"] = font_weights if font_weights else []

    return result


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

def _create_generator(unity_version, game_path, data_path, compile_method):
    generator = TypeTreeGenerator(unity_version)
    if compile_method == "Mono":
        managed_dir = os.path.join(data_path, "Managed")
        for fn in os.listdir(managed_dir):
            if not fn.endswith(".dll"):
                continue
            try:
                with open(os.path.join(managed_dir, fn), "rb") as f:
                    generator.load_dll(f.read())
            except Exception:
                pass
    else:
        il2cpp_path = os.path.join(game_path, "GameAssembly.dll")
        with open(il2cpp_path, "rb") as f:
            il2cpp = f.read()
        metadata_path = os.path.join(data_path, "il2cpp_data", "Metadata", "global-metadata.dat")
        with open(metadata_path, "rb") as f:
            metadata = f.read()
        generator.load_il2cpp(il2cpp, metadata)
    return generator


def scan_fonts(game_path):
    data_path = get_data_path(game_path)
    unity_version = get_unity_version(game_path)
    assets_files = find_assets_files(game_path)
    compile_method = get_compile_method(data_path)
    generator = _create_generator(unity_version, game_path, data_path, compile_method)

    fonts = {
        "ttf": [],
        "sdf": []
    }

    for assets_file in assets_files:
        try:
            env = UnityPy.load(assets_file)
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
                    parse_dict = None
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
                            # New TMP: m_FaceInfo + m_AtlasTextures
                            # Legacy TMP: m_fontInfo + atlas
                            if ("m_AtlasTextures" in parse_dict and "m_FaceInfo" in parse_dict) or \
                               ("atlas" in parse_dict and "m_fontInfo" in parse_dict):
                                is_font = True
                        except:
                            pass
                    if is_font:
                        try:
                            if parse_dict is None:
                                parse_dict = obj.parse_as_dict()
                            # New/legacy field compatibility
                            atlas_textures = parse_dict.get("m_AtlasTextures", [])
                            glyph_count = len(parse_dict.get("m_GlyphTable", []))
                            # Legacy TMP
                            if not atlas_textures and "atlas" in parse_dict:
                                atlas_textures = []
                            if glyph_count == 0:
                                glyph_count = len(parse_dict.get("m_glyphInfoList", []))
                            if atlas_textures:
                                first_atlas = atlas_textures[0]
                                if first_atlas.get("m_FileID", 0) != 0 and first_atlas.get("m_PathID", 0) == 0:
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
    output_file = os.path.join(get_script_dir(), f"{game_name}.json")

    result = {}

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

    print(f"Font info saved to '{output_file}'.")
    print(f"  - TTF fonts: {len(fonts['ttf'])}")
    print(f"  - SDF fonts: {len(fonts['sdf'])}")
    return output_file


def load_font_assets(font_name):
    kr_assets = os.path.join(get_script_dir(), "KR_ASSETS")
    normalized = normalize_font_name(font_name)

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


def replace_fonts_in_file(unity_version, game_path, assets_file, replacements, replace_ttf=True, replace_sdf=True, generator=None):
    fn_without_path = os.path.basename(assets_file)
    data_path = get_data_path(game_path)
    tmp_path = os.path.join(data_path, "temp")

    if not os.path.exists(tmp_path):
        os.makedirs(tmp_path)
    else:
        shutil.rmtree(tmp_path)
        os.makedirs(tmp_path)

    env = UnityPy.load(assets_file)
    if generator is None:
        compile_method = get_compile_method(data_path)
        generator = _create_generator(unity_version, game_path, data_path, compile_method)
    env.typetree_generator = generator

    texture_replacements = {}
    material_replacements = {}
    modified = False

    for obj in env.objects:
        assets_name = obj.assets_file.name
        if obj.type.name == "Font" and replace_ttf:
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
                    font = obj.parse_as_object()
                    print(f"Replacing TTF font: {assets_name} | {font.m_Name} | (PathID: {font_pathid} -> {replacement_font})")
                    font.m_FontData = assets["ttf_data"]
                    font.save()
                    modified = True

        if obj.type.name == "MonoBehaviour" and replace_sdf:
            try:
                parse_dict = obj.parse_as_dict()
            except:
                continue
            is_new_tmp = "m_FaceInfo" in parse_dict and "m_AtlasTextures" in parse_dict
            is_old_tmp = "m_fontInfo" in parse_dict and "atlas" in parse_dict
            if is_new_tmp or is_old_tmp:
                # Skip only external reference stubs
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

                replacement_font = None
                for key, info in replacements.items():
                    if info.get("Type") == "SDF" and info.get("File") == fn_without_path and info.get("Path_ID") == pathid and info.get("assets_name") == assets_name:
                        if info.get("Replace_to"):
                            replacement_font = info["Replace_to"]
                            break

                if replacement_font:
                    assets = load_font_assets(replacement_font)
                    if assets["sdf_data"] and assets["sdf_atlas"]:
                        print(f"Replacing SDF font: {assets_name} | {objname} | (PathID: {pathid}) -> {replacement_font}")

                        # Normalize replacement data to new TMP format (handles both old/new JSON)
                        replace_data = normalize_sdf_data(assets["sdf_data"])

                        # Preserve original references
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
                            # Target is legacy TMP → convert normalized data to legacy format
                            atlas_ref = parse_dict["atlas"]
                            m_AtlasTextures_FileID = atlas_ref["m_FileID"]
                            m_AtlasTextures_PathID = atlas_ref["m_PathID"]

                            old_font_info = convert_face_info_new_to_old(
                                replace_data["m_FaceInfo"],
                                replace_data.get("m_AtlasPadding", 0),
                                replace_data.get("m_AtlasWidth", 0),
                                replace_data.get("m_AtlasHeight", 0)
                            )
                            old_glyph_list = convert_glyphs_new_to_old(
                                replace_data.get("m_GlyphTable", []),
                                replace_data.get("m_CharacterTable", [])
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
                            # Target is new TMP → apply normalized data directly
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
                            parse_dict["m_CreationSettings"]["characterSequence"] = ""

                        # Common: restore references
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
                print(f"Replacing texture: {obj.peek_name()} (PathID: {obj.path_id})")
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
        print(f"Saving '{fn_without_path}'...")

        save_success = False

        def _save_env_file(packer=None):
            try:
                if packer is None:
                    return env.file.save()
                return env.file.save(packer=packer)
            except TypeError:
                # AssetsFile.save does not support packer; fall back to default
                return env.file.save()

        def _make_packer(compression_flag):
            """block_info_flag gets pure compression bits only, data_flag keeps structure bits + compression"""
            dataflags = getattr(env.file, "dataflags", None)
            if dataflags is None:
                return None
            try:
                data_flag = (int(dataflags) & ~0x3F) | compression_flag
            except Exception:
                return None
            return (data_flag, compression_flag)

        def _try_save(packer_label, log_label):
            nonlocal save_success
            try:
                sf = _save_env_file(packer_label)
                with open(f"{tmp_path}/{fn_without_path}", "wb") as f:
                    f.write(sf)
                save_success = True
                return True
            except Exception as e:
                print(f"  Save method {log_label} failed: {e}")
                return False

        # Try original compression -> LZ4 -> uncompressed fallback
        original_compression = int(getattr(env.file, "_block_info_flags", 0)) & 0x3F
        original_packer = _make_packer(original_compression)
        if not _try_save(original_packer or "original", "1"):
            lz4_packer = _make_packer(2)
            print("  Retrying with lz4 compression...")
            if not _try_save(lz4_packer or "lz4", "2"):
                none_packer = _make_packer(0)
                print("  Retrying with no compression...")
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
                print(f"  Save complete (size: {saved_size} bytes)")
            else:
                print("  Warning: saved file not found")
                save_success = False

        if not save_success:
            print("  Error: failed to save file.")

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
    print(f"Error: {message}")
    input("\nPress Enter to exit...")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Replace Unity game fonts with Korean fonts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --gamepath "D:\\Games\\Muck" --parse
  %(prog)s --gamepath "D:\\Games\\Muck" --mulmaru
  %(prog)s --gamepath "D:\\Games\\Muck" --nanumgothic --sdfonly
  %(prog)s --gamepath "D:\\Games\\Muck" --list Muck.json
        """
    )

    parser.add_argument("--gamepath", type=str, help="Game root path (e.g. D:\\Games\\Muck)")
    parser.add_argument("--parse", action="store_true", help="Export font info to JSON")
    parser.add_argument("--mulmaru", action="store_true", help="Replace all fonts with Mulmaru")
    parser.add_argument("--nanumgothic", action="store_true", help="Replace all fonts with NanumGothic")
    parser.add_argument("--sdfonly", action="store_true", help="Replace SDF fonts only")
    parser.add_argument("--ttfonly", action="store_true", help="Replace TTF fonts only")
    parser.add_argument("--list", type=str, metavar="JSON_FILE", help="Replace fonts using a JSON file")
    parser.add_argument("--verbose", action="store_true", help="Save all logs to verbose.txt")

    args = parser.parse_args()

    verbose_file = None
    if args.verbose:
        verbose_path = os.path.join(get_script_dir(), "verbose.txt")
        verbose_file = open(verbose_path, "w", encoding="utf-8")
        sys.stdout = TeeWriter(verbose_file, sys.__stdout__)
        sys.stderr = TeeWriter(verbose_file, sys.__stderr__)
        print(f"[verbose] Saving logs to '{verbose_path}'.")

    input_path = args.gamepath
    if not input_path:
        input_path = input("Enter game path: ").strip()
        if not input_path:
            exit_with_error("Game path is required.")

    if not os.path.isdir(input_path):
        exit_with_error(f"'{input_path}' is not a valid directory.")

    try:
        game_path, data_path = resolve_game_path(input_path)
        compile_method = get_compile_method(data_path)
        print(f"Game path: {game_path}")
        print(f"Data path: {data_path}")
        print(f"Compile method: {compile_method}")
    except FileNotFoundError as e:
        exit_with_error(str(e))
    if os.path.exists(os.path.join(data_path, "temp")):
        shutil.rmtree(os.path.join(data_path, "temp"))
    replace_ttf = not args.sdfonly
    replace_sdf = not args.ttfonly

    if args.sdfonly and args.ttfonly:
        exit_with_error("Cannot use --sdfonly and --ttfonly at the same time.")

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
            args.list = input("Enter JSON file path: ").strip()
            if not args.list:
                exit_with_error("JSON file path is required.")
        elif choice == "3":
            mode = "mulmaru"
        elif choice == "4":
            mode = "nanumgothic"
        else:
            exit_with_error("Invalid selection.")

    if compile_method == "Il2cpp" and not os.path.exists(os.path.join(data_path, "Managed")):
        binary_path = os.path.join(game_path, "GameAssembly.dll")
        metadata_path = os.path.join(data_path, "il2cpp_data", "Metadata", "global-metadata.dat")
        if not os.path.exists(binary_path) or not os.path.exists(metadata_path):
            exit_with_error("For Il2cpp games, the 'Managed' folder or 'GameAssembly.dll' and 'global-metadata.dat' files are required.\nPlease check that this is a valid Unity game folder.")
        dumper_path = os.path.join(get_script_dir(), "Il2CppDumper", "Il2CppDumper.exe")
        target_path = os.path.join(data_path, "Managed_")
        os.makedirs(target_path, exist_ok=True)
        command = [os.path.abspath(dumper_path), os.path.abspath(binary_path), os.path.abspath(metadata_path), os.path.abspath(target_path)]
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
                encoding='utf-8'
            )

            if process.returncode == 0:
                print(process.stdout)
                shutil.move(os.path.join(data_path, "Managed_", "DummyDll"), os.path.join(data_path, "Managed"))
                shutil.rmtree(os.path.join(data_path, "Managed_"))
                print("Dummy DLL generated successfully!")
            else:
                print(process.stderr)
                exit_with_error("Failed to generate Il2cpp dummy DLL")

        except Exception as e:
            exit_with_error(f"Exception while running Il2CppDumper: {e}")

    if mode == "parse":
        parse_fonts(game_path)
        input("\nPress Enter to exit...")
        return
    elif mode == "mulmaru":
        print("Bulk replacing with Mulmaru...")
        replacements = create_batch_replacements(game_path, "Mulmaru", replace_ttf, replace_sdf)
        print(f"Found fonts: TTF {sum(1 for v in replacements.values() if v['Type'] == 'TTF')}, SDF {sum(1 for v in replacements.values() if v['Type'] == 'SDF')}")
    elif mode == "nanumgothic":
        print("Bulk replacing with NanumGothic...")
        replacements = create_batch_replacements(game_path, "NanumGothic", replace_ttf, replace_sdf)
        print(f"Found fonts: TTF {sum(1 for v in replacements.values() if v['Type'] == 'TTF')}, SDF {sum(1 for v in replacements.values() if v['Type'] == 'SDF')}")
    elif mode == "list":
        if not os.path.exists(args.list):
            exit_with_error(f"File not found: '{args.list}'")

        print(f"Replacing using '{args.list}'...")
        with open(args.list, "r", encoding="utf-8") as f:
            replacements = json.load(f)

        for key, info in replacements.items():
            if info.get("Replace_to"):
                info["Replace_to"] = normalize_font_name(info["Replace_to"])

    unity_version = get_unity_version(game_path)
    assets_files = find_assets_files(game_path)
    generator = _create_generator(unity_version, game_path, data_path, compile_method)

    files_to_process = set()
    for key, info in replacements.items():
        if info.get("Replace_to"):
            files_to_process.add(info["File"])

    modified_count = 0
    for assets_file in assets_files:
        fn = os.path.basename(assets_file)
        if fn in files_to_process:
            print(f"\nProcessing: {fn}")
            if replace_fonts_in_file(unity_version, game_path, assets_file, replacements, replace_ttf, replace_sdf, generator=generator):
                modified_count += 1

    print(f"\nDone! Modified {modified_count} file(s).")
    input("\nPress Enter to exit...")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        tb_module.print_exc()
        input("\nPress Enter to exit...")
        sys.exit(1)
    finally:
        if isinstance(sys.stdout, TeeWriter):
            sys.stdout.file.close()
            sys.stdout = sys.__stdout__
        if isinstance(sys.stderr, TeeWriter):
            sys.stderr.file.close()
            sys.stderr = sys.__stderr__
