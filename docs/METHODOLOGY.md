# 측정 방법과 결과 해석

- 원본/PDF snapshot: `67b4ff8d3a55e5bb50c46a44315de749a4ef07a7`의 contributor catalog. 측정 엔진 SHA는 매 실행 별도로 resolve하므로 corpus 파일 버전과 혼동하지 않습니다.
- Native: `cargo build --locked --release --bin rhwp --features native-skia`.
- WASM: upstream `scripts/wasm-pack-locked.sh --target web --release`; `npm ci --prefix rhwp-studio`.
- Fontconfig/Freetype, Poppler, Pillow, PDFium, fonttools, Rust/WASM, Node/Chrome을 사용합니다. 실제 실행 환경·설치 및 공급 font inventory, native/WASM/lockfile fingerprint를 보존합니다. 측정 후 environment fingerprint에는 upstream의 실제 font_supply/native_webfont_fallback provenance와 export receipt hash도 포함합니다.
- CLI flag static probe 및 runtime `--help`를 확인합니다. `--file-target KEY DOC PDF`, `--out`, `--rasterizer png`, `--silhouette-only`, `--dpi 96`, `--compat`를 명시합니다. WASM에는 `--wasm-pkg`를 전달합니다.
- 현재 4개 PDF는 `compat=2022`입니다. 2024 golden을 추가하면 반드시 `2024`를 명시합니다.
- 현재 font environment는 upstream 기여자 검사와 동일하게 **명시적 substitution 없음**이며 공개 웹폰트를 공급합니다. `font_environment.path=null`이 이 계약을 나타냅니다. 검증된 별도 mapping을 등록하면 `--font-environment`를 전달할 수 있습니다.
- 공개 WOFF는 upstream과 같은 fonttools 방식으로 실행기에서 결정적으로 TTF container로 변환합니다. 원본 SHA, 변환 도구 버전, 변환 후 font inventory를 구분합니다.
- `--resume`나 부분 결과 cache를 사용하지 않습니다. Git diff는 측정을 대체하지 않습니다. source/protocol/corpus/font/adapter가 다른 결과를 최신 전체 점수로 합치지 않습니다.


## 지표 해석

Golden fidelity, backend parity, PR regression은 별개입니다. 이 페이지의 점수는 첫 번째뿐이며 나머지는 unavailable입니다. 향후 PR artifact를 수집하더라도 실제 head와 synthetic merge tree, run/attempt 및 검증 출처를 확인하기 전에는 golden 결과에 넣지 않습니다.

Raw silhouette는 96dpi, RGB 232 ink threshold와 2px dilation tolerance의 모양 겹침 보조값입니다. 의미 정확도, 미세 수식/글자 검증이나 Hancom 완전 호환 인증이 아닙니다. 단일 정확도% 대신 measured/target/failed/skipped 문서·페이지, unmeasured pages, page-count mismatch, median/nearest-rank P10/min/below90를 표시합니다. 각 run/backend 내 페이지 단위 집계입니다.

exit 1은 완전한 manifest·페이지 목록·PDF 쪽수 계약이 확인되면 quality alert로 보존합니다. 그 외 실행 실패는 failed/partial입니다. 누락 데이터는 0이나 100으로 대체하지 않습니다. latest attempted와 last complete는 별도로 표시합니다.

현재 corpus hash에 해당하는 실행만 화면에 보이고, 이전 빈 corpus 등의 기록은 data branch에 보존합니다. 재배포는 원래 시각·환경의 과거 결과를 다시 보여 줄 뿐이며 현재 runner/build와 동등하다는 뜻이 아닙니다. 현재 환경에서 다시 실측하려면 workflow_dispatch에 tag 또는 SHA를 명시하세요. identity의 선언된 코드·corpus·font 계약과 실제 실행 후 environment/build fingerprint를 구별합니다. JSON은 engine/dashboard SHA, source ref/type/time, protocol, corpus/font/adapter fingerprint와 실제 environment/build fingerprint를 제공합니다.


## Canvas2D와 Skia 비교 화면

WASM Canvas2D는 측정 SHA에서 새로 빌드한 browser Canvas2D 경로이며 Native Skia는 native-skia feature로 빌드한 CLI 경로입니다. 같은 브라우저의 렌더러만 교체하는 실험이 아니므로 실행 환경과 글꼴 공급 차이가 영향을 줄 수 있습니다.

비교표는 같은 immutable 실행의 동일 원본·golden·페이지·compat·font 계약·protocol만 사용합니다. 두 문서 모두 complete이고 rendered/golden/manifest 쪽수가 맞아야 나란히 점수를 표시합니다. Skia minus Canvas2D는 두 Hancom 대비 silhouette 점수의 차이이며 두 렌더러 이미지의 직접 유사도 또는 성숙도 비율이 아닙니다. 미완료·쪽수 불일치 결과는 비교표에서 unavailable이고 개별 상세에는 남습니다.

각 실행의 요약과 문서·페이지 상세는 열 제목으로 정렬할 수 있습니다. 쪽수 일치율은 쪽수를 아는 문서 중 같은 문서의 비율이고, 쪽수 미상 문서를 별도로 표시합니다. 직접 backend parity와 PR regression, 이미지 비교는 아직 제공하지 않습니다. 허가 없는 원본 및 이미지는 게시하지 않습니다.

[운영](OPERATIONS.md) · [문서 목록](README.md)
