# AI Citation Analyzer — Streamlit MVP

기존 `ai_citation_question.ipynb`의 핵심 로직을 웹 UI로 옮긴 MVP입니다.

## 현재 구현된 기능
- 질문 Excel 업로드
- 질문을 한 건씩 화면에 표시
- AI 모델 선택
- AI 답변 붙여넣기
- 답변에서 http/https Citation URL 자동 추출
- OpenAI 이미지 URL 제외
- Query String 제거 및 답변 내 중복 URL 제거
- URL → Domain 변환
- Domain → Brand / Source Category 매핑
- 질문 Metadata와 Citation 결합
- 결과 누적
- 브랜드/출처 유형 Dashboard
- Excel 다운로드
- 외부 brand_map.xlsx 업로드

## 실행 방법

### 1) Python 설치
Python 3.10 이상 권장

### 2) 터미널에서 이 폴더로 이동
예:
`cd ai_citation_streamlit_mvp`

### 3) 패키지 설치
`pip install -r requirements.txt`

### 4) 실행
`streamlit run app.py`

실행하면 브라우저가 열립니다. 안 열리면 터미널에 표시되는 Local URL을 브라우저에 입력하세요.

## 질문 Excel 필수 컬럼
`id`, `category`, `sub_category`, `region`, `persona`, `question`

## 브랜드 맵 컬럼
`domain`, `brand`, `category`

앱에 기존 브랜드 맵이 기본 내장되어 있으며, 별도의 `brand_map.xlsx`를 업로드하면 그 파일을 사용합니다.

## 원본 노트북 대비 변경점
- Colab 전용 `files.upload()` / `files.download()` 제거
- 셀 단위 수작업 실행을 Streamlit UI로 통합
- `all_results`를 Streamlit Session State로 관리
- 같은 질문 + 같은 AI 모델을 다시 분석하면 기존 결과를 교체
- Dashboard와 Excel 다운로드 기능 추가
- 원본 `get_category()` OTA 목록의 문자열 쉼표 누락 가능성을 피하고 브랜드 맵 하나로 분류 로직 통합

## MVP의 의도적 한계
현재 버전은 AI API를 호출하지 않습니다. 사용자가 AI 답변을 붙여넣으면 이후 Citation 처리부터 자동화합니다.
다음 버전에서 AI API 자동 질의, 프로젝트 저장/불러오기, 미분류 도메인 관리, 모델별/질문별 비교 Dashboard 등을 붙일 수 있습니다.
