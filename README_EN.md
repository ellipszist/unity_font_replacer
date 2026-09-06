[> for Korean version of README.md](README.md)

# Unity Font Replacer

A tool to replace Unity game fonts with Korean/custom fonts. Supports both TTF and TextMeshPro SDF fonts.

## Quick Start (EXE-first)

After extracting a release ZIP, the folder typically looks like this:

```
release_en/
├── unity_font_replacer_en.exe
├── export_fonts_en.exe
├── KR_ASSETS/
├── Il2CppDumper/
└── README_EN.md
```

`make_sdf.exe` is distributed as a standalone ZIP (`make_sdf_vX.Y.Z.zip`).

Recommended run:

```bat
cd release_en
unity_font_replacer_en.exe
```

| Executable | Description |
|-----------|------|
| `unity_font_replacer_ko.exe` | Font replacement tool (Korean UI) |
| `unity_font_replacer_en.exe` | Font replacement tool (English UI) |
| `export_fonts_ko.exe` | TMP SDF font exporter (Korean UI) |
| `export_fonts_en.exe` | TMP SDF font exporter (English UI) |
| `make_sdf.exe` | TTF -> TMP SDF JSON/Atlas generator (standalone ZIP) |

---

## Font Replacement (unity_font_replacer_en.exe)

### Basic Usage

```bat
:: Interactive mode (asks for game path)
unity_font_replacer_en.exe

:: Set game path + bulk replace with Mulmaru
unity_font_replacer_en.exe --gamepath "C:/path/to/game" --mulmaru

:: Replace all TTF/SDF fonts from your TTF (SDF is auto-generated)
unity_font_replacer_en.exe --gamepath "C:/path/to/game" --font "D:\Fonts\MyFont.ttf"
```

- Primary mode arguments (`--parse`, `--mulmaru`, `--nanumgothic`, `--font`, `--list`, `--preview-export`) are **mutually exclusive**.
- Interactive EXE runs wait for Enter before exit; explicit CLI invocations exit immediately when the job finishes.

### Command Line Options

#### General

| Option | Description |
|------|------|
| `--gamepath <path>` | Game root path or `_Data` folder path |
| `--parse` | Export font info to JSON |
| `--list <JSON>` | Replace fonts from a JSON mapping |
| `--font <font/TTF/OTF>` | Bulk replace with this font (SDF targets are auto-generated for TTF/OTF) |
| `--verbose` | Keep concise console logs and save detailed DEBUG logs (path/Unity version/per-file/per-font) to `verbose.txt` |

- With `--verbose`, a `verbose.txt` file is created next to the executable (or script) and includes timestamped, level-tagged detailed trace logs.

#### Replacement Targets

| Option | Description |
|------|------|
| `--mulmaru` | Bulk replace all fonts with Mulmaru |
| `--nanumgothic` | Bulk replace all fonts with NanumGothic |
| `--sdfonly` | Replace SDF fonts only |
| `--ttfonly` | Replace TTF fonts only |
| `--target-file <name>` | Limit replacement to specific file name(s) (repeatable/comma-separated) |

Changing only a Dynamic TMP source TTF can reuse stale glyph IDs and display unrelated characters. Such TTF-only replacements are refused. Select the linked SDF assets with `--freeze-dynamic`, or leave the source TTF unchanged. TTF replacement may now require TypeTrees to check these dependencies.

TTF replacement is optional. Use `--sdfonly --freeze-dynamic` to replace the selected TMP character tables, glyphs and atlases together while preserving the original TTFs. Static atlases cannot add missing characters dynamically, so include the required character set or provide a suitable fallback.

#### TMP FontAsset Options

| Option | Description |
|------|------|
| `--use-game-material` | Keep the in-game Material style instead of compatible replacement-Material style values (required atlas values are always synchronized) |
| `--force-raster` | Generate an Alpha8 raster atlas and retarget each Material to a reachable TMP Bitmap shader |
| `--allow-unsafe-full-color-shader-fallback` | Testing only. Store raster atlases as white-RGB RGBA32 and explicitly allow `TextMeshPro/Sprite`/`Bitmap Custom Atlas` fallbacks |
| `--allow-unsafe-gui-text-fallback` | Testing only. Use RGBA32 storage and explicitly allow the `GUI/Text Shader` fallback without TMP UI masking or depth support |
| `--freeze-dynamic` | Explicitly freeze Dynamic/DynamicOS TMP FontAssets to baked Static and clear the runtime source Font PPtr |
| `--use-game-line-metrics` | Keep in-game line metrics (pointSize still follows replacement font) |
| `--outline-ratio <float>` | Multiply classic/SRP outline thickness and softness on the currently selected Material baseline (default `1.0`) |
| `--charset <file/text>` | Charset for TTF/OTF-to-SDF/raster atlas generation (default `CharList_3911.txt`) |

#### Save / Output

| Option | Description |
|------|------|
| `--original-compress` / `--no-original-compress` | Prefer original compression (default) / prefer uncompressed-family saving |
| `--temp-dir <path>` | Set root path for temporary save files (fast SSD/NVMe recommended) |
| `--output-only <path>` | Keep originals untouched; write modified files only to this folder (preserve relative paths) |
| `--split-save-force` | Skip one-shot and force one-by-one SDF split save |
| `--oneshot-save-force` | Force one-shot only (disable split-save fallback) |

- `--output-only` cannot be combined with `--preview-export`.

#### PS5 / Scan

| Option | Description |
|------|------|
| `--ps5-swizzle` | PS5 atlas swizzle detect/transform (masks auto-computed per texture size, `rotate=90`) |
| `--preview-export` | Save SDF atlas + glyph crop PNGs into `preview/` (unswizzled view when used with `--ps5-swizzle`) |
| `--scan-jobs <N>`, `--max-workers <N>` | Number of parallel scan workers (default: `1`) |
| `--scan-stall-seconds <seconds>` | Inactivity threshold when CPU/I/O/progress all stop (default: `300`, `0` disables; not a total per-file runtime limit) |
| `--exclude-ext <list>` | Additional scan-excluded extensions (comma-separated, e.g. `"resS,.resource,.split0"`) |

### Examples

**Basic replacement:**

```bat
:: Replace all fonts with Mulmaru
unity_font_replacer_en.exe --gamepath "C:/path/to/game" --mulmaru

:: Replace SDF only with NanumGothic
unity_font_replacer_en.exe --gamepath "C:/path/to/game" --nanumgothic --sdfonly

:: Replace using JSON mapping
unity_font_replacer_en.exe --gamepath "C:/path/to/game" --list font_map.json

:: Replace all fonts with a custom TTF
unity_font_replacer_en.exe --gamepath "C:/path/to/game" --font "D:\Fonts\Galmuri14.ttf"

:: Generate SDF from a custom TTF using a charset extracted from translated text
unity_font_replacer_en.exe --gamepath "C:/path/to/game" --font "D:\Fonts\Galmuri14.ttf" --charset "D:\Fonts\charset.txt"
```

**Parsing / Scan:**

```bat
:: Export font info (creates font_map.json)
unity_font_replacer_en.exe --gamepath "C:/path/to/game" --parse

:: Parallel workers + PS5 swizzle detection fields (alias: --max-workers)
unity_font_replacer_en.exe --gamepath "C:/path/to/game" --parse --max-workers 10 --ps5-swizzle

:: Exclude additional extensions (comma-separated, with or without leading dot)
unity_font_replacer_en.exe --gamepath "C:/path/to/game" --parse --exclude-ext "resS,.resource,.split0"
```

**SDF options:**

```bat
:: Keep original in-game material parameters
unity_font_replacer_en.exe --gamepath "C:/path/to/game" --nanumgothic --use-game-material

:: Keep in-game line metrics
unity_font_replacer_en.exe --gamepath "C:/path/to/game" --nanumgothic --use-game-line-metrics

:: Replace a Dynamic FontAsset as Static when runtime glyph addition is intentionally disabled
unity_font_replacer_en.exe --gamepath "C:/path/to/game" --nanumgothic --freeze-dynamic

:: Make outlines 25% thicker on the current material baseline
unity_font_replacer_en.exe --gamepath "C:/path/to/game" --nanumgothic --outline-ratio 1.25

:: Make outlines thinner using the original in-game material as baseline
unity_font_replacer_en.exe --gamepath "C:/path/to/game" --nanumgothic --use-game-material --outline-ratio 0.6
```

**Save / Output:**

```bat
:: Limit replacement to a specific file
unity_font_replacer_en.exe --gamepath "C:/path/to/game" --nanumgothic --target-file "sharedassets0.assets"

:: Keep originals and write modified files to a separate folder
unity_font_replacer_en.exe --gamepath "C:/path/to/game" --nanumgothic --output-only "D:\output"

:: Prefer original compression on save
unity_font_replacer_en.exe --gamepath "C:/path/to/game" --nanumgothic --original-compress

:: Use a fast SSD/NVMe path for temporary save files
unity_font_replacer_en.exe --gamepath "C:/path/to/game" --nanumgothic --temp-dir "E:\UFR_TEMP"
```

**PS5 preview:**

```bat
:: Export normal (PC) previews
unity_font_replacer_en.exe --gamepath "C:/path/to/game" --preview-export --sdfonly

:: Export PS5 previews in unswizzled view
unity_font_replacer_en.exe --gamepath "C:/path/to/game" --preview-export --ps5-swizzle --sdfonly
```

---

## Per-Font Replacement (--list)

1. Run `--parse` to generate font info JSON.
2. Fill `Replace_to` for entries you want to replace.
3. Run with `--list`.

JSON example (without `--ps5-swizzle`):

```json
{
    "sharedassets0.assets|sharedassets0.assets|Arial|TTF|123": {
        "File": "sharedassets0.assets",
        "assets_name": "sharedassets0.assets",
        "Path_ID": 123,
        "Type": "TTF",
        "Name": "Arial",
        "Replace_to": "Mulmaru"
    },
    "sharedassets0.assets|sharedassets0.assets|Arial SDF|SDF|456": {
        "File": "sharedassets0.assets",
        "assets_name": "sharedassets0.assets",
        "Path_ID": 456,
        "Type": "SDF",
        "Name": "Arial SDF",
        "force_raster": "False",
        "Replace_to": ""
    }
}
```

### force_raster field

In `--parse` JSON, `force_raster` is included **only for SDF entries**, with default `"False"`.

| Field | Description |
|------|------|
| `force_raster` | Convert that FontAsset to an Alpha8 raster atlas (`"True"` / `"False"`, default `"False"`) |

- SDF and Bitmap Materials have different shader contracts, so changing only `m_AtlasRenderMode` is unsafe.
- `force_raster: "True"` or `--force-raster` converts the linked Material `m_Shader` and SavedProperties together with the FontAsset and atlas.
- The tool verifies both the compiled Shader name and its concrete property contract through an existing PPtr route. It saves nothing when no compatible shader is reachable.

### PS5 swizzle fields

If you run `--parse` with `--ps5-swizzle`, SDF entries include two additional fields:

| Field | Description |
|------|------|
| `swizzle` | Auto-detected target atlas state (`"True"` / `"False"`) |
| `process_swizzle` | Force replacement atlas into swizzled state (default `"False"`) |

- Old JSON files (without these keys) remain compatible.

JSON example (with `--ps5-swizzle`, SDF):

```json
{
    "sharedassets0.assets|sharedassets0.assets|Arial SDF|SDF|456": {
        "File": "sharedassets0.assets",
        "assets_name": "sharedassets0.assets",
        "Path_ID": 456,
        "Type": "SDF",
        "Name": "Arial SDF",
        "force_raster": "False",
        "swizzle": "True",
        "process_swizzle": "False",
        "Replace_to": ""
    }
}
```

### Replace_to formats

If `Replace_to` is empty, that font is skipped.

| Input | Examples |
|------|------|
| Font name | `Mulmaru`, `NanumGothic` |
| TTF file | `Mulmaru.ttf` |
| SDF JSON | `Mulmaru SDF.json` |
| SDF Atlas | `Mulmaru SDF Atlas.png` |
| Material | `NGothic Material.json` |

If an SDF entry's `Replace_to` points to a `.ttf` or `.otf`, the tool auto-generates a temporary SDF set using that target font's `m_AtlasPadding`, then applies the replacement.

---

## PS5 Validation Workflow (--preview-export)

To compare original vs replaced with the exact same extraction pipeline:

1. Create JSON for the target file only.
2. Run `--list + --ps5-swizzle + --preview-export` on original data (extract original crops).
3. Replace with `--nanumgothic --ps5-swizzle`.
4. Run `--list + --ps5-swizzle + --preview-export` again (extract replaced crops).
5. Compare the two preview outputs.

Example (single PS5 bundle target):

```bat
:: 1) Create JSON for a single target file
unity_font_replacer_en.exe --gamepath "C:\Game\Game_Data" ^
    --parse --target-file "38871756d6e98b9e67fb2e7a61dbb88e.bundle" --ps5-swizzle

:: 2) Extract original crops
unity_font_replacer_en.exe --gamepath "C:\Game\Game_Data" ^
    --list "Game.json" --target-file "38871756d6e98b9e67fb2e7a61dbb88e.bundle" ^
    --ps5-swizzle --preview-export --sdfonly

:: 3) Replace with NanumGothic (use --output-only to keep originals intact)
unity_font_replacer_en.exe --gamepath "C:\Game\Game_Data" ^
    --nanumgothic --sdfonly --target-file "38871756d6e98b9e67fb2e7a61dbb88e.bundle" ^
    --ps5-swizzle --output-only "D:\output"

:: 4) Extract replaced crops
unity_font_replacer_en.exe --gamepath "C:\Game\Game_Data" ^
    --list "Game.json" --target-file "38871756d6e98b9e67fb2e7a61dbb88e.bundle" ^
    --ps5-swizzle --preview-export --sdfonly
```

Output locations:

| Type | Path |
|------|------|
| Atlas preview | `preview/<file>/<assets_name>__<atlas_pathid>__<font>__unswizzled__*.png` |
| Glyph crops | `preview/<file>/<assets_name>__<atlas_pathid>__<font>/U+XXXX*.png` |

---

## Font Export (export_fonts_en.exe)

Exports TMP SDF font assets.

```bat
:: Positional path argument (recommended)
export_fonts_en.exe "D:\MyGame"

:: You can also pass _Data directly
export_fonts_en.exe "D:\MyGame\MyGame_Data"

:: If omitted, it prompts for the game path
export_fonts_en.exe
```

Output files are created in the current working directory:

| Output file | Description |
|-------------|------|
| `FontAssetName.json` | TMP font data |
| `FontAssetName SDF Atlas.png` | SDF Atlas image |
| `Material_*.json` | Material data (if present) |

---

## Supported Fonts

| Font | Description |
|-----------|------|
| Mulmaru | Mulmaru Korean font |
| NanumGothic | NanumGothic Korean font |

## Adding Custom Fonts

Add these files under `KR_ASSETS`:

| File | Required |
|------|----------|
| `FontName.ttf` or `.otf` | Required |
| `FontName SDF.json` / `Raster.json` / `.json` | Optional (can be auto-generated from TTF/OTF) |
| `FontName SDF Atlas.png` / `Raster Atlas.png` / `Atlas.png` | Optional (can be auto-generated from TTF/OTF) |
| `FontName SDF Material.json` / `Raster Material.json` / `Material.json` | Optional |

If SDF data is missing, use `--font` or set a JSON `Replace_to` field to a TTF/OTF path for automatic generation. Use `make_sdf.exe` below when you want to keep generated files.

---

## SDF Generator (make_sdf.exe)

You can generate TMP-compatible JSON/atlas directly from a TTF:

```bat
make_sdf.exe --ttf Mulmaru.ttf
```

| Option | Description | Default |
|--------|-------------|---------|
| `--ttf <ttfname>` | TTF file path/name | (required) |
| `--atlas-size <w,h>` | Atlas resolution | `4096,4096` |
| `--point-size <int or auto>` | Sampling point size | `auto` |
| `--padding <int>` | Atlas padding | `7` |
| `--charset <txtpath or characters>` | Charset file path or literal characters | `./CharList_3911.txt` |
| `--rendermode <sdf,raster>` | Output render mode | `sdf` |

---

## Run from Source (Optional)

If you prefer Python scripts instead of EXEs:

### Requirements

- Python 3.12 recommended
- Packages: `custom UnityPy 1.25.3 fork`, `TypeTreeGeneratorAPI`, `Pillow`, `fontTools`, `numpy`, `scipy`, `psutil`

```bash
pip install TypeTreeGeneratorAPI Pillow fonttools numpy scipy psutil
pip install --upgrade git+https://github.com/snowyegret23/UnityPy.git@bccc488474556a5aab30121d7a6c7500c54a80c7
```

When this repository and `UnityPy` share the same parent directory, source runs
automatically prefer the sibling checkout. Saving stops with an actionable error
if the required low-memory APIs are unavailable.

### Examples

```bash
python unity_font_replacer_en.py --gamepath "C:/path/to/game" --mulmaru
python export_fonts_en.py "D:\MyGame"
```

---

## Notes

### Save

- The default save order is `original -> lz4 -> safe-none -> legacy-none`. Only `--no-original-compress` changes it to `safe-none -> legacy-none -> original -> lz4`.
- Every changed object is verified after reopening the saved file by exact CAB name, signed PathID, and raw-object SHA-256.
- Cross-file TMP Atlas/Material and local Addressables catalog patches commit only after every target validates; missing targets, conflicts, or save failures roll the whole related set back.
- For local Standalone Addressables bundles, the catalog CRC is set to zero and the actual size is synchronized. `m_Hash` is preserved because the local `LoadFromFile` path does not use it. Remote, forced-UnityWebRequest, and non-Standalone paths are refused.
- Unity `.split0/.split1` assets are skipped for replacement because safe re-splitting is not supported. The exporter reads the set once through `.split0`.
- CLI temporary files and the IL2CPP `DummyDll` cache are created outside the game under the system temporary path. Use `--temp-dir` to select a fast SSD/NVMe path.
- For large multi-SDF replacements, split-save fallback is enabled by default when one-shot fails (adaptive batch size).

### Scan

- `--parse` reuses a bounded pool of persistent worker processes. The executable is no longer restarted for every file, removing most startup overhead from large scans.
- If a worker exits or its response pipe closes, the file assigned at that moment is recorded as a hard-crash target and retried once on a clean worker.
- A live worker is classified as `stalled` only when CPU, I/O, and progress signals all remain unchanged for `--scan-stall-seconds`. A large file is never failed solely for exceeding a total elapsed time.
- No total deadline is imposed on a process that remains active, including a possible CPU loop. Stop it manually or isolate the file with `--target-file` when that distinction requires investigation.
- You can increase scan throughput with `--scan-jobs` (alias: `--max-workers`).
- Scanning uses blacklist-based exclusion (`*.bak`, `.info`, `.config`, etc.).
- Add extra exclusion extensions with `--exclude-ext "resS,.resource,.split0"` when needed.
- Use `--target-file` to restrict replacements to specific files.

### TMP FontAsset (SDF / Raster) Replacement

- Default line metrics mode scales original proportions to the replacement font's pointSize.
- Use `--use-game-line-metrics` to keep original in-game line metrics. (pointSize still follows replacement font.)
- By default, the Material referenced directly by a FontAsset receives compatible same-name float/color style values from the replacement font Material. The in-game shader, keywords, auxiliary textures, and stencil/mask/clip/render state are preserved.
- `--use-game-material` also keeps the direct Material's in-game style values. Both modes synchronize `_MainTex` and the new padding-based `_GradientScale`. Classic SDF Materials also receive actual texture dimensions and recomputed official `_ScaleRatioA/B/C` values; `_IsoPerimeter`-based SRP Materials neither receive absent classic fields nor have stale classic values rewritten.
- Presets/submaterials that reference the same atlas are resolved by exact outer file, CAB, and signed PathID and receive the atlas contract while retaining each preset's own color, outline, underlay, and keywords.
- Bulk `--nanumgothic` / `--mulmaru` replacement chooses the smallest built-in preset (`Padding_5` / `Padding_7` / `Padding_15`) that is not smaller than the source. Padding above 15 is generated exactly from the TTF.
- `--font <TTF/OTF>` or a JSON `Replace_to` TTF/OTF path auto-generates a temporary SDF atlas using the source `m_AtlasPadding`.
- Automatic generation uses default charset `CharList_3911.txt`, a `4096x4096` atlas, and automatic point-size search.
- Actual TTF glyph IDs and simple OpenType `kern` pairs are rebuilt into TMP feature records. Fonts requiring unsupported GPOS/GSUB/GDEF structures are refused instead of silently saving incorrect shaping.
- If translated text contains Hangul, CJK, or special characters outside the default charset, pass the real character list with `--charset <file>`. Per JSON entry, use `Charset` or `charset`.
- Empty TMP fallback FontAssets are included as SDF replacement targets when they still have an atlas reference. This prevents unresolved characters from falling back into an unchanged `* SDF - Fallback` asset with no glyphs.
- When FontAssets share an atlas, every owner must be selected for the same replacement. Partial selection or conflicting replacement fonts are refused.
- Results are normalized to a static single atlas. Dynamic/DynamicOS targets are refused by default; use `--freeze-dynamic` only when disabling runtime glyph addition is intentional. It freezes the asset to Static and clears the runtime source Font PPtr, so every required character must be included with `--charset`.
- Existing Bitmap TMP FontAssets automatically receive a raster atlas. Use `force_raster: "True"` or `--force-raster` to convert an SDF FontAsset to raster.
- Raster conversion uses only shaders reachable through existing PPtr routes and preserves the currently linked compatible PPtr first. The officially safe automatic Alpha8 candidates are `TextMeshPro/Bitmap` and `TextMeshPro/Mobile/Bitmap`; the concrete compiled property contract is verified before selection. The tool fails before saving when no safe candidate is reachable.
- `TextMeshPro/Sprite` and `TextMeshPro/Bitmap Custom Atlas` consume full RGB samples, so connecting an unchanged Alpha8 atlas produces black glyphs. `--allow-unsafe-full-color-shader-fallback` stores raster atlases as RGBA32 with `RGB=(255,255,255), A=coverage`. Raw texture memory is four times that of Alpha8.
- `--allow-unsafe-gui-text-fallback` also uses RGBA32 storage to avoid black multiplication. `GUI/Text Shader` still has no stencil/`RectMask2D` contract and always passes the depth test, so text can escape masks or show through 3D geometry.
- Raster shaders do not implement SDF outline, underlay, glow, or gradient properties, so conversion removes those properties and stale keywords. The default applies the replacement face tint to the direct Material, while `--use-game-material` keeps its in-game tint; linked-preset tints, supported clip/stencil values, and the `UNITY_UI_ALPHACLIP` toggle are always preserved.
- TTF/OTF-generated raster atlases do not inherit SDF effect padding. They use a five-texel transparent margin, covering TMP bitmap's one-texel baseline plus the optional four-texel `Extra Padding` UV expansion while avoiding wasted atlas resolution.
- `--outline-ratio` treats the current Material baseline as `1.0` and multiplies classic `_OutlineWidth`, `_OutlineSoftness`, and `_Outline2Width`, plus the outline components (Y/Z/W) of SRP `_IsoPerimeter` / `_Softness`. SRP face components (X) and outline position offsets remain unchanged.
- `--outline-ratio 1.25` makes outlines 25% thicker, while `--outline-ratio 0.6` makes them thinner.
- `--outline-ratio` uses an explicitly supplied replacement outline value by default (falling back to that Material's in-game value when absent), and the in-game value with `--use-game-material` or for linked presets. A zero baseline remains zero at every ratio.
- Raster conversion synchronizes the creation setting and runtime render mode, selecting modern TextCore `RASTER_MODE_BITMAP` or the legacy TMP bitmap enum from the serialized shape.
- Old, hybrid, and modern shapes identified in the official TMP 0.1.x through 4.0 preview sources are selected from actual TypeTree fields. Processing continues only when the real binary TypeTree can be read and the saved result can be reopened; unknown or contradictory render/schema data is refused instead of guessed from a version number.

### Preview Export

- `--preview-export` writes SDF atlas previews and glyph crops into `preview/`.
- `--preview-export --ps5-swizzle` writes previews in unswizzled view.
- `--preview-export` cannot be combined with any other primary mode argument.
- `--preview-export` cannot be combined with `--output-only`.

### PS5 Swizzle

- `--ps5-swizzle` uses metadata-first detection (with raw-data fallback) to decide target SDF atlas swizzle state.
- Swizzle masks are auto-computed from texture dimensions (power-of-two).
- `swizzle` and `process_swizzle` are added to `--parse` JSON only when `--ps5-swizzle` is used.
- Set `process_swizzle: "True"` in JSON to force replacement atlas swizzle conversion regardless of auto detection.

### General

- Primary mode arguments (`--parse`, `--mulmaru`, `--nanumgothic`, `--font`, `--list`, `--preview-export`) are mutually exclusive.
- `TypeTreeGeneratorAPI` is required for TMP(FontAsset) parsing/replacement.
- Interactive path input strips repeated wrapping quotes automatically.
- Back up game files before modification.
- Some games may restore modified files by integrity checks.
- Check Terms of Service before using in online games.

---

---

## Special Thanks

- [UnityPy](https://github.com/K0lb3/UnityPy) by K0lb3
- [Il2CppDumper](https://github.com/Perfare/Il2CppDumper) by Perfare
- [NanumGothic](https://hangeul.naver.com/font) by NAVER | [License](https://help.naver.com/service/30016/contents/18088?osType=PC&lang=ko)
- [Mulmaru](https://github.com/mushsooni/mulmaru) by mushsooni | [License](https://github.com/mushsooni/mulmaru/blob/main/LICENSE_ko)

## License

MIT License

