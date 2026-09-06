import copy
import io
from attrs import evolve

from fontTools.ttLib import TTFont
from PIL import Image
from UnityPy.classes import PPtr
from UnityPy.enums import TextureFormat
from UnityPy.streams import EndianBinaryReader

from tmp_font_schema import _all_valid_atlas_refs, _atlas_ref_ids, _get_tmp_material_reference


GENERATED_PREFIX = "__UFR_"


def _ref(path_id, file_id=0):
    return {"m_FileID": file_id, "m_PathID": path_id}


def _deref(obj, pointer):
    file_id, path_id = _atlas_ref_ids(pointer)
    if not path_id:
        return None
    return PPtr(m_FileID=file_id, m_PathID=path_id, assetsfile=obj.assets_file).deref()


def _original_bytes(obj):
    position = obj.reader.Position
    try:
        obj.reader.Position = obj.byte_start
        return obj.reader.read_bytes(obj.byte_size)
    finally:
        obj.reader.Position = position


def _view(obj, raw):
    return evolve(
        obj, reader=EndianBinaryReader(raw, endian=obj.reader.endian),
        byte_start=0, byte_size=len(raw), data=None,
    )


def _current_tree(obj):
    raw = obj.get_raw_data() if obj.data is not None else _original_bytes(obj)
    return _view(obj, raw).parse_as_dict()


def _write(obj, tree):
    obj.patch(tree)


def _fallback_key(tree):
    for key in ("m_FallbackFontAssetTable", "fallbackFontAssets"):
        if isinstance(tree.get(key), list):
            return key
    raise ValueError("TMP font has no supported fallback table")


def _set_fallbacks(tree, refs):
    _fallback_key(tree)
    for key in ("m_FallbackFontAssetTable", "fallbackFontAssets"):
        if isinstance(tree.get(key), list):
            tree[key] = copy.deepcopy(refs)


def _clear_typefaces(tree):
    for key in ("m_FontWeightTable", "fontWeights"):
        for pair in tree.get(key, []) or []:
            for name in ("regularTypeface", "italicTypeface"):
                if isinstance(pair.get(name), dict):
                    pair[name] = _ref(0)


def reset_dynamic_font(tree, font_bytes):
    required = (
        "m_AtlasPopulationMode", "m_CharacterTable", "m_GlyphTable",
        "m_UsedGlyphRects", "m_FreeGlyphRects", "m_FaceInfo", "m_AtlasTextures",
    )
    if any(key not in tree for key in required):
        raise ValueError("TTF priority requires a modern, dynamically populatable TMP schema")
    if not _atlas_ref_ids(tree.get("m_SourceFontFile"))[1]:
        raise ValueError("TTF priority requires an explicit source Font reference")
    width, height = int(tree["m_AtlasWidth"]), int(tree["m_AtlasHeight"])
    mode = int(tree["m_AtlasRenderMode"])
    if (width <= 1 or height <= 1 or mode < 256 or mode & ~0xFFFF or mode & 0x300
            or not mode & 0x70 or (mode & 0x10 and mode & 0x60)):
        raise ValueError("Unsupported TMP dynamic atlas dimensions or render mode")
    face = tree["m_FaceInfo"]
    point_size = float(face["m_PointSize"])
    if point_size <= 0:
        raise ValueError("TMP point size must be positive")
    with TTFont(io.BytesIO(font_bytes), lazy=True) as font:
        units = font["head"].unitsPerEm
        scale = point_size / units
        hhea = font["hhea"]
        names = font["name"]
        values = {
            "m_FaceIndex": 0,
            "m_FamilyName": names.getBestFamilyName(),
            "m_StyleName": names.getBestSubFamilyName(),
            "m_UnitsPerEM": units,
            "m_AscentLine": hhea.ascent * scale,
            "m_DescentLine": hhea.descent * scale,
            "m_LineHeight": (hhea.ascent - hhea.descent + hhea.lineGap) * scale,
        }
        os2 = font.get("OS/2")
        for target, source in (("m_CapLine", "sCapHeight"), ("m_MeanLine", "sxHeight")):
            if os2 is not None and hasattr(os2, source):
                values[target] = getattr(os2, source) * scale
        for key, value in values.items():
            if key in face and value is not None:
                face[key] = value
    tree["m_AtlasPopulationMode"] = 1
    if "InternalDynamicOS" in tree:
        tree["InternalDynamicOS"] = False
    if "m_SourceFontFilePath" in tree:
        tree["m_SourceFontFilePath"] = ""
    for key in ("m_CharacterTable", "m_GlyphTable", "m_UsedGlyphRects", "m_glyphInfoList"):
        if key in tree:
            tree[key] = []
    modifier = 0 if mode & 0x10 else 1
    tree["m_FreeGlyphRects"] = [{
        "m_X": 0, "m_Y": 0, "m_Width": width - modifier, "m_Height": height - modifier,
    }]
    tree["m_AtlasTextures"] = [copy.deepcopy(tree["m_AtlasTextures"][0])]
    if "m_AtlasTextureIndex" in tree:
        tree["m_AtlasTextureIndex"] = 0
    for table_key in ("m_FontFeatureTable", "m_KerningTable", "m_kerningInfo"):
        table = tree.get(table_key)
        if isinstance(table, dict):
            for key in table:
                if isinstance(table[key], list):
                    table[key] = []
    if "m_ShouldReimportFontFeatures" in tree:
        tree["m_ShouldReimportFontFeatures"] = False
    _clear_typefaces(tree)


class FontPrioritySession:
    def __init__(self, env, entries, font_targets, resolve_ref=None):
        self.env = env
        self.resolve_ref = resolve_ref or _deref
        self.entries = entries
        self.font_targets = font_targets
        self.editable = {id(obj.assets_file) for obj in env.objects}
        self.created = []
        self.named = {}
        self.previous_ttf = set()
        for obj in env.objects:
            if obj.type.name not in {"Font", "MonoBehaviour", "Texture2D", "Material"}:
                continue
            name = obj.parse_monobehaviour_head().m_Name if obj.type.name == "MonoBehaviour" else obj.peek_name()
            if str(name).startswith(GENERATED_PREFIX):
                self.named[(id(obj.assets_file), str(name))] = obj
                if obj.type.name == "Font" and str(name).startswith(f"{GENERATED_PREFIX}FONT__"):
                    self.previous_ttf.add((str(obj.assets_file.name), int(str(name).rsplit("__", 1)[1])))

    def _clone(self, obj, name, destination=None):
        destination = obj.assets_file if destination is None else destination
        external = destination is not obj.assets_file
        if external:
            name = f"{name}__{obj.assets_file.name}"
        key = (id(destination), name)
        if key in self.named:
            return self.named[key]
        if id(destination) not in self.editable:
            raise ValueError("Font priority cannot yet clone dependencies from another outer asset file")
        if external and obj.type.name != "Texture2D":
            raise ValueError("Only atlas textures can be localized from another asset file")
        path_id = max([0, *destination.objects]) + 1
        limit = (1 << (63 if obj.version2 >= 14 or obj.assets_file.big_id_enabled else 31)) - 1
        if path_id > limit:
            raise ValueError("No free positive PathID for a preserved font object")
        clone = _view(obj, _original_bytes(obj))
        clone.path_id = path_id
        if external:
            self._localize_texture(clone, destination)
        peek = clone._get_typetree_node().get_name_peek_node()
        if not peek or peek[1] != "m_Name":
            raise ValueError("Cannot safely name a preserved font dependency")
        node, name_key = peek
        tree = clone.parse_as_dict(node, check_read=False)
        consumed = clone.reader.Position
        tail = _original_bytes(clone)[consumed:]
        tree[name_key] = name
        clone.patch(tree, nodes=node)
        clone.set_raw_data(clone.get_raw_data() + tail)
        destination.objects[path_id] = clone
        self.named[key] = clone
        self.created.append((obj, clone))
        return clone

    def _localize_texture(self, clone, destination):
        source = clone.assets_file
        if (source.header.version != destination.header.version or source.unity_version != destination.unity_version
                or source.target_platform != destination.target_platform
                or source.reader.endian != destination.reader.endian):
            raise ValueError("External atlas serialization version, platform or endianness differs")
        serialized_type = clone.serialized_type
        if serialized_type is None or getattr(serialized_type, "type_dependencies", None):
            raise ValueError("External atlas has unsupported serialized type dependencies")
        tree = clone.parse_as_dict()
        def check_pointers(value):
            if isinstance(value, dict):
                if "m_FileID" in value and "m_PathID" in value and value["m_PathID"]:
                    raise ValueError("External atlas contains a non-null object reference")
                for child in value.values():
                    check_pointers(child)
            elif isinstance(value, (list, tuple)):
                for child in value:
                    check_pointers(child)
        check_pointers(tree)
        texture = clone.parse_as_object()
        stream = getattr(texture, "m_StreamData", None)
        texture.image_data = bytes(texture.get_image_data()) if texture.image_data or (stream and stream.size) else b""
        if stream is not None:
            stream.path, stream.offset, stream.size = "", 0, 0
        clone.patch(texture)
        raw = clone.get_raw_data()
        local_type = next((item for item in destination.types
                           if item.class_id == serialized_type.class_id
                           and item.old_type_hash == serialized_type.old_type_hash), None)
        if local_type is None:
            local_type = copy.copy(serialized_type)
            if destination._enable_type_tree and local_type.node is None:
                raise ValueError("External atlas is missing the destination's required TypeTree")
            destination.types.append(local_type)
        clone.assets_file = destination
        clone.serialized_type = local_type
        if clone.version2 >= 16:
            clone.type_id = destination.types.index(local_type)
        clone.reader = EndianBinaryReader(raw, endian=clone.reader.endian)
        clone.byte_start, clone.byte_size, clone.data = 0, len(raw), None

    def _preserve_ref(self, owner, pointer, prefix, textures=None):
        target = self.resolve_ref(owner, pointer)
        if target is None:
            return copy.deepcopy(pointer)
        clone = self._clone(target, f"{GENERATED_PREFIX}{prefix}__{target.path_id}", owner.assets_file)
        if textures is not None and target.type.name == "Material":
            tree = _current_tree(clone)
            for pair in tree.get("m_SavedProperties", {}).get("m_TexEnvs", []):
                value = pair[1] if isinstance(pair, (list, tuple)) else pair.get("second", {})
                ref = value.get("m_Texture")
                if not isinstance(ref, dict):
                    continue
                texture = self.resolve_ref(clone, ref)
                replacement = textures.get((id(texture.assets_file), texture.path_id)) if texture else None
                if replacement:
                    ref["m_FileID"] = 0
                    ref["m_PathID"] = replacement.path_id
            _write(clone, tree)
        result = copy.deepcopy(pointer)
        result["m_FileID"] = 0
        result["m_PathID"] = clone.path_id
        return result

    def _original_font(self, owner, baseline):
        marker = f"{GENERATED_PREFIX}ORIGINAL__{owner.path_id}"
        existing = self.named.get((id(owner.assets_file), marker))
        if existing is not None:
            tree = _current_tree(existing)
            source = self.resolve_ref(existing, tree.get("m_SourceFontFile"))
            if source and (str(source.assets_file.name), source.path_id) in self.font_targets:
                tree["m_SourceFontFile"] = self._preserve_ref(existing, tree["m_SourceFontFile"], "FONT")
                _write(existing, tree)
            return existing
        clone = self._clone(owner, marker)
        tree = copy.deepcopy(baseline)
        tree["m_Name"] = marker
        textures = {}
        for pointer in _all_valid_atlas_refs(tree):
            texture = self.resolve_ref(owner, pointer)
            preserved = self._clone(texture, f"{GENERATED_PREFIX}ATLAS__{texture.path_id}", owner.assets_file)
            textures[(id(texture.assets_file), texture.path_id)] = preserved
        for pointer in tree.get("m_AtlasTextures", []):
            texture = self.resolve_ref(owner, pointer)
            if texture:
                pointer["m_FileID"] = 0
                pointer["m_PathID"] = textures[(id(texture.assets_file), texture.path_id)].path_id
        for key in ("atlas", "m_AtlasTexture"):
            pointer = tree.get(key)
            texture = self.resolve_ref(owner, pointer)
            if texture:
                pointer["m_FileID"] = 0
                pointer["m_PathID"] = textures[(id(texture.assets_file), texture.path_id)].path_id
        material_key, _, material_id = _get_tmp_material_reference(tree)
        if material_id:
            tree[material_key] = self._preserve_ref(owner, tree[material_key], "MATERIAL", textures)
        source = self.resolve_ref(owner, tree.get("m_SourceFontFile"))
        if source and (str(source.assets_file.name), source.path_id) in self.font_targets:
            tree["m_SourceFontFile"] = self._preserve_ref(owner, tree["m_SourceFontFile"], "FONT")
        _write(clone, tree)
        return clone

    def _blank_atlas(self, owner, tree):
        texture_obj = self.resolve_ref(owner, tree["m_AtlasTextures"][0])
        texture = _view(texture_obj, texture_obj.get_raw_data()).parse_as_object()
        with Image.new("RGBA", (int(tree["m_AtlasWidth"]), int(tree["m_AtlasHeight"])), (255, 255, 255, 0)) as image:
            texture.set_image(image, target_format=TextureFormat.Alpha8, mipmap_count=1)
        texture.m_IsReadable = True
        texture_obj.patch(texture)

    def apply(self, satisfied_ttf, patched_sdf):
        originals = {}
        active = []
        for obj, baseline, source_key, source_ref in self.entries:
            key = (str(obj.assets_file.name), int(obj.path_id))
            has_ttf = source_key in satisfied_ttf or source_key in self.previous_ttf
            has_sdf = key in patched_sdf
            if not has_ttf and not has_sdf:
                continue
            original = self._original_font(obj, baseline)
            originals[(id(obj.assets_file), obj.path_id)] = original
            active.append((obj, baseline, source_key, source_ref, has_ttf, has_sdf, original))

        for obj, baseline, source_key, source_ref, has_ttf, has_sdf, original in active:
            tree = _current_tree(obj)
            original_ref = _ref(original.path_id)
            if has_ttf:
                source = self.resolve_ref(obj, source_ref)
                font_bytes = _view(source, source.get_raw_data()).parse_as_object().m_FontData
                if has_sdf:
                    name = f"{GENERATED_PREFIX}DYNAMIC__{obj.path_id}"
                    existing_dynamic = self.named.get((id(obj.assets_file), name))
                    dynamic = self._clone(obj, name)
                    if existing_dynamic is not None:
                        dynamic_tree = _current_tree(dynamic)
                    else:
                        dynamic_tree = copy.deepcopy(baseline)
                        dynamic_tree["m_Name"] = name
                        suffix = f"DYNAMIC_{obj.assets_file.name}_{obj.path_id}"
                        pointer = dynamic_tree["m_AtlasTextures"][0]
                        dynamic_tree["m_AtlasTextures"] = [self._preserve_ref(obj, pointer, suffix)]
                        texture = self.resolve_ref(obj, pointer)
                        new_texture = self.resolve_ref(obj, dynamic_tree["m_AtlasTextures"][0])
                        material_key, _, material_id = _get_tmp_material_reference(dynamic_tree)
                        if not material_id:
                            raise ValueError("Dynamic fallback requires a TMP material")
                        dynamic_tree[material_key] = self._preserve_ref(
                            obj, dynamic_tree[material_key], suffix,
                            {(id(texture.assets_file), texture.path_id): new_texture},
                        )
                    dynamic_tree["m_SourceFontFile"] = copy.deepcopy(source_ref)
                    reset_dynamic_font(dynamic_tree, bytes(font_bytes))
                    _set_fallbacks(dynamic_tree, [original_ref])
                    self._blank_atlas(dynamic, dynamic_tree)
                    _write(dynamic, dynamic_tree)
                    _set_fallbacks(tree, [_ref(dynamic.path_id)])
                else:
                    tree["m_SourceFontFile"] = copy.deepcopy(source_ref)
                    reset_dynamic_font(tree, bytes(font_bytes))
                    self._blank_atlas(obj, tree)
                    _set_fallbacks(tree, [original_ref])
            else:
                _set_fallbacks(tree, [original_ref])
            if has_sdf:
                if "m_AtlasPopulationMode" in tree:
                    tree["m_AtlasPopulationMode"] = 0
                if "InternalDynamicOS" in tree:
                    tree["InternalDynamicOS"] = False
                if "m_SourceFontFile" in tree:
                    tree["m_SourceFontFile"] = _ref(0)
            _clear_typefaces(tree)
            _write(obj, tree)

        for obj, baseline, _, _, _, _, original in active:
            tree = _current_tree(original)
            for key in ("m_FallbackFontAssetTable", "fallbackFontAssets"):
                for pointer in tree.get(key, []) or []:
                    target = self.resolve_ref(obj, pointer)
                    preserved = originals.get((id(target.assets_file), target.path_id)) if target else None
                    if preserved:
                        pointer["m_PathID"] = preserved.path_id
            for key in ("m_FontWeightTable", "fontWeights"):
                for pair in tree.get(key, []) or []:
                    for pointer in pair.values():
                        target = self.resolve_ref(obj, pointer)
                        preserved = originals.get((id(target.assets_file), target.path_id)) if target else None
                        if preserved:
                            pointer["m_PathID"] = preserved.path_id
            _write(original, tree)
        self._update_preloads()
        return len(active)

    def _update_preloads(self):
        if not self.created:
            return
        for obj in self.env.objects:
            if obj.type.name != "AssetBundle":
                continue
            tree = obj.parse_as_dict()
            table = tree.get("m_PreloadTable", [])
            if any(clone.assets_file is not obj.assets_file for _, clone in self.created):
                raise ValueError("Cross-CAB AssetBundle preload extension is not supported")
            infos = [pair[1] for pair in tree.get("m_Container", [])]
            if isinstance(tree.get("m_MainAsset"), dict):
                infos.append(tree["m_MainAsset"])
            for info in infos:
                start, size = int(info["preloadIndex"]), int(info["preloadSize"])
                if start < 0 or size < 0 or start + size > len(table):
                    raise ValueError("Invalid AssetBundle preload range")
                refs = copy.deepcopy(table[start:start + size])
                refs.extend(_ref(clone.path_id) for _, clone in self.created if clone.assets_file is obj.assets_file)
                info["preloadIndex"], info["preloadSize"] = len(table), len(refs)
                table.extend(refs)
            _write(obj, tree)
