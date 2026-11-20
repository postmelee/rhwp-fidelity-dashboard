# 아키텍처와 신뢰 경계

1. **resolve**는 6시간마다 GitHub REST stable release 목록을 끝까지 페이지네이션하고 draft/prerelease를 제외합니다. 최신 안정 릴리즈에 해당 identity의 시도가 없으면 먼저 선택합니다. 그다음 과거 미시도 릴리즈를 published time/id 순서로 처리합니다. 과거 unsupported release도 누락시키지 않고 실패/미지원 결과를 남깁니다. 미측정 release를 실패 재시도보다 우선합니다. 모든 release에 기록이 있으면 failed/partial 중 가장 오래전에 시도한 항목을 다시 측정하며, 같은 immutable identity의 보존된 시도가 총 3회에 이르면 자동 재시도를 멈춥니다. 완주한 quality alert는 실행 실패로 재시도하지 않습니다.
2. 이미 관측한 tag도 actual commit까지 다시 해석합니다. annotated tag chain을 지원하며 재태깅된 SHA는 별도 기록입니다. 수동 tag/40자리 SHA는 재시도할 수 있습니다. main push는 기존 원장으로 Pages만 갱신합니다. 일정 실행과 수동 실행은 측정 workflow가 담당합니다.
3. **measure**는 쓰기 권한 없는 별도 runner에서 `edwardkim/rhwp` **전체 소스**를 exact commit SHA로 checkout합니다. Visual Sweep 일부 파일을 떼어 복사하지 않습니다. 같은 checkout에서 Native CLI와 fresh WASM을 빌드합니다.
4. 각 문서/backend의 1페이지 smoke가 완료되면 전쪽을 새 출력 디렉터리에서 측정합니다. Native와 WASM 각각 독립 PDF와 비교하며 서로를 golden으로 사용하지 않습니다.
5. **record**는 새 trusted checkout에서 JSON whitelist를 검증하고 run ID/attempt별 기록을 `data` branch에 append합니다. 동일 기록의 다른 내용 덮어쓰기를 거부합니다. upstream HTML, 이미지, 문서, 폰트, render tree 및 raw 진단 파일은 배포하지 않습니다.
6. **Pages** workflow는 원장 읽기와 배포 권한만 가지고 사이트를 생성합니다. main push와 Pages 수동 실행은 이 경로만 실행합니다. Fidelity도 측정을 기록한 뒤 또는 재사용할 때 같은 게시 workflow를 호출합니다. ledger 저장 후 Pages가 실패한 경우 다음 poll이 재측정 없이 배포를 복구합니다. 14일 artifact는 전달 수단이고 영구 history는 data branch입니다.

측정 producer fingerprint는 core, adapter 및 Fidelity의 measure job 정의를 해시합니다. 사이트, Pages 배포, 릴리즈 선택 변경은 측정 identity에 영향을 주지 않습니다. 한 개의 검증된 기존 fingerprint는 해당 producer 내용과 동일한 새 fingerprint로 선택 단계에서만 해석합니다. 예전 JSON의 fingerprint와 시도 수는 보존됩니다.

외부 저장소 release/workflow_run 이벤트가 이 저장소로 직접 온다고 가정하지 않습니다. PR artifact 수집은 구현하지 않았으며 devel push마다 renderer CI가 있다고 가정하지 않습니다.


## 보안

Actions commit SHA pin, checkout `persist-credentials:false`, 최소 job 권한과 분리된 Pages OIDC를 사용합니다. ref를 환경변수로 전달하고 shell에 삽입하지 않습니다. tag chain, 경로 이탈/symlink, 고정 asset origin과 hash, asset당 최대 32MiB와 결과 JSON 최대 8MB, 타입·범위·NaN, 중복/누락 페이지 및 public field whitelist를 검사합니다. data branch를 코드로 checkout하거나 실행하지 않습니다.

upstream의 현재 contributor gate 결과를 새 측정으로 복사하지 않습니다. 이 dashboard의 producer와 실제 실행 결과만 사용합니다. 기존 자료는 새 Hancom 인쇄 없이 재사용합니다. 전체 workflow 취소 또는 publisher 인프라 장애는 실측 성공으로 표시하지 않습니다.


[운영](OPERATIONS.md) · [측정 방법](METHODOLOGY.md) · [문서 목록](README.md)
