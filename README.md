# rhwp fidelity dashboard

독립 Hancom Print PDF를 기준으로 rhwp의 **WASM Canvas2D와 Native Skia** 렌더링 결과를 비교하는 공개 대시보드입니다. 고정된 upstream commit에서 두 경로를 새로 빌드하고, 같은 문서·쪽·측정 계약의 결과를 나란히 제공합니다.

**[대시보드 열기](https://postmelee.github.io/rhwp-fidelity-dashboard/)** · [문서 안내](docs/README.md)

현재 corpus는 공개 사용 근거를 확인한 4개 문서·각 1쪽입니다. 표시되는 raw silhouette는 모양 겹침 보조 지표이며 전체 문서 호환 정확도나 Skia 성숙도 비율이 아닙니다. 미측정·실패·부분 결과를 구분하고 원래 측정 시각과 재현정보를 보존합니다. 원본 문서, PDF, 글꼴 및 이미지는 배포하지 않습니다.

## 사용

대시보드에서 실행별 범위와 상태를 확인하고, Canvas2D·Skia 비교표 및 문서·페이지 상세를 펼쳐 열 제목으로 정렬하세요. 직접 렌더러 간 픽셀 비교는 아직 미측정입니다.

안정 릴리즈는 6시간 간격으로 자동 확인합니다. 특정 tag 또는 exact commit을 다시 측정하려면 Actions의 **Fidelity → Run workflow**에서 ref를 지정하거나 다음 명령을 사용하세요.

```sh
gh workflow run fidelity.yml -R postmelee/rhwp-fidelity-dashboard -f ref=v0.9.0
```

## 문서

- [측정 방법과 비교 지표의 한계](docs/METHODOLOGY.md)
- [정답지·글꼴·corpus 확장](docs/CORPUS.md)
- [운영·수동 실행·개발 명령](docs/OPERATIONS.md)
- [자동화 설계·영구 기록·배포 복구](docs/ARCHITECTURE.md)
- [실제 실행과 검증 기록](docs/VERIFICATION.md)
