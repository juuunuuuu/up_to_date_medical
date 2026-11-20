import json
import os
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from google import genai
from google.genai import types

# 주요 의학 저널 + 단순 코멘트/사설 제외 필터
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

        # 초록이 너무 짧은 단신은 제외
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
    당신은 임상의학 및 의과학 저널의 수석 에디터입니다.
    아래 {len(candidates)}개의 최신 논문 후보 중 **임상적 중요도와 파급력이 가장 높은 핵심 연구 1편**을 고른 뒤, 매일 아침 깊이 있게 학습할 수 있도록 한국어로 브리핑을 작성해 주세요.

    [선별 기준]
    1. 대규모 무작위 대조시험(RCT), 진료 지침을 바꿀 수 있는 임상 연구, 핵심 병태생리/신약 기전을 규명한 연구를 최우선으로 선택하세요.
    2. 지엽적인 증례나 단순 행정·정책 코멘트는 피하세요.

    [후보 논문 목록]
    {candidates_text}

    반드시 아래 JSON 스키마로만 응답하세요:
    {{
      "selected_index": 선택한 후보의 번호 (0부터 {len(candidates) - 1} 사이의 정수),
      "ko_title": "직관적이고 명확한 한국어 제목",
      "category": "분과 1개 (예: 신경과, 순환기내과, 종양학, 감염내과, 내분비내과 등)",
      "one_line": "이 연구가 왜 중요한지 한 줄 핵심 결론",
      "background": "연구 배경 및 목적 (2~3문장)",
      "methods": "연구 대상 및 방법 (핵심 수치 포함, 2~3문장)",
      "results": "주요 결과 및 통계적 수치 (2~3문장)",
      "clinical_implication": "임상적 의의 및 한계점 (2문장)",
      "key_concepts": [
        {{
          "term": "순수 의학 개념 용어 (영어 원어 병기)",
          "explanation": "질환의 병태생리(pathophysiology), 해부·생리학적 기전, 약물의 작용 기전(MOA), 또는 핵심 진단·임상 특징을 의학적으로 정확하고 깊이 있게 풀어쓴 설명 (3~4문장)"
        }}
      ]
    }}

    [중요 제약사항]
    - key_concepts에는 **오직 순수 의학 개념(질환, 병태생리, 생리학, 약리 기전, 해부학, 바이오마커 등)만 3~4개** 작성하세요.
    - 성향점수 매칭, 콕스 비례위험 모델, 메타분석, 위험비(HR), 신뢰구간 같은 **통계·역학·연구방법론 용어는 절대 포함하지 마세요.**
    """

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2,
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
