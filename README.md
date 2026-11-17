# Nb-Si 합금 조성–상–물성 시뮬레이터

Nb-Si 기반 합금의 조성을 슬라이더로 바꾸면 **평형 상 구성**(pycalphad 계산)과
**물성 예측**(문헌 데이터 기반)이 바로 바뀌는 웹 도구입니다.

> 현재 상태: 계산·보간·검증 모듈과 데이터 양식까지 완성. **Nb-Si TDB 파일을 기다리는 중**입니다.

## 진행 상황

| 단계 | 내용 | 상태 |
|---|---|---|
| 0 | 환경 확인 (pycalphad 등 설치) | 완료 |
| 0-1 | 공개 TDB 확보·검증 | **TDB 파일 대기** (NIMS CPDDB) |
| 1 | 열역학 계산 모듈 `calphad_engine.py` | 코드 완료, Nb-Si 확인 대기 |
| 2 | 조성 격자 계산 `build_grid.py` | 코드 완료, Nb-Si 계산 대기 |
| 2-1 | 1차 시연 화면 | 예정 |
| 3 | 문헌 데이터 양식 | 완료 (`data/LITERATURE_GUIDE.md`) |
| 3 | 사용자 DB 가져오기 (`src/import_user_db.py`) | 완료 (데이터 파일은 공개 저장소에 올리지 않음) |
| 3-1 ~ 6 | 논문 수집·물성 모델·화면 완성 | 예정 |

## 설치 (처음 한 번)

Python 3.10 이상이 필요합니다. 터미널(Windows는 "명령 프롬프트" 또는 "PowerShell")에서 실행합니다.

**1. 코드 내려받기**

```bash
git clone https://github.com/<내 GitHub 아이디>/nbsi-simulator.git
```

```bash
cd nbsi-simulator
```

**2. 가상환경 만들기** (이 프로젝트 전용 Python 공간)

```bash
python -m venv .venv
```

**3. 가상환경 켜기**

Windows:

```bash
.venv\Scripts\activate
```

Mac / Linux:

```bash
source .venv/bin/activate
```

**4. 패키지 설치**

```bash
pip install -r requirements.txt
```

이후에는 터미널을 새로 열 때마다 3번(가상환경 켜기)만 하면 됩니다.

## 데이터 파일 (공개 저장소에 없음)

이 저장소는 공개(Public)라서 아래 파일은 올리지 않습니다 (`.gitignore`에 등록).
각자 PC에 두고 사용합니다.

| 파일 | 만드는 법 |
|---|---|
| `data/raw_user/A_NbSilicide_DB.xlsx`, `B_Nballoy_1117.xlsx` | 연구실 원본 DB를 이 이름으로 복사 |
| `data/literature.csv` 등 | 원본 DB를 넣은 뒤 아래 두 명령 실행 |
| `data/tdb/*.tdb` | NIMS CPDDB 등에서 직접 내려받기 (재배포 금지) |

```bash
python -m src.import_user_db
```

```bash
python -m src.import_user_db --commit --by "승인자 이름" --basis "at.%"
```

## 사용법

### TDB 후보 검증 → 승인

1. 내려받은 TDB를 `data/tdb_candidates/`에 넣습니다.
2. 검증합니다. 읽기 오류 여부, 원소·상 목록, 상태도 그림, 보고서가 같은 폴더에 생깁니다.

```bash
python -m src.tdb_finder check data/tdb_candidates/NbSi.tdb --pair Nb Si
```

3. 그림을 원 논문의 상태도와 비교한 뒤, 맞으면 승인합니다. 파일이 `data/tdb/`로 복사되고 출처가 기록됩니다.

```bash
python -m src.tdb_finder approve data/tdb_candidates/NbSi.tdb --by "이름" --source "저자, 학술지, 연도, DOI" --terms "이용 조건"
```

### 조성 격자 계산

`config/grid_NbSi.json`의 `tdb_file`을 승인한 파일 이름으로 고친 뒤 실행합니다.
중간에 멈춰도 다시 실행하면 이어서 계산합니다.

```bash
python -m src.build_grid config/grid_NbSi.json
```

### 문헌 데이터 점검

```bash
python -m src.literature_schema check data/literature.csv
```

### 자동 점검 (코드가 제대로 동작하는지)

```bash
python -m pytest -q tests
```

## 폴더 구조

```
config/        격자 계산 범위 설정 (원소 추가는 여기서)
data/tdb/      승인된 열역학 DB (출처는 data/tdb/README.md)
data/tdb_candidates/  검증 전 TDB 후보와 검증 보고서
data/literature.csv   승인된 문헌 물성 데이터 (모델 학습용)
data/extracted_pending.csv  승인 대기 중인 추출 데이터 (학습에 쓰지 않음)
src/           계산·보간·검증 코드
tests/         자동 점검
```

## 한계 (현재)

- 상 구성은 **평형 계산** 결과입니다. 실제 시편(주조, 단시간 열처리)의 상분율은 공정에 따라 다를 수 있습니다.
- 계산 결과의 정확도는 사용한 TDB의 품질에 달려 있습니다.
- 슬라이더 값은 미리 계산한 격자 사이를 보간한 값이라, 상 경계 근처에서는 격자 간격만큼의 오차가 있을 수 있습니다.
