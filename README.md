# rhwp fidelity dashboard

독립적인 Hancom Print PDF를 기준으로 rhwp의 Native Skia와 fresh WASM Canvas2D를 각각 측정하는 별도 non-fork 저장소입니다. 기존 rhwp 및 preview lab은 수정하지 않습니다.

**현재 corpus는 비어 있습니다.** 공개 사용 허가, 원본 대응 관계, 독립 Hancom Print PDF와 실제 폰트 계약이 확인된 문서가 아직 없습니다. 최초 화면에는 empty/unavailable이 표시되며 정확도 숫자를 만들지 않습니다. 이 저장소의 테스트에 사용하는 숫자는 schema 단위 테스트용이며 실제 렌더 점수가 아닙니다.

## 구조

1. **resolve**: 6시간마다 GitHub REST `releases/latest`를 조회합니다. draft/prerelease를 거부하고 annotated tag를 최종 commit SHA까지 해석합니다. 수동 tag/40자리 SHA도 지원합니다. 외부 저장소 release/workflow_run 이벤트를 이 저장소가 직접 받는다고 가정하지 않습니다.
2. **measure**: 별도 읽기 전용 job이 `edwardkim/rhwp` 전체 소스를 exact SHA로 checkout합니다. `scripts/visual_sweep.py` 및 상대 import를 원래 위치에서 재사용합니다. upstream 코드를 실행하는 이 job에는 쓰기 권한, Pages OIDC, 저장소 secret을 공급하지 않습니다.
3. **publish**: 새로운 trusted checkout에서 숫자 schema를 검증하고 `data` branch에 run ID/attempt별 JSON을 append합니다. upstream HTML, 이미지, render tree, 로그를 배포하지 않습니다. 검증되지 않은 artifact는 미측정 상태로 처리합니다.
4. OIDC Pages가 검증된 정적 HTML/JSON만 배포합니다. artifact 14일 보존은 전달 수단일 뿐, history는 `data` branch에 계속 남습니다. 동일 이름의 서로 다른 내용으로 기존 결과를 덮어쓸 수 없습니다.

일반 push도 최초 배포와 adapter 변경 검증을 시작합니다. 동일 SHA/corpus/font/adapter/protocol의 release poll은 새 측정을 생략합니다. 이것은 이전 결과를 새 실행의 점수로 복제하는 cache가 아닙니다. 환경을 바꾸고 다시 측정하려면 수동 tag/SHA를 지정합니다. 재태깅은 SHA가 달라지므로 별도 기록을 남깁니다.

## 운영

GitHub Settings → Pages → Source를 **GitHub Actions**로 설정합니다. Actions와 Pages 쓰기 권한이 허용되어야 합니다. `github-pages` environment 보호 규칙이 있으면 해당 승인 절차가 적용됩니다.

```sh
gh workflow run fidelity.yml -R postmelee/rhwp-fidelity-dashboard -f ref=v0.9.0
gh workflow run fidelity.yml -R postmelee/rhwp-fidelity-dashboard -f ref=c9095c5f67632e6721e800ccc7fb43ea49d26682
gh run list -R postmelee/rhwp-fidelity-dashboard
```

수동 실행에서 ref를 비우면 latest stable release를 polling합니다. 실패한 동일 계약을 재시도하려면 ref를 명시합니다. 로컬 검증은 Python 3.12 이상에서 다음과 같습니다.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/pipeline.py build --ledger empty-ledger --out site
python3 -m http.server 8000 --directory site
# 다른 터미널
python3 scripts/http_smoke.py
```

Checks workflow는 단위 테스트, HTML build, HTTP smoke 및 actionlint를 실행합니다. renderer build/smoke/full은 corpus가 비어 있으면 실행하지 않습니다. 정적 CLI contract probe와 전체 source checkout만 수행합니다. 빈 데이터 배포 성공을 Native/WASM 렌더 성공으로 해석하지 않습니다.

## 최초 실제 측정 조건

`corpus/manifest.json`에 공개 허가된 원본과 그 원본에서 **독립적으로 생성한 Hancom Print PDF**만 등록합니다. upstream sample/PDF 파일 개수나 baseline manifest를 유효한 golden corpus로 간주하지 않습니다. 사용자 제보 원문, 상용 폰트, arbitrary upstream HTML/이미지는 추가하지 않습니다. 원본 및 PDF의 source/provenance/publication evidence도 공개 가능한 내용이어야 합니다.

문서 항목 schema:

```json
{
  "id": "approved-document",
  "document": {"path": "files/example.hwpx", "sha256": "<64 hex>", "source": "<approved source>", "provenance": "<original document history>"},
  "golden": {"path": "files/example.pdf", "sha256": "<64 hex>", "source": "<approved source>", "provenance": "Hancom Print 2024; independent operator and print settings"},
  "compat": "2024",
  "pages": 1,
  "font_environment": {"path": "fonts/environment.json", "sha256": "<64 hex>", "source": "<verified environment>", "provenance": "<actual face mapping evidence>"},
  "fonts": [{"path": "fonts/approved.ttf", "sha256": "<64 hex>", "source": "<font origin>", "license": "<redistribution license>", "publication_approved": true}],
  "publication": {"approved": true, "metadata_approved": true, "evidence": "<explicit public-use permission>"}
}
```

이 예시는 schema 설명이며 실존 문서나 허가를 주장하지 않습니다. 모든 path는 corpus 내부의 실제 파일이어야 하며 SHA-256을 검증합니다. 필요한 font 파일의 배포 권한이 없으면 공개 corpus에 넣지 않습니다. `font_environment` JSON은 upstream의 실제 font environment 형식을 사용합니다. 실제 설치·공급·face 대응과 PDF 독립 생성 사실은 사람이 검증해야 하며 선언만으로 인증되지 않습니다.

측정 전에 모든 입력 hash, CLI flag contract 및 실행 `--help`를 확인합니다. Native CLI는 `cargo build --locked --release --bin rhwp --features native-skia`, WASM은 upstream `scripts/wasm-pack-locked.sh --target web --release`, browser dependency는 `npm ci --prefix rhwp-studio`로 준비합니다. Fontconfig/Freetype, Poppler, Pillow, PDFium, fonttools, Rust/WASM, Node와 Chrome이 필요합니다. 실제 환경/설치 폰트 inventory와 producer binary/WASM/lockfile의 fingerprint를 기록합니다.

각 문서·backend에서 **1페이지 smoke 후 전쪽**을 별도로 실행합니다. Hancom 2024 golden에는 `--compat 2024`를 반드시 전달합니다(기본값 2022에 의존하지 않음). 반복 가능한 `--file-target KEY DOC PDF` 인터페이스를 사용하며 현재 adapter는 오류 격리를 위해 문서별로 호출합니다. Native와 WASM은 서로가 아니라 각각 같은 독립 PDF를 기준으로 측정합니다.

## 지표와 해석

- Golden fidelity: 96dpi, RGB 232 threshold, 2px dilation tolerance의 raw silhouette 보조 지표입니다. 의미 정확도, 미세 글자/수식 검증 또는 Hancom 완전 호환 인증이 아닙니다.
- Backend parity는 별도이며 현재 unavailable입니다. 동일 PDF에 대한 점수가 비슷하다고 backend 간 픽셀이 같다는 의미는 아닙니다.
- PR regression도 별도이며 현재 unavailable입니다. PR artifact 수집은 구현하지 않았습니다. 향후 수집 시 repository/run/attempt, actual PR head와 synthetic merge tree를 구분하고 검증되지 않은 결과를 golden 점수에 합산하지 않아야 합니다.
- 단일 전체 정확도% 대신 target/measured/failed/skipped 문서·페이지, unmeasured pages, page-count mismatch, median/P10/min/below90를 표시합니다. P10은 nearest-rank, 집계 단위는 각 immutable run/backend의 페이지입니다.
- exit 1도 완전한 manifest·쪽 목록·PDF 쪽수 계약이 확인되면 quality alert로 보존합니다. 그 외 실행 실패는 failed/partial입니다. 90 미만과 쪽수 차이는 별도로 표시합니다.
- latest attempted와 last complete를 분리합니다. 현재 corpus hash와 일치하는 실행만 화면에 보이며 예전 corpus 기록은 data branch에 보존합니다. 서로 다른 엔진 SHA의 결과를 최신 전체 점수로 합치지 않습니다.
- source SHA, source tag/type/time, protocol, corpus/font/adapter fingerprint와 environment/build fingerprint를 JSON에 남깁니다. 아직 빌드하지 않은 fingerprint는 null입니다. 출처 commit 링크를 제공합니다.

## 안전성과 제한

모든 Actions는 commit SHA로 pin하고 checkout은 `persist-credentials: false`입니다. 사용자 ref는 환경변수로 전달하고 shell에 interpolation하지 않습니다. tag/ref, hash, 숫자 타입·범위, path traversal, symlink, JSON 크기, 중복/누락 페이지 및 public field whitelist를 검사합니다. data branch를 코드로 checkout/실행하지 않습니다. publish는 upstream 실행 job과 별도 runner이며 그 job에서 생성한 HTML을 사용하지 않습니다.

`--resume`와 부분 결과 cache는 사용하지 않습니다. Git diff는 측정 대체 근거가 아니며 현재 증분 최적화는 없습니다. 완전한 새 측정 또는 명시적 미측정으로 남습니다. workflow timeout/cancel·build 실패 시 artifact가 없어도 publisher는 unavailable 상태를 기록합니다(전체 workflow가 수동 취소되거나 publisher가 인프라 장애로 실행되지 못한 경우는 Actions 기록을 확인해야 합니다).

현재 adapter는 v0.9.0의 확인된 contract를 대상으로 하며 새 release에서는 probe가 실패하면 측정을 보류합니다. 실제 golden이 없는 초기 상태에서는 renderer build 및 Hancom 비교를 검증했다고 주장하지 않습니다. 실제 corpus를 추가한 첫 실행의 build/Chrome/font 공급, smoke와 전쪽 결과를 직접 확인한 뒤 운영 범위를 확대해야 합니다.

## 확인한 upstream 출처

- v0.9.0 actual commit: [c9095c5f67632e6721e800ccc7fb43ea49d26682](https://github.com/edwardkim/rhwp/commit/c9095c5f67632e6721e800ccc7fb43ea49d26682)
- [Visual Sweep source](https://github.com/edwardkim/rhwp/blob/c9095c5f67632e6721e800ccc7fb43ea49d26682/scripts/visual_sweep.py)
- [Visual Sweep guide](https://github.com/edwardkim/rhwp/blob/c9095c5f67632e6721e800ccc7fb43ea49d26682/mydocs/manual/verification/visual_sweep_guide.md)
- [Full sweep workflow](https://github.com/edwardkim/rhwp/blob/c9095c5f67632e6721e800ccc7fb43ea49d26682/.github/workflows/full-renderer-sweep.yml)
- [Render diff workflow](https://github.com/edwardkim/rhwp/blob/c9095c5f67632e6721e800ccc7fb43ea49d26682/.github/workflows/render-diff.yml)
- [Release native build](https://github.com/edwardkim/rhwp/blob/c9095c5f67632e6721e800ccc7fb43ea49d26682/.github/workflows/release-binary.yml)

devel push마다 새로운 render CI가 있다고 가정하지 않습니다. baseline의 일부 페이지 목록이나 파일 수는 전체 독립 golden coverage를 나타내지 않습니다.
