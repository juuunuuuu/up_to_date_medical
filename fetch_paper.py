import json
import os
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from google import genai
from google.genai import types

# 신경학, 응급의학, 임상약리학 주요 저널 + 3대 종합저널 내 관련 주제 필터
PUBMED_QUERY = (
    '('
    '("Lancet Neurology"[Journal] OR "JAMA Neurology"[Journal] OR "Neurology"[Journal] OR "Stroke"[Journal] OR '
    '"Annals of Emergency Medicine"[Journal] OR "Resuscitation"[Journal] OR "Critical Care Medicine"[Journal] OR '
    '"Clinical Pharmacology and Therapeutics"[Journal] OR "British Journal of Clinical Pharmacology"[Journal] OR "Drugs"[Journal]) '
    'OR '
    '(("New England Journal of Medicine"[Journal] OR "Lancet"[Journal] OR "JAMA"[Journal]) AND '
    '(neurology[tiab] OR neurological[tiab] OR stroke[tiab] OR migraine[tiab] OR epilepsy[tiab] OR dementia[tiab] OR '
    'emergency[tiab] OR resuscitation[tiab] OR trauma[tiab] OR overdose[tiab] OR toxicology[tiab] OR sepsis[tiab] OR shock[tiab] OR '
    'pharmacology[tiab] OR pharmacokinetics[tiab] OR pharmacodynamics[tiab] OR "drug interaction"[tiab] OR "adverse drug"[tiab]))'
    ') '
    'AND hasabstract[text] '
    'NOT ("Letter"[pt] OR "Editorial"[pt] OR "Comment"[pt] OR "Published Erratum"[pt])'
)
DATA_FILE = "data/papers.json"


def get_recent_pmids(query: str, retmax: int = 30) -> list[str]:
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


def select_and_summarize(candidates: list[dict], recent_categories: list[str]) -> tuple[dict, dict]:
    client = genai.Client()

    candidates_text = ""
    for idx, c in enumerate(candidates):
        candidates_text += (
            f"\n--- [후보 {idx}] ---\n"
            f"저널: {c['journal']}\n"
            f"제목: {c['title']}\n"
            f"초록:\n{c['abstract']}\n"
        )

    recent_info = ", ".join(recent_categories) if recent_categories else "없음"

    prompt = f"""
    당신은 후배에게 최신 임상 의학 지식을 쉽고 명쾌하게 설명해 주는 친절한 임상 멘토입니다.
    현재 **[신경학, 응급의학, 임상약리학]** 세 과목을 집중 학습 중입니다.
    아래 {len(candidates)}개의 최신 논문 후보 중 **이 세 분야와 가장 밀접하고 임상적으로 배울 점이 많은 핵심 연구 1편**을 고른 뒤, 딱딱한 논문 번역투가 아닌 **이야기하듯 술술 읽히는 임상 브리핑**을 작성해 주세요.

    [선별 기준]
    1. 반드시 **신경학, 응급의학, 임상약리학** 중 하나에 명확히 해당하는 연구를 선택하세요.
    2. 최근 선정된 분야 기록: [{recent_info}] -> 가능하면 최근에 연달아 나온 분야보다 다른 분야가 골고루 섞이도록 우선순위를 두세요.
    3. 대규모 임상시험, 진료 지침 변화, 핵심 약물 기전(PK/PD, 수용체 작용)이나 응급 처치 프로토콜을 다룬 연구를 우선하세요.

    [작성 원칙 - 매우 중요]
    1. **논문 초록 요약투 금지:** "1차 평가변수는 ~였다", "최소제곱평균 차이(97.5% CI, p=0.022)" 같은 딱딱한 연구 방법론과 복잡한 통계 수치는 과감히 빼세요.
    2. **기초 개념부터 친절하게:**
       - 신경학이면 핵심 신경해부·생리 및 질환 기전을,
       - 응급의학이면 급성기 병태생리와 초기 처치의 핵심 원리를,
       - 임상약리학이면 약물의 작용 기전(MOA), 약동학/약력학(PK/PD), 부작용 및 상호작용 원리를 배경지식이 없어도 이해할 수 있게 쉽게 설명해 주세요.
    3. **가독성 최우선:** 한 문장을 길게 쓰지 말고, 핵심 결과는 짧은 불릿 포인트로 정리해 아침에 2분 만에 술술 읽히게 만드세요.

    [후보 논문 목록]
    {candidates_text}

    반드시 아래 JSON 스키마로만 응답하세요:
    {{
      "selected_index": 선택한 후보의 번호 (0부터 {len(candidates) - 1} 사이의 정수),
      "ko_title": "핵심 내용이 직관적으로 와닿는 흥미로운 한국어 제목",
      "category": "신경학, 응급의학, 임상약리학 중 가장 적합한 1개만 정확히 기입",
      "one_line": "이 연구가 왜 의미 있는지 한 줄로 쉽게 요약",
      "disease_background": "1) 먼저 알아야 할 임상 배경: 이 연구가 다루는 질환이나 응급/약물 상황의 핵심 특징과 기존 치료의 현실적인 한계를 쉽게 설명 (3~4문장)",
      "key_mechanism": "2) 핵심 타겟과 작용 원리: 이 논문에서 가장 중요한 병태생리 기전, 약물 작용 원리(MOA/PK/PD), 혹은 응급 처치의 의학적 원리를 알기 쉽게 풀어서 설명 (3~4문장)",
      "study_takeaway": [
        "연구 대상과 투여/치료 방식을 한 줄로 쉽게 요약",
        "가장 핵심적인 치료 효과를 쉬운 수치로 요약 (복잡한 p값, 신뢰구간 제외)",
        "부작용, 금기증 또는 안전성 측면을 한 줄로 요약"
      ],
      "clinical_point": "진료실·응급실 적용 포인트: 실제 임상 현장에서 어떤 환자에게 어떻게 활용될 수 있을지 명쾌하게 정리 (2문장)",
      "key_concepts": [
        {{
          "term": "함께 알아두면 좋은 핵심 의학·약리 용어 (영어 원어 병기)",
          "explanation": "교과서적인 딱딱한 정의 대신, 임상적 맥락에서 왜 중요한지 쉽게 풀어쓴 설명 (2~3문장)"
        }}
      ]
    }}
    ※ key_concepts에는 질환/생리/약리/응급의학 등 순수 의학 개념만 2~3개 작성하고, 통계·연구방법론 용어는 절대 넣지 마세요.
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
    recent_categories = [p.get("category", "") for p in papers[:3]]

    recent_pmids = get_recent_pmids(PUBMED_QUERY, retmax=30)
    unseen_pmids = [p for p in recent_pmids if p not in existing_pmids][:12]

    candidates = fetch_candidates_details(unseen_pmids)
    if not candidates:
        print("새로운 후보 논문이 없습니다.")
        return

    chosen_article, summary = select_and_summarize(candidates, recent_categories)

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

    print(f"선별 및 저장 완료: [{new_entry['category']}] {new_entry['ko_title']} (PMID: {new_entry['pmid']})")


if __name__ == "__main__":
    main()
