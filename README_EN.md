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

Recommended run:

```bat
cd release_en
unity_font_replacer_en.exe
```

Executables:

- `unity_font_replacer.exe`: Font replacement tool (Korean UI)
- `unity_font_replacer_en.exe`: Font replacement tool (English UI)
- `export_fonts.exe`: TMP SDF font exporter (Korean UI)
- `export_fonts_en.exe`: TMP SDF font exporter (English UI)

## Font Replacement (unity_font_replacer_en.exe)

### Basic Usage

```bat
:: Interactive mode (asks for game path)
unity_font_replacer_en.exe

:: Set game path + bulk replace with Mulmaru
unity_font_replacer_en.exe --gamepath "D:\Games\Muck" --mulmaru
```

### Command Line Options

| Option | Description |
|------|------|
| `--gamepath <path>` | Game root path or `_Data` folder path |
| `--parse` | Export font info to JSON |
| `--mulmaru` | Bulk replace all fonts with Mulmaru |
| `--nanumgothic` | Bulk replace all fonts with NanumGothic |
| `--sdfonly` | Replace SDF fonts only |
| `--ttfonly` | Replace TTF fonts only |
| `--list <JSON>` | Replace fonts from a JSON mapping |

### Examples

```bat
:: Export font info (creates Muck.json)
unity_font_replacer_en.exe --gamepath "D:\Games\Muck" --parse

:: Replace all fonts with Mulmaru
unity_font_replacer_en.exe --gamepath "D:\Games\Muck" --mulmaru

:: Replace SDF only with NanumGothic
unity_font_replacer_en.exe --gamepath "D:\Games\Muck" --nanumgothic --sdfonly

:: Replace using JSON mapping
unity_font_replacer_en.exe --gamepath "D:\Games\Muck" --list Muck.json
```

## Per-Font Replacement (--list)

1. Run `--parse` to generate font info JSON.
2. Fill `Replace_to` for entries you want to replace.
3. Run with `--list`.

JSON example:

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
        "Replace_to": ""
    }
}
```

- If `Replace_to` is empty, that font is skipped.
- Valid `Replace_to` forms:
  - `Mulmaru` or `Mulmaru.ttf`
  - `NanumGothic` or `NanumGothic.ttf`
  - `Mulmaru SDF` or `Mulmaru SDF.json` or `Mulmaru SDF Atlas.png`

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

- `TMP_FontAssetName.json`
- `TMP_FontAssetName SDF Atlas.png`
- (if present) `Material_*.json`

## Supported Fonts

| Font | Description |
|-----------|------|
| Mulmaru | Mulmaru Korean font |
| NanumGothic | NanumGothic Korean font |

## Adding Custom Fonts

Add these files under `KR_ASSETS`:

- `FontName.ttf`
- `FontName SDF.json`
- `FontName SDF Atlas.png`

You can generate SDF font data with `export_fonts_en.exe`.

## Run from Source (Optional)

If you prefer Python scripts instead of EXEs:

### Requirements

- Python 3.12 recommended
- Packages: `UnityPy`, `TypeTreeGeneratorAPI`, `Pillow`

```bash
pip install UnityPy TypeTreeGeneratorAPI Pillow
```

### Examples

```bash
python unity_font_replacer_en.py --gamepath "D:\Games\Muck" --mulmaru
python export_fonts_en.py "D:\MyGame"
```

## Notes

- Save tries to preserve original compression; fallback order is `lz4 -> safe-none`.
- `TypeTreeGeneratorAPI` is required for TMP(FontAsset) parsing/replacement.
- Back up game files before modification.
- Some games may restore modified files by integrity checks.
- Check Terms of Service before using in online games.

## Special Thanks

- [UnityPy](https://github.com/K0lb3/UnityPy) by K0lb3
- [Il2CppDumper](https://github.com/Perfare/Il2CppDumper) by Perfare
- [NanumGothic](https://hangeul.naver.com/font) by NAVER | [License](https://help.naver.com/service/30016/contents/18088?osType=PC&lang=ko)
- [Mulmaru](https://github.com/mushsooni/mulmaru) by mushsooni | [License](https://github.com/mushsooni/mulmaru/blob/main/LICENSE_ko)

## License

MIT License
