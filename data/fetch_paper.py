import json
import os
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from google import genai
from google.genai import types

# 1. 관심 검색어 및 저널 설정 (원하는 대로 수정 가능)
# 예: NEJM, Lancet, JAMA, Nature Medicine, Neurology 등 주요 저널 + 최신 임상 연구
PUBMED_QUERY = (
    '("New England Journal of Medicine"[Journal] OR "Lancet"[Journal] OR '
    '"JAMA"[Journal] OR "Nature medicine"[Journal] OR "Neurology"[Journal]) '
    'AND hasabstract[text]'
)
DATA_FILE = "data/papers.json"


def get_recent_pmids(query: str, retmax: int = 15) -> list[str]:
    encoded_query = urllib.parse.quote(query)
    url = (
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"
        f"db=pubmed&term={encoded_query}&retmax={retmax}&sort=pub+date&retmode=json"
    )
    with urllib.request.urlopen(url) as res:
        data = json.loads(res.read().decode("utf-8"))
        return data.get("esearchresult", {}).get("idlist", [])


def fetch_article_details(pmid: str) -> dict | None:
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={pmid}&retmode=xml"
    with urllib.request.urlopen(url) as res:
        xml_data = res.read()

    root = ET.fromstring(xml_data)
    article = root.find(".//PubmedArticle")
    if article is None:
        return None

    title = "".join(article.find(".//ArticleTitle").itertext()).strip()
    journal = article.findtext(".//Journal/Title", default="Unknown Journal")
    
    abstract_parts = []
    for elem in article.findall(".//Abstract/AbstractText"):
        label = elem.attrib.get("Label", "")
        text = "".join(elem.itertext()).strip()
        abstract_parts.append(f"{label}: {text}" if label else text)
    abstract = "\n".join(abstract_parts)

    if not abstract:
        return None

    return {
        "pmid": pmid,
        "title": title,
        "journal": journal,
        "abstract": abstract,
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
    }


def summarize_with_gemini(article: dict) -> dict:
    client = genai.Client()  # 환경변수 GEMINI_API_KEY 자동 인식

    prompt = f"""
    당신은 의학 연구 브리핑 에디터입니다. 아래 PubMed 논문의 초록을 읽고, 매일 아침 3분 안에 핵심을 파악할 수 있도록 한국어로 구조화해 요약해 주세요.
    전문 의학 용어는 원어(영어)를 그대로 병기하거나 자연스럽게 사용해 정확도를 유지하세요.

    [논문 정보]
    - 저널: {article['journal']}
    - 제목: {article['title']}
    - 초록: {article['abstract']}

    반드시 아래 JSON 스키마로만 응답하세요:
    {{
      "ko_title": "직관적이고 명확한 한국어 제목",
      "category": "분과 또는 핵심 키워드 1개 (예: 신경과, 순환기내과, 종양학, 의학AI 등)",
      "one_line": "이 연구가 왜 중요한지 한 줄 핵심 결론",
      "background": "연구 배경 및 목적 (2~3문장)",
      "methods": "연구 대상 및 방법 (핵심 수치 포함, 2~3문장)",
      "results": "주요 결과 및 통계적 수치 (2~3문장)",
      "clinical_implication": "임상적 의의 및 한계점 (2문장)"
    }}
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.3,
        ),
    )
    return json.loads(response.text)


def main():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            papers = json.load(f)
    else:
        papers = []

    existing_pmids = {p["pmid"] for p in papers}
    recent_pmids = get_recent_pmids(PUBMED_QUERY)

    selected_article = None
    for pmid in recent_pmids:
        if pmid not in existing_pmids:
            details = fetch_article_details(pmid)
            if details:
                selected_article = details
                break

    if not selected_article:
        print("새로운 초록 포함 논문이 없습니다.")
        return

    summary = summarize_with_gemini(selected_article)
    new_entry = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "pmid": selected_article["pmid"],
        "original_title": selected_article["title"],
        "journal": selected_article["journal"],
        "url": selected_article["url"],
        **summary,
    }

    papers.insert(0, new_entry)  # 최신 논문이 맨 위로 오도록 추가
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(papers, f, ensure_ascii=False, indent=2)

    print(f"저장 완료: {new_entry['ko_title']} (PMID: {new_entry['pmid']})")


if __name__ == "__main__":
    main()
