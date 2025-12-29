import os
import re
from typing import Any, Dict, List, Optional
from fastapi.responses import RedirectResponse
import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

if os.getenv("RENDER") is None:   # Render 환경이 아니면(=로컬이면) .env 로드
    load_dotenv()


SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or ""

app = FastAPI(title="FastAPI + Supabase Dashboard")

TABLES = {
    "trend": "trend",
    "party_domain_metrics": "party_domain_metrics",
    "law_reform_gpt": "law_reform_gpt",
    # ✅ DB 스크린샷 기준: law_reform_state 가 맞습니다.
    "law_reform_state": "law_reform_state",
    "text_recap": "text_recap",
    "people_recap": "people_recap",
    "data_request_recap": "data_request_recap",
    # 필요하면 나중에 사용
    "questions": "questions",
}

def _headers() -> Dict[str, str]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        # run.cmd로 실행하면 들어옵니다.
        return {}
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept": "application/json",
    }

async def sb_select(table: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="SUPABASE_URL / SUPABASE_KEY 가 설정되지 않았습니다. run.cmd로 실행하세요.")
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, headers=_headers(), params=params)
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()

def session_label(n: int) -> str:
    return f"{n}회"

def parse_session_no(s: str) -> Optional[int]:
    if not s:
        return None
    m = re.search(r"(\d+)", str(s))
    return int(m.group(1)) if m else None

# -------------------------
# API (좌상단)
# -------------------------

@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")

@app.get("/api/questions")
async def api_questions(limit: int = 5000, offset: int = 0):
    return await sb_select(TABLES["questions"], {"select": "*", "limit": limit, "offset": offset})


@app.get("/api/trend")
async def api_trend(limit: int = 5000, offset: int = 0):
    return await sb_select(TABLES["trend"], {"select": "*", "limit": limit, "offset": offset})

@app.get("/api/party-domain-metrics")
async def api_party_domain_metrics(limit: int = 5000, offset: int = 0):
    return await sb_select(TABLES["party_domain_metrics"], {"select": "*", "limit": limit, "offset": offset})

# ✅ 레거시 경로(사용자 테스트용): /trend 로도 뜨게
@app.get("/trend")
async def trend_alias(limit: int = 5000, offset: int = 0):
    return await api_trend(limit=limit, offset=offset)

# -------------------------
# API (우측: law)
# -------------------------
@app.get("/api/law/state")
async def api_law_state(limit: int = 5000, offset: int = 0):
    # year, quarter, party, num_law_reform_requests 등
    return await sb_select(TABLES["law_reform_state"], {"select": "*", "limit": limit, "offset": offset})

@app.get("/api/law/gpt")
async def api_law_gpt(limit: int = 5000, offset: int = 0):
    # is_law_reform_gpt, law_reform_type_gpt 등
    return await sb_select(TABLES["law_reform_gpt"], {"select": "*", "limit": limit, "offset": offset})

# -------------------------
# API (하단: recap, 회차 선택)
# -------------------------
@app.get("/api/sessions")
async def api_sessions():
    # text_recap(회차), people_recap(회차), data_request_recap(회의회차)에서 회차 모아 dropdown 구성
    rows_text = await sb_select(TABLES["text_recap"], {"select": "회차", "limit": 10000, "offset": 0})
    rows_people = await sb_select(TABLES["people_recap"], {"select": "회차", "limit": 10000, "offset": 0})
    rows_data = await sb_select(TABLES["data_request_recap"], {"select": "회의회차", "limit": 10000, "offset": 0})

    ses = set()
    for r in rows_text:
        n = parse_session_no(r.get("회차"))
        if n: ses.add(n)
    for r in rows_people:
        n = parse_session_no(r.get("회차"))
        if n: ses.add(n)
    for r in rows_data:
        n = parse_session_no(r.get("회의회차"))
        if n: ses.add(n)

    return sorted(ses)

@app.get("/api/recap/text")
async def api_recap_text(session_no: int = Query(...), limit: int = 50, offset: int = 0):
    lab = session_label(session_no)
    return await sb_select(
        TABLES["text_recap"],
        {"select": "*", "회차": f"eq.{lab}", "limit": limit, "offset": offset},
    )

@app.get("/api/recap/people")
async def api_recap_people(session_no: int = Query(...), limit: int = 100, offset: int = 0):
    lab = session_label(session_no)
    return await sb_select(
        TABLES["people_recap"],
        {"select": "*", "회차": f"eq.{lab}", "limit": limit, "offset": offset},
    )

@app.get("/api/recap/data")
async def api_recap_data(session_no: int = Query(...), limit: int = 100, offset: int = 0):
    lab = session_label(session_no)
    return await sb_select(
        TABLES["data_request_recap"],
        {"select": "*", "회의회차": f"eq.{lab}", "limit": limit, "offset": offset},
    )

# -------------------------
# DASHBOARD
# -------------------------
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return HTML_PAGE

HTML_PAGE = r"""
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <title>통합 대시보드</title>
  <script src="https://cdn.plot.ly/plotly-2.30.0.min.js"></script>
  <style>
    body { font-family: Arial, sans-serif; margin: 18px; background:#fafafa; }
    h2 { margin: 0 0 10px 0; }
    h3 { margin: 0 0 10px 0; }
    .stack { display:flex; flex-direction:column; gap:14px; }

    .card { background:#fff; border: 1px solid #e6e6e6; border-radius: 12px; padding: 14px; }
    .cardhead { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom: 8px; }
    .controls { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
    select, input { padding: 6px 8px; }
    button { padding: 6px 10px; cursor:pointer; }

    .row2 { display:grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .plot { width: 100%; height: 420px; }
    .plot-sm { width: 100%; height: 380px; }

    .tabs { display:flex; gap:8px; margin: 10px 0 10px 0; }
    .tabbtn { padding: 6px 10px; border:1px solid #ddd; border-radius: 8px; background:#f8f8f8; cursor:pointer; }
    .tabbtn.active { background:#e9f0ff; border-color:#bcd0ff; }

    .muted { color:#666; font-size:12px; }
    .err { color:#b00020; font-size: 13px; white-space: pre-wrap; }

    table { border-collapse: collapse; width: 100%; table-layout: fixed; }
    th, td { border: 1px solid #ddd; padding: 6px 8px; font-size: 13px; vertical-align: top; word-wrap: break-word; }
    th { background: #fafafa; }

    .pager { display:flex; gap:10px; align-items:center; margin-top: 10px; }

    /* 요구자료 카드 */
    .req-card { background:white; border-radius:10px; padding:12px 14px; margin-bottom:10px; box-shadow:0 1px 2px rgba(0,0,0,0.06); border:1px solid #eee; }
    .req-name { font-weight:700; font-size:15px; }
    .req-target { margin-top:4px; color:#666; font-size:13px; }
    .req-body { margin-top:8px; color:#333; white-space: pre-wrap; }
    .badge { display:inline-block; padding:2px 8px; border-radius:999px; border:1px solid #ddd; font-size:12px; color:#555; margin-left:6px; }

    @media (max-width: 1100px){
      .row2 { grid-template-columns: 1fr; }
      .plot, .plot-sm { height: 420px; }
    }
  </style>
</head>
<body>

  <h2>통합 대시보드</h2>

  <div class="stack">

    <!-- [ Trend + 정당별 관심사 ] -->
    <div class="card">
      <div class="cardhead">
        <h3>[ Trend + 정당별 관심사 ]</h3>
        <div class="controls">
          <label>Top N</label>
          <input id="topN" type="number" min="1" max="50" value="7"/>
          <button id="reloadAll">Reload</button>
        </div>
      </div>
      <div class="row2">
        <div id="plot_trend" class="plot"></div>
        <div id="plot_party_mpr" class="plot"></div>
      </div>
      <div class="muted">※ Top N은 이 블록에만 적용</div>
    </div>

    <!-- [ Law 관련 + questions ] -->
    <div class="card">
      <div class="cardhead">
        <h3>[ Law 관련 + Questions ]</h3>
        <div class="muted">※ 분기×정당 기준(스택 바)</div>
      </div>
      <div class="row2">
        <div id="plot_law_by_q" class="plot"></div>
        <div id="plot_questions_by_q" class="plot"></div>
      </div>
    </div>

    <!-- [ 회차 관련 요약 ] -->
    <div class="card">
      <div class="cardhead">
        <h3>[ 회차 관련 요약 ]</h3>
        <div class="controls">
          <label>회차</label>
          <select id="sessionSel"></select>
          <span class="muted">※ 회차 선택은 아래 요약(Recap)에만 적용</span>
        </div>
      </div>

      <div class="tabs">
        <button class="tabbtn active" data-tab="text">회의 요약(text_recap)</button>
        <button class="tabbtn" data-tab="people">발언 요약(people_recap)</button>
        <button class="tabbtn" data-tab="data">요구자료(data_request_recap)</button>
      </div>

      <div class="controls" style="margin-bottom:10px;">
        <label>검색(현재 페이지 내)</label>
        <input id="q" placeholder="키워드 입력" style="min-width:260px;"/>
      </div>

      <div id="tableWrap"></div>
      <div class="pager">
        <button id="prev">Prev</button>
        <span id="pageInfo"></span>
        <button id="next">Next</button>
      </div>
    </div>

  </div>

<script>
const state = {
  topN: 7,
  tab: "text",
  offset: 0,
  sessionNo: null,
  limit: { text: 50, people: 100, data: 100 },
  lastRows: []
};

function setErr(divId, msg){
  const el = document.getElementById(divId);
  el.innerHTML = `<div class="err">${msg}</div>`;
}

function uniq(arr){ return [...new Set(arr)]; }

async function fetchJSON(url){
  const res = await fetch(url);
  if (!res.ok) throw new Error(await res.text());
  return await res.json();
}

function topDomains(rows, metric, topN){
  const sums = new Map();
  for (const r of rows){
    const d = r.policy_domain;
    const v = Number(r[metric] ?? 0);
    sums.set(d, (sums.get(d) ?? 0) + v);
  }
  return [...sums.entries()].sort((a,b)=>b[1]-a[1]).slice(0, topN).map(x=>x[0]);
}

function tracesParty(rows, metric, domains){
  const parties = uniq(rows.map(r=>r.party)).sort();
  const domainSet = new Set(domains);
  const m = new Map(parties.map(p => [p, new Map()]));

  for (const r of rows){
    if (!domainSet.has(r.policy_domain)) continue;
    m.get(r.party).set(r.policy_domain, Number(r[metric] ?? 0));
  }

  return parties.map(p => ({
    type:"bar",
    name:p,
    x:domains,
    y:domains.map(d => m.get(p).get(d) ?? 0),
    hovertemplate: "%{x}<br>"+p+"<br>"+metric+": %{y}<extra></extra>"
  }));
}

function renderGroupedBar(divId, title, rows, metric, topN){
  const domains = topDomains(rows, metric, topN);
  const data = tracesParty(rows, metric, domains);
  Plotly.newPlot(divId, data, {
    title:{text:title, x:0},
    barmode:"group",
    xaxis:{tickangle:-20, automargin:true},
    yaxis:{title:metric, automargin:true},
    margin:{t:50, r:20, b:120, l:70},
    legend:{orientation:"h"}
  }, {responsive:true, displaylogo:false});
}

function renderTrendLine(divId, title, rows, topN){
  const enriched = rows.map(r => {
    const p = r.period ?? (String(r.year) + "-Q" + String(r.quarter));
    return {...r, __period: p, __count: Number(r.count ?? 0)};
  });

  const sums = new Map();
  for (const r of enriched){
    const d = r.policy_domain;
    sums.set(d, (sums.get(d) ?? 0) + r.__count);
  }
  const domains = [...sums.entries()].sort((a,b)=>b[1]-a[1]).slice(0, topN).map(x=>x[0]);
  const domainSet = new Set(domains);

  const periods = uniq(enriched.map(r=>r.__period)).sort();

  const byDomain = new Map(domains.map(d => [d, new Map()]));
  for (const r of enriched){
    if (!domainSet.has(r.policy_domain)) continue;
    byDomain.get(r.policy_domain).set(r.__period, r.__count);
  }

  const data = domains.map(d => ({
    type:"scatter",
    mode:"lines+markers",
    name:d,
    x: periods,
    y: periods.map(p => byDomain.get(d).get(p) ?? 0),
    hovertemplate: "%{x}<br>"+d+"<br>count: %{y}<extra></extra>"
  }));

  Plotly.newPlot(divId, data, {
    title:{text:title, x:0},
    xaxis:{tickangle:-20, automargin:true},
    yaxis:{title:"count", automargin:true},
    margin:{t:50, r:20, b:120, l:70},
    legend:{orientation:"h"}
  }, {responsive:true, displaylogo:false});
}

function renderStackedByQuarter(divId, title, rows, valueCol){
  // rows: year, quarter, party, valueCol
  const enriched = rows.map(r => ({
    period: (String(r.year) + "-Q" + String(r.quarter)),
    party: r.party ?? "미분류",
    v: Number(r[valueCol] ?? 0)
  }));

  const periods = uniq(enriched.map(r=>r.period)).sort();
  const parties = uniq(enriched.map(r=>r.party)).sort();

  const map = new Map(parties.map(p=>[p, new Map()]));
  for (const r of enriched){
    map.get(r.party).set(r.period, (map.get(r.party).get(r.period) ?? 0) + r.v);
  }

  const data = parties.map(p => ({
    type:"bar",
    name:p,
    x:periods,
    y:periods.map(per => map.get(p).get(per) ?? 0),
    hovertemplate: "%{x}<br>"+p+"<br>"+valueCol+": %{y}<extra></extra>"
  }));

  Plotly.newPlot(divId, data, {
    title:{text:title, x:0},
    barmode:"stack",
    xaxis:{tickangle:-20, automargin:true},
    yaxis:{title:valueCol, automargin:true},
    margin:{t:50, r:20, b:120, l:70},
    legend:{orientation:"h"}
  }, {responsive:true, displaylogo:false});
}

function session_label(n){ return `${n}회`; }

async function initSessions(){
  const sel = document.getElementById("sessionSel");
  sel.innerHTML = "";
  const sessions = await fetchJSON("/api/sessions");
  if (!sessions || sessions.length === 0){
    sel.innerHTML = `<option value="">(회차 없음)</option>`;
    state.sessionNo = null;
    return;
  }
  for (const s of sessions){
    const opt = document.createElement("option");
    opt.value = String(s);
    opt.textContent = session_label(s);
    sel.appendChild(opt);
  }
  state.sessionNo = Number(sel.value);
}

function buildTable(rows, q){
  if (!rows || rows.length === 0) return "<div>데이터 없음</div>";
  const keys = Object.keys(rows[0]);
  const qq = (q || "").trim().toLowerCase();

  let filtered = rows;
  if (qq){
    filtered = rows.filter(r => JSON.stringify(r).toLowerCase().includes(qq));
  }

  const thead = "<tr>" + keys.map(k=>`<th>${k}</th>`).join("") + "</tr>";
  const tbody = filtered.map(r => "<tr>" + keys.map(k=>`<td>${r[k] ?? ""}</td>`).join("") + "</tr>").join("");
  return `<table><thead>${thead}</thead><tbody>${tbody}</tbody></table>`;
}

function buildDataCards(rows, q){
  if (!rows || rows.length === 0) return "<div>데이터 없음</div>";
  const qq = (q || "").trim().toLowerCase();
  let filtered = rows;
  if (qq){
    filtered = rows.filter(r => JSON.stringify(r).toLowerCase().includes(qq));
  }
  return filtered.map(r => {
    const name = r["요구자명"] ?? "";
    const target = r["대상"] ?? "";
    const req = r["실제요구자료"] ?? "";
    const cat = r["카테고리"];
    const badge = cat ? `<span class="badge">${cat}</span>` : "";
    return `
      <div class="req-card">
        <div class="req-name">${name}${badge}</div>
        <div class="req-target">대상: ${target}</div>
        <div class="req-body">${req}</div>
      </div>
    `;
  }).join("");
}

async function loadBlock1(){
  const topN = Number(document.getElementById("topN").value || 7);
  state.topN = topN;
  try {
    const [partyRows, trendRows] = await Promise.all([
      fetchJSON("/api/party-domain-metrics?limit=5000"),
      fetchJSON("/api/trend?limit=5000"),
    ]);
    renderTrendLine("plot_trend", "Trend: 분기별 정책도메인(topN)", trendRows, topN);
    renderGroupedBar("plot_party_mpr", "정당별: 회의출석률(topN 도메인)", partyRows, "meeting_presence_rate", topN);
  } catch (e){
    setErr("plot_trend", String(e));
    setErr("plot_party_mpr", String(e));
  }
}

async function loadBlock2(){
  try {
    const [lawStateRows, questionsRows] = await Promise.all([
      fetchJSON("/api/law/state?limit=5000"),
      fetchJSON("/api/questions?limit=5000"),
    ]);
    renderStackedByQuarter("plot_law_by_q", "법개정 요구(분기×정당)", lawStateRows, "num_law_reform_requests");
    renderStackedByQuarter("plot_questions_by_q", "질의 건수(분기×정당)", questionsRows, "num_questions");
  } catch (e){
    setErr("plot_law_by_q", String(e));
    setErr("plot_questions_by_q", String(e));
  }
}

async function loadRecap(){
  if (!state.sessionNo){
    document.getElementById("tableWrap").innerHTML = "<div>회차를 선택하세요</div>";
    return;
  }

  const q = document.getElementById("q").value || "";
  const limit = state.limit[state.tab];
  const offset = state.offset;

  const urlMap = {
    text: `/api/recap/text?session_no=${state.sessionNo}&limit=${limit}&offset=${offset}`,
    people: `/api/recap/people?session_no=${state.sessionNo}&limit=${limit}&offset=${offset}`,
    data: `/api/recap/data?session_no=${state.sessionNo}&limit=${limit}&offset=${offset}`,
  };

  try {
    const rows = await fetchJSON(urlMap[state.tab]);
    state.lastRows = rows;

    const wrap = document.getElementById("tableWrap");
    if (state.tab === "data"){
      wrap.innerHTML = buildDataCards(rows, q);
    } else {
      wrap.innerHTML = buildTable(rows, q);
    }

    document.getElementById("pageInfo").textContent =
      `${state.tab} | session=${state.sessionNo} | offset=${offset} | rows=${rows.length}`;

  } catch (e){
    document.getElementById("tableWrap").innerHTML = `<div class="err">${String(e)}</div>`;
  }
}

function setActiveTab(tab){
  state.tab = tab;
  state.offset = 0;
  document.querySelectorAll(".tabbtn").forEach(b=>{
    b.classList.toggle("active", b.dataset.tab === tab);
  });
  loadRecap();
}

document.getElementById("reloadAll").addEventListener("click", async ()=>{
  await loadBlock1();
  await loadBlock2();
  await loadRecap();
});

document.getElementById("sessionSel").addEventListener("change", async (e)=>{
  state.sessionNo = Number(e.target.value);
  state.offset = 0;
  await loadRecap();
});

document.getElementById("q").addEventListener("input", ()=>{
  const wrap = document.getElementById("tableWrap");
  const q = document.getElementById("q").value || "";
  if (state.tab === "data"){
    wrap.innerHTML = buildDataCards(state.lastRows, q);
  } else {
    wrap.innerHTML = buildTable(state.lastRows, q);
  }
});

document.getElementById("prev").addEventListener("click", async ()=>{
  const step = state.limit[state.tab];
  state.offset = Math.max(0, state.offset - step);
  await loadRecap();
});
document.getElementById("next").addEventListener("click", async ()=>{
  const step = state.limit[state.tab];
  if (!state.lastRows || state.lastRows.length < step) return;
  state.offset += step;
  await loadRecap();
});

document.querySelectorAll(".tabbtn").forEach(b=>{
  b.addEventListener("click", ()=>setActiveTab(b.dataset.tab));
});

(async function boot(){
  try{
    await initSessions();
    await loadBlock1();
    await loadBlock2();
    await loadRecap();
  } catch(e){
    document.body.insertAdjacentHTML("beforeend", `<div class="err">${String(e)}</div>`);
  }
})();
</script>

</body>
</html>
"""
