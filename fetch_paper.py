<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
  <meta name="apple-mobile-web-app-capable" content="yes" />
  <meta name="apple-mobile-web-app-status-bar-style" content="default" />
  <meta name="apple-mobile-web-app-title" content="MedBrief" />
  <title>Daily MedBrief</title>
  <style>
    :root {
      --bg: #f8f9fa;
      --card: #ffffff;
      --sub-card: #f1f5f9;
      --text: #1e293b;
      --muted: #64748b;
      --accent: #0f766e;
      --accent-soft: #f0fdfa;
      --border: #e2e8f0;
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --bg: #0f1115;
        --card: #181b20;
        --sub-card: #21262e;
        --text: #e2e8f0;
        --muted: #94a3b8;
        --accent: #2dd4bf;
        --accent-soft: #132a28;
        --border: #2a2f38;
      }
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Pretendard", sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.75;
      word-break: keep-all;
      padding: 24px 16px 64px;
    }
    .container { max-width: 720px; margin: 0 auto; }
    header {
      display: flex; justify-content: space-between; align-items: baseline;
      margin-bottom: 24px; padding-bottom: 12px; border-bottom: 1px solid var(--border);
    }
    header h1 { font-size: 1.35rem; font-weight: 700; letter-spacing: -0.02em; }
    header span { font-size: 0.85rem; color: var(--muted); }
    .card {
      background: var(--card); border: 1px solid var(--border);
      border-radius: 16px; padding: 26px 24px; margin-bottom: 24px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.03);
    }
    .badge-row { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
    .badge {
      background: var(--accent-soft); color: var(--accent);
      font-size: 0.78rem; font-weight: 700; padding: 4px 10px; border-radius: 999px;
    }
    .journal { font-size: 0.82rem; color: var(--muted); font-weight: 500; }
    .ko-title { font-size: 1.35rem; font-weight: 700; line-height: 1.4; margin-bottom: 6px; letter-spacing: -0.01em; }
    .en-title { font-size: 0.85rem; color: var(--muted); margin-bottom: 18px; line-height: 1.45; }
    .one-line {
      background: var(--accent-soft); border-left: 4px solid var(--accent);
      padding: 14px 16px; border-radius: 8px; font-weight: 600; font-size: 0.96rem;
      margin-bottom: 24px;
    }
    .section { margin-bottom: 22px; }
    .section h3 {
      font-size: 0.92rem; color: var(--accent); margin-bottom: 6px; font-weight: 700;
      display: flex; align-items: center; gap: 6px;
    }
    .section p { font-size: 0.96rem; }
    .takeaway-list { padding-left: 18px; font-size: 0.96rem; }
    .takeaway-list li { margin-bottom: 8px; }
    .concepts-box {
      margin-top: 24px;
      padding: 18px;
      background: var(--sub-card);
      border-radius: 12px;
      border: 1px solid var(--border);
    }
    .concepts-box h3 {
      font-size: 0.9rem;
      color: var(--accent);
      margin-bottom: 12px;
      font-weight: 700;
    }
    .concept-item { margin-bottom: 14px; }
    .concept-item:last-child { margin-bottom: 0; }
    .concept-term { font-weight: 700; font-size: 0.93rem; margin-bottom: 3px; }
    .concept-desc { font-size: 0.9rem; opacity: 0.92; line-height: 1.65; }
    .pubmed-link {
      display: inline-block; margin-top: 20px; font-size: 0.85rem;
      color: var(--accent); text-decoration: none; font-weight: 600;
    }
    .archive-header {
      display: flex; justify-content: space-between; align-items: center;
      margin: 32px 0 14px; gap: 12px;
    }
    .archive-header h2 { font-size: 1.05rem; }
    input[type="search"] {
      padding: 8px 12px; border-radius: 10px; border: 1px solid var(--border);
      background: var(--card); color: var(--text); font-size: 0.88rem; width: 200px;
    }
    .archive-item {
      background: var(--card); border: 1px solid var(--border); border-radius: 12px;
      padding: 14px 16px; margin-bottom: 10px; cursor: pointer; transition: border-color 0.15s;
    }
    .archive-item:hover { border-color: var(--accent); }
    .archive-item .meta { font-size: 0.78rem; color: var(--muted); margin-bottom: 4px; }
    .archive-item .title { font-size: 0.95rem; font-weight: 600; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>Daily MedBrief</h1>
      <span id="today-date"></span>
    </header>

    <main id="featured-paper">
      <div class="card">데이터를 불러오는 중입니다...</div>
    </main>

    <div class="archive-header">
      <h2>이전 브리핑 아카이브</h2>
      <input type="search" id="search-input" placeholder="키워드·분과 검색..." />
    </div>
    <div id="archive-list"></div>
  </div>

  <script>
    let allPapers = [];

    function renderFeatured(paper) {
      const container = document.getElementById('featured-paper');
      if (!paper) {
        container.innerHTML = `<div class="card">아직 수집된 논문이 없습니다. GitHub Actions를 실행해 첫 논문을 가져와 주세요.</div>`;
        return;
      }
      document.getElementById('today-date').textContent = paper.date;

      const conceptsHtml = (paper.key_concepts && paper.key_concepts.length > 0)
        ? `
          <div class="concepts-box">
            <h3>📖 함께 알아둘 핵심 의학 용어</h3>
            ${paper.key_concepts.map(c => `
              <div class="concept-item">
                <div class="concept-term">• ${c.term}</div>
                <div class="concept-desc">${c.explanation}</div>
              </div>
            `).join('')}
          </div>
        `
        : '';

      // 새 포맷(스토리텔링형)과 기존 포맷 모두 호환 렌더링
      let bodyHtml = '';
      if (paper.disease_background) {
        const takeaways = Array.isArray(paper.study_takeaway)
          ? `<ul class="takeaway-list">${paper.study_takeaway.map(t => `<li>${t}</li>`).join('')}</ul>`
          : `<p>${paper.study_takeaway || ''}</p>`;

        bodyHtml = `
          <div class="section"><h3>🩺 먼저 알아야 할 질환 이야기</h3><p>${paper.disease_background}</p></div>
          <div class="section"><h3>🧬 핵심 타겟과 작용 원리</h3><p>${paper.key_mechanism}</p></div>
          <div class="section"><h3>📌 이번 연구에서 확인된 핵심</h3>${takeaways}</div>
          <div class="section"><h3>🏥 진료실 적용 포인트</h3><p>${paper.clinical_point}</p></div>
        `;
      } else {
        bodyHtml = `
          <div class="section"><h3>배경 및 목적</h3><p>${paper.background}</p></div>
          <div class="section"><h3>연구 방법</h3><p>${paper.methods}</p></div>
          <div class="section"><h3>핵심 결과</h3><p>${paper.results}</p></div>
          <div class="section"><h3>임상적 의의 및 한계</h3><p>${paper.clinical_implication}</p></div>
        `;
      }

      container.innerHTML = `
        <article class="card">
          <div class="badge-row">
            <span class="badge">${paper.category}</span>
            <span class="journal">${paper.journal}</span>
          </div>
          <h2 class="ko-title">${paper.ko_title}</h2>
          <p class="en-title">${paper.original_title}</p>
          <div class="one-line">💡 ${paper.one_line}</div>
          ${bodyHtml}
          ${conceptsHtml}
          <a class="pubmed-link" href="${paper.url}" target="_blank" rel="noopener">PubMed 원문 보기 (PMID: ${paper.pmid}) →</a>
        </article>
      `;
    }

    function renderArchive(papers) {
      const list = document.getElementById('archive-list');
      list.innerHTML = papers.map((p, idx) => `
        <div class="archive-item" onclick="selectPaper(${idx})">
          <div class="meta">${p.date} · ${p.category} · ${p.journal}</div>
          <div class="title">${p.ko_title}</div>
        </div>
      `).join('');
    }

    function selectPaper(index) {
      renderFeatured(allPapers[index]);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    document.getElementById('search-input').addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase();
      const filtered = allPapers.filter(p =>
        p.ko_title.toLowerCase().includes(q) ||
        p.original_title.toLowerCase().includes(q) ||
        p.category.toLowerCase().includes(q) ||
        p.journal.toLowerCase().includes(q)
      );
      renderArchive(filtered);
    });

    fetch('./data/papers.json?t=' + Date.now())
      .then(res => res.json())
      .then(data => {
        allPapers = data;
        renderFeatured(allPapers[0]);
        renderArchive(allPapers);
      })
      .catch(() => renderFeatured(null));
  </script>
</body>
</html>
