# 운영과 개발

Pages Source는 **GitHub Actions**로 설정합니다. Actions의 contents/pages write 및 OIDC가 허용되어야 합니다.

```sh
gh workflow run fidelity.yml -R postmelee/rhwp-fidelity-dashboard -f ref=v0.9.0
gh workflow run fidelity.yml -R postmelee/rhwp-fidelity-dashboard -f ref=67b4ff8d3a55e5bb50c46a44315de749a4ef07a7
gh workflow run pages.yml -R postmelee/rhwp-fidelity-dashboard
gh run list -R postmelee/rhwp-fidelity-dashboard
```

ref를 비우면 stable backlog를 처리합니다. 실패한 같은 계약을 3회 제한 이후에도 다시 측정하려면 ref를 지정합니다. 수동 실행은 항상 허용되며 보존된 시도 수에는 포함됩니다. 제한은 data branch에 보존된 측정 시도를 기준으로 하므로 ledger 기록 자체가 실패한 인프라 장애는 Actions에서 별도로 확인해야 합니다. 재배포만 필요하면 **Pages → Run workflow**를 실행합니다. Pages는 원장만 읽고 HTML과 JSON을 게시한 뒤 실제 공개 파일을 대조합니다. schedule 자체가 GitHub에서 비활성화되거나 resolver가 네트워크 오류로 실패하면 해당 Actions 상태를 확인해야 합니다.

이 저장소를 clone한 뒤 저장소 루트에서 Python 3.12 이상으로 실행합니다. 아래 로컬 명령은 빈 ledger의 페이지를 검증하며 upstream 엔진을 빌드하지 않습니다:

```sh
python3 -m unittest discover -s tests -v
python3 scripts/pipeline.py build --ledger empty-ledger --out site
python3 -m http.server 8000 --directory site
# 다른 터미널
python3 scripts/http_smoke.py
```

Checks workflow가 단위 테스트, actionlint, 페이지 build와 HTTP smoke를 수행합니다. 단위 테스트의 숫자는 실제 렌더 점수가 아닙니다.


## 빌드 시간과 장애 확인

Native release와 fresh WASM release의 cold build가 대부분의 시간을 차지합니다. 실제 첫 정상 실행에서는 각각 약 24분과 18분이었습니다. 개별 producer 명령은 60분, 측정 job은 180분으로 제한합니다. PDF raster preflight가 먼저 실행되며 단계별 시간을 로그에 남깁니다. workflow의 녹색 상태만으로 실측 성공을 판단하지 말고 immutable JSON의 backend/document 상태를 확인하세요.

[검증 이력](VERIFICATION.md) · [자동화 설계와 재시도 정책](ARCHITECTURE.md) · [문서 목록](README.md)

## Upstream PR 증적 재현

[대시보드 이슈 #1](https://github.com/postmelee/rhwp-fidelity-dashboard/issues/1)과 [upstream 이슈 #9242](https://github.com/edwardkim/rhwp/issues/9242)의 첫 수집 범위는 [Render Diff run 44925877031 attempt 1](https://github.com/edwardkim/rhwp/actions/runs/44925877031/attempts/1)의 artifact 14716643303입니다. 저장한 ZIP과 원본 증적 commit이 있는 upstream checkout으로 숫자 원장을 재현할 수 있습니다. 두 명령은 JSON을 표준출력에 씁니다.

```sh
python3 scripts/pr_evidence.py "$ARTIFACT_ZIP" | cmp - corpus/pr-evidence/render-diff-44925877031-1.json
python3 scripts/check_pr_9024.py --upstream "$UPSTREAM_CHECKOUT" | cmp - corpus/pr-evidence/visual-sweep-9024.json
```

Render Diff는 ZIP 해시 검증 후 Canvas·PDF 결과 JSON과 빌드·브라우저 소비 영수증을 읽습니다. CI에서 확인한 1쪽 범위와 이미지 크기 결과를 표시합니다. 문서 전체 쪽수, base 측정 및 독립 한컴 Print는 해당 artifact에서 미확인입니다. WASM 패키지의 해시와 브라우저에서 수신한 WASM 해시를 대조할 수 있으며 PDF용 Native CLI의 실행 경로는 workflow에 기록되어 있습니다. Native CLI 바이트 해시는 공개 영수증에서 미확인입니다.

별도 [PR #9024의 Visual Sweep](https://github.com/edwardkim/rhwp/pull/9024)은 같은 HWPX와 독립 한컴 Print PDF를 사용한 Native 및 WASM의 base/head 결과입니다. 비교 TSV의 raw 수치를 해시가 확인된 두 쪽 원본 TSV의 표시 정밀도와 대조합니다. 동일 backend·입력·참조·DPI·compat·래스터 및 글꼴 조건의 공통 쪽에서만 차이를 표시합니다. 두 검증 harness의 스크립트 변경은 결과 이미지의 범례 글꼴 선택에 국한됩니다.

## Print 영수증 묶음의 릴리즈 측정

`corpus/receipt-cohort.json`은 엔진 커밋, 원본 인벤토리 커밋, 영수증 SHA-256과 각 원본·PDF의 바이트 및 쪽수를 고정합니다. upstream은 이 묶음을 공개 검증 입력 34종·46쪽으로 설명합니다. [검증 입력의 용도](https://github.com/edwardkim/rhwp/blob/2f4f60fbffa1cbed1d7baa8b6d36f40f0940dee0/mydocs/pr/assets/hyunmyungjanelee_20261112/README.md)

Actions의 **Receipt-backed release measurement**를 main에서 수동 실행할 수 있습니다. 첫 문서 2쪽의 양쪽 측정이 성공하면 동일 runner에서 나머지 33문서를 측정합니다. 두 단계의 실제 실행물과 환경 해시는 각 단계에 기록합니다. 실패한 job을 재실행하면 새 attempt가 생깁니다. 한 attempt의 빈 쪽을 다른 attempt의 점수로 채우지 않습니다. 숫자 artifact는 14일간 보존되고, main의 수동 실행은 완료 후 **Archive release cohort**가 data 브랜치의 `cohorts/<run>-<attempt>.json`에 보존합니다. PR 실행은 생산 head와 테스트한 merge SHA를 대조한 명시적 `corpus/receipt-import.json`으로 반영합니다.

사이트의 문서·페이지 탭에서 해당 실행의 양쪽 결과, 쪽수 일치, 분포와 낮은 점수를 확인합니다. 전체 경로 원장에는 원본 대신 경로의 UTF-8 SHA-256, Git blob, 루트, 형식, 검사별 이관과 실측 상태를 게시합니다. 저장소 상대 경로를 입력하면 브라우저 안에서 같은 해시를 계산합니다. 지정 영수증 집합 밖의 행은 다른 정답 PDF가 존재할 수 있습니다. 원본·PDF·PNG·개별 글꼴은 게시하지 않습니다.


### 로컬 Hancom Print 영수증으로 추가 경로 측정

측정 전 원본 트리는 인벤토리 커밋 `2f4f60fbffa1cbed1d7baa8b6d36f40f0940dee0`에 고정한다. 로컬에서 생성한 PDF를 동일 checkout의 영수증 상대 경로에 두고, upstream `audit_print_pairs.py`가 지원하는 `cases[]` Print 기록을 사용한다. 기존 묶음 JSON 또는 upstream 갱신 도구가 `--receipt-dir`에 쌓은 job별 JSON 디렉터리를 지정할 수 있다. 원본과 PDF 경로가 같은 영수증의 내용이 충돌하면 해당 원본에 `conflicting_receipts`를 남겨 검토할 수 있다. 실행물은 별도 엔진 checkout에서 빌드한다. Linux 측정 도구 설치 버전은 `.github/workflows/receipt-shards.yml`에 있다.

```sh
prepared=$(python3 scripts/local_print_intake.py "$inventory_checkout" "$receipts" "$private_dir/intake" \
  --metadata-evidence "$numeric_metadata_approval" --compat 2022)
python3 scripts/cohort_shards.py "$engine_checkout" "$private_dir/results" \
  --local-corpus "$prepared" --engine-sha "$engine_sha" --pages-per-shard 32
```

`intake.json`은 전체 경로에 영수증 상태를 남긴다. 원본 Git blob과 현재 바이트가 다르거나 유효한 PDF가 복수인 경로는 선택을 보류한다. 준비한 폴더에는 원본과 PDF가 들어 있으므로 로컬에 보관한다. 같은 실행을 다시 시작하면 쪽 범위·실행물·환경이 일치하는 완료 샤드를 재사용한다. `plan.json`, `status.json`, `shard-*.json`에서 해당 엔진의 실행 범위와 수치를 검토할 수 있다. 이 명령은 결과를 공개 원장에 전송하지 않는다.


### 추적 코호트의 샤드 실행과 재개 점검

Actions의 **Verify receipt shards**에서 정확한 engine SHA와 `scope=tracked`를 선택하면 현재 추적 코호트의 Print 영수증과 등록 근거를 검증하고 모든 문서를 샤드로 실행합니다. 기본 `original`은 기존 Print 영수증 묶음을 사용합니다. 완료 검사기는 선택한 입력 명세에서 문서·backend·쪽 키를 계산하고 샤드 출력이 각 키를 정확히 한 번씩 포함하는지 확인합니다. 예정대로 첫 샤드를 재사용했는지와 같은 생산물·환경으로 실행했는지도 함께 확인합니다. 결과는 수치 artifact로 보관합니다.

### 과거 안정 릴리즈의 생산기 호환성

Stable Track은 측정 job을 시작하기 전에 태그를 Git 커밋으로 해석하고 현재 Visual Sweep 생산기에 필요한 스크립트와 옵션을 검사합니다. 확인된 누락은 `compatibility/<run>-<attempt>.json`에 기록하고 다음 릴리즈를 확인합니다. 정적 검사를 통과한 릴리즈는 실제 빌드 및 측정으로 진행합니다. 인증·권한, 요청 제한, 시간 초과, API 응답 오류는 이후 시도에서 재확인합니다.

Run history의 **Stable release compatibility**에서 고정된 커밋과 판정 근거를 확인할 수 있습니다. 기존 측정 및 실패 기록은 `cohorts/`에서 계속 조회할 수 있습니다. 스크립트나 옵션 요구가 달라지면 생산기 계약 식별값도 바뀌어 이전 판정은 새 계약에 적용되지 않습니다.
