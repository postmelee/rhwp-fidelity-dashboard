# rhwp fidelity dashboard

독립 Hancom Print PDF를 기준으로 Native Skia와 fresh WASM Canvas2D를 각각 측정하는 별도 non-fork 저장소입니다. 기존 rhwp와 preview lab은 변경하지 않습니다.

현재 corpus는 upstream이 기여자 공통 검사로 지정한 **4개 문서, 각 1쪽**입니다. 원본/PDF를 다시 만들거나 이 저장소에 재배포하지 않습니다. 고정 commit에서 기존 파일을 임시 다운로드하고 SHA-256을 확인합니다. 공개 웹폰트도 실행기에만 공급합니다. Pages와 data branch에는 검증된 숫자 및 허용 메타데이터만 기록합니다. [재사용 근거와 4개 페어](corpus/PROVENANCE.md)를 확인하세요. 실행이 완료되지 않은 결과는 unavailable/failed/partial이며 점수를 만들지 않습니다.

[실제 검증 기록과 초기 실패 수정 내역](docs/VERIFICATION.md)을 확인할 수 있습니다. PDFium은 upstream 계약과 같은 **pypdfium2 5.13.0**으로 고정하고, 실제 PDF raster preflight를 엔진 빌드 전에 수행합니다.

## 구조와 자동화

1. **resolve**는 6시간마다 GitHub REST stable release 목록을 끝까지 페이지네이션하고 draft/prerelease를 제외합니다. published time/id 순서로 아직 측정하지 않은 가장 오래된 항목 하나를 선택합니다. 중단 중 여러 release가 생겨도 다음 poll들이 backlog를 순서대로 처리합니다. 과거 unsupported release도 누락시키지 않고 실패/미지원 결과를 남깁니다. 미측정 release를 실패 재시도보다 우선합니다. 모든 release에 기록이 있으면 failed/partial 중 가장 오래전에 시도한 항목을 다시 측정하며, 같은 immutable identity의 보존된 시도가 총 3회에 이르면 자동 재시도를 멈춥니다. 완주한 quality alert는 실행 실패로 재시도하지 않습니다.
2. 이미 관측한 tag도 actual commit까지 다시 해석합니다. annotated tag chain을 지원하며 재태깅된 SHA는 별도 기록입니다. 수동 tag/40자리 SHA는 재시도할 수 있습니다. main push는 최신 stable을 확인하며, schedule은 과거 backlog를 처리합니다.
3. **measure**는 쓰기 권한 없는 별도 runner에서 `edwardkim/rhwp` **전체 소스**를 exact commit SHA로 checkout합니다. Visual Sweep 일부 파일을 떼어 복사하지 않습니다. 같은 checkout에서 Native CLI와 fresh WASM을 빌드합니다.
4. 각 문서/backend의 1페이지 smoke가 완료되면 전쪽을 새 출력 디렉터리에서 측정합니다. Native와 WASM 각각 독립 PDF와 비교하며 서로를 golden으로 사용하지 않습니다.
5. **publish**는 새 trusted checkout에서 JSON whitelist를 검증하고 run ID/attempt별 기록을 `data` branch에 append합니다. 동일 기록의 다른 내용 덮어쓰기를 거부합니다. upstream HTML, 이미지, 문서, 폰트, render tree 및 raw 진단 파일은 배포하지 않습니다.
6. **측정 필요와 배포 필요는 독립입니다.** 새 측정이 필요 없어도 ledger로 사이트를 다시 build/deploy합니다. ledger 저장 후 Pages가 실패한 경우 다음 poll이 재측정 없이 배포를 복구합니다. 14일 artifact는 전달 수단이고 영구 history는 data branch입니다.

외부 저장소 release/workflow_run 이벤트가 이 저장소로 직접 온다고 가정하지 않습니다. PR artifact 수집은 구현하지 않았으며 devel push마다 renderer CI가 있다고 가정하지 않습니다.

## 사용

Pages Source는 **GitHub Actions**로 설정합니다. Actions의 contents/pages write 및 OIDC가 허용되어야 합니다.

```sh
gh workflow run fidelity.yml -R postmelee/rhwp-fidelity-dashboard -f ref=v0.9.0
gh workflow run fidelity.yml -R postmelee/rhwp-fidelity-dashboard -f ref=67b4ff8d3a55e5bb50c46a44315de749a4ef07a7
gh run list -R postmelee/rhwp-fidelity-dashboard
```

ref를 비우면 stable backlog를 처리합니다. 실패한 같은 계약을 3회 제한 이후에도 다시 측정하려면 ref를 지정합니다. 수동 실행은 항상 허용되며 보존된 시도 수에는 포함됩니다. 제한은 data branch에 보존된 측정 시도를 기준으로 하므로 ledger 기록 자체가 실패한 인프라 장애는 Actions에서 별도로 확인해야 합니다. 재배포만 필요하면 다음 poll이 자동으로 처리합니다. schedule 자체가 GitHub에서 비활성화되거나 resolver가 네트워크 오류로 실패하면 해당 Actions 상태를 확인해야 합니다.

Python 3.12 이상에서:

```sh
python3 -m unittest discover -s tests -v
python3 scripts/pipeline.py build --ledger empty-ledger --out site
python3 -m http.server 8000 --directory site
# 다른 터미널
python3 scripts/http_smoke.py
```

Checks workflow가 단위 테스트, actionlint, 페이지 build와 HTTP smoke를 수행합니다. 단위 테스트의 숫자는 실제 렌더 점수가 아닙니다.

## 측정 계약

- 원본/PDF snapshot: `67b4ff8d3a55e5bb50c46a44315de749a4ef07a7`의 contributor catalog. 측정 엔진 SHA는 매 실행 별도로 resolve하므로 corpus 파일 버전과 혼동하지 않습니다.
- Native: `cargo build --locked --release --bin rhwp --features native-skia`.
- WASM: upstream `scripts/wasm-pack-locked.sh --target web --release`; `npm ci --prefix rhwp-studio`.
- Fontconfig/Freetype, Poppler, Pillow, PDFium, fonttools, Rust/WASM, Node/Chrome을 사용합니다. 실제 실행 환경·설치 및 공급 font inventory, native/WASM/lockfile fingerprint를 보존합니다. 측정 후 environment fingerprint에는 upstream의 실제 font_supply/native_webfont_fallback provenance와 export receipt hash도 포함합니다.
- CLI flag static probe 및 runtime `--help`를 확인합니다. `--file-target KEY DOC PDF`, `--out`, `--rasterizer png`, `--silhouette-only`, `--dpi 96`, `--compat`를 명시합니다. WASM에는 `--wasm-pkg`를 전달합니다.
- 현재 4개 PDF는 `compat=2022`입니다. 2024 golden을 추가하면 반드시 `2024`를 명시합니다.
- 현재 font environment는 upstream 기여자 검사와 동일하게 **명시적 substitution 없음**이며 공개 웹폰트를 공급합니다. `font_environment.path=null`이 이 계약을 나타냅니다. 검증된 별도 mapping을 등록하면 `--font-environment`를 전달할 수 있습니다.
- 공개 WOFF는 upstream과 같은 fonttools 방식으로 실행기에서 결정적으로 TTF container로 변환합니다. 원본 SHA, 변환 도구 버전, 변환 후 font inventory를 구분합니다.
- `--resume`나 부분 결과 cache를 사용하지 않습니다. Git diff는 측정을 대체하지 않습니다. source/protocol/corpus/font/adapter가 다른 결과를 최신 전체 점수로 합치지 않습니다.

## 읽는 방법

Golden fidelity, backend parity, PR regression은 별개입니다. 이 페이지의 점수는 첫 번째뿐이며 나머지는 unavailable입니다. 향후 PR artifact를 수집하더라도 실제 head와 synthetic merge tree, run/attempt 및 검증 출처를 확인하기 전에는 golden 결과에 넣지 않습니다.

Raw silhouette는 96dpi, RGB 232 ink threshold와 2px dilation tolerance의 모양 겹침 보조값입니다. 의미 정확도, 미세 수식/글자 검증이나 Hancom 완전 호환 인증이 아닙니다. 단일 정확도% 대신 measured/target/failed/skipped 문서·페이지, unmeasured pages, page-count mismatch, median/nearest-rank P10/min/below90를 표시합니다. 각 run/backend 내 페이지 단위 집계입니다.

exit 1은 완전한 manifest·페이지 목록·PDF 쪽수 계약이 확인되면 quality alert로 보존합니다. 그 외 실행 실패는 failed/partial입니다. 누락 데이터는 0이나 100으로 대체하지 않습니다. latest attempted와 last complete는 별도로 표시합니다.

현재 corpus hash에 해당하는 실행만 화면에 보이고, 이전 빈 corpus 등의 기록은 data branch에 보존합니다. 재배포는 원래 시각·환경의 과거 결과를 다시 보여 줄 뿐이며 현재 runner/build와 동등하다는 뜻이 아닙니다. 현재 환경에서 다시 실측하려면 workflow_dispatch에 tag 또는 SHA를 명시하세요. identity의 선언된 코드·corpus·font 계약과 실제 실행 후 environment/build fingerprint를 구별합니다. JSON은 engine/dashboard SHA, source ref/type/time, protocol, corpus/font/adapter fingerprint와 실제 environment/build fingerprint를 제공합니다.

## 기존 전체 oracle 카탈로그

기존 upstream resolver·catalog 생성기를 재사용해 실제 audit를 실행했습니다. [재생성 결과, 범위와 누락 PDF 검토 절차](corpus/ORACLE_CATALOG.md)를 참고하세요. 기존 체크인 보고서의 수치는 서로 달랐으며, catalog 후보를 Print 출처나 공개 허가로 간주하지 않습니다.

## 추가 corpus

`corpus/manifest.json`의 실제 4개 항목을 schema 예제로 사용하세요. 원본과 독립 Hancom Print PDF의 실제 대응, source snapshot, SHA-256, 쪽수, compat, font 계약과 사용 근거를 먼저 확인해야 합니다. 이름이 비슷하거나 같은 저장소에 있다는 이유만으로 승인하지 않습니다.

`publication.approved`는 기록한 근거에 따른 측정 사용과 허용 metadata 게시만을 뜻합니다. `raw_files:false`가 필수이며 원본/폰트 재배포 허가로 확대하지 않습니다. font의 `usage_approved`도 실행기 사용 범위입니다. 이 프로젝트는 original document, PDF, font 파일을 배포하지 않습니다.

## 보안과 제한

Actions commit SHA pin, checkout `persist-credentials:false`, 최소 job 권한과 분리된 Pages OIDC를 사용합니다. ref를 환경변수로 전달하고 shell에 삽입하지 않습니다. tag chain, 경로 이탈/symlink, 고정 asset origin과 hash, asset당 최대 32MiB와 결과 JSON 최대 8MB, 타입·범위·NaN, 중복/누락 페이지 및 public field whitelist를 검사합니다. data branch를 코드로 checkout하거나 실행하지 않습니다.

upstream의 현재 contributor gate 결과를 새 측정으로 복사하지 않습니다. 이 dashboard의 producer와 실제 실행 결과만 사용합니다. 기존 자료는 새 Hancom 인쇄 없이 재사용합니다. 전체 workflow 취소 또는 publisher 인프라 장애는 실측 성공으로 표시하지 않습니다.

최초 구현의 클라우드 환경은 provisioning 실패로 사용할 수 없었고, 실제 GitHub Actions에서 테스트/build/HTTP smoke를 검증했습니다. renderer 실측 상태는 각 immutable 실행 JSON과 Actions 결과가 기준입니다.
