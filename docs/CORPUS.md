# Corpus와 정답지

`corpus/manifest.json`의 실제 4개 항목을 schema 예제로 사용하세요. 원본과 독립 Hancom Print PDF의 실제 대응, source snapshot, SHA-256, 쪽수, compat, font 계약과 사용 근거를 먼저 확인해야 합니다. 이름이 비슷하거나 같은 저장소에 있다는 이유만으로 승인하지 않습니다.

`publication.approved`는 기록한 근거에 따른 측정 사용과 허용 metadata 게시만을 뜻합니다. `raw_files:false`가 필수이며 원본/폰트 재배포 허가로 확대하지 않습니다. font의 `usage_approved`도 실행기 사용 범위입니다. 이 프로젝트는 original document, PDF, font 파일을 배포하지 않습니다.


현재 승인된 범위는 기존 upstream contributor gate의 4개 문서·각 1쪽입니다. 기존 독립 Hancom Print PDF를 재사용하며 파일을 다시 출력하거나 재배포하지 않습니다. PDFium은 upstream 계약과 같은 pypdfium2 5.13.0을 사용합니다.

- [고정 manifest](../corpus/manifest.json)
- [4개 페어와 공개 사용 근거](../corpus/PROVENANCE.md)
- [upstream oracle resolver 재사용과 누락 PDF 검토](../corpus/ORACLE_CATALOG.md)
- [측정 계약](METHODOLOGY.md)
- [문서 목록](README.md)

## 전체 원본 인벤토리

`summary.json`의 `corpus_inventory`는 네 루트에 있는 모든 HWP/HWPX 경로와 고유 Git blob을 집계합니다. 릴리즈별 `target_documents`와 `target_pages`는 해당 smoke 실행의 분모입니다. Print 영수증 집계는 지정한 한 묶음의 원본·PDF 실제 바이트와 Print 근거에 한정됩니다. 릴리즈 실측률은 별도의 실행 기록이 필요합니다.

해당 Git 커밋과 객체를 읽을 수 있는 rhwp 저장소에서 아래 명령으로 전체 행을 재생성할 수 있습니다. 명령은 고정 커밋의 Git 객체를 읽습니다.

```sh
python3 scripts/corpus_inventory.py /path/to/rhwp --rows /tmp/rhwp-inventory.json --check
```

각 행에는 원본 경로, blob, 동일 blob을 가리키는 경로 수, 일반 회귀 보류, 검사 축별 이관과 추적 이슈, 쪽수 기준표 등록, resolver 수집 범위와 지정한 영수증의 감사 결과가 있습니다. 빈 이관 목록은 해당 원장의 이관 기록이 없다는 뜻입니다. 빈 영수증 목록은 해당 묶음에 증거가 없다는 뜻입니다. Pages에는 루트별 합계와 검증 건수를 공개합니다.
