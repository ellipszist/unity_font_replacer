[> for English verison of README.md](README_EN.md)

# Unity Font Replacer

Unity 게임의 폰트를 한글 폰트로 교체하는 도구입니다. TTF 폰트와 TextMeshPro SDF 폰트를 모두 지원합니다.

## 빠른 시작 (EXE 기준)

릴리즈 ZIP을 풀면 보통 아래처럼 구성됩니다.

```
release/
├── unity_font_replacer.exe
├── export_fonts.exe
├── KR_ASSETS/
├── Il2CppDumper/
└── README.md
```

권장 실행 방식:

```bat
cd release
unity_font_replacer.exe
```

- `unity_font_replacer.exe`: 폰트 교체 도구 (한국어 UI)
- `unity_font_replacer_en.exe`: 폰트 교체 도구 (영문 UI)
- `export_fonts.exe`: TMP SDF 폰트 추출 도구 (한국어 UI)
- `export_fonts_en.exe`: TMP SDF 폰트 추출 도구 (영문 UI)

## 폰트 교체 (unity_font_replacer.exe)

### 기본 사용법

```bat
:: 대화형 모드 (게임 경로 입력)
unity_font_replacer.exe

:: 게임 경로 지정 + Mulmaru 일괄 교체
unity_font_replacer.exe --gamepath "D:\Games\Muck" --mulmaru
```

### 명령줄 옵션

| 옵션 | 설명 |
|------|------|
| `--gamepath <경로>` | 게임 루트 경로 또는 `_Data` 폴더 경로 |
| `--parse` | 게임 폰트 정보를 JSON 파일로 출력 |
| `--mulmaru` | 모든 폰트를 Mulmaru로 일괄 교체 |
| `--nanumgothic` | 모든 폰트를 NanumGothic으로 일괄 교체 |
| `--sdfonly` | SDF 폰트만 교체 |
| `--ttfonly` | TTF 폰트만 교체 |
| `--list <JSON파일>` | JSON 파일 기준 개별 폰트 교체 |
| `--target-file <파일명>` | 지정한 파일명만 교체 대상에 포함 (여러 번/콤마로 지정 가능) |
| `--use-game-material` | SDF 교체 시 게임 원본 Material 파라미터 유지 (기본: 교체 Material 보정 적용) |
| `--use-game-line-metrics` | SDF 교체 시 게임 원본 줄 간격 메트릭 사용 (기본: 교체 폰트 메트릭 보정 적용, pointSize는 교체값 유지) |
| `--original-compress` | 저장 시 원본 압축 모드를 우선 사용 (기본: 무압축 계열 우선) |
| `--temp-dir <경로>` | 임시 저장 폴더 루트 경로 지정 (빠른 SSD/NVMe 권장) |
| `--split-save-force` | 대형 SDF 다건 교체에서 one-shot을 건너뛰고 SDF 1개씩 강제 분할 저장 |
| `--oneshot-save-force` | 대형 SDF 다건 교체에서도 분할 저장 폴백 없이 one-shot만 시도 |

### 사용 예시

```bat
:: 폰트 정보 파싱 (Muck.json 생성)
unity_font_replacer.exe --gamepath "D:\Games\Muck" --parse

:: Mulmaru로 전체 교체
unity_font_replacer.exe --gamepath "D:\Games\Muck" --mulmaru

:: NanumGothic으로 SDF만 교체
unity_font_replacer.exe --gamepath "D:\Games\Muck" --nanumgothic --sdfonly

:: SDF 교체 + 게임 원본 Material 파라미터 유지
unity_font_replacer.exe --gamepath "D:\Games\Muck" --nanumgothic --use-game-material

:: SDF 줄 간격 메트릭은 게임 원본 유지 (pointSize는 교체값 유지)
unity_font_replacer.exe --gamepath "D:\Games\Muck" --nanumgothic --use-game-line-metrics

:: 특정 파일만 대상으로 교체
unity_font_replacer.exe --gamepath "D:\Games\Muck" --nanumgothic --target-file "sharedassets0.assets"

:: 저장 시 원본 압축 우선
unity_font_replacer.exe --gamepath "D:\Games\Muck" --nanumgothic --original-compress

:: 임시 저장 폴더를 빠른 SSD/NVMe 경로로 지정
unity_font_replacer.exe --gamepath "D:\Games\Muck" --nanumgothic --temp-dir "E:\UFR_TEMP"

:: one-shot 건너뛰고 SDF 1개씩 강제 분할 저장
unity_font_replacer.exe --gamepath "D:\Games\Muck" --nanumgothic --split-save-force

:: 분할 저장 폴백 없이 one-shot만 강제
unity_font_replacer.exe --gamepath "D:\Games\Muck" --nanumgothic --oneshot-save-force

:: JSON 기반 개별 교체
unity_font_replacer.exe --gamepath "D:\Games\Muck" --list Muck.json
```

## 개별 폰트 교체 (--list)

1. `--parse`로 폰트 정보 JSON 생성
2. JSON의 `Replace_to` 필드에 원하는 폰트 이름 입력
3. `--list`로 교체 실행

JSON 예시:

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

- `Replace_to`가 비어 있으면 해당 항목은 교체하지 않습니다.
- `Replace_to` 예시:
  - `Mulmaru` 또는 `Mulmaru.ttf`
  - `NanumGothic` 또는 `NanumGothic.ttf`
  - `Mulmaru SDF` 또는 `Mulmaru SDF.json` 또는 `Mulmaru SDF Atlas.png`

## 폰트 추출 (export_fonts.exe)

TextMeshPro SDF 폰트를 추출하는 도구입니다.

```bat
:: 경로 인자 방식 (권장)
export_fonts.exe "D:\MyGame"

:: 또는 _Data 직접 지정
export_fonts.exe "D:\MyGame\MyGame_Data"

:: 인자 생략 시 대화형 프롬프트
export_fonts.exe
```

실행 후 현재 작업 디렉터리에 다음 파일이 생성됩니다.
- `TMP_FontAsset이름.json`
- `TMP_FontAsset이름 SDF Atlas.png`
- (있는 경우) `Material_*.json`

## 지원 폰트

| 폰트 이름 | 설명 |
|-----------|------|
| Mulmaru | 물마루체 |
| NanumGothic | 나눔고딕 |

## 커스텀 폰트 추가

`KR_ASSETS` 폴더에 아래 파일을 추가하면 됩니다.

- `폰트이름.ttf`
- `폰트이름 SDF.json`
- `폰트이름 SDF Atlas.png`

SDF 데이터는 `export_fonts.exe`로 추출할 수 있습니다.

## 소스 실행 (선택)

EXE 대신 Python 소스로 실행하려면:

### 요구 사항

- Python 3.12 권장
- 패키지: `UnityPy(포크)`, `TypeTreeGeneratorAPI`, `Pillow`

```bash
pip install TypeTreeGeneratorAPI Pillow
pip install --upgrade git+https://github.com/snowyegret23/UnityPy.git
```

### 실행 예시

```bash
python unity_font_replacer.py --gamepath "D:\Games\Muck" --mulmaru
python export_fonts.py "D:\MyGame"
```

## 주의 사항

- 저장 기본 모드는 무압축 계열 우선(`safe-none -> legacy-none`)이며, 실패 시 `original -> lz4` 순으로 폴백합니다.
- 저장 시 원본 압축 우선이 필요하면 `--original-compress`를 사용하세요.
- 저장 속도가 느리면 `--temp-dir`로 임시 저장 폴더를 빠른 SSD/NVMe 경로로 지정해 보세요.
- 프로그램 종료 시 임시 폴더는 자동 정리됩니다.
- 대형 SDF 다건 교체에서는 기본적으로 one-shot 실패 시 적응형 분할 저장(배치 크기 자동 조절)으로 폴백합니다.
  - `--split-save-force`: one-shot을 건너뛰고 SDF 1개씩 강제 분할 저장
  - `--oneshot-save-force`: 분할 저장 폴백 비활성화(one-shot만 시도)
- 파일 단위로 제한하려면 `--target-file`을 사용하세요.
- 기본 줄 간격 메트릭 모드는 게임 원본 비율을 기준으로 교체 폰트 pointSize에 맞게 보정 적용합니다.
- 게임 원본 줄 간격 메트릭을 그대로 쓰려면 `--use-game-line-metrics`를 사용하세요. pointSize는 항상 교체 폰트 값을 사용합니다.
- SDF 교체 시 기본은 `KR_ASSETS/* SDF Material.json` 머티리얼 float를 적용하며, padding 비율 기준 보정도 함께 적용합니다.
- 원본 게임 머티리얼 스타일을 유지하려면 `--use-game-material`을 사용하세요.
- TMP(FontAsset) 파싱/교체를 위해 `TypeTreeGeneratorAPI`가 필요합니다.
- 게임 파일 수정 전 백업을 권장합니다.
- 일부 게임은 무결성 검사로 수정 파일이 원복될 수 있습니다.
- 온라인 게임 사용 시 이용 약관을 확인하세요.

## Special Thanks

- [UnityPy](https://github.com/K0lb3/UnityPy) by K0lb3
- [Il2CppDumper](https://github.com/Perfare/Il2CppDumper) by Perfare
- [나눔고딕](https://hangeul.naver.com/font) by NAVER | [License](https://help.naver.com/service/30016/contents/18088?osType=PC&lang=ko)
- [물마루](https://github.com/mushsooni/mulmaru) by mushsooni | [License](https://github.com/mushsooni/mulmaru/blob/main/LICENSE_ko)

## 라이선스

MIT License
