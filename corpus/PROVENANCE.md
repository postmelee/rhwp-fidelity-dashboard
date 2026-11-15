# 기존 Hancom Print 자료 재사용 근거

조사 snapshot: `edwardkim/rhwp@67b4ff8d3a55e5bb50c46a44315de749a4ef07a7`.

- [공개 CONTRIBUTING 안내](https://github.com/edwardkim/rhwp/blob/67b4ff8d3a55e5bb50c46a44315de749a4ef07a7/CONTRIBUTING.md)는 기여자 공통 검사가 저장소의 기존 원본·Print PDF를 재사용하며 공개 웹폰트와 OS 로컬 글꼴을 사용할 수 있다고 명시합니다. 비공개 한컴 OTF나 MCP는 요구하지 않습니다.
- [정확한 4개 페어 catalog](https://github.com/edwardkim/rhwp/blob/67b4ff8d3a55e5bb50c46a44315de749a4ef07a7/scripts/data/contributor_visual_gate.json)는 원본/PDF path, SHA-256, bytes, 각 1쪽, compat 2022를 고정합니다.
- [검증 코드](https://github.com/edwardkim/rhwp/blob/67b4ff8d3a55e5bb50c46a44315de749a4ef07a7/scripts/visual_sweep_contributor.py)는 두 파일의 실제 hash와 보호 baseline의 문서·PDF·쪽수·DPI·compat가 일치하는지 검사합니다. 이 프로젝트는 그 과거 점수를 현재 측정으로 가져오지 않습니다.
- [공개 웹폰트 공급 계약](https://github.com/edwardkim/rhwp/blob/67b4ff8d3a55e5bb50c46a44315de749a4ef07a7/scripts/visual_sweep_handbook.py)은 KoPub 6개 TTF와 HCR Batang WOFF의 출처/고정 SHA를 제공합니다.
- [angle 합성 입력과 독립 Print 근거](https://github.com/edwardkim/rhwp/blob/67b4ff8d3a55e5bb50c46a44315de749a4ef07a7/mydocs/working/task_m100_8371_stage1.md)는 angle-2400 원본과 PDF의 같은 hash, Hancom 2020 MCP Print job, 버전 11.0.0.9136, pdf_print_method=0을 기록합니다.
- [re-03 생성 계획](https://github.com/edwardkim/rhwp/blob/67b4ff8d3a55e5bb50c46a44315de749a4ef07a7/mydocs/plans/archives/task_403.md)은 반복 영문 abcdef 형태의 폭 검사용 합성 자료임을 설명합니다.

| ID | 기존 원본 | 기존 PDF | 쪽수 / compat |
|---|---|---|---|
| 52ee61fe7201e36b | samples/re-03-latin-only-hancom.hwp | pdf/re-03-latin-only-hancom-hwp-2020.pdf | 1 / 2022 |
| 59f6ab1155623bda | mydocs/pr/assets/issue_8371/angle-narrow/angle-2400.hwpx | 같은 디렉터리의 angle-2400-2020.pdf | 1 / 2022 |
| cdacd874b6e6ac66 | samples/pic-crop-01.hwp | pdf/pic-crop-01-2022.pdf | 1 / 2022 |
| d03a9dde3d5dc7ac | samples/shape-group-02.hwp | pdf/shape-group-02-hwp-2020.pdf | 1 / 2022 |

정확한 해시는 [manifest.json](manifest.json)에 있습니다. 원본/PDF actual bytes 검사는 매 실행 시 수행합니다. 파일명이나 upstream 전체 파일 개수로 유효성을 추정하지 않습니다.

허가 판단의 범위는 upstream이 명시적으로 안내한 공개 기여자 검사의 4개 페어 재사용입니다. 저장소 전체의 제3자 문서·이미지·폰트에 대한 재배포 허가를 주장하지 않습니다. 원본/PDF/font는 `corpus/cache/`의 일시 파일일 뿐 Git이나 Pages에 넣지 않으며, 숫자와 허용된 출처 metadata만 게시합니다. 새 PDF를 출력하지 않습니다.

18개 문서·backend별 1,771쪽의 큰 보호 baseline은 이번 4쪽 범위와 구분합니다. 전체 corpus 또는 특정 상용 폰트 환경의 호환도를 이 결과로 주장하지 않습니다.
