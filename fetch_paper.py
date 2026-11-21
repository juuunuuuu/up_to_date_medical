import json
import os
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from google import genai
from google.genai import types

# ==============================================================================
# [필수 수정] 아래 두 줄만 본인의 ntfy 채널명과 개인 브리핑 웹사이트 주소로 바꾸세요!
# ==============================================================================
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "haruachim_jun_0803")
SITE_URL = "https://juuunuuuu.github.io/up_to_date_medical/"
# ==============================================================================

# 소화기학 · 순환기학 · 내분비학 주요 임상 연구 필터 (사설·코멘트 제외)
PUBMED_QUERY = (
    '('
    '("Gastroenterology"[Journal] OR "Gut"[Journal] OR "Hepatology"[Journal] OR "Gastroenterology"[MeSH Terms]) OR '
    '("Circulation"[Journal] OR "European heart journal"[Journal] OR "Journal of the American College of Cardiology"[Journal] OR "Cardiology"[MeSH Terms]) OR '
    '("Diabetes care"[Journal] OR "The lancet. Diabetes & endocrinology"[Journal] OR "Journal of clinical endocrinology and metabolism"[Journal] OR "Endocrinology"[MeSH Terms]) OR '
    '(("New England Journal of Medicine"[Journal] OR "Lancet"[Journal] OR "JAMA"[Journal]) AND '
    '(gastroenterology[tiab] OR hepatology[tiab] OR cardiology[tiab] OR cardiovascular[tiab] OR heart failure[tiab] OR diabetes[tiab] OR endocrinology[tiab] OR metabolic[tiab]))'
    ') '
    'AND hasabstract[text] '
    'NOT ("Letter"[pt] OR "Editorial"[pt] OR "Comment"[pt] OR "Published Erratum"[pt])'
)

DATA_DIR = "data"
PAPERS_FILE = "data/papers.json"


def get_recent_pmids(query: str, retmax: int = 30) -> list[str]:
    encoded_query = urllib.parse.quote(query)
    url = (
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"
        f"db=pubmed&term={encoded_query}&retmax={retmax}&sort=pub+date&retmode=json"
    )
    with urllib.request.urlopen(url, timeout=30) as res:
        data = json.loads(res.read().decode("utf-8"))
        return data.get("esearchresult", {}).get("idlist", [])


def fetch_candidates_details(pmids: list[str]) -> list[dict]:
    if not pmids:
        return []
    ids_str = ",".join(pmids)
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={ids_str}&retmode=xml"
    with urllib.request.urlopen(url, timeout=30) as res:
        xml_data = res.read()

    root = ET.fromstring(xml_data)
    candidates = []
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//MedlineCitation/PMID", default="").strip()
        title_elem = article.find(".//ArticleTitle")
        title = "".join(title_elem.itertext()).strip() if title_elem is not None else ""
        journal = article.findtext(".//Journal/Title", default="Unknown Journal")

        abstract_parts = []
        for elem in article.findall(".//Abstract/AbstractText"):
            label = elem.attrib.get("Label", "")
            text = "".join(elem.itertext()).strip()
            abstract_parts.append(f"{label}: {text}" if label else text)
        abstract = "\n".join(abstract_parts)

        if pmid and len(abstract) > 350:
            candidates.append({
                "pmid": pmid,
                "title": title,
                "journal": journal,
                "abstract": abstract,
            })
    return candidates


def summarize_daily_paper(candidates: list[dict]) -> tuple[dict, dict]:
    client = genai.Client()
    candidates_text = ""
    for idx, c in enumerate(candidates):
        candidates_text += f"\n--- [후보 {idx}] ---\n저널: {c['journal']}\n제목: {c['title']}\n초록:\n{c['abstract']}\n"

    prompt = f"""
    당신은 의대생·의료인을 위한 아침 의학 브리핑 에디터입니다.
    아래 {len(candidates)}개의 최신 논문 후보 중 **소화기학, 순환기학, 내분비학** 세 과목에 해당하면서 임상적으로 가장 중요하고 흥미로운 연구 1편을 고르세요.

    [작성 원칙]
    - 연구 논문과 수필 사이의 담백하고 읽기 편한 어조로 작성하세요.
    - 딱딱한 통계 나열("p<0.001로 유의하였다") 대신, 진료실에서 환자가 물어볼 법한 질문에서 시작해 기전과 임상적 의미를 이야기하듯 풀어주세요.
    - 핵심 의학 용어는 한국어와 영어 원어를 함께 표기하세요.

    [후보 논문 목록]
    {candidates_text}

    반드시 아래 JSON 형식으로만 응답하세요:
    {{
      "selected_index": 선택한 후보 번호 (0 ~ {len(candidates) - 1}),
      "specialty": "소화기학" 또는 "순환기학" 또는 "내분비학",
      "headline": "호기심을 자극하는 명쾌한 한국어 제목 (1~2줄)",
      "one_line_takeaway": "핵심 결론 1줄 요약",
      "clinical_context": "먼저 알아야 할 질환 이야기 (진료실 질문과 기존 치료의 한계, 4~5문장)",
      "mechanism": "핵심 타겟과 작용 원리 (병태생리 및 약물 기전, 4~5문장)",
      "key_findings": [
        "연구 대상 및 규모 요약 1줄",
        "핵심 임상 결과 수치 요약 1줄",
        "실제 치료 전략에 주는 시사점 1줄"
      ],
      "clinical_pearl": "진료실 적용 포인트 (환자에게 어떻게 설명하고 적용할지 3~4문장)",
      "key_terms": [
        {{
          "term": "핵심 의학 용어 1 (영어 원어)",
          "desc": "임상적 맥락을 담은 쉬운 설명 (2문장)"
        }},
        {{
          "term": "핵심 의학 용어 2 (영어 원어)",
          "desc": "임상적 맥락을 담은 쉬운 설명 (2문장)"
        }}
      ]
    }}
    """

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.4,
        ),
    )
    result = json.loads(response.text)
    idx = result.pop("selected_index", 0)
    if not (0 <= idx < len(candidates)):
        idx = 0
    return candidates[idx], result


def send_ntfy_notification(briefing: dict):
    if not NTFY_TOPIC:
        return
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    title = f"[{briefing['specialty']}] 오늘의 아침 논문 브리핑"
    message = f"{briefing['headline']}\n👉 {briefing['one_line_takeaway']}"

    req = urllib.request.Request(
        url,
        data=message.encode("utf-8"),
        headers={
            "Title": title.encode("utf-8"),
            "Click": SITE_URL.encode("utf-8"),
            "Priority": "high",
            "Tags": "stethoscope,sunrise",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            print(f"ntfy 알림 전송 완료: {res.status}")
    except Exception as e:
        print(f"ntfy 알림 전송 실패: {e}")


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(PAPERS_FILE):
        with open(PAPERS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
            existing_papers = raw if isinstance(raw, list) else [raw]
    else:
        existing_papers = []

    seen_pmids = {str(p.get("pmid")) for p in existing_papers if p.get("pmid")}
    recent_pmids = get_recent_pmids(PUBMED_QUERY, retmax=30)
    unseen_pmids = [p for p in recent_pmids if p not in seen_pmids][:12]
    candidates = fetch_candidates_details(unseen_pmids)

    if not candidates:
        print("새로운 후보 논문이 없습니다.")
        return

    chosen, briefing = summarize_daily_paper(candidates)
    briefing["pmid"] = chosen["pmid"]
    briefing["original_title"] = chosen["title"]
    briefing["journal"] = chosen["journal"]
    briefing["date"] = datetime.now().strftime("%Y-%m-%d")

    updated_papers = [briefing] + existing_papers[:29]
    with open(PAPERS_FILE, "w", encoding="utf-8") as f:
        json.dump(updated_papers, f, ensure_ascii=False, indent=2)

    send_ntfy_notification(briefing)
    print(f"브리핑 저장 완료 [{briefing['specialty']}]: {briefing['headline']}")


if __name__ == "__main__":
    main()
