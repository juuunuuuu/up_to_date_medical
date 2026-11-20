import json
import os
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from google import genai
from google.genai import types

PUBMED_QUERY = (
    '("New England Journal of Medicine"[Journal] OR "Lancet"[Journal] OR '
    '"JAMA"[Journal] OR "Nature medicine"[Journal] OR "BMJ"[Journal] OR '
    '"Annals of internal medicine"[Journal] OR "Neurology"[Journal] OR "Circulation"[Journal]) '
    'AND hasabstract[text] '
    'NOT ("Letter"[pt] OR "Editorial"[pt] OR "Comment"[pt] OR "Published Erratum"[pt])'
)
DATA_FILE = "data/papers.json"


def get_recent_pmids(query: str, retmax: int = 25) -> list[str]:
    encoded_query = urllib.parse.quote(query)
    url = (
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"
        f"db=pubmed&term={encoded_query}&retmax={retmax}&sort=pub+date&retmode=json"
    )
    with urllib.request.urlopen(url) as res:
        data = json.loads(res.read().decode("utf-8"))
        return data.get("esearchresult", {}).get("idlist", [])


def fetch_candidates_details(pmids: list[str]) -> list[dict]:
    if not pmids:
        return []
    ids_str = ",".join(pmids)
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={ids_str}&retmode=xml"
    with urllib.request.urlopen(url) as res:
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

        if pmid and len(abstract) > 300:
            candidates.append({
                "pmid": pmid,
                "title": title,
                "journal": journal,
                "abstract": abstract,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            })

    return candidates


def select_and_summarize(candidates: list[dict]) -> tuple[dict, dict]:
    client = genai.Client()

    candidates_text = ""
    for idx, c in enumerate(candidates):
        candidates_text += (
            f"\n--- [후보 {idx}] ---\n"
            f"저널: {c['journal']}\n"
            f"제목: {c['title']}\n"
            f"초록:\n{c['abstract']}\n"
        )

    prompt = f"""
    당신은 후배 의대생에게 최신 임상 의학 지식을 쉽고 명쾌하게 설명해 주는 친절한 임상 멘토입니다.
    아래 {len(candidates)}개의 최신 논문 후보 중 **임상적으로 배울 점이 많고 중요한 연구 1편**을 고른 뒤, 딱딱한 논문 번역투가 아닌 **이야기하듯 술술 읽히는 임상 브리핑**을 작성해 주세요.

    [작성 원칙 - 매우 중요]
    1. **논문 초록 요약투 금지:** "1차 평가변수는 ~였다", "최소제곱평균 차이 -0.6일(97.5% CI, p=0.022)" 같은 딱딱한 연구 방법론과 복잡한 통계 수치는 과감히 빼세요.
    2. **기초 의학 개념부터 친절하게:** 논문에 등장하는 핵심 질환(예: 편두통)과 핵심 타겟/물질(예: CGRP, 특정 수용체, 병태생리 기전)이 무엇인지 기본 개념부터 알기 쉽게 설명해 주세요.
    3. **가독성 최우선:** 한 문장을 길게 쓰지 말고, 핵심 결과는 짧은 불릿 포인트로 정리해 아침에 2분 만에 술술 읽히게 만드세요.

    [후보 논문 목록]
    {candidates_text}

    반드시 아래 JSON 스키마로만 응답하세요:
    {{
      "selected_index": 선택한 후보의 번호 (0부터 {len(candidates) - 1} 사이의 정수),
      "ko_title": "핵심 내용이 직관적으로 와닿는 흥미로운 한국어 제목",
      "category": "분과 1개 (예: 신경과, 순환기내과, 종양학, 감염내과, 내분비내과 등)",
      "one_line": "이 연구가 왜 의미 있는지 한 줄로 쉽게 요약",
      "disease_background": "1) 먼저 알아야 할 질환 이야기: 이 연구가 다루는 질환(예: 편두통 등)의 핵심 특징과 기존 치료법이 가진 현실적인 한계를 배경지식이 없어도 이해할 수 있게 설명 (3~4문장)",
      "key_mechanism": "2) 핵심 타겟과 작용 원리: 이 논문에서 가장 중요한 의학적 개념·물질·기전(예: CGRP가 무엇이고 어떤 역할을 하는지, 약물이 어떻게 작동하는지 등)을 알기 쉽게 풀어서 설명 (3~4문장)",
      "study_takeaway": [
        "연구 대상과 투여/치료 방식을 한 줄로 쉽게 요약",
        "가장 핵심적인 치료 효과를 쉬운 수치로 요약 (복잡한 p값, 신뢰구간 제외)",
        "부작용이나 안전성 측면을 한 줄로 요약"
      ],
      "clinical_point": "진료실 적용 포인트: 앞으로 실제 임상 현장에서 어떤 환자에게 어떻게 활용될 수 있을지 명쾌하게 정리 (2문장)",
      "key_concepts": [
        {{
          "term": "함께 알아두면 좋은 핵심 의학 용어 (영어 원어 병기)",
          "explanation": "교과서적인 딱딱한 정의 대신, 임상적 맥락에서 왜 중요한지 쉽게 풀어쓴 설명 (2~3문장)"
        }}
      ]
    }}
    ※ key_concepts에는 질환/생리/약리 등 순수 의학 개념만 2~3개 작성하고, 통계·연구방법론 용어는 절대 넣지 마세요.
    """

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.35,
        ),
    )
    result = json.loads(response.text)
    idx = result.pop("selected_index", 0)
    if not (0 <= idx < len(candidates)):
        idx = 0

    return candidates[idx], result


def main():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            papers = json.load(f)
    else:
        papers = []

    existing_pmids = {p["pmid"] for p in papers}
    recent_pmids = get_recent_pmids(PUBMED_QUERY, retmax=25)
    unseen_pmids = [p for p in recent_pmids if p not in existing_pmids][:10]

    candidates = fetch_candidates_details(unseen_pmids)
    if not candidates:
        print("새로운 후보 논문이 없습니다.")
        return

    chosen_article, summary = select_and_summarize(candidates)

    new_entry = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "pmid": chosen_article["pmid"],
        "original_title": chosen_article["title"],
        "journal": chosen_article["journal"],
        "url": chosen_article["url"],
        **summary,
    }

    papers.insert(0, new_entry)
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(papers, f, ensure_ascii=False, indent=2)

    print(f"선별 및 저장 완료: {new_entry['ko_title']} (PMID: {new_entry['pmid']})")


if __name__ == "__main__":
    main()
