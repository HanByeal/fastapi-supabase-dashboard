import os
import re
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

load_dotenv()

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or ""

app = FastAPI(title="FastAPI + Supabase Dashboard (Single DB)")

TABLES = {
    "trend": "trend",
    "party_domain_metrics": "party_domain_metrics",
    "text_recap": "text_recap",
    "people_recap": "people_recap",
    "data_request_recap": "data_request_recap",
    "law_reform_stats_row": "law_reform_stats_row",
    "question_stats_session_rows": "question_stats_session_rows",
}


def _headers() -> Dict[str, str]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {}
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept": "application/json",
    }


async def sb_select(table: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_URL / SUPABASE_KEY 가 설정되지 않았습니다. (.env 또는 run.cmd 확인)",
        )
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, headers=_headers(), params=params)
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()


def session_label(n: int) -> str:
    return f"{n}회"


def parse_session_no(s: Any) -> Optional[int]:
    if s is None:
        return None
    m = re.search(r"(\d+)", str(s))
    return int(m.group(1)) if m else None


# =========================
# API
# =========================
@app.get("/api/trend")
async def api_trend(limit: int = 5000, offset: int = 0):
    return await sb_select(TABLES["trend"], {"select": "*", "limit": limit, "offset": offset})


@app.get("/api/party-domain-metrics")
async def api_party_domain_metrics(limit: int = 5000, offset: int = 0):
    return await sb_select(TABLES["party_domain_metrics"], {"select": "*", "limit": limit, "offset": offset})


@app.get("/api/sessions")
async def api_sessions():
    rows_text = await sb_select(TABLES["text_recap"], {"select": "회차", "limit": 10000, "offset": 0})
    rows_people = await sb_select(TABLES["people_recap"], {"select": "회차", "limit": 10000, "offset": 0})
    rows_data = await sb_select(TABLES["data_request_recap"], {"select": "회의회차", "limit": 10000, "offset": 0})

    ses = set()
    for r in rows_text:
        n = parse_session_no(r.get("회차"))
        if n:
            ses.add(n)
    for r in rows_people:
        n = parse_session_no(r.get("회차"))
        if n:
            ses.add(n)
    for r in rows_data:
        n = parse_session_no(r.get("회의회차"))
        if n:
            ses.add(n)

    return sorted(ses)


@app.get("/api/recap/text")
async def api_recap_text(session_no: int = Query(...), limit: int = 20, offset: int = 0):
    lab = session_label(session_no)
    return await sb_select(
        TABLES["text_recap"],
        {"select": "*", "회차": f"eq.{lab}", "limit": limit, "offset": offset},
    )


@app.get("/api/recap/people")
async def api_recap_people(session_no: int = Query(...), limit: int = 20, offset: int = 0):
    lab = session_label(session_no)
    return await sb_select(
        TABLES["people_recap"],
        {"select": "*", "회차": f"eq.{lab}", "limit": limit, "offset": offset},
    )


@app.get("/api/recap/data")
async def api_recap_data(session_no: int = Query(...), limit: int = 20, offset: int = 0):
    lab = session_label(session_no)
    return await sb_select(
        TABLES["data_request_recap"],
        {"select": "*", "회의회차": f"eq.{lab}", "limit": limit, "offset": offset},
    )


@app.get("/api/law/stats/policy")
async def api_law_stats_policy(limit: int = 5000, offset: int = 0):
    return await sb_select(TABLES["law_reform_stats_row"], {"select": "*", "limit": limit, "offset": offset})


@app.get("/api/law/stats/session")
async def api_law_stats_session(limit: int = 5000, offset: int = 0):
    return await sb_select(TABLES["law_reform_stats_row"], {"select": "*", "limit": limit, "offset": offset})


@app.get("/api/questions/stats/session")
async def api_questions_stats_session(limit: int = 5000, offset: int = 0):
    return await sb_select(
        TABLES["question_stats_session_rows"],
        {"select": "*", "limit": limit, "offset": offset},
    )


# =========================
# Dashboard page
# =========================
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return HTML_PAGE


HTML_PAGE = r"""
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <title>국회 회의록 대시보드</title>
  <script src="https://cdn.plot.ly/plotly-2.30.0.min.js"></script>
  <style>
    body { font-family: Arial, sans-serif; margin: 18px; background:#fafafa; }
    h2, h3 { margin:0; }
    .stack { display:flex; flex-direction:column; gap:14px; }

    .card {
      background:#fff;
      border: 1px solid #e6e6e6;
      border-radius: 12px;
      padding: 14px;
      box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }

    .cardhead {
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap:12px;
      flex-wrap:wrap;
      margin-bottom: 10px;
    }
    .controls { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
    select, input {
      padding:6px 10px;
      border:1px solid #dcdcdc;
      border-radius:10px;
      background:#fff;
      outline:none;
    }
    select:focus, input:focus { border-color:#bcd0ff; box-shadow:0 0 0 3px rgba(188,208,255,0.35); }

    .section-title{
      display:inline-flex;
      align-items:center;
      gap:10px;
      padding:8px 12px;
      border-radius:10px;
      background:#2b6cb0;
      color:#fff;
      font-weight:800;
      font-size:14px;
      line-height:1;
    }

    .tabs { display:flex; gap:8px; margin: 6px 0 10px 0; }
    .tabbtn {
      padding: 7px 12px;
      border:1px solid #d7d7d7;
      border-radius: 10px;
      background:#f8f8f8;
      cursor:pointer;
      font-weight:700;
    }
    .tabbtn:hover { background:#f2f2f2; }
    .tabbtn.active { background:#e9f0ff; border-color:#bcd0ff; }

    .row2 { display:grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .plot { width: 100%; height: 420px; }

    .err { color:#b00020; font-size: 13px; white-space: pre-wrap; }

    table { border-collapse: collapse; width: 100%; table-layout: fixed; }
    th, td { border: 1px solid #ddd; padding: 6px 8px; font-size: 13px; vertical-align: top; word-wrap: break-word; }
    th { background: #fafafa; }

    /* Summary cards */
    .sum-card{
      background:#fff;
      border:1px solid #eee;
      border-radius:12px;
      padding:12px 14px;
      margin-bottom:10px;
      box-shadow:0 1px 2px rgba(0,0,0,0.05);
    }
    .pill{
      display:inline-block;
      font-size:12px;
      padding:3px 10px;
      border-radius:999px;
      border:1px solid #cfe0ff;
      color:#1f4b99;
      background:#eef5ff;
      font-weight:800;
    }

    /* 회의요약: 좌(안건/요약) + 우(키워드박스) */
    .sum-grid{
      display:grid;
      grid-template-columns: 2fr 1fr;
      gap: 12px;
      align-items: stretch;
      margin-top:10px;
    }
    .sum-left{
      border:1px solid #eee;
      border-radius:12px;
      background:#fff;
      padding:12px 14px;
    }
    .kw-box{
      border:1px solid #eee;
      border-radius:12px;
      background:#fafafa;
      padding: 12px;
      min-height: 220px;
    }

    .block-title{
      font-weight:900;
      font-size:14px;
      margin: 2px 0 8px 0;
    }
    .agenda-box{
      background:#f3f3f3;
      border-radius:10px;
      padding:10px 12px;
      margin-bottom:14px;
    }
    .agenda-item{
      margin: 0 0 6px 0;
      padding-left: 14px;
      position: relative;
      line-height: 1.35;
      font-size:13px;
      color:#222;
    }
    .agenda-item::before{
      content:"•";
      position:absolute;
      left:0;
      top:0;
      color:#444;
      font-weight:900;
    }

    .summary-text{
      font-size:13px;
      line-height:1.55;
      color:#222;
      white-space:pre-wrap;
    }

    .kw-title{ font-weight:900; margin: 2px 0 10px 0; }
    .kw-item{
      font-size:18px;
      font-weight:900;
      line-height:1.55;
      text-align:center;
      color:#111;
    }

    /* people/data: list cards */
    .req-card { background:white; border-radius:10px; padding:12px 14px; margin-bottom:10px; box-shadow:0 1px 2px rgba(0,0,0,0.05); border:1px solid #eee; }
    .req-name { font-weight:800; font-size:15px; display:flex; gap:8px; align-items:center; }
    .req-target { margin-top:4px; color:#666; font-size:13px; }
    .req-body { margin-top:8px; color:#222; white-space: pre-wrap; line-height:1.45; }

    .badge {
      display:inline-block;
      padding:2px 8px;
      border-radius:999px;
      border:1px solid #ddd;
      font-size:12px;
      color:#555;
      background:#fff;
    }
    .pill-red{
      display:inline-block;
      font-size:12px;
      padding:2px 8px;
      border-radius:999px;
      border:1px solid #ffb7b7;
      background:#fff0f0;
      color:#8a1f1f;
      font-weight:800;
    }

    /* controls row under tabs */
    #filterWrap{
      display:flex;
      gap:10px;
      align-items:center;
      flex-wrap:wrap;
      margin-bottom:10px;
    }

    /* 더보기 */
    .more-wrap{ display:flex; justify-content:center; margin-top: 10px; }
    .more-btn{
      padding:10px 14px;
      border-radius:12px;
      border:1px solid #d7d7d7;
      background:#f8f8f8;
      cursor:pointer;
      font-weight:800;
      min-width:120px;
    }
    .more-btn:hover{ background:#f1f1f1; }

    @media (max-width: 1100px){
      .row2 { grid-template-columns: 1fr; }
      .plot { height: 420px; }
      .sum-grid{ grid-template-columns: 1fr; }
    }
  </style>
</head>

<body>
  <div class="stack">

    <!-- 1) 회차별 회의록 분석 -->
    <div class="card">
      <div class="cardhead">
        <!-- ✅ 배지 오른쪽에 회차 선택을 붙임 -->
        <div class="controls">
          <div class="section-title">회차별 회의록 분석</div>
          <label style="font-weight:800;">회차</label>
          <select id="sessionSel"></select>
        </div>
      </div>

      <div class="tabs">
        <button class="tabbtn active" data-tab="text">회의요약</button>
        <button class="tabbtn" data-tab="people">발언요약</button>
        <button class="tabbtn" data-tab="data">요구자료</button>
      </div>

      <div id="filterWrap">
        <label style="font-weight:800;">정당</label>
        <select id="partySel" style="min-width:140px;"></select>

        <label style="font-weight:800;">검색</label>
        <input id="q" placeholder="키워드 입력" style="min-width:260px;"/>
      </div>

      <div id="summaryWrap"></div>

      <div class="more-wrap" id="moreWrap">
        <button class="more-btn" id="moreBtn">더보기</button>
      </div>
    </div>

    <!-- 2) 주요 질의 의원 -->
    <div class="card">
      <div class="cardhead">
        <div class="section-title">주요 질의 의원</div>
      </div>
      <div class="row2">
        <div id="plot_q_top10" class="plot"></div>
        <div id="tbl_q_all" class="plot" style="height:auto; min-height:420px; overflow:auto;"></div>
      </div>
    </div>

    <!-- 3) 법개정/제도개선/규정변경 -->
    <div class="card">
      <div class="cardhead">
        <div class="section-title">법개정/제도개선/규정변경</div>
      </div>
      <div class="row2">
        <div id="plot_law_by_category" class="plot"></div>
        <div id="plot_law_by_party" class="plot"></div>
      </div>
    </div>

    <!-- 4) 주요 트렌드(분기별) / 정당별 -->
    <div class="card">
      <div class="cardhead">
        <div class="section-title">주요 트렌드(분기별) / 정당별</div>
      </div>
      <div class="row2">
        <div id="plot_trend" class="plot"></div>
        <div id="plot_party_mpr" class="plot"></div>
      </div>
    </div>

  </div>

<script>
/* =========================
   공통 유틸
   ========================= */
const state = {
  tab: "text",
  sessionNo: null,
  party: "전체",
  q: "",
  offset: 0,
  pageSize: { text: 1, people: 20, data: 20 },
  cacheRows: { text: [], people: [], data: [] },
  hasMore: true
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

function pickFirst(obj, keys){
  for (const k of keys){
    if (obj[k] != null && String(obj[k]).trim() !== "") return String(obj[k]).trim();
  }
  return null;
}

/* =========================
   정당 색상(고정)
   ========================= */
function partyColor(party){
  const p = (party || "").trim();
  const map = new Map([
    ["더불어민주당", "#3b82f6"], ["민주당", "#3b82f6"],
    ["국민의힘", "#ef4444"],
    ["정의당", "#f59e0b"],
    ["개혁신당", "#f97316"],
    ["조국혁신당", "#16a34a"],
    ["진보당", "#ec4899"],
    ["기본소득당", "#7c3aed"],
    ["사회민주당", "#14b8a6"],
    ["무소속", "#9ca3af"],
  ]);
  if (map.has(p)) return map.get(p);
  if (p.includes("민주")) return "#3b82f6";
  if (p.includes("국민의힘")) return "#ef4444";
  if (p.includes("정의")) return "#f59e0b";
  if (p.includes("개혁")) return "#f97316";
  if (p.includes("조국")) return "#16a34a";
  if (p.includes("진보")) return "#ec4899";
  if (p.includes("무소속")) return "#9ca3af";
  return "#64748b";
}

/* =========================
   상단 탭: 필터 UI 표시/숨김
   ========================= */
function refreshFilterUI(){
  const filterWrap = document.getElementById("filterWrap");
  const moreWrap = document.getElementById("moreWrap");

  if (state.tab === "text"){
    filterWrap.style.display = "none";     // 회의요약은 검색/정당필터 없음
    moreWrap.style.display = "none";       // 회의요약은 더보기 없음
    return;
  }
  filterWrap.style.display = "";
  moreWrap.style.display = "";
}

function getParty(r, tab){
  if (tab === "people"){
    return pickFirst(r, ["정당", "party"]) ?? "기타";
  }
  if (tab === "data"){
    // 현재는 없지만, 생기면 자동 작동
    return pickFirst(r, ["정당", "party", "요구자정당", "소속정당"]) ?? null;
  }
  return null;
}

function buildPartyOptionsFromRows(rows){
  const partySel = document.getElementById("partySel");

  if (!(state.tab === "people" || state.tab === "data")){
    partySel.innerHTML = "";
    state.party = "전체";
    return;
  }

  const parties = [];
  for (const r of rows){
    const p = getParty(r, state.tab);
    if (p) parties.push(p);
  }

  const opts = (parties.length > 0)
    ? ["전체", ...uniq(parties).filter(Boolean).sort()]
    : ["전체"]; // data에 정당이 없으면 전체만

  partySel.innerHTML = "";
  for (const p of opts){
    const opt = document.createElement("option");
    opt.value = p;
    opt.textContent = p;
    partySel.appendChild(opt);
  }

  partySel.value = "전체";
  state.party = "전체";
}

function applyFilters(rows){
  let out = rows;

  if ((state.tab === "people" || state.tab === "data") && state.party && state.party !== "전체"){
    out = out.filter(r => {
      const p = getParty(r, state.tab);
      if (!p) return true; // 정당 컬럼 없으면 필터 무시
      return p === state.party;
    });
  }

  const qq = (state.q || "").trim().toLowerCase();
  if (qq){
    out = out.filter(r => JSON.stringify(r).toLowerCase().includes(qq));
  }
  return out;
}

/* =========================
   회의요약 렌더
   - 주요안건: ; 구분자를 줄바꿈 + 불릿
   - 회의내용 요약: 더보기 없이 전체 표시
   - 키워드: 오른쪽 박스(세로 정렬)
   ========================= */
function formatAgendaItems(agendaRaw){
  if (!agendaRaw) return [];
  return String(agendaRaw)
    .split(/;|；/g)
    .map(s => s.trim())
    .filter(Boolean);
}

function parseKeywords(keywordRaw){
  if (!keywordRaw) return [];
  return String(keywordRaw)
    .split(/\s+/)
    .map(s => s.trim())
    .filter(Boolean)
    .map(s => s.startsWith("#") ? s.slice(1) : s);
}

function renderTextRecap(rows){
  if (!rows || rows.length === 0) return "<div>데이터 없음</div>";

  const r = rows[0]; // 회의요약은 보통 1행
  const agendaRaw = pickFirst(r, ["주요안건", "안건", "agenda", "main_agenda"]);
  const summary = pickFirst(r, ["회의내용 요약", "회의요약", "요약", "summary", "text", "본문"]) ?? "";
  const keywordsArr = parseKeywords(pickFirst(r, ["키워드", "keyword", "keywords"]));

  const agendaItems = formatAgendaItems(agendaRaw);

  const agendaHtml = agendaItems.length
    ? `<div class="agenda-box">
         ${agendaItems.map(x => `<div class="agenda-item">${x}</div>`).join("")}
       </div>`
    : `<div class="agenda-box"><div class="err">주요안건 없음</div></div>`;

  const kwHtml = (keywordsArr.length === 0)
    ? `<div class="kw-box"><div class="kw-title">키워드</div><div class="err">키워드 없음</div></div>`
    : `<div class="kw-box">
         <div class="kw-title">키워드</div>
         <div class="kw-item">${keywordsArr.join("<br>")}</div>
       </div>`;

  return `
    <div class="sum-card">
      <div><span class="pill">${state.sessionNo}회</span></div>

      <div class="sum-grid">
        <div class="sum-left">
          <div class="block-title">주요안건</div>
          ${agendaHtml}

          <div class="block-title">회의내용 요약</div>
          <div class="summary-text">${summary}</div>
        </div>

        ${kwHtml}
      </div>
    </div>
  `;
}

/* =========================
   발언요약 렌더 (카드)
   ========================= */
function renderPeopleCards(rows){
  const filtered = applyFilters(rows);
  if (!filtered || filtered.length === 0) return "<div>데이터 없음</div>";

  return filtered.map(r => {
    const name = r["의원명"] ?? r["발언자"] ?? r["speaker_name"] ?? "";
    const party = r["정당"] ?? r["party"] ?? "";
    const body = r["발화내용 요약"] ?? r["요약"] ?? r["summary"] ?? r["text"] ?? "";
    const partyTag = party ? `<span class="pill-red">${party}</span>` : "";
    return `
      <div class="sum-card">
        <div class="req-name">${name}${partyTag}</div>
        <div class="req-body">${body}</div>
      </div>
    `;
  }).join("");
}

/* =========================
   요구자료 렌더 (카드)
   ========================= */
function renderDataCards(rows){
  const filtered = applyFilters(rows);
  if (!filtered || filtered.length === 0) return "<div>데이터 없음</div>";

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

/* =========================
   회차 목록 + 데이터 로드(더보기 포함)
   ========================= */
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

function resetListState(){
  state.offset = 0;
  state.cacheRows[state.tab] = [];
  state.hasMore = true;
  document.getElementById("moreBtn").disabled = false;
  document.getElementById("moreBtn").textContent = "더보기";
}

async function loadPageAppend(){
  if (!state.sessionNo) return;

  const limit = state.pageSize[state.tab];
  const offset = state.offset;

  const urlMap = {
    text: `/api/recap/text?session_no=${state.sessionNo}&limit=${limit}&offset=${offset}`,
    people: `/api/recap/people?session_no=${state.sessionNo}&limit=${limit}&offset=${offset}`,
    data: `/api/recap/data?session_no=${state.sessionNo}&limit=${limit}&offset=${offset}`,
  };

  const rows = await fetchJSON(urlMap[state.tab]);

  if (state.tab === "text"){
    state.cacheRows.text = rows;
    state.hasMore = false;
    document.getElementById("moreWrap").style.display = "none";
    return;
  }

  // append
  state.cacheRows[state.tab] = state.cacheRows[state.tab].concat(rows);
  state.offset += rows.length;

  // hasMore 판정: rows가 limit보다 작으면 끝
  if (rows.length < limit){
    state.hasMore = false;
    document.getElementById("moreBtn").disabled = true;
    document.getElementById("moreBtn").textContent = "마지막입니다";
  } else {
    state.hasMore = true;
    document.getElementById("moreBtn").disabled = false;
    document.getElementById("moreBtn").textContent = "더보기";
  }
}

function renderSummary(){
  const wrap = document.getElementById("summaryWrap");

  if (state.tab === "text"){
    wrap.innerHTML = renderTextRecap(state.cacheRows.text);
    return;
  }
  if (state.tab === "people"){
    wrap.innerHTML = renderPeopleCards(state.cacheRows.people);
    return;
  }
  wrap.innerHTML = renderDataCards(state.cacheRows.data);
}

async function loadAndRenderFirst(){
  refreshFilterUI();
  resetListState();
  document.getElementById("summaryWrap").innerHTML = "";
  await loadPageAppend();

  // 첫 로드 후 정당 옵션 채우기(현재 페이지 데이터 기준)
  if (state.tab === "people" || state.tab === "data"){
    buildPartyOptionsFromRows(state.cacheRows[state.tab]);
  }
  renderSummary();
}

/* =========================
   2) 주요 질의 의원
   ========================= */
function buildQuestionAgg(qRows){
  const m = new Map(); // speaker||party -> sum
  for (const r of qRows){
    const speaker = r.speaker_name ?? "";
    const party = r.party ?? "미분류";
    const v = Number(r.num_questions ?? 0);
    if (!speaker) continue;
    const key = speaker + "||" + party;
    m.set(key, (m.get(key) ?? 0) + v);
  }
  const arr = [...m.entries()].map(([k,v]) => {
    const [speaker, party] = k.split("||");
    return {speaker, party, num_questions:v};
  });
  arr.sort((a,b)=>b.num_questions - a.num_questions);
  return arr;
}

function renderTop10(divId, rowsTop10){
  const parties = [...new Set(rowsTop10.map(r=>r.party))].sort();
  const x = rowsTop10.map(r=>r.speaker);

  const data = parties.map(p => ({
    type:"bar",
    name:p,
    x,
    y: rowsTop10.map(r => (r.party===p ? r.num_questions : 0)),
    marker: { color: partyColor(p) },
    hovertemplate: "%{x}<br>"+p+"<br>질의 수: %{y}<extra></extra>"
  }));

  Plotly.newPlot(divId, data, {
    title:{text:"질의의원 Top 10", x:0},
    barmode:"group",
    xaxis:{tickangle:-20, automargin:true},
    yaxis:{title:"질의 수", automargin:true},
    margin:{t:50, r:20, b:120, l:70},
    legend:{orientation:"h"}
  }, {responsive:true, displaylogo:false});
}

let __qAll = [];
let __qPage = 0;
const __qPageSize = 10;

window.__qPageChange = (delta) => {
  __qPage = Math.max(0, __qPage + delta);
  renderQuestionTable("tbl_q_all", __qAll, __qPage, __qPageSize);
};

function renderQuestionTable(divId, rowsAll, page, pageSize){
  const total = rowsAll.length;
  const start = page * pageSize;
  const end = Math.min(total, start + pageSize);
  const slice = rowsAll.slice(start, end);

  const thead = "<tr><th>순위</th><th>발화자</th><th>정당</th><th>질의 수</th></tr>";

  const tbody = slice.map((r,i)=>
    `<tr>
      <td>${start+i+1}</td>
      <td>${r.speaker}</td>
      <td>${r.party}</td>
      <td>${r.num_questions}</td>
    </tr>`
  ).join("");

  const pager = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin:8px 0;">
      <div>${total===0?0:start+1} - ${end} / ${total}</div>
      <div style="display:flex;gap:8px;">
        <button id="q_prev" ${page===0?"disabled":""}>◀</button>
        <button id="q_next" ${end>=total?"disabled":""}>▶</button>
      </div>
    </div>
  `;

  document.getElementById(divId).innerHTML =
    pager + `<table><thead>${thead}</thead><tbody>${tbody}</tbody></table>`;

  document.getElementById("q_prev")?.addEventListener("click", ()=> window.__qPageChange(-1));
  document.getElementById("q_next")?.addEventListener("click", ()=> window.__qPageChange(+1));
}

async function loadQuestions(){
  try{
    const qRows = await fetchJSON("/api/questions/stats/session?limit=5000");
    __qAll = buildQuestionAgg(qRows);

    const top10 = __qAll.slice(0, 10);
    renderTop10("plot_q_top10", top10);

    __qPage = 0;
    renderQuestionTable("tbl_q_all", __qAll, __qPage, __qPageSize);

  }catch(e){
    setErr("plot_q_top10", String(e));
    document.getElementById("tbl_q_all").innerHTML = `<div class="err">${String(e)}</div>`;
  }
}

/* =========================
   3) Law
   ========================= */
function buildStackSimple(rows, labelField, getA, getB, getC){
  const sums = new Map();
  for (const r of rows){
    const k = r[labelField] ?? "미분류";
    const v = getA(r) + getB(r) + getC(r);
    sums.set(k, (sums.get(k) ?? 0) + v);
  }
  const labels = [...sums.entries()].sort((a,b)=>b[1]-a[1]).map(x=>x[0]);

  const m = new Map(labels.map(l => [l, {a:0,b:0,c:0}]));
  for (const r of rows){
    const k = r[labelField] ?? "미분류";
    if (!m.has(k)) m.set(k, {a:0,b:0,c:0});
    const obj = m.get(k);
    obj.a += getA(r);
    obj.b += getB(r);
    obj.c += getC(r);
  }

  return {
    labels,
    yA: labels.map(l => m.get(l).a),
    yB: labels.map(l => m.get(l).b),
    yC: labels.map(l => m.get(l).c),
  };
}

function renderStackedLaw(divId, title, xLabels, yLaw, ySys, yReg){
  const data = [
    {type:"bar", name:"법 개정",   x:xLabels, y:yLaw},
    {type:"bar", name:"제도 개선", x:xLabels, y:ySys},
    {type:"bar", name:"규정 변경", x:xLabels, y:yReg},
  ];

  Plotly.newPlot(divId, data, {
    title:{text:title, x:0},
    barmode:"stack",
    xaxis:{tickangle:-20, automargin:true},
    yaxis:{title:"건수", automargin:true},
    margin:{t:50, r:20, b:170, l:70},
    legend:{ orientation:"h", x:0, y:-0.25, xanchor:"left", yanchor:"top" },
  }, {responsive:true, displaylogo:false});
}

async function loadLaw(){
  try{
    const rows = await fetchJSON("/api/law/stats/policy?limit=5000");

    const getLaw = r => Number(r["num_scope_법개정"] ?? r.num_scope_law ?? 0);
    const getSys = r => Number(r["num_scope_제도개선"] ?? r.num_scope_system ?? 0);
    const getReg = r => Number(r["num_scope_규정변경"] ?? r.num_scope_regulation ?? r.num_scope_rule ?? 0);

    const cat = buildStackSimple(rows, "policy_mid", getLaw, getSys, getReg);
    renderStackedLaw("plot_law_by_category", "카테고리별", cat.labels, cat.yA, cat.yB, cat.yC);

    const party = buildStackSimple(rows, "party", getLaw, getSys, getReg);
    renderStackedLaw("plot_law_by_party", "정당별", party.labels, party.yA, party.yB, party.yC);

  }catch(e){
    setErr("plot_law_by_category", String(e));
    setErr("plot_law_by_party", String(e));
  }
}

/* =========================
   4) 트렌드 / 정당별 (건수)
   ========================= */
function renderTrendLineAll(divId, rows){
  const enriched = rows.map(r => {
    const p = r.period ?? (String(r.year) + "-Q" + String(r.quarter));
    return {...r, __period: p, __count: Number(r.count ?? 0)};
  });

  const periods = uniq(enriched.map(r=>r.__period)).sort();
  const domains = uniq(enriched.map(r=>r.policy_domain)).sort();

  const byDomain = new Map(domains.map(d => [d, new Map()]));
  for (const r of enriched){
    byDomain.get(r.policy_domain).set(r.__period, r.__count);
  }

  const data = domains.map(d => ({
    type:"scatter",
    mode:"lines+markers",
    name:d,
    x: periods,
    y: periods.map(p => byDomain.get(d).get(p) ?? 0),
    hovertemplate: "%{x}<br>"+d+"<br>건수: %{y}<extra></extra>"
  }));

  Plotly.newPlot(divId, data, {
    title:{text:"분기별 트렌드(건수)", x:0},
    xaxis:{tickangle:-20, automargin:true},
    yaxis:{title:"건수", automargin:true},
    margin:{t:50, r:20, b:210, l:70},
    legend:{ orientation:"h", x:0, y:-0.45, xanchor:"left", yanchor:"top" },
  }, {responsive:true, displaylogo:false});
}

function renderPartyBarAll(divId, rows){
  const l2s = uniq(rows.map(r=>r.l2)).sort();
  const parties = uniq(rows.map(r=>r.party)).sort();

  const m = new Map(parties.map(p => [p, new Map()]));
  for (const r of rows){
    const p = r.party ?? "미분류";
    const l2 = r.l2 ?? "미분류";
    const v = Number(r.meeting_count ?? 0);
    if (!m.has(p)) m.set(p, new Map());
    m.get(p).set(l2, v);
  }

  const data = parties.map(p => ({
    type:"bar",
    name:p,
    x:l2s,
    y:l2s.map(l2 => m.get(p)?.get(l2) ?? 0),
    hovertemplate: "%{x}<br>"+p+"<br>건수: %{y}<extra></extra>"
  }));

  Plotly.newPlot(divId, data, {
    title:{text:"정당별 관심(건수)", x:0},
    barmode:"group",
    xaxis:{tickangle:-20, automargin:true},
    yaxis:{title:"건수", automargin:true},
    margin:{t:50, r:20, b:210, l:70},
    legend:{ orientation:"h", x:0, y:-0.45, xanchor:"left", yanchor:"top" },
  }, {responsive:true, displaylogo:false});
}

async function loadTrendAndParty(){
  try{
    const [trendRows, partyRows] = await Promise.all([
      fetchJSON("/api/trend?limit=5000"),
      fetchJSON("/api/party-domain-metrics?limit=5000"),
    ]);

    if (!trendRows || trendRows.length === 0) setErr("plot_trend", "trend 데이터가 없습니다.");
    else renderTrendLineAll("plot_trend", trendRows);

    if (!partyRows || partyRows.length === 0) setErr("plot_party_mpr", "party metrics 데이터가 없습니다.");
    else renderPartyBarAll("plot_party_mpr", partyRows);

  }catch(e){
    setErr("plot_trend", String(e));
    setErr("plot_party_mpr", String(e));
  }
}

/* =========================
   이벤트
   ========================= */
document.getElementById("sessionSel").addEventListener("change", async (e) => {
  state.sessionNo = Number(e.target.value);

  // 탭 유지 + 목록 리셋
  state.q = "";
  document.getElementById("q").value = "";
  state.party = "전체";
  document.getElementById("partySel").value = "전체";

  await loadAndRenderFirst();
});

document.getElementById("q").addEventListener("input", () => {
  state.q = document.getElementById("q").value || "";
  renderSummary();
});

document.getElementById("partySel").addEventListener("change", () => {
  state.party = document.getElementById("partySel").value || "전체";
  renderSummary();
});

document.getElementById("moreBtn").addEventListener("click", async () => {
  try{
    document.getElementById("moreBtn").disabled = true;
    document.getElementById("moreBtn").textContent = "불러오는 중...";
    await loadPageAppend();

    // 더보기로 데이터가 늘었으니 정당 옵션도 최신 반영(people만 확실 / data는 정당 생기면 반영)
    if (state.tab === "people" || state.tab === "data"){
      const prevParty = state.party;
      buildPartyOptionsFromRows(state.cacheRows[state.tab]);
      // 기존 선택 유지 시도
      const partySel = document.getElementById("partySel");
      const options = [...partySel.options].map(o=>o.value);
      if (options.includes(prevParty)){
        partySel.value = prevParty;
        state.party = prevParty;
      }
    }

    renderSummary();

  }catch(e){
    alert(String(e));
  } finally {
    if (state.hasMore){
      document.getElementById("moreBtn").disabled = false;
      document.getElementById("moreBtn").textContent = "더보기";
    }
  }
});

for (const btn of document.querySelectorAll(".tabbtn")){
  btn.addEventListener("click", async () => {
    for (const b of document.querySelectorAll(".tabbtn")) b.classList.remove("active");
    btn.classList.add("active");

    state.tab = btn.dataset.tab;

    // 탭 변경 시 리셋
    state.q = "";
    document.getElementById("q").value = "";
    state.party = "전체";
    document.getElementById("partySel").value = "전체";

    await loadAndRenderFirst();
  });
}

/* =========================
   초기 로드
   ========================= */
(async () => {
  await initSessions();
  refreshFilterUI();
  await loadAndRenderFirst();
  await loadQuestions();
  await loadLaw();
  await loadTrendAndParty();
})();
</script>
</body>
</html>
"""
