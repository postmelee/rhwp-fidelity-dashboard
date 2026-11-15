# Corpus와 정답지

`corpus/manifest.json`의 실제 4개 항목을 schema 예제로 사용하세요. 원본과 독립 Hancom Print PDF의 실제 대응, source snapshot, SHA-256, 쪽수, compat, font 계약과 사용 근거를 먼저 확인해야 합니다. 이름이 비슷하거나 같은 저장소에 있다는 이유만으로 승인하지 않습니다.

`publication.approved`는 기록한 근거에 따른 측정 사용과 허용 metadata 게시만을 뜻합니다. `raw_files:false`가 필수이며 원본/폰트 재배포 허가로 확대하지 않습니다. font의 `usage_approved`도 실행기 사용 범위입니다. 이 프로젝트는 original document, PDF, font 파일을 배포하지 않습니다.


현재 승인된 범위는 기존 upstream contributor gate의 4개 문서·각 1쪽입니다. 기존 독립 Hancom Print PDF를 재사용하며 파일을 다시 출력하거나 재배포하지 않습니다. PDFium은 upstream 계약과 같은 pypdfium2 5.13.0을 사용합니다.

- [고정 manifest](../corpus/manifest.json)
- [4개 페어와 공개 사용 근거](../corpus/PROVENANCE.md)
- [upstream oracle resolver 재사용과 누락 PDF 검토](../corpus/ORACLE_CATALOG.md)
- [측정 계약](METHODOLOGY.md)
- [문서 목록](README.md)
