
import io
import re
from urllib.parse import urlparse, urlunparse

import pandas as pd
import streamlit as st

st.set_page_config(page_title="AI Citation Analyzer", page_icon="🔎", layout="wide")

DEFAULT_BRAND_MAP = [
    ["hanatour.com", "하나투어", "여행사"],
    ["modetour.com", "모두투어", "여행사"],
    ["verygoodtour.com", "참좋은여행", "여행사"],
    ["yellowballoon.co.kr", "노랑풍선", "여행사"],
    ["kyowontour.com", "교원투어", "여행사"],
    ["nol.interpark.com", "인터파크투어", "여행사"],
    ["nol.yanolja.com", "야놀자", "OTA"],
    ["yeogi.com", "여기어때", "OTA"],
    ["booking.com", "Booking.com", "OTA"],
    ["agoda.com", "Agoda", "OTA"],
    ["expedia.com", "Expedia", "OTA"],
    ["tripadvisor.com", "Tripadvisor", "OTA/리뷰플랫폼"],
    ["klook.com", "Klook", "OTA"],
    ["kkday.com", "KKday", "OTA"],
    ["japan.travel", "JNTO", "관광청/공공기관"],
    ["visitkorea.or.kr", "한국관광공사", "관광청/공공기관"],
    ["blog.naver.com", "네이버 블로그", "블로그/콘텐츠"],
    ["post.naver.com", "네이버 포스트", "블로그/콘텐츠"],
    ["tistory.com", "티스토리", "블로그/콘텐츠"],
    ["brunch.co.kr", "브런치", "블로그/콘텐츠"],
    ["naver.com", "네이버", "포털"],
    ["daum.net", "다음", "포털"],
    ["google.com", "구글", "포털"],
    ["youtube.com", "YouTube", "SNS/영상"],
    ["youtu.be", "YouTube", "SNS/영상"],
    ["instagram.com", "Instagram", "SNS/영상"],
    ["tiktok.com", "TikTok", "SNS/영상"],
]
DEFAULT_BRAND_DF = pd.DataFrame(DEFAULT_BRAND_MAP, columns=["domain", "brand", "category"])

REQUIRED_COLUMNS = ["id", "category", "sub_category", "region", "persona", "question"]

def extract_urls(text):
    if text is None or pd.isna(text):
        return []
    urls = re.findall(r'https?://[^\s\)\]\}>"\']+', str(text))
    cleaned = []
    for url in urls:
        url = url.rstrip(".,;:!?")
        if "images.openai.com" in url:
            continue
        parsed = urlparse(url)
        normalized = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
        if normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned

def get_domain(url):
    try:
        domain = urlparse(url).netloc.lower()
        return domain[4:] if domain.startswith("www.") else domain
    except Exception:
        return ""

def lookup_domain(domain, mapping, field):
    # Exact match first; then allow a subdomain to inherit its parent-domain mapping.
    exact = mapping.loc[mapping["domain"].str.lower() == domain.lower()]
    if not exact.empty:
        return exact.iloc[0][field]
    candidates = mapping[mapping["domain"].apply(
        lambda d: domain.lower().endswith("." + str(d).lower())
    )]
    if not candidates.empty:
        candidates = candidates.assign(_len=candidates["domain"].str.len()).sort_values("_len", ascending=False)
        return candidates.iloc[0][field]
    return "기타"

def analyze_answer(question_row, answer_text, ai_model, mapping):
    rows = []
    for url in extract_urls(answer_text):
        domain = get_domain(url)
        rows.append({
            "question_id": question_row["id"],
            "category": question_row["category"],
            "sub_category": question_row["sub_category"],
            "region": question_row["region"],
            "persona": question_row["persona"],
            "question": question_row["question"],
            "ai_model": ai_model,
            "answer": answer_text,
            "url": url,
            "domain": domain,
            "brand": lookup_domain(domain, mapping, "brand"),
            "source_category": lookup_domain(domain, mapping, "category"),
        })
    return pd.DataFrame(rows)

def to_excel_bytes(df):
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="citation_result")
    return bio.getvalue()

if "questions" not in st.session_state:
    st.session_state.questions = None
if "results" not in st.session_state:
    st.session_state.results = pd.DataFrame()
if "current_idx" not in st.session_state:
    st.session_state.current_idx = 0

st.title("AI Citation Analyzer")
st.caption("AI 답변을 붙여넣으면 Citation URL을 추출·정제하고, 출처/브랜드 단위의 분석 데이터로 변환합니다.")

with st.sidebar:
    st.header("1. 분석 설정")
    ai_model = st.selectbox("AI 모델", ["ChatGPT", "Gemini", "Claude", "Perplexity", "기타"])
    st.divider()
    st.subheader("질문 파일")
    q_file = st.file_uploader("질문 Excel 업로드", type=["xlsx"], key="questions_file")
    st.caption("필수 컬럼: id, category, sub_category, region, persona, question")

    st.subheader("브랜드 맵")
    map_file = st.file_uploader("brand_map.xlsx (선택)", type=["xlsx"], key="map_file")
    if map_file:
        brand_map = pd.read_excel(map_file)
        if not {"domain", "brand", "category"}.issubset(brand_map.columns):
            st.error("브랜드 맵에는 domain, brand, category 컬럼이 필요합니다.")
            st.stop()
    else:
        brand_map = DEFAULT_BRAND_DF.copy()

    st.download_button(
        "기본 brand_map 다운로드",
        data=to_excel_bytes(DEFAULT_BRAND_DF),
        file_name="brand_map.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

if q_file:
    questions = pd.read_excel(q_file)
    missing = [c for c in REQUIRED_COLUMNS if c not in questions.columns]
    if missing:
        st.error("질문 파일에 다음 컬럼이 없습니다: " + ", ".join(missing))
        st.stop()
    # 새 파일이 올라오면 세션 질문 갱신
    if st.session_state.questions is None or not questions.equals(st.session_state.questions):
        st.session_state.questions = questions
        st.session_state.current_idx = 0
        st.session_state.results = pd.DataFrame()

if st.session_state.questions is None:
    st.info("왼쪽에서 질문 Excel 파일을 업로드하면 분석을 시작할 수 있습니다.")
    st.subheader("MVP가 하는 일")
    st.write("질문 선택 → AI 답변 붙여넣기 → URL 추출/정제 → 도메인 식별 → 브랜드/출처 분류 → 누적 결과 → Excel 다운로드")
    st.stop()

questions = st.session_state.questions
idx = min(st.session_state.current_idx, len(questions)-1)
q = questions.iloc[idx]

top1, top2, top3, top4 = st.columns(4)
top1.metric("전체 질문", len(questions))
top2.metric("현재 질문", f"{idx+1}/{len(questions)}")
top3.metric("누적 Citation", len(st.session_state.results))
done_questions = st.session_state.results["question_id"].nunique() if not st.session_state.results.empty else 0
top4.metric("처리 질문", done_questions)

st.progress((idx + 1) / len(questions))

left, right = st.columns([1, 1.35], gap="large")
with left:
    st.subheader("2. 질문")
    st.markdown(f"**ID**  {q['id']}")
    st.markdown(f"**Category**  {q['category']} / {q['sub_category']}")
    st.markdown(f"**Region**  {q['region']}")
    st.markdown(f"**Persona**  {q['persona']}")
    st.info(str(q["question"]))

    c1, c2 = st.columns(2)
    if c1.button("← 이전", disabled=idx == 0, use_container_width=True):
        st.session_state.current_idx -= 1
        st.rerun()
    if c2.button("다음 →", disabled=idx >= len(questions)-1, use_container_width=True):
        st.session_state.current_idx += 1
        st.rerun()

with right:
    st.subheader("3. AI 답변")
    answer = st.text_area(
        "AI의 답변 전체를 그대로 붙여넣으세요.",
        height=360,
        placeholder="여기에 ChatGPT / Gemini / Claude 등의 답변을 붙여넣으세요...",
        key=f"answer_{q['id']}_{idx}",
    )
    if st.button("Citation 분석 및 저장", type="primary", use_container_width=True):
        if not answer.strip():
            st.warning("AI 답변을 먼저 붙여넣어 주세요.")
        else:
            result = analyze_answer(q, answer, ai_model, brand_map)
            if result.empty:
                st.warning("답변에서 http/https URL을 찾지 못했습니다.")
            else:
                # 같은 질문+모델의 기존 결과는 교체하여 중복 누적 방지
                old = st.session_state.results
                if not old.empty:
                    old = old[~((old["question_id"] == q["id"]) & (old["ai_model"] == ai_model))]
                st.session_state.results = pd.concat([old, result], ignore_index=True)
                st.success(f"{len(result)}개의 Citation을 추출해 저장했습니다.")

st.divider()
st.subheader("4. 분석 Dashboard")

res = st.session_state.results
if res.empty:
    st.caption("Citation을 하나 이상 분석하면 Dashboard가 표시됩니다.")
else:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Citation", f"{len(res):,}")
    m2.metric("Unique Domain", f"{res['domain'].nunique():,}")
    m3.metric("Brand", f"{res.loc[res['brand'] != '기타', 'brand'].nunique():,}")
    other_rate = (res["brand"].eq("기타").mean() * 100)
    m4.metric("미분류 비중", f"{other_rate:.1f}%")

    tab1, tab2, tab3 = st.tabs(["브랜드", "출처 유형", "Raw Data"])
    with tab1:
        brand_counts = res["brand"].value_counts().rename_axis("brand").reset_index(name="citations")
        st.bar_chart(brand_counts.set_index("brand"))
        st.dataframe(brand_counts, use_container_width=True, hide_index=True)
    with tab2:
        cat_counts = res["source_category"].value_counts().rename_axis("source_category").reset_index(name="citations")
        st.bar_chart(cat_counts.set_index("source_category"))
        st.dataframe(cat_counts, use_container_width=True, hide_index=True)
    with tab3:
        st.dataframe(res, use_container_width=True, hide_index=True)

    st.download_button(
        "분석 결과 Excel 다운로드",
        data=to_excel_bytes(res),
        file_name="citation_result.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )

    if st.button("현재 세션 결과 초기화"):
        st.session_state.results = pd.DataFrame()
        st.rerun()
