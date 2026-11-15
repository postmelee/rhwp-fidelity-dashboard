# 실행 검증 기록

이 기록은 실제 Actions와 immutable ledger를 구분합니다. 테스트용 이미지 비교는 엔진의 fidelity 점수가 아닙니다.

- 초기 4개 페어 실측 run [43743368459](https://github.com/postmelee/rhwp-fidelity-dashboard/actions/runs/43743368459): producer 단계 43분 8초 후 종료. 빌드는 생성됐지만 Native/WASM 모두 smoke 실패하여 점수 없음. [실패 ledger](https://github.com/postmelee/rhwp-fidelity-dashboard/blob/data/records/43743368459-1.json)를 보존했습니다. 초기에 단계별 시간을 기록하지 않아 43분을 Native/WASM별로 정확히 나눌 수 없습니다. 명령 timeout으로 종료된 실행은 아닙니다.
- 원인 재현 [43748233448](https://github.com/postmelee/rhwp-fidelity-dashboard/actions/runs/43748233448): 잘못 고정한 pypdfium2 4.30.0이 upstream의 `with PdfDocument(...)` API를 지원하지 않아 TypeError 발생. `fill_rect` 인자 순서도 upstream이 사용하는 5.x와 다릅니다.
- upstream [Visual Sweep guide](https://github.com/edwardkim/rhwp/blob/c9095c5f67632e6721e800ccc7fb43ea49d26682/mydocs/manual/verification/visual_sweep_guide.md)의 pypdfium2 5.13.0으로 수정했습니다.
- 수정된 실제 PDF raster·manifest 계약 테스트 [43748555879](https://github.com/postmelee/rhwp-fidelity-dashboard/actions/runs/43748555879)는 통과했습니다. PDF preflight를 고비용 엔진 빌드 앞으로 옮겼습니다.
- 동일한 잘못된 의존성으로 실행 중이던 [43747020016](https://github.com/postmelee/rhwp-fidelity-dashboard/actions/runs/43747020016)은 수정 계약 테스트 성공 후 중단했습니다. 측정 unavailable 상태를 기록한 publisher는 성공했고 2026-11-15 18:49 UTC에 공개 HTML과 summary JSON의 정확한 일치를 확인했습니다. 이 실행은 실측 성공이 아닙니다.
- 첫 publisher는 업로드 직후 Pages artifact 목록에서 해당 파일을 찾지 못해 실패했습니다. 업로드·배포를 같은 SHA 고정 uploader 경로로 맞추고 정확한 artifact ID가 목록에 나타날 때까지 기다리며, 재배포 시 Pages artifact를 교체할 수 있게 수정했습니다. immutable ledger는 덮어쓰지 않습니다.

실제 release 빌드는 upstream 설정을 유지합니다: Native release의 LTO 및 codegen-units=1, fresh WASM release/wasm-opt. 빠른 dev 빌드 결과로 대체하지 않습니다. 개별 producer 명령 제한은 60분, 전체 측정 job은 180분이며 실패/timeout은 점수로 바꾸지 않습니다.

수정된 전체 실측·배포 실행은 [43748870086](https://github.com/postmelee/rhwp-fidelity-dashboard/actions/runs/43748870086)입니다. 완료 상태와 수치는 [data branch](https://github.com/postmelee/rhwp-fidelity-dashboard/tree/data/records) 및 [공개 dashboard](https://postmelee.github.io/rhwp-fidelity-dashboard/)의 JSON을 기준으로 확인합니다. 정적 README에 테스트 숫자나 과거 점수를 최신 실측처럼 복사하지 않습니다.

Pages artifact 지연에 대한 단위 테스트는 지연 후 정확한 ID 노출, 잘못된 ID·만료·중복 거부, 제한 내 미노출 실패를 검증합니다. 새 측정이 필요 없는 경로는 `publish --reuse`로 ledger를 읽어 다시 배포하며 새 측정 기록을 만들지 않습니다.
