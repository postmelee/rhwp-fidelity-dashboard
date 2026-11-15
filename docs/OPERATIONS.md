# 운영과 개발

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


## 빌드 시간과 장애 확인

Native release와 fresh WASM release의 cold build가 대부분의 시간을 차지합니다. 실제 첫 정상 실행에서는 각각 약 24분과 18분이었습니다. 개별 producer 명령은 60분, 측정 job은 180분으로 제한합니다. PDF raster preflight가 먼저 실행되며 단계별 시간을 로그에 남깁니다. workflow의 녹색 상태만으로 실측 성공을 판단하지 말고 immutable JSON의 backend/document 상태를 확인하세요.

[검증 이력](VERIFICATION.md) · [자동화 설계와 재시도 정책](ARCHITECTURE.md) · [문서 목록](README.md)
