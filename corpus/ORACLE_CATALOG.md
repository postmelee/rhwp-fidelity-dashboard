# 기존 oracle 카탈로그 재사용

조사한 upstream snapshot: [`67b4ff8d3a55e5bb50c46a44315de749a4ef07a7`](https://github.com/edwardkim/rhwp/tree/67b4ff8d3a55e5bb50c46a44315de749a4ef07a7/tools/oracle_public).

이 프로젝트의 4개 기여자 페어는 기존 Print PDF를 사용합니다. corpus 확장 시에는 별도 이름 매칭을 만들지 않고 upstream `oracle_resolver.py`와 `fatten_catalog.py`를 그대로 실행합니다. `Oracle catalog audit` Actions workflow는 전체 snapshot을 읽기 전용으로 checkout하고 upstream 테스트와 재생성을 실행하며, 공개 로그에는 집계 개수만 남깁니다. 원본, PDF, 근접 후보 목록은 artifact나 Pages로 게시하지 않습니다.

## 저장된 보고서는 현재 inventory가 아닐 수 있습니다

같은 snapshot에 체크인된 산출물도 서로 다릅니다.

| 산출물 | 링크/쌍 | 짝 있는 문서 | 미매칭 문서 | 미사용 PDF |
| --- | ---: | ---: | ---: | ---: |
| `oracle_pairs.json` | 931 | 518 | 399 | — |
| `reports/coverage_matrix.md` | 1,030 | 565 | 414 | 216 |
| `catalogs/unmatched.json` | — | — | 400 | — |
| `catalogs/unused_oracle_pdfs.json` | — | — | — | 213 |

이 숫자는 기존 파일의 내용이며 새 실측 정확도나 최신 전수 결과가 아닙니다. 생성기 재실행 결과와 구분해야 합니다. `targetPairCount:269`도 목표 참고값이고 실제 개수가 아닙니다.

## 실제 재생성 검증

[Oracle catalog audit run 43746255362](https://github.com/postmelee/rhwp-fidelity-dashboard/actions/runs/43746255362)가 2026-11-15 UTC에 성공했습니다. upstream resolver 21개 테스트와 fatten catalog 3개 테스트를 통과한 뒤 전체 고정 snapshot에서 재생성했습니다.

| 항목 | 재생성 결과 |
| --- | ---: |
| 샘플 문서 (matched + unmatched) | 1,719 |
| 짝 있는 문서 | 996 |
| 문서×PDF 링크 | 1,434 |
| 미매칭 문서 | 723 |
| 스캔한 PDF 후보 | 3,870 |
| 미사용 PDF | 2,495 |
| CHEAP_OK 링크 | 1,432 |
| PAGE_ERROR 링크 | 2 |

버전별 링크는 2018: 0, 2020: 861, 2022: 376, 2024: 197입니다. 이 수치는 기본 resolver 범위의 이름/경로 매칭과 PDF 구조 검사 결과이며 독립 Print·허가·시각 충실도 검증 수가 아닙니다. 미사용 PDF에는 이름/경로/버전 규칙에 맞지 않는 기존 자료가 포함되므로 723개를 그대로 신규 인쇄 수로 해석하지 않습니다.

## 기존 도구의 범위

- resolver는 기본적으로 `samples/`와 `pdf/`를 상대 하위 경로·파일명·2018/2020/2022/2024 버전 규칙으로 연결합니다. 한 문서의 여러 한컴 버전 PDF는 별도 링크로 유지하며 HWP/HWPX suffix를 구별합니다.
- `mydocs/pr/assets/`의 별도 페어는 기본 resolver 범위 밖입니다. 따라서 현재 4개 corpus의 angle 페어가 resolver에 없다는 이유로 정답지 누락이라고 판단하지 않습니다.
- `fatten_catalog.py`는 resolver를 다시 사용해 버전/형식/문서군 coverage, unmatched와 near-miss PDF, unused PDF 목록을 만듭니다.
- `cheap_sweep`의 PDF signature, 바이트 수, 쪽수 및 `CHEAP_OK` 판정은 렌더 충실도나 독립 Print 생성 증명이 아닙니다. 이 생성기는 rhwp 렌더를 하지 않습니다.
- `multiver_index.py`는 stem×한컴 버전으로 PDF를 모으고 쪽수를 비교합니다. 버전을 추정할 수 없으면 unknown, LFS pointer·PDF 파싱 실패 등은 page_count=null로 남깁니다. 픽셀 비교는 수행하지 않습니다.
- `page_smoke.py`는 별도 쪽수 비교 도구입니다. silhouette 측정과 구별합니다.

## 부족한 정답지만 생성하려면

1. 같은 immutable upstream snapshot에서 resolver와 fatten catalog를 다시 생성합니다.
2. unmatched 문서와 unused/near-miss PDF를 함께 검토합니다. 상대 경로 차이·버전 suffix·별도 assets 위치 때문에 연결되지 않았을 수 있으므로, unmatched를 바로 인쇄 대기열로 사용하지 않습니다.
3. 기존 PDF가 있으면 실제 문서 짝, 독립 Hancom **Print** 출처, 한컴 버전/compat, SHA-256, 페이지 수, font 계약과 측정/metadata 사용 근거를 확인해 재사용합니다. catalog 자체에는 이 승인·출처 검증이 충분하지 않습니다.
4. 위 확인 뒤에도 필요한 golden만 사용자의 Hancom PDF export MCP 후보로 남깁니다. 새 출력 전에 원하는 버전과 font 환경을 고정하고 Print receipt, 원본/PDF hash를 보존해야 합니다.
5. 검증된 쌍만 dashboard manifest에 등록하고 smoke 후 전체 승인 corpus를 측정합니다. 별도 Hancom 버전과 engine SHA 결과를 섞어 하나의 점수로 만들지 않습니다.

이 corpus는 기존 Print PDF를 재사용합니다. raw 자료의 공개 재배포 허가를 추정하지 않습니다.

## MCP refresh 결과의 검증

기존 `refresh_oracle_pdfs.py`는 canonical PDF가 있으면 현재 원본 hash와의 일치를 보장하지 않은 채 건너뛸 수 있고, MCP preflight 거부가 경고와 종료 코드 0으로 끝날 수 있다는 별도 검토 결과가 있습니다. 이 dashboard는 해당 refresh를 실행하지 않습니다. 향후 사용하더라도 프로세스 exit 0만 성공으로 간주하지 말고 문서별 성공·거부·실패·누락을 대조하고, 실제 한컴 엔진/Print 경로·유효한 PDF·원본 hash·출력 hash를 독립 확인해야 합니다.
