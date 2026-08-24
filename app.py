
import io
import re
from html.parser import HTMLParser
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import pandas as pd
import streamlit as st

st.set_page_config(page_title="AI Citation Analyzer", page_icon="🔎", layout="wide")

# -----------------------------
# 기본 브랜드/출처 맵
# -----------------------------
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

DEFAULT_BRAND_DF = pd.DataFrame(
    DEFAULT_BRAND_MAP, columns=["domain", "brand", "category"]
)

REQUIRED_COLUMNS = ["id", "category", "sub_category", "region", "persona", "question"]


# -----------------------------
# URL 추출/정제
# -----------------------------
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "gclid", "fbclid", "mc_cid", "mc_eid"
}


def clean_url(url):
    """URL의 fragment와 대표적인 tracking parameter만 제거한다."""
    if not url:
        return ""

    url = str(url).strip().rstrip(".,;:!?)]}>\"'")
    if not re.match(r"^https?://", url, flags=re.I):
        return ""

    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return ""

        filtered_query = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if k.lower() not in TRACKING_PARAMS
        ]

        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                urlencode(filtered_query, doseq=True),
                "",  # fragment 제거
            )
        )
    except Exception:
        return ""


def extract_urls_from_text(text):
    if text is None or pd.isna(text):
        return []

    urls = re.findall(
        r'https?://[^\s<>\)\]\}>"\']+',
        str(text),
        flags=re.I,
    )

    cleaned = []
    for url in urls:
        url = clean_url(url)
        if not url:
            continue
        if "images.openai.com" in url.lower():
            continue
        if url not in cleaned:
            cleaned.append(url)
    return cleaned


class LinkHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)


def extract_urls_from_html(html_text):
    """클립보드의 text/html 안에 숨어 있는 <a href='...'> 주소를 추출한다."""
    if not html_text:
        return []

    parser = LinkHTMLParser()
    try:
        parser.feed(str(html_text))
    except Exception:
        pass

    # href뿐 아니라 HTML 소스 자체에 노출된 URL도 함께 확인
    candidates = list(parser.hrefs) + extract_urls_from_text(html_text)

    cleaned = []
    for url in candidates:
        url = clean_url(url)
        if not url:
            continue

        lowered = url.lower()

        # ChatGPT 자체 UI/이미지 주소는 Citation에서 제외
        if "images.openai.com" in lowered:
            continue
        if url not in cleaned:
            cleaned.append(url)

    return cleaned


def merge_urls(plain_text, html_text):
    """HTML href를 우선하고, 일반 텍스트 URL을 보완적으로 합친다."""
    urls = []
    for url in extract_urls_from_html(html_text) + extract_urls_from_text(plain_text):
        if url not in urls:
            urls.append(url)
    return urls


def get_domain(url):
    try:
        domain = urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
        return domain[4:] if domain.startswith("www.") else domain
    except Exception:
        return ""


def lookup_domain(domain, mapping, field):
    exact = mapping.loc[mapping["domain"].str.lower() == domain.lower()]
    if not exact.empty:
        return exact.iloc[0][field]

    candidates = mapping[
        mapping["domain"].apply(
            lambda d: domain.lower().endswith("." + str(d).lower())
        )
    ]
    if not candidates.empty:
        candidates = (
            candidates.assign(_len=candidates["domain"].str.len())
            .sort_values("_len", ascending=False)
        )
        return candidates.iloc[0][field]

    return "기타"


def analyze_answer(question_row, answer_text, urls, ai_model, mapping):
    rows = []

    for url in urls:
        domain = get_domain(url)
        rows.append(
            {
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
            }
        )

    return pd.DataFrame(rows)


def to_excel_bytes(df):
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="citation_result")
    return bio.getvalue()


# -----------------------------
# Rich Paste Component
# Ctrl+V 시 text/plain + text/html을 동시에 Python으로 전달
# -----------------------------
PASTE_HTML = """
<div class="paste-wrap">
  <div class="paste-label">AI 답변 전체를 여기에 붙여넣으세요.</div>
  <div id="pastebox" class="pastebox" contenteditable="true"
       role="textbox" aria-multiline="true"
       data-placeholder="ChatGPT / Gemini / Claude 답변을 전체 선택한 뒤 Ctrl+C → 여기서 Ctrl+V"></div>
  <div id="status" class="status">붙여넣기 전</div>
</div>
"""

PASTE_CSS = """
.paste-wrap {
  width: 100%;
  font-family: var(--st-font);
}
.paste-label {
  margin-bottom: 8px;
  font-size: 14px;
}
.pastebox {
  min-height: 300px;
  max-height: 430px;
  overflow-y: auto;
  box-sizing: border-box;
  padding: 14px;
  border: 1px solid rgba(49, 51, 63, 0.20);
  border-radius: 8px;
  background: var(--st-secondary-background-color);
  white-space: pre-wrap;
  outline: none;
  line-height: 1.55;
}
.pastebox:empty:before {
  content: attr(data-placeholder);
  color: rgba(49, 51, 63, 0.45);
  pointer-events: none;
}
.pastebox:focus {
  border-color: var(--st-primary-color);
  box-shadow: 0 0 0 1px var(--st-primary-color);
}
.status {
  margin-top: 7px;
  font-size: 12px;
  opacity: 0.70;
}
"""

PASTE_JS = r"""
export default function(component) {
  const { parentElement, setStateValue, data } = component;
  const box = parentElement.querySelector('#pastebox');
  const status = parentElement.querySelector('#status');

  // Python 쪽 상태가 있고 박스가 비어 있을 때만 화면 복원
  const savedPlain = data?.plain_text ?? '';
  if (!box.dataset.initialized) {
    box.dataset.initialized = '1';
    if (savedPlain) {
      box.textContent = savedPlain;
      status.textContent = '저장된 답변 복원됨';
    }
  }

  box.onpaste = (event) => {
    event.preventDefault();

    const clipboard = event.clipboardData || window.clipboardData;
    const plain = clipboard?.getData('text/plain') || '';
    const html = clipboard?.getData('text/html') || '';

    // 화면에는 안전하게 plain text만 표시
    box.textContent = plain;

    // HTML은 화면에 렌더링하지 않고 Python으로만 전달
    setStateValue('payload', {
      plain_text: plain,
      html_text: html
    });

    status.textContent = html
      ? '붙여넣기 완료 · 숨은 하이퍼링크 정보 감지'
      : '붙여넣기 완료 · 일반 텍스트만 감지';
  };

  // 사용자가 직접 내용을 수정한 경우 plain text만 갱신
  box.onblur = () => {
    const plain = box.innerText || '';
    setStateValue('payload', {
      plain_text: plain,
      html_text: data?.html_text ?? ''
    });
  };
}
"""


def build_paste_component():
    # Components v2는 한 app.py 안에서 HTML/CSS/JS 양방향 통신이 가능
    try:
        return st.components.v2.component(
            "rich_clipboard_paste",
            html=PASTE_HTML,
            css=PASTE_CSS,
            js=PASTE_JS,
        )
    except AttributeError:
        return None


rich_paste_component = build_paste_component()


def rich_paste_box(key):
    """Component state에서 plain/html payload를 반환."""
    if rich_paste_component is None:
        st.error(
            "현재 Streamlit 버전이 너무 낮아 하이퍼링크 붙여넣기를 지원하지 않습니다. "
            "requirements.txt의 streamlit 버전을 최신 버전으로 올려주세요."
        )
        fallback = st.text_area(
            "AI 답변 전체를 붙여넣으세요.",
            height=300,
            key=f"{key}_fallback",
        )
        return fallback, ""

    state = st.session_state.get(key, {})
    payload = state.get("payload", {}) if isinstance(state, dict) else {}
    plain_text = payload.get("plain_text", "") if isinstance(payload, dict) else ""
    html_text = payload.get("html_text", "") if isinstance(payload, dict) else ""

    result = rich_paste_component(
        data={
            "plain_text": plain_text,
            "html_text": html_text,
        },
        default={"payload": payload},
        key=key,
        on_payload_change=lambda: None,
    )

    # 현재 렌더 결과에서도 읽어보기
    try:
        if getattr(result, "payload", None):
            payload = result.payload
            plain_text = payload.get("plain_text", "")
            html_text = payload.get("html_text", "")
    except Exception:
        pass

    return plain_text, html_text


# -----------------------------
# Session state
# -----------------------------
if "questions" not in st.session_state:
    st.session_state.questions = None
if "results" not in st.session_state:
    st.session_state.results = pd.DataFrame()
if "current_idx" not in st.session_state:
    st.session_state.current_idx = 0


# -----------------------------
# UI
# -----------------------------
st.title("AI Citation Analyzer")
st.caption(
    "AI 답변 전체를 한 번 붙여넣으면, 일반 텍스트뿐 아니라 클립보드 HTML의 숨은 하이퍼링크까지 읽어 Citation을 자동 추출합니다."
)

with st.sidebar:
    st.header("1. 분석 설정")
    ai_model = st.selectbox(
        "AI 모델",
        ["ChatGPT", "Gemini", "Claude", "Perplexity", "기타"],
    )

    st.divider()
    st.subheader("질문 파일")
    q_file = st.file_uploader(
        "질문 Excel 업로드",
        type=["xlsx"],
        key="questions_file",
    )
    st.caption("필수 컬럼: id, category, sub_category, region, persona, question")

    st.subheader("브랜드 맵")
    map_file = st.file_uploader(
        "brand_map.xlsx (선택)",
        type=["xlsx"],
        key="map_file",
    )

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

    if (
        st.session_state.questions is None
        or not questions.equals(st.session_state.questions)
    ):
        st.session_state.questions = questions
        st.session_state.current_idx = 0
        st.session_state.results = pd.DataFrame()


if st.session_state.questions is None:
    st.info("왼쪽에서 질문 Excel 파일을 업로드하면 분석을 시작할 수 있습니다.")
    st.subheader("이 버전이 하는 일")
    st.write(
        "질문 선택 → AI 답변 전체 복사/붙여넣기 → 클립보드 HTML의 href 자동 추출 "
        "→ URL 정제 → 도메인 식별 → 브랜드/출처 분류 → 누적 결과 → Excel 다운로드"
    )
    st.stop()


questions = st.session_state.questions
idx = min(st.session_state.current_idx, len(questions) - 1)
q = questions.iloc[idx]

top1, top2, top3, top4 = st.columns(4)
top1.metric("전체 질문", len(questions))
top2.metric("현재 질문", f"{idx + 1}/{len(questions)}")
top3.metric("누적 Citation", len(st.session_state.results))

done_questions = (
    st.session_state.results["question_id"].nunique()
    if not st.session_state.results.empty
    else 0
)
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

    if c1.button(
        "← 이전",
        disabled=idx == 0,
        use_container_width=True,
    ):
        st.session_state.current_idx -= 1
        st.rerun()

    if c2.button(
        "다음 →",
        disabled=idx >= len(questions) - 1,
        use_container_width=True,
    ):
        st.session_state.current_idx += 1
        st.rerun()


with right:
    st.subheader("3. AI 답변")

    st.caption(
        "권장: AI 답변을 마우스로 전체 선택 → Ctrl+C → 아래 박스에서 Ctrl+V. "
        "화면에 주소가 보이지 않아도 하이퍼링크의 href를 읽습니다."
    )

    paste_key = f"rich_answer_{q['id']}_{idx}"
    answer, clipboard_html = rich_paste_box(paste_key)

    detected_urls = merge_urls(answer, clipboard_html)

    if answer:
        html_status = "감지됨" if clipboard_html else "없음"
        st.caption(
            f"클립보드 HTML: {html_status} · 자동 감지 Citation: {len(detected_urls)}개"
        )

        if detected_urls:
            with st.expander("감지된 Citation 미리보기", expanded=False):
                for i, url in enumerate(detected_urls, start=1):
                    st.write(f"{i}. {url}")
        else:
            st.warning(
                "Citation URL을 찾지 못했습니다. ChatGPT의 '복사' 버튼 대신 "
                "답변 영역을 마우스로 전체 선택해서 Ctrl+C한 뒤 다시 붙여넣어 보세요."
            )

    if st.button(
        "Citation 분석 및 저장",
        type="primary",
        use_container_width=True,
    ):
        if not answer.strip():
            st.warning("AI 답변을 붙여넣어 주세요.")
        elif not detected_urls:
            st.warning(
                "답변에서 Citation 링크를 찾지 못했습니다. "
                "답변 영역을 직접 선택해 복사한 뒤 다시 붙여넣어 주세요."
            )
        else:
            result = analyze_answer(
                q,
                answer,
                detected_urls,
                ai_model,
                brand_map,
            )

            old = st.session_state.results

            if not old.empty:
                old = old[
                    ~(
                        (old["question_id"] == q["id"])
                        & (old["ai_model"] == ai_model)
                    )
                ]

            st.session_state.results = pd.concat(
                [old, result],
                ignore_index=True,
            )

            st.success(
                f"{len(result)}개의 Citation을 자동 추출해 저장했습니다."
            )


st.divider()
st.subheader("4. 분석 Dashboard")

res = st.session_state.results

if res.empty:
    st.caption("Citation을 하나 이상 분석하면 Dashboard가 표시됩니다.")
else:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Citation", f"{len(res):,}")
    m2.metric("Unique Domain", f"{res['domain'].nunique():,}")
    m3.metric(
        "Brand",
        f"{res.loc[res['brand'] != '기타', 'brand'].nunique():,}",
    )

    other_rate = res["brand"].eq("기타").mean() * 100
    m4.metric("미분류 비중", f"{other_rate:.1f}%")

    tab1, tab2, tab3 = st.tabs(
        ["브랜드", "출처 유형", "Raw Data"]
    )

    with tab1:
        brand_counts = (
            res["brand"]
            .value_counts()
            .rename_axis("brand")
            .reset_index(name="citations")
        )
        st.bar_chart(brand_counts.set_index("brand"))
        st.dataframe(
            brand_counts,
            use_container_width=True,
            hide_index=True,
        )

    with tab2:
        cat_counts = (
            res["source_category"]
            .value_counts()
            .rename_axis("source_category")
            .reset_index(name="citations")
        )
        st.bar_chart(cat_counts.set_index("source_category"))
        st.dataframe(
            cat_counts,
            use_container_width=True,
            hide_index=True,
        )

    with tab3:
        st.dataframe(
            res,
            use_container_width=True,
            hide_index=True,
        )

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
