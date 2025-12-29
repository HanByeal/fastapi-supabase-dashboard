import os
import re
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

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

    # ✅ Law + Questions (DB 통합본)
    "law_reform_stats_policy_rows": "law_reform_stats_policy_rows",
    "law_reform_stats_session_rows": "law_reform_stats_session_rows",
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


def parse_session_no(s: str) -> Optional[int]:
    if not s:
        return None
    m = re.search(r"(\d+)", str(s))
    return int(m.group(1)) if m else None


# =========================
# API (DB1)
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
async def api_recap_text(session_no: int = Query(...), limit: int = 50, offset: int = 0):
    lab = session_label(session_no)
    return await sb_select(TABLES["text_recap"], {"select": "*", "회차": f"eq.{lab}", "limit": limit, "offset": offset})


@app.get("/api/recap/people")
async def api_recap_people(session_no: int = Query(...), limit: int = 100, offset: int = 0):
    lab = session_label(session_no)
    return await sb_select(TABLES["people_recap"], {"select": "*", "회차": f"eq.{lab}", "limit": limit, "offset": offset})


@app.get("/api/recap/data")
async def api_recap_data(session_no: int = Query(...), limit: int = 100, offset: int = 0):
    lab = session_label(session_no)
    return await sb_select(TABLES["data_request_recap"], {"select": "*", "회의회차": f"eq.{lab}", "limit": limit, "offset": offset})


# =========================
# Law + Questions API (통합 DB)
# =========================
@app.get("/api/law/stats/policy")
async def api_law_stats_policy(limit: int = 5000, offset: int = 0):
    return await sb_select(TABLES["law_reform_stats_policy_rows"], {"select": "*", "limit": limit, "offset": offset})


@app.get("/api/law/stats/session")
async def api_law_stats_session(limit: int = 5000, offset: int = 0):
    return await sb_select(TABLES["law_reform_stats_session_rows"], {"select": "*", "limit": limit, "offset": offset})


@app.get("/api/questions/stats/session")
async def api_questions_stats_session(limit: int = 5000, offset: int = 0):
    return await sb_select(TABLES["question_stats_session_rows"], {"select": "*", "limit": limit, "offset": offset})


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
  <title>대시보드</title>
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

    .tabs { display:flex; gap:8px; margin: 10px 0 10px 0; }
    .tabbtn { padding: 6px 10px; border:1px solid #ddd; border-radius: 8px; background:#f8f8f8; cursor:pointer; }
    .tabbtn.active { background:#e9f0ff; border-color:#bcd0ff; }

    .muted { color:#666; font-size:12px; }
    .err { color:#b00020; font-size: 13px; white-space: pre-wrap; }

    table { border-collapse: collapse; width: 100%; table-layout: fixed; }
    th, td { border: 1px solid #ddd; padding: 6px 8px; font-size: 13px; vertical-align: top; word-wrap: break-word; }
    th { background: #fafafa; }

    .pager { display:flex; gap:10px; align-items:center; margin-top: 10px; }

    .req-card { background:white; border-radius:10px; padding:12px 14px; margin-bottom:10px; box-shadow:0 1px 2px rgba(0,0,0,0.06); border:1px solid #eee; }
    .req-name { font-weight:700; font-size:15px; }
    .req-target { margin-top:4px; color:#666; font-size:13px; }
    .req-body { margin-top:8px; color:#333; white-space: pre-wrap; }
    .badge { display:inline-block; padding:2px 8px; border-radius:999px; border:1px solid #ddd; font-size:12px; color:#555; margin-left:6px; }

    @media (max-width: 1100px){
      .row2 { grid-template-columns: 1fr; }
      .plot { height: 420px; }
    }
  </style>
</head>
<body>

  <h2>대시보드</h2>

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

    <!-- [ Law 관련 + Questions ] -->
    <div class="card">
      <div class="cardhead">
        <h3>[ Law 관련 + Questions ]</h3>
        <div class="muted">※ DB1 통합 테이블 기준</div>
      </div>

      <div class="row2">
        <div id="plot_law_by_category" class="plot"></div>
        <div id="plot_law_by_party" class="plot"></div>
      </div>

      <div class="row2" style="margin-top:12px;">
        <div id="plot_q_top10" class="plot"></div>
        <div id="tbl_q_all" class="plot" style="height:auto; min-height:420px; overflow:auto;"></div>
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

/* =========================
   Block1: Trend + party_domain_metrics (기존)
   ========================= */
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

    // ✅ 아래 여백 더 확보
    margin:{t:50, r:20, b:210, l:70},

    // ✅ 범례를 그래프 밖으로 더 내리기
    legend:{
      orientation:"h",
      x:0,
      y:-0.45,      // 더 내리려면 -0.55, -0.65
      xanchor:"left",
      yanchor:"top"
    },
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

    // ✅ 아래 여백 더 확보 (범례가 밖으로 빠져도 안 잘리게)
    margin:{t:50, r:20, b:210, l:70},

    // ✅ 범례를 그래프 밖으로 더 내리기
    legend:{
      orientation:"h",
      x:0,
      y:-0.45,        // 더 내리려면 -0.55, -0.65
      xanchor:"left",
      yanchor:"top"
    },
  }, {responsive:true, displaylogo:false});
}

/* =========================
   Block2: Law + Questions (핵심)
   ========================= */
function regVal(r){
  // session_rows는 num_scope_rule일 수 있음
  return Number(r.num_scope_regulation ?? r.num_scope_rule ?? 0);
}

function sortLabelsByTotal(rows, labelField, getLaw, getSys, getReg){
  const sums = new Map();
  for (const r of rows){
    const k = r[labelField] ?? "미분류";
    const v = (getLaw(r)+getSys(r)+getReg(r));
    sums.set(k, (sums.get(k) ?? 0) + v);
  }
  return [...sums.entries()].sort((a,b)=>b[1]-a[1]).map(x=>x[0]);
}

function buildStack(rows, labelField, getLaw, getSys, getReg){
  const labels = sortLabelsByTotal(rows, labelField, getLaw, getSys, getReg);
  const m = new Map(labels.map(l => [l, {law:0, sys:0, reg:0}]));

  for (const r of rows){
    const k = r[labelField] ?? "미분류";
    if (!m.has(k)) m.set(k, {law:0, sys:0, reg:0});
    const obj = m.get(k);
    obj.law += getLaw(r);
    obj.sys += getSys(r);
    obj.reg += getReg(r);
  }

  return {
    labels,
    yLaw: labels.map(l => m.get(l).law),
    ySys: labels.map(l => m.get(l).sys),
    yReg: labels.map(l => m.get(l).reg),
  };
}

function renderStacked(divId, title, xLabels, yLaw, ySys, yReg){
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

    // ✅ 아래 여백을 늘려서 범례가 안 가리게
    margin:{t:50, r:20, b:170, l:70},

    // ✅ 범례를 그래프 밖(아래)로 내리기
    legend:{
      orientation:"h",
      x:0,
      y:-0.25,   // 더 내리고 싶으면 -0.35 같은 식으로
      xanchor:"left",
      yanchor:"top"
    },
  }, {responsive:true, displaylogo:false});
}

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
    y: rowsTop10.map(r => (r.party===p ? r.num_questions : 0))
  }));

  Plotly.newPlot(divId, data, {
    title:{text:"질의의원 Top 10", x:0},
    barmode:"group",
    xaxis:{tickangle:-20, automargin:true},
    yaxis:{title:"질의 건수", automargin:true},
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

  const thead = "<tr><th>rank</th><th>speaker</th><th>party</th><th>num_questions</th></tr>";
  const tbody = slice.map((r,i)=>
    `<tr><td>${start+i+1}</td><td>${r.speaker}</td><td>${r.party}</td><td>${r.num_questions}</td></tr>`
  ).join("");

  const pager = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin:8px 0;">
      <div>${start+1} - ${end} / ${total}</div>
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

async function loadLawQuestions(){
  try{
    const [policyRows, sessionRows, qRows] = await Promise.all([
      fetchJSON("/api/law/stats/policy?limit=5000"),
      fetchJSON("/api/law/stats/session?limit=5000"),
      fetchJSON("/api/questions/stats/session?limit=5000"),
    ]);

    // (1) 카테고리별(policy_enum) 스택
    const cat = buildStack(
      policyRows,
      "policy_enum",
      r => Number(r.num_scope_law ?? 0),
      r => Number(r.num_scope_system ?? 0),
      r => Number(r.num_scope_regulation ?? 0)
    );
    renderStacked(
      "plot_law_by_category",
      "법 개정/제도 개선/규정 변경 (카테고리별)",
      cat.labels, cat.yLaw, cat.ySys, cat.yReg
    );

    // (2) 정당별 스택
    const party = buildStack(
      sessionRows,
      "party",
      r => Number(r.num_scope_law ?? 0),
      r => Number(r.num_scope_system ?? 0),
      r => regVal(r)
    );
    renderStacked(
      "plot_law_by_party",
      "법 개정/제도 개선/규정 변경 (정당별)",
      party.labels, party.yLaw, party.ySys, party.yReg
    );

    // (3) 질의의원 Top10 + 전체 테이블
    __qAll = buildQuestionAgg(qRows);
    const top10 = __qAll.slice(0, 10);
    renderTop10("plot_q_top10", top10);

    __qPage = 0;
    renderQuestionTable("tbl_q_all", __qAll, __qPage, __qPageSize);

  } catch(e){
    setErr("plot_law_by_category", String(e));
    setErr("plot_law_by_party", String(e));
    setErr("plot_q_top10", String(e));
    document.getElementById("tbl_q_all").innerHTML = `<div class="err">${String(e)}</div>`;
  }
}

/* =========================
   Recap (기존)
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

async function loadBlock1(){
  const topN = Number(document.getElementById("topN").value || 7);
  state.topN = topN;
  try {
    const [partyRows, trendRows] = await Promise.all([
      fetchJSON("/api/party-domain-metrics?limit=5000"),
      fetchJSON("/api/trend?limit=5000"),
    ]);
    renderTrendLine("plot_trend", "Trend: 분기별 정책도메인(topN)", trendRows, topN);
    renderGroupedBar("plot_party_mpr", "정당별: (topN 도메인)", partyRows, "meeting_presence_rate", topN);
  } catch (e){
    setErr("plot_trend", String(e));
    setErr("plot_party_mpr", String(e));
  }
}

/* =========================
   이벤트
   ========================= */
document.getElementById("reloadAll").addEventListener("click", async () => {
  state.offset = 0;
  await loadBlock1();
  await loadLawQuestions();
  await loadRecap();
});

document.getElementById("sessionSel").addEventListener("change", async (e) => {
  state.sessionNo = Number(e.target.value);
  state.offset = 0;
  await loadRecap();
});

document.getElementById("prev").addEventListener("click", async () => {
  state.offset = Math.max(0, state.offset - state.limit[state.tab]);
  await loadRecap();
});

document.getElementById("next").addEventListener("click", async () => {
  state.offset = state.offset + state.limit[state.tab];
  await loadRecap();
});

document.getElementById("q").addEventListener("input", () => {
  const q = document.getElementById("q").value || "";
  const wrap = document.getElementById("tableWrap");
  if (state.tab === "data"){
    wrap.innerHTML = buildDataCards(state.lastRows, q);
  } else {
    wrap.innerHTML = buildTable(state.lastRows, q);
  }
});

for (const btn of document.querySelectorAll(".tabbtn")){
  btn.addEventListener("click", async () => {
    for (const b of document.querySelectorAll(".tabbtn")) b.classList.remove("active");
    btn.classList.add("active");
    state.tab = btn.dataset.tab;
    state.offset = 0;
    await loadRecap();
  });
}

/* =========================
   초기 로드
   ========================= */
(async () => {
  await initSessions();
  await loadBlock1();
  await loadLawQuestions();
  await loadRecap();
})();
</script>

</body>
</html>
"""
