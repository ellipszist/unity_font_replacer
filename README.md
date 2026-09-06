[> for English version of README.md](README_EN.md)

# Unity Font Replacer

Unity 게임의 폰트를 한글 폰트로 교체하는 도구입니다. TTF 폰트와 TextMeshPro SDF 폰트를 모두 지원합니다.

## 빠른 시작 (EXE 기준)

릴리즈 ZIP을 풀면 보통 아래처럼 구성됩니다.

```
release/
├── unity_font_replacer_ko.exe
├── export_fonts_ko.exe
├── KR_ASSETS/
├── Il2CppDumper/
└── README.md
```

`make_sdf.exe`는 별도 단독 ZIP(`make_sdf_vX.Y.Z.zip`)으로 제공합니다.

권장 실행 방식:

```bat
cd release
unity_font_replacer_ko.exe
```

| 실행 파일 | 설명 |
|-----------|------|
| `unity_font_replacer_ko.exe` | 폰트 교체 도구 (한국어 UI) |
| `unity_font_replacer_en.exe` | 폰트 교체 도구 (영문 UI) |
| `export_fonts_ko.exe` | TMP SDF 폰트 추출 도구 (한국어 UI) |
| `export_fonts_en.exe` | TMP SDF 폰트 추출 도구 (영문 UI) |
| `make_sdf.exe` | TTF -> TMP SDF JSON/Atlas 생성 도구 (별도 단독 ZIP) |

---

## 폰트 교체 (unity_font_replacer_ko.exe)

### 기본 사용법

```bat
:: 대화형 모드 (게임 경로 입력)
unity_font_replacer_ko.exe

:: 게임 경로 지정 + Mulmaru 일괄 교체
unity_font_replacer_ko.exe --gamepath "C:/path/to/game" --mulmaru

:: 내가 가진 TTF로 TTF/SDF 전체 교체 (SDF는 자동 생성)
unity_font_replacer_ko.exe --gamepath "C:/path/to/game" --font "D:\Fonts\MyFont.ttf"
```

- 기본 작업 모드 인자(`--parse`, `--mulmaru`, `--nanumgothic`, `--font`, `--list`, `--preview-export`)는 **하나만** 사용할 수 있습니다.
- EXE를 대화형으로 실행하면 종료 전 엔터 입력을 기다리고, 명령줄 인자를 준 CLI 실행은 작업 완료 후 바로 종료됩니다.

### 명령줄 옵션

#### 기본

| 옵션 | 설명 |
|------|------|
| `--gamepath <경로>` | 게임 루트 경로 또는 `_Data` 폴더 경로 |
| `--parse` | 게임 폰트 정보를 JSON 파일로 출력 |
| `--list <JSON파일>` | JSON 파일 기준 개별 폰트 교체 |
| `--font <폰트/TTF/OTF>` | 지정 폰트로 전체 교체 (TTF/OTF이면 SDF 대상 자동 생성) |
| `--verbose` | 콘솔은 현재 수준으로 유지하고, `verbose.txt`에 상세 DEBUG 로그(경로/Unity 버전/파일별/폰트별)를 저장 |

- `--verbose`를 사용하면 실행 파일(또는 스크립트) 기준 폴더에 `verbose.txt`가 생성되며, 타임스탬프/로그 레벨이 포함된 상세 추적 로그가 기록됩니다.

#### 교체 대상

| 옵션 | 설명 |
|------|------|
| `--mulmaru` | 모든 폰트를 Mulmaru로 일괄 교체 |
| `--nanumgothic` | 모든 폰트를 NanumGothic으로 일괄 교체 |
| `--sdfonly` | SDF 폰트만 교체 |
| `--ttfonly` | TTF 폰트만 교체 |
| `--target-file <파일명>` | 지정한 파일명만 교체 대상에 포함 (여러 번/콤마로 지정 가능) |

Dynamic TMP의 source TTF만 변경하면 기존 glyph ID와 충돌해 한글이 다른 문자로 표시될 수 있습니다. 이런 TTF 단독 교체는 중단됩니다. 연결된 SDF도 함께 선택하고 `--freeze-dynamic`을 사용하거나 source TTF를 교체 대상에서 제외하세요. TTF 교체 실행 시에도 이 연결을 검사할 TypeTree가 필요할 수 있습니다.

TTF 교체는 필수가 아닙니다. `--sdfonly --freeze-dynamic`으로 선택한 TMP의 문자표·글리프·atlas를 함께 교체하면 원본 TTF는 유지됩니다. Static atlas에 포함되지 않은 문자는 동적으로 추가되지 않으므로 필요한 글자셋이나 fallback을 준비해야 합니다.

#### TMP FontAsset 교체 옵션

| 옵션 | 설명 |
|------|------|
| `--use-game-material` | 교체 폰트 Material의 호환 스타일값 대신 게임 원본 Material 스타일값 유지 (atlas 필수값은 항상 동기화) |
| `--force-raster` | Alpha8 Raster atlas를 생성하고, 각 Material을 현재 파일에서 실제로 도달 가능한 TMP Bitmap shader로 재연결 |
| `--allow-unsafe-full-color-shader-fallback` | 테스트 전용. Raster atlas를 흰색 RGB가 보존되는 RGBA32로 저장하고 `TextMeshPro/Sprite`/`Bitmap Custom Atlas` fallback을 명시적으로 허용 |
| `--allow-unsafe-gui-text-fallback` | 테스트 전용. RGBA32 저장과 함께 TMP UI mask/depth를 지원하지 않는 `GUI/Text Shader` fallback을 명시적으로 허용 |
| `--freeze-dynamic` | Dynamic/DynamicOS TMP FontAsset을 명시적으로 baked Static으로 고정하고 runtime source Font PPtr 해제 |
| `--use-game-line-metrics` | 게임 원본 줄 간격 메트릭 사용 (pointSize는 교체값 유지) |
| `--outline-ratio <float>` | 현재 선택된 Material 기준 classic/SRP outline 두께·softness에 배율 적용 (기본 `1.0`) |
| `--charset <파일/문자열>` | TTF/OTF에서 SDF/Raster atlas 자동 생성 시 사용할 글자셋 지정 (기본 `CharList_3911.txt`) |

#### 저장

| 옵션 | 설명 |
|------|------|
| `--original-compress` / `--no-original-compress` | 원본 압축 우선 저장 (기본 활성화) / 무압축 계열 우선 저장 |
| `--temp-dir <경로>` | 임시 저장 폴더 루트 경로 지정 (빠른 SSD/NVMe 권장) |
| `--output-only <경로>` | 원본은 유지하고, 수정된 파일만 지정 폴더에 저장 (상대 경로 유지) |
| `--split-save-force` | one-shot을 건너뛰고 SDF 1개씩 강제 분할 저장 |
| `--oneshot-save-force` | 분할 저장 폴백 없이 one-shot만 시도 |

- `--output-only`는 `--preview-export`와 함께 사용할 수 없습니다.

#### PS5 / 스캔

| 옵션 | 설명 |
|------|------|
| `--ps5-swizzle` | PS5 Atlas swizzle 자동 판별/변환 (텍스쳐 크기별 mask 자동 계산, `rotate=90`) |
| `--preview-export` | `preview/`에 SDF Atlas + 글리프 crop PNG 저장 (`--ps5-swizzle`와 함께 사용 시 unswizzle 기준) |
| `--scan-jobs <N>`, `--max-workers <N>` | 폰트 스캔 병렬 워커 수 (기본: `1`) |
| `--scan-stall-seconds <초>` | CPU/I/O/진행 신호가 모두 멈춘 워커의 정지 판정 시간 (기본: `300`, `0`이면 비활성화; 파일 총 처리시간 제한 아님) |
| `--exclude-ext <목록>` | 추가 스캔 제외 확장자(콤마 구분, 예: `"resS,.resource,.split0"`) |

### 사용 예시

**기본 교체:**

```bat
:: Mulmaru로 전체 교체
unity_font_replacer_ko.exe --gamepath "C:/path/to/game" --mulmaru

:: NanumGothic으로 SDF만 교체
unity_font_replacer_ko.exe --gamepath "C:/path/to/game" --nanumgothic --sdfonly

:: JSON 기반 개별 교체
unity_font_replacer_ko.exe --gamepath "C:/path/to/game" --list font_map.json

:: 사용자 TTF로 전체 교체
unity_font_replacer_ko.exe --gamepath "C:/path/to/game" --font "D:\Fonts\Galmuri14.ttf"

:: 번역문에서 추출한 글자셋으로 사용자 TTF SDF 생성
unity_font_replacer_ko.exe --gamepath "C:/path/to/game" --font "D:\Fonts\Galmuri14.ttf" --charset "D:\Fonts\charset.txt"
```

**파싱 / 스캔:**

```bat
:: 폰트 정보 파싱 (font_map.json 생성)
unity_font_replacer_ko.exe --gamepath "C:/path/to/game" --parse

:: 병렬 워커 + PS5 swizzle 판별 필드 포함 (alias: --max-workers)
unity_font_replacer_ko.exe --gamepath "C:/path/to/game" --parse --max-workers 10 --ps5-swizzle

:: 추가 확장자 제외 (쉼표 구분, 점 유무 모두 허용)
unity_font_replacer_ko.exe --gamepath "C:/path/to/game" --parse --exclude-ext "resS,.resource,.split0"
```

**SDF 옵션:**

```bat
:: 게임 원본 Material 파라미터 유지
unity_font_replacer_ko.exe --gamepath "C:/path/to/game" --nanumgothic --use-game-material

:: 게임 원본 줄 간격 메트릭 유지
unity_font_replacer_ko.exe --gamepath "C:/path/to/game" --nanumgothic --use-game-line-metrics

:: Dynamic FontAsset이 있는 게임에서 동적 글리프 추가를 포기하고 Static으로 교체
unity_font_replacer_ko.exe --gamepath "C:/path/to/game" --nanumgothic --freeze-dynamic

:: 현재 선택된 Material 기준 외곽선 1.25배
unity_font_replacer_ko.exe --gamepath "C:/path/to/game" --nanumgothic --outline-ratio 1.25

:: 게임 원본 Material 기준 외곽선 0.6배
unity_font_replacer_ko.exe --gamepath "C:/path/to/game" --nanumgothic --use-game-material --outline-ratio 0.6
```

**저장 / 출력:**

```bat
:: 특정 파일만 대상으로 교체
unity_font_replacer_ko.exe --gamepath "C:/path/to/game" --nanumgothic --target-file "sharedassets0.assets"

:: 원본 유지 + 수정 파일만 별도 폴더 출력
unity_font_replacer_ko.exe --gamepath "C:/path/to/game" --nanumgothic --output-only "D:\output"

:: 저장 시 원본 압축 우선
unity_font_replacer_ko.exe --gamepath "C:/path/to/game" --nanumgothic --original-compress

:: 임시 저장 폴더를 빠른 SSD/NVMe 경로로 지정
unity_font_replacer_ko.exe --gamepath "C:/path/to/game" --nanumgothic --temp-dir "E:\UFR_TEMP"
```

**PS5 미리보기:**

```bat
:: 일반(PC) 미리보기 export
unity_font_replacer_ko.exe --gamepath "C:/path/to/game" --preview-export --sdfonly

:: PS5 unswizzle 기준 미리보기 export
unity_font_replacer_ko.exe --gamepath "C:/path/to/game" --preview-export --ps5-swizzle --sdfonly
```

---

## 개별 폰트 교체 (--list)

1. `--parse`로 폰트 정보 JSON 생성
2. JSON의 `Replace_to` 필드에 원하는 폰트 이름 입력
3. `--list`로 교체 실행

JSON 예시 (`--ps5-swizzle` 미사용):

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

### force_raster 필드

`--parse` JSON에서는 **SDF 항목에만** `force_raster` 필드가 포함되며 기본값은 `"False"`입니다.

| 필드 | 설명 |
|------|------|
| `force_raster` | 해당 FontAsset을 Alpha8 Raster atlas로 변환 (`"True"` / `"False"`, 기본 `"False"`) |

- SDF와 Bitmap Material은 shader 계약이 달라 `m_AtlasRenderMode`만 바꾸는 변환은 안전하지 않습니다.
- `force_raster: "True"` 또는 `--force-raster`를 지정하면 FontAsset/atlas뿐 아니라 연결된 Material의 `m_Shader`와 SavedProperties도 함께 변환합니다.
- 기존 PPtr로 도달 가능한 compiled Shader의 이름과 실제 property 계약을 모두 확인하며, 호환 shader가 없으면 파일을 저장하지 않고 중단합니다.

### PS5 swizzle 필드

`--ps5-swizzle`를 함께 사용해 `--parse`하면, SDF 항목에 아래 2개 필드가 추가됩니다.

| 필드 | 설명 |
|------|------|
| `swizzle` | 원본 대상 Atlas의 자동 판별 결과 (`"True"` / `"False"`) |
| `process_swizzle` | 교체 Atlas를 swizzle 상태로 강제 변환할지 여부 (기본 `"False"`) |

- 구버전 JSON(해당 키 없음)도 그대로 호환됩니다.

JSON 예시 (`--ps5-swizzle` 사용, SDF):

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

### Replace_to 지정 방법

`Replace_to`가 비어 있으면 해당 항목은 교체하지 않습니다.

| 입력 | 예시 |
|------|------|
| 폰트 이름 | `Mulmaru`, `NanumGothic` |
| TTF 파일 | `Mulmaru.ttf` |
| SDF JSON | `Mulmaru SDF.json` |
| SDF Atlas | `Mulmaru SDF Atlas.png` |
| Material | `NGothic Material.json` |

SDF 항목의 `Replace_to`에 `.ttf` 또는 `.otf` 파일 경로를 넣으면, 대상 게임 SDF 폰트의 `m_AtlasPadding` 값에 맞춰 임시 SDF 세트를 자동 생성한 뒤 교체합니다.

---

## PS5 검증 워크플로 (--preview-export)

원본/수정본을 같은 방법으로 비교하려면 아래 순서를 권장합니다.

1. 대상 파일만 스캔 JSON 생성
2. 원본 상태에서 `--list + --ps5-swizzle + --preview-export` 실행 (원본 crop 추출)
3. `--nanumgothic --ps5-swizzle`로 교체
4. 다시 `--list + --ps5-swizzle + --preview-export` 실행 (수정본 crop 추출)
5. 두 결과를 비교

예시 (PS5 번들 1개만 검증):

```bat
:: 1) 대상 파일 JSON 생성
unity_font_replacer_ko.exe --gamepath "C:\Game\Game_Data" ^
    --parse --target-file "38871756d6e98b9e67fb2e7a61dbb88e.bundle" --ps5-swizzle

:: 2) 원본 crop 추출
unity_font_replacer_ko.exe --gamepath "C:\Game\Game_Data" ^
    --list "Game.json" --target-file "38871756d6e98b9e67fb2e7a61dbb88e.bundle" ^
    --ps5-swizzle --preview-export --sdfonly

:: 3) NanumGothic 교체 (원본 보호 필요 시 --output-only 사용)
unity_font_replacer_ko.exe --gamepath "C:\Game\Game_Data" ^
    --nanumgothic --sdfonly --target-file "38871756d6e98b9e67fb2e7a61dbb88e.bundle" ^
    --ps5-swizzle --output-only "D:\output"

:: 4) 수정본 crop 추출
unity_font_replacer_ko.exe --gamepath "C:\Game\Game_Data" ^
    --list "Game.json" --target-file "38871756d6e98b9e67fb2e7a61dbb88e.bundle" ^
    --ps5-swizzle --preview-export --sdfonly
```

출력 경로:

| 종류 | 경로 |
|------|------|
| Atlas preview | `preview/<파일명>/<assets_name>__<atlas_pathid>__<font>__unswizzled__*.png` |
| Glyph crop | `preview/<파일명>/<assets_name>__<atlas_pathid>__<font>/U+XXXX*.png` |

---

## 폰트 추출 (export_fonts_ko.exe)

TextMeshPro SDF 폰트를 추출하는 도구입니다.

```bat
:: 경로 인자 방식 (권장)
export_fonts_ko.exe "D:\MyGame"

:: 또는 _Data 직접 지정
export_fonts_ko.exe "D:\MyGame\MyGame_Data"

:: 인자 생략 시 대화형 프롬프트
export_fonts_ko.exe
```

실행 후 현재 작업 디렉터리에 다음 파일이 생성됩니다.

| 출력 파일 | 설명 |
|-----------|------|
| `FontAsset이름.json` | TMP 폰트 데이터 |
| `FontAsset이름 SDF Atlas.png` | SDF Atlas 이미지 |
| `Material_*.json` | Material 데이터 (있는 경우) |

---

## 지원 폰트

| 폰트 이름 | 설명 |
|-----------|------|
| Mulmaru | 물마루 |
| NanumGothic | 나눔고딕 |

## 커스텀 폰트 추가

`KR_ASSETS` 폴더에 아래 파일을 추가하면 됩니다.

| 파일 | 필수 여부 |
|------|-----------|
| `폰트이름.ttf` 또는 `.otf` | 필수 |
| `폰트이름 SDF.json` / `Raster.json` / `.json` | 선택 (없으면 TTF/OTF에서 자동 생성 가능) |
| `폰트이름 SDF Atlas.png` / `Raster Atlas.png` / `Atlas.png` | 선택 (없으면 TTF/OTF에서 자동 생성 가능) |
| `폰트이름 SDF Material.json` / `Raster Material.json` / `Material.json` | 선택 |

SDF 데이터가 없으면 `--font` 또는 `--list`의 `Replace_to`에 TTF/OTF를 지정해 자동 생성할 수 있습니다. 별도 파일로 보관하고 싶을 때는 아래 `make_sdf.exe`를 사용하세요.

---

## SDF 생성 도구 (make_sdf.exe)

TTF에서 TMP 호환 JSON/Atlas를 직접 생성할 수 있습니다.

```bat
make_sdf.exe --ttf Mulmaru.ttf
```

| 인자 | 설명 | 기본값 |
|------|------|--------|
| `--ttf <ttfname>` | TTF 파일 경로/이름 | (필수) |
| `--atlas-size <w,h>` | 아틀라스 해상도 | `4096,4096` |
| `--point-size <int or auto>` | 샘플링 포인트 크기 | `auto` |
| `--padding <int>` | 아틀라스 패딩 | `7` |
| `--charset <txtpath or characters>` | 문자셋 파일 경로 또는 직접 문자열 | `./CharList_3911.txt` |
| `--rendermode <sdf,raster>` | 출력 렌더 모드 | `sdf` |

---

## 소스 실행 (선택)

EXE 대신 Python 소스로 실행하려면:

### 요구 사항

- Python 3.12 권장
- 패키지: `UnityPy 1.25.3 커스텀 포크`, `TypeTreeGeneratorAPI`, `Pillow`, `fontTools`, `numpy`, `scipy`, `psutil`

```bash
pip install TypeTreeGeneratorAPI Pillow fonttools numpy scipy psutil
pip install --upgrade git+https://github.com/snowyegret23/UnityPy.git@bccc488474556a5aab30121d7a6c7500c54a80c7
```

이 저장소와 `UnityPy` 저장소가 같은 상위 폴더에 있으면 소스 실행 시 sibling
`UnityPy`를 자동으로 우선 사용합니다. 필요한 저메모리 API가 없으면 저장 전에
오류를 내고 중단합니다.

### 실행 예시

```bash
python unity_font_replacer_ko.py --gamepath "C:/path/to/game" --mulmaru
python export_fonts_ko.py "D:\MyGame"
```

---

## 주의 사항

### 저장

- 기본 저장 순서는 `original -> lz4 -> safe-none -> legacy-none`입니다. `--no-original-compress`일 때만 `safe-none -> legacy-none -> original -> lz4` 순서로 시도합니다.
- 저장된 모든 변경 객체는 파일을 다시 열어 정확한 CAB 이름, signed PathID, raw object SHA-256으로 검증합니다.
- 외부 파일의 TMP Atlas/Material 및 로컬 Addressables catalog 패치는 모두 검증된 경우에만 확정되며, 대상 누락·충돌·저장 실패 시 관련 파일 전체를 실행 전 상태로 롤백합니다.
- 로컬 Standalone Addressables bundle은 catalog의 CRC를 0으로 설정하고 실제 크기를 동기화합니다. `m_Hash`는 로컬 `LoadFromFile` 경로에서 사용되지 않아 보존합니다. 원격·UnityWebRequest 강제·비 Standalone 경로는 안전하게 거부합니다.
- Unity `.split0/.split1` 분할 에셋은 안전한 재분할 저장을 지원하지 않아 교체 대상에서 제외됩니다. 추출기는 `.split0`을 통해 한 번만 읽습니다.
- CLI 임시 파일과 IL2CPP `DummyDll` cache는 게임 폴더 밖의 시스템 임시 경로에 생성됩니다. 저장 속도가 느리면 `--temp-dir`로 빠른 SSD/NVMe 경로를 지정하세요.
- 프로그램 종료 시 임시 폴더는 자동 정리됩니다.
- 대형 SDF 다건 교체에서는 기본적으로 one-shot 실패 시 적응형 분할 저장(배치 크기 자동 조절)으로 폴백합니다.

### 스캔

- `--parse`는 지정한 수의 영구 워커 프로세스를 재사용합니다. EXE를 파일마다 다시 시작하지 않으므로 대량 스캔의 시작 비용이 크게 줄어듭니다.
- 워커가 비정상 종료되거나 응답 파이프가 닫히면 당시 처리 중이던 파일을 하드 크래시 대상으로 기록하고, 새 워커에서 한 번 재시도합니다.
- 살아 있는 워커는 CPU/I/O/진행 신호가 모두 `--scan-stall-seconds` 동안 변하지 않을 때만 `stalled`로 구분합니다. 큰 파일의 총 처리시간만으로 크래시 처리하지 않습니다.
- 무한 CPU 루프처럼 계속 활동 중인 프로세스에는 총 시간 제한을 강제하지 않습니다. 필요하면 실행을 직접 중단하거나 대상 파일을 `--target-file`로 분리해 확인하세요.
- 스캔 속도를 높이려면 `--scan-jobs`(별칭: `--max-workers`)로 워커 수를 늘릴 수 있습니다.
- 스캔은 블랙리스트 기반 제외를 사용합니다 (`*.bak`, `.info`, `.config` 등 제외).
- 추가 제외 확장자가 필요하면 `--exclude-ext "resS,.resource,.split0"`처럼 지정하세요.
- 파일 단위로 제한하려면 `--target-file`을 사용하세요.

### TMP FontAsset (SDF / Raster) 교체

- 기본 줄 간격 메트릭 모드는 게임 원본 비율을 기준으로 교체 폰트 pointSize에 맞게 보정 적용합니다.
- 게임 원본 줄 간격 메트릭을 그대로 쓰려면 `--use-game-line-metrics`를 사용하세요. (pointSize는 항상 교체 폰트 값)
- 기본 SDF 교체는 FontAsset이 직접 참조하는 Material에 교체 폰트 Material의 호환 가능한 동일 이름 float/color 스타일값을 적용합니다. 게임 shader·keyword·보조 texture와 stencil/mask/clip/render 상태는 유지합니다.
- `--use-game-material`을 지정하면 직접 Material도 게임 원본 스타일값을 유지합니다. 두 모드 모두 `_MainTex`와 새 padding 기반 `_GradientScale`을 동기화합니다. Classic SDF는 실제 texture width/height와 공식 `_ScaleRatioA/B/C`도 갱신하지만, `_IsoPerimeter` 기반 SRP Material에는 존재하지 않는 classic 필드를 주입하거나 남아 있는 stale 값을 변경하지 않습니다.
- 같은 atlas를 참조하는 preset/submaterial은 exact outer file/CAB/signed PathID로 찾아 atlas 계약을 함께 갱신하되, 각 preset 고유의 색·outline·underlay·keyword는 유지합니다.
- `--nanumgothic` / `--mulmaru` 일괄 교체는 원본보다 작지 않은 최소 내장 preset(`Padding_5` / `Padding_7` / `Padding_15`)을 선택하고, 15보다 크면 TTF에서 정확한 padding으로 생성합니다.
- `--font <TTF/OTF>` 또는 JSON `Replace_to`의 TTF/OTF 지정은 원본 `m_AtlasPadding` 값에 맞춰 임시 SDF atlas를 자동 생성합니다.
- 자동 생성은 기본 문자셋 `CharList_3911.txt`, atlas `4096x4096`, point size 자동 탐색을 사용합니다.
- TTF의 실제 glyph ID와 단순 OpenType `kern` pair를 TMP feature record로 다시 생성합니다. 지원하지 않는 GPOS/GSUB/GDEF lookup이 필요한 폰트는 잘못된 shaping을 조용히 저장하지 않고 중단합니다.
- 번역문에 기본 문자셋에 없는 한글/한자/특수문자가 있으면 `--charset <파일>`로 실제 사용 문자 목록을 지정하세요. JSON 항목별로는 `Charset` 또는 `charset` 필드를 사용할 수 있습니다.
- 글리프가 0개인 TMP fallback FontAsset도 atlas 참조가 있으면 SDF 교체 대상에 포함합니다. 일부 게임의 `* SDF - Fallback` 빈 에셋이 남아 누락 글자가 빈칸으로 떨어지는 문제를 줄이기 위한 처리입니다.
- 하나의 atlas를 여러 FontAsset이 공유하면 모든 소유자를 같은 폰트로 선택한 경우에만 교체합니다. 일부만 선택하거나 서로 다른 폰트로 지정하면 중단합니다.
- 교체 결과는 static single-atlas로 정규화됩니다. 원래 Dynamic/DynamicOS인 FontAsset은 기본적으로 중단하며, 동적 글리프 추가를 포기할 의도가 명확할 때만 `--freeze-dynamic`으로 Static 고정 및 runtime source Font PPtr 해제를 허용합니다. 이때 필요한 모든 문자를 `--charset`에 포함해야 합니다.
- 원래 Bitmap인 TMP FontAsset은 자동으로 Raster atlas를 생성합니다. SDF FontAsset은 `force_raster: "True"` 또는 `--force-raster`로 Raster 변환할 수 있습니다.
- Raster 변환은 기존 PPtr 경로로 도달 가능한 shader만 사용하고, 현재 연결된 호환 PPtr을 우선 보존합니다. Alpha8에서 공식적으로 안전한 자동 후보는 `TextMeshPro/Bitmap`과 `TextMeshPro/Mobile/Bitmap`이며, compiled Shader의 실제 property 계약까지 검증합니다. 안전한 후보가 없으면 저장 전에 중단합니다.
- `TextMeshPro/Sprite`와 `TextMeshPro/Bitmap Custom Atlas`는 RGB 전체를 읽으므로 Alpha8 atlas를 그대로 연결하면 검정 glyph가 됩니다. `--allow-unsafe-full-color-shader-fallback`은 해당 교체 작업의 Raster atlas를 `RGB=(255,255,255), A=coverage`인 RGBA32로 저장합니다. 원시 texture 메모리는 Alpha8의 4배가 됩니다.
- `--allow-unsafe-gui-text-fallback`도 검정 곱셈을 막기 위해 RGBA32 저장을 사용합니다. `GUI/Text Shader` 자체에는 stencil/`RectMask2D`가 없고 depth test가 항상 통과하므로, 마스크 밖으로 글자가 새거나 3D 물체를 뚫고 보이는 한계는 남습니다.
- Raster shader에는 SDF의 outline/underlay/glow/gradient 계약이 없으므로 해당 속성과 keyword를 제거합니다. 기본 모드는 직접 Material에 교체 Material의 face tint를 적용하고 `--use-game-material`은 게임 tint를 유지하며, 연결 preset의 tint와 shader가 지원하는 clip/stencil 값 및 `UNITY_UI_ALPHACLIP` toggle은 항상 보존합니다.
- TTF/OTF에서 생성하는 Raster atlas는 SDF effect padding을 상속하지 않고 5 texel의 투명 여백을 사용합니다. 이는 TMP bitmap의 기본 1 texel과 `Extra Padding`의 추가 4 texel UV 확장을 모두 보호하면서 atlas 해상도 낭비를 줄입니다.
- `--outline-ratio`는 현재 선택된 Material 기준값을 1.0으로 보고 classic의 `_OutlineWidth`, `_OutlineSoftness`, `_Outline2Width`와 SRP의 `_IsoPerimeter`/`_Softness` 중 outline 성분(Y/Z/W)에 추가 배율을 곱합니다. SRP의 face 성분(X)과 outline 위치 offset은 유지합니다.
- `--outline-ratio 1.25`는 외곽선을 25% 두껍게, `--outline-ratio 0.6`은 더 얇게 만듭니다.
- `--outline-ratio`의 기준은 기본 모드에서 교체 Material에 명시된 outline 값(없으면 해당 게임 값), `--use-game-material`과 연결 preset에서는 게임 값입니다. 기준값이 `0`이면 배율을 적용해도 `0`을 유지합니다.
- Raster 변환은 현대 TextCore의 `RASTER_MODE_BITMAP`과 구형 TMP의 bitmap enum을 직렬화 형태에 맞게 선택하며, 생성 설정과 runtime render mode를 함께 동기화합니다.
- 공식 TMP 0.1.x~4.0 pre 소스에서 확인된 구형·hybrid·신형 형태를 실제 TypeTree 필드 기준으로 판별합니다. 실제 binary의 TypeTree를 읽고 저장 후 재검증할 수 있을 때만 진행하며, 알 수 없거나 모순된 render/schema는 버전 숫자로 추측하지 않고 중단합니다.

### Preview Export

- `--preview-export`는 SDF Atlas/글리프 crop 미리보기를 `preview/`에 저장합니다.
- `--preview-export --ps5-swizzle` 조합이면 unswizzle 기준으로 preview를 저장합니다.
- `--preview-export`는 다른 기본 작업 모드 인자와 함께 사용할 수 없습니다.
- `--preview-export`와 `--output-only`는 함께 사용할 수 없습니다.

### PS5 Swizzle

- `--ps5-swizzle`는 메타데이터 기반 판정(우선) + raw-data 판정을 이용해 SDF Atlas swizzle 상태를 자동 판별합니다.
- Swizzle mask는 텍스쳐 크기(2의 거듭제곱)에 맞게 자동으로 계산됩니다.
- `swizzle`/`process_swizzle` 필드는 `--ps5-swizzle` 모드에서만 `--parse` JSON에 추가됩니다.
- `process_swizzle: "True"`를 JSON에 지정하면 자동 판정과 무관하게 교체 Atlas를 swizzle 상태로 변환합니다.

### 일반

- 기본 작업 모드 인자(`--parse`, `--mulmaru`, `--nanumgothic`, `--font`, `--list`, `--preview-export`)는 하나만 사용할 수 있습니다.
- `TypeTreeGeneratorAPI`가 TMP(FontAsset) 파싱/교체에 필요합니다.
- 대화형 입력에서 경로 앞뒤 따옴표가 중복되어도 자동으로 정리해 처리합니다.
- 게임 파일 수정 전 백업을 권장합니다.
- 일부 게임은 무결성 검사로 수정 파일이 원복될 수 있습니다.
- 온라인 게임 사용 시 이용 약관을 확인하세요.

---

## Special Thanks

- [UnityPy](https://github.com/K0lb3/UnityPy) by K0lb3
- [Il2CppDumper](https://github.com/Perfare/Il2CppDumper) by Perfare
- [나눔고딕](https://hangeul.naver.com/font) by NAVER | [License](https://help.naver.com/service/30016/contents/18088?osType=PC&lang=ko)
- [물마루](https://github.com/mushsooni/mulmaru) by mushsooni | [License](https://github.com/mushsooni/mulmaru/blob/main/LICENSE_ko)

## 라이선스

MIT License

