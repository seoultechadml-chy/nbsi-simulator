# 문헌 데이터 작성 안내 (`literature.csv`)

`literature.csv`는 물성 모델이 학습하는 **승인된 데이터**만 담는 파일입니다.
엑셀로 열어 편집해도 됩니다. 저장할 때는 **CSV UTF-8 (쉼표로 분리)** 형식을 고르세요.

- 한 줄에 시편 하나와 물성 시험 조건 하나를 적습니다.
  같은 시편을 주조 상태와 열처리 후로 각각 시험했으면 두 줄이 됩니다.
- 모르는 칸은 **비워 둡니다.** 추측해서 채우지 않습니다.
- 숫자 칸에는 숫자만 적습니다. `15 ± 2`는 `15`와 `2`로 나눠 `fracture_toughness_MPam05`와 `fracture_toughness_std`에 넣습니다.

## 열 설명

| 열 | 내용 | 예시 |
|---|---|---|
| `alloy_id` | 시편 이름. 논문에 쓰인 이름을 그대로 씁니다 | `Nb-16Si-22Ti` |
| `Nb` ~ `Fe` | 조성. 없는 원소는 0 또는 빈칸 | `62`, `16`, `22` |
| `composition_basis` | `at.% 공칭` / `at.% 실측` / `wt.% 공칭` / `wt.% 실측` 중 하나 | `at.% 공칭` |
| `process` | 제조 공정 | `아크용해`, `SPS`, `방향성응고` |
| `heat_treatment_temp_C` | 열처리 온도(°C). 주조 상태면 비우고 `process`에 `as-cast`를 함께 적습니다 | `1500` |
| `heat_treatment_time_h` | 열처리 시간(h) | `100` |
| `phase_fraction_measured` | 실측 상분율. `상:값; 상:값` 형식 | `Nbss:45; Nb5Si3:55` |
| `phase_fraction_basis` | 상분율 단위 | `vol.%`, `area.%` |
| `hardness_HV` | 비커스 경도 | `520` |
| `hardness_load_kgf` | 경도 시험 하중 | `0.5` |
| `compressive_strength_MPa` | 압축강도. 기준(항복/최대)이 다르면 `notes`에 적습니다 | `1800` |
| `fracture_toughness_MPam05` | 파괴인성 (MPa·m^0.5) | `12.5` |
| `fracture_toughness_std` | 표준편차 또는 ± 값 | `1.1` |
| `toughness_method` | 파괴인성 시험법 | `SENB`, `chevron notch`, `압입` |
| `test_temperature_C` | 물성 시험 온도. 상온이면 `25` | `25` |
| `source` | 논문 DOI 또는 `자체 측정` | `10.1016/j.intermet.xxxx` |
| `source_location` | 값이 나온 위치 | `p.5, Table 2` |
| `entry_method` | `자동 추출` / `직접 입력` / `파일 가져오기` | `직접 입력` |
| `approved_by`, `approved_date` | 승인자와 날짜 (YYYY-MM-DD) | `홍길동`, `2026-11-17` |
| `notes` | 그 밖의 메모 | |

## 파괴인성 데이터 주의점

- **시험법을 꼭 적어 주세요.** SENB, chevron notch, 압입법은 같은 재료에서도 값이 크게 다를 수 있습니다.
  모델이 시험법을 구분해 학습하거나 걸러 낼 수 있게 하려는 것입니다.
- 노치 형태(직선/쉐브론), 사전균열 여부 같은 정보는 `notes`에 적어 두면 나중에 쓸 수 있습니다.

## 점검 명령

파일을 고친 뒤 아래 명령을 실행하면 조성 합이 100이 아닌 행, 단위 미기재, 출처 없음 같은 문제를 알려 줍니다.
파일 내용은 바꾸지 않습니다.

```bash
python -m src.literature_schema check data/literature.csv
```

## 관련 파일

- `extracted_pending.csv`: 논문에서 자동으로 뽑았지만 아직 승인하지 않은 값. 학습에 쓰지 않습니다.
- `papers/graph_extraction_needed.csv`: 그래프에만 값이 있어 직접 읽어야 하는 논문·그림 목록.
