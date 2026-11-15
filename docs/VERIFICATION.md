# 실행 검증 기록

이 기록은 실제 Actions와 immutable ledger를 구분합니다. 테스트용 이미지 비교는 엔진의 fidelity 점수가 아닙니다.

- 초기 4개 페어 실측 run [43743368459](https://github.com/postmelee/rhwp-fidelity-dashboard/actions/runs/43743368459): producer 단계 43분 8초 후 종료. 빌드는 생성됐지만 Native/WASM 모두 smoke 실패하여 점수 없음. [실패 ledger](https://github.com/postmelee/rhwp-fidelity-dashboard/blob/data/records/43743368459-1.json)를 보존했습니다. 초기에 단계별 시간을 기록하지 않아 43분을 Native/WASM별로 정확히 나눌 수 없습니다. 명령 timeout으로 종료된 실행은 아닙니다.
- 원인 재현 [43748233448](https://github.com/postmelee/rhwp-fidelity-dashboard/actions/runs/43748233448): 잘못 고정한 pypdfium2 4.30.0이 upstream의 `with PdfDocument(...)` API를 지원하지 않아 TypeError 발생. `fill_rect` 인자 순서도 upstream이 사용하는 5.x와 다릅니다.
- upstream [Visual Sweep guide](https://github.com/edwardkim/rhwp/blob/c9095c5f67632e6721e800ccc7fb43ea49d26682/mydocs/manual/verification/visual_sweep_guide.md)의 pypdfium2 5.13.0으로 수정했습니다.
- 수정된 실제 PDF raster·manifest 계약 테스트 [43748555879](https://github.com/postmelee/rhwp-fidelity-dashboard/actions/runs/43748555879)는 통과했습니다. PDF preflight를 고비용 엔진 빌드 앞으로 옮겼습니다.
- 동일한 잘못된 의존성으로 실행 중이던 [43747020016](https://github.com/postmelee/rhwp-fidelity-dashboard/actions/runs/43747020016)은 수정 계약 테스트 성공 후 중단했습니다. 측정 unavailable 상태를 기록한 publisher는 성공했고 2026-11-15 18:49 UTC에 공개 HTML과 summary JSON의 정확한 일치를 확인했습니다. 이 실행은 실측 성공이 아닙니다.
- 첫 publisher는 업로드 직후 Pages artifact 목록에서 해당 파일을 찾지 못해 실패했습니다. 정확한 artifact ID가 목록에 나타날 때까지 기다리고, 재배포 시 Pages artifact를 교체할 수 있게 수정했습니다. immutable ledger는 덮어쓰지 않습니다.

실제 release 빌드는 upstream 설정을 유지합니다: Native release의 LTO 및 codegen-units=1, fresh WASM release/wasm-opt. 빠른 dev 빌드 결과로 대체하지 않습니다. 개별 producer 명령 제한은 60분, 전체 측정 job은 180분이며 실패/timeout은 점수로 바꾸지 않습니다.

수정된 전체 실측·배포 실행은 [43748870086](https://github.com/postmelee/rhwp-fidelity-dashboard/actions/runs/43748870086)입니다. 완료 상태와 수치는 [data branch](https://github.com/postmelee/rhwp-fidelity-dashboard/tree/data/records) 및 [공개 dashboard](https://postmelee.github.io/rhwp-fidelity-dashboard/)의 JSON을 기준으로 확인합니다. 정적 README에 테스트 숫자나 과거 점수를 최신 실측처럼 복사하지 않습니다.

Pages artifact 지연에 대한 단위 테스트는 지연 후 정확한 ID 노출, 잘못된 ID·만료·중복 거부, 제한 내 미노출 실패를 검증합니다. 새 측정이 필요 없는 경로는 `publish --reuse`로 ledger를 읽어 다시 배포하며 새 측정 기록을 만들지 않습니다.

## 첫 정상 실측과 배포 복구

[43748870086의 immutable 결과](https://github.com/postmelee/rhwp-fidelity-dashboard/blob/data/records/43748870086-1.json)는 Native와 WASM 각각 4개 문서·4쪽 complete입니다. engine은 `c9095c5f67632e6721e800ccc7fb43ea49d26682` (v0.9.0), producer는 `2a9baa8a50c8529354620b1de465e1bd83ff77f0`입니다.

| 기존 Print 페어 | Native raw silhouette | WASM raw silhouette |
| --- | ---: | ---: |
| re-03-latin-only-hancom | 100 | 100 |
| angle-2400 | 100 | 100 |
| pic-crop-01 | 99.99756 | 94.65178 |
| shape-group-02 | 100 | 100 |

두 backend 모두 median 100, below90 0, page-count mismatch 0입니다. P10/min은 Native 99.99756, WASM 94.65178입니다. 이 값은 해당 4개 페어·원래 실행 환경의 96dpi/2px 실루엣 보조값이며 전체 문서 호환 정확도가 아닙니다. 원본 숫자와 environment/build fingerprint는 위 JSON을 확인하세요.

실제 단계 시간: PDF preflight 약 0.16초, Native release build 1425.92초, WASM release build 1082.71초, npm dependency 설치 10.46초. smoke와 본 측정은 약 57초였습니다. 긴 실행 시간은 주로 두 cold release 빌드였으며 timeout은 없었습니다.

이 실행의 측정은 성공했지만 Pages 서비스가 artifact 인식 이후 `deployment_failed`를 반환했습니다. 상태 API의 상세 error는 null이어서 정확한 서버 내부 원인은 단정할 수 없습니다. Pages 표준 GNU tar 형식과 `upload-artifact v4`의 고정 SHA를 사용한 경로로 복구했습니다.

[재측정 없는 ledger 배포 43753904638](https://github.com/postmelee/rhwp-fidelity-dashboard/actions/runs/43753904638)는 37개 테스트 및 `publish --reuse` 후 2026-11-15 19:42 UTC에 공개 HTML과 정확한 summary JSON 일치를 확인했습니다. 이 작업은 measurement artifact 대신 durable data branch를 읽었습니다. 진단·복구용 일회성 workflow와 특정 이전 run을 중단하는 actions-write job은 검증 뒤 main에서 제거했습니다. 상시 배포는 Fidelity workflow가 담당합니다.

## 재시도 정책 반영 후 전체 실측

[43753904763](https://github.com/postmelee/rhwp-fidelity-dashboard/actions/runs/43753904763)은 두 backend 각각 4개 문서·4쪽 complete로 완료됐고, publisher가 2026-11-15 20:26 UTC에 공개 HTML과 정확한 summary JSON의 일치를 검증했습니다. [별도 immutable 기록](https://github.com/postmelee/rhwp-fidelity-dashboard/blob/data/records/43753904763-1.json)에 원래 측정 시각과 환경을 보존합니다. 점수는 위 첫 정상 실측과 같았으며 이를 새 환경과의 일반적인 동등성으로 해석하지 않습니다.

이번 단계 시간은 Native release build 1222.16초, WASM release build 999.83초, browser dependency 설치 6.74초입니다. 모든 문서의 smoke 및 full 측정은 exit 0이었고 timeout은 없었습니다.

Canvas2D·Skia 비교 화면은 같은 실행의 완료·쪽수 일치 페어만 연결합니다. 누락 페이지를 0으로 채우지 않는 회귀 테스트와 실제 HTML 생성 검증을 포함한 [Checks 43756652817](https://github.com/postmelee/rhwp-fidelity-dashboard/actions/runs/43756652817)에서 39개 단위 테스트, actionlint, 페이지 build와 HTTP smoke가 통과했습니다.
