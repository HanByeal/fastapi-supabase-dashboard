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
  <title>대시보드</title>

  <script src="https://cdn.plot.ly/plotly-2.30.0.min.js"></script>

  <!-- ✅ WordCloud (d3 + d3-cloud) -->
  <script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
  <script src="https://cdn.jsdelivr.net/npm/d3-cloud@1/build/d3.layout.cloud.js"></script>

  <style>
    body { font-family: Arial, sans-serif; margin: 18px; background:#fafafa; color:#111; }
    h2 { margin: 0 0 12px 0; }
    h3 { margin: 0; font-size: 16px; }

    .stack { display:flex; flex-direction:column; gap:14px; }

    .card { background:#fff; border: 1px solid #e6e6e6; border-radius: 14px; padding: 14px; }
    .cardhead { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom: 10px; }

    .titleRow { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
    .badgeTitle{
      display:inline-flex; align-items:center; gap:8px;
      padding:7px 12px; border-radius:999px;
      background:#111; color:#fff; font-weight:800; font-size:13px;
      letter-spacing:-0.2px;
    }

    .controls { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
    select, input { padding: 7px 10px; border:1px solid #ddd; border-radius:10px; background:#fff; }
    .selectWrap{ display:inline-flex; align-items:center; gap:8px; }
    .selectLabel{ font-size:12px; color:#555; font-weight:700; }

    .row2 { display:grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .plot { width: 100%; height: 420px; }

    .tabs { display:flex; gap:8px; margin: 10px 0 10px 0; }
    .tabbtn {
      padding: 7px 10px; border:1px solid #ddd; border-radius: 12px;
      background:#f7f7f7; cursor:pointer; font-weight:800; font-size:13px;
    }
    .tabbtn.active { background:#eef3ff; border-color:#bcd0ff; }

    .err { color:#b00020; font-size: 13px; white-space: pre-wrap; }

    table { border-collapse: collapse; width: 100%; table-layout: fixed; }
    th, td { border: 1px solid #ddd; padding: 7px 9px; font-size: 13px; vertical-align: top; word-wrap: break-word; }
    th { background: #fafafa; }

    /* people/data 카드 */
    .req-card { background:white; border-radius:12px; padding:12px 14px; margin-bottom:10px; border:1px solid #eee; }
    .req-name { font-weight:900; font-size:15px; display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
    .req-target { margin-top:4px; color:#666; font-size:13px; }
    .req-body { margin-top:8px; color:#222; white-space: pre-wrap; line-height:1.45; }
    .badge { display:inline-flex; align-items:center; padding:3px 9px; border-radius:999px; border:1px solid #ddd; font-size:12px; color:#333; background:#f4f4f4; font-weight:800; }

    /* ✅ 회의요약(텍스트) UI */
    .recapBox { border:1px solid #eee; border-radius:14px; padding:14px; background:#fff; }
    .recapSection { margin-top:12px; }
    .secTitle { font-weight:900; font-size:13px; margin-bottom:8px; }
    .bulletList { margin:0; padding-left:16px; }
    .bulletList li { margin:4px 0; line-height:1.35; }
    .summaryText { white-space: pre-wrap; line-height:1.55; color:#222; padding-left: 2px; }

    /* ✅ 회의요약 상단: [주요안건 | 키워드(워드클라우드)] */
    .textGrid{
      display:grid;
      grid-template-columns: 1fr 340px;
      grid-template-rows: auto 1fr;
      gap:12px;
      align-items:stretch;
    }
    .textGrid .leftTop { grid-column:1; grid-row:1; }
    .textGrid .leftBottom { grid-column:1; grid-row:2; }
    .textGrid .rightKw { grid-column:2; grid-row:1 / span 2; }

    .kwCloud {
      width: 100%;
      height: 260px;
      border:1px solid #eee;
      border-radius:12px;
      background:#fbfbfb;
    }

    /* ✅ 더보기(people/data용) */
    .moreBtn{
      margin-top: 10px;
      padding: 8px 12px;
      border-radius: 12px;
      border: 1px solid #ddd;
      background: #fff;
      cursor: pointer;
      font-weight: 900;
      font-size: 13px;
    }
    .moreRow { display:flex; justify-content:center; }

    @media (max-width: 1100px){
      .textGrid{ grid-template-columns: 1fr; grid-template-rows: auto auto auto; }
      .textGrid .rightKw{ grid-column:1; grid-row:auto; }
      .kwCloud{ height: 220px; }
    }
  </style>
</head>

<body>
  <h2>대시보드</h2>

  <div class="stack">

    <!-- 1) 회차별 회의록 분석 -->
    <div class="card">
      <div class="cardhead">
        <div class="titleRow">
          <span class="badgeTitle">회차별 회의록 분석</span>
          <div class="selectWrap">
            <span class="selectLabel">회차</span>
            <select id="sessionSel"></select>
          </div>
        </div>
      </div>

      <div class="tabs">
        <button class="tabbtn active" data-tab="text">회의요약</button>
        <button class="tabbtn" data-tab="people">발언요약</button>
        <button class="tabbtn" data-tab="data">요구자료</button>
      </div>

      <div id="filterRow" class="controls" style="margin-bottom:10px; display:none;">
        <div class="selectWrap" style="gap:8px;">
          <span class="selectLabel">정당</span>
          <select id="partySel"></select>
        </div>
        <div class="selectWrap" style="gap:8px;">
          <span class="selectLabel">검색</span>
          <input id="q" placeholder="키워드 입력" style="min-width:260px;"/>
        </div>
      </div>

      <div id="tableWrap"></div>
      <div id="moreWrap" class="moreRow"></div>
    </div>

    <!-- 2) 주요 질의의원 -->
    <div class="card">
      <div class="cardhead">
        <h3>주요 질의의원</h3>
      </div>
      <div class="row2">
        <div id="plot_q_top10" class="plot"></div>
        <div id="tbl_q_all" class="plot" style="height:auto; min-height:420px; overflow:auto;"></div>
      </div>
    </div>

    <!-- 3) 법 개정 / 제도개선 / 규정변경 -->
    <div class="card">
      <div class="cardhead">
        <h3>법 개정 · 제도 개선 · 규정 변경</h3>
      </div>
      <div class="row2">
        <div id="plot_law_by_category" class="plot"></div>
        <div id="plot_law_by_party" class="plot"></div>
      </div>
    </div>

    <!-- 4) 트렌드 / 정당별 -->
    <div class="card">
      <div class="cardhead">
        <h3>주요 트렌드 · 정당별 관심</h3>
      </div>
      <div class="row2">
        <div id="plot_trend" class="plot"></div>
        <div id="plot_party" class="plot"></div>
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

  // people/data는 더보기 방식
  more: { people: 20, data: 20 },
  shown: { people: 20, data: 20 },

  // filter
  party: "",   // "" = 전체
  q: "",

  // last fetched rows for current tab
  lastRows: [],

  // for wordcloud
  __pendingWordcloud: [],
};

function uniq(arr){ return [...new Set(arr)]; }

async function fetchJSON(url){
  const res = await fetch(url);
  if (!res.ok) throw new Error(await res.text());
  return await res.json();
}

function setErr(divId, msg){
  document.getElementById(divId).innerHTML = `<div class="err">${msg}</div>`;
}

/* ✅ 여러 키 중 첫 값 선택(발언요약 안 나오던 핵심 원인 해결) */
function pickFirst(obj, keys){
  for (const k of keys){
    if (obj && obj[k] != null){
      const v = obj[k];
      if (typeof v === "string"){
        const t = v.trim();
        if (t) return t;
      } else {
        return v; // object/number 등은 그대로
      }
    }
  }
  return null;
}

function normStr(x){
  if (x == null) return "";
  return String(x).trim();
}

/* =========================
   정당 색상(고정 · 최종)
   ========================= */
function partyColor(party){
  const p = (party || "").trim();
  const map = new Map([
    ["더불어민주당", "#003B96"], ["민주당", "#003B96"],
    ["국민의힘", "#E61E2B"],
    ["기본소득당", "#00D2C3"],
    ["조국혁신당", "#0073CF"],
    ["무소속", "#9ca3af"],
  ]);
  if (map.has(p)) return map.get(p);

  if (p.includes("더불어") || p.includes("민주")) return "#003B96";
  if (p.includes("국민의힘")) return "#E61E2B";
  if (p.includes("기본소득")) return "#00D2C3";
  if (p.includes("조국")) return "#0073CF";
  if (p.includes("무소속")) return "#9ca3af";
  return "#64748b";
}

function textColorForBg(hex){
  if (!hex || !hex.startsWith("#") || hex.length !== 7) return "#fff";
  const r = parseInt(hex.slice(1,3), 16);
  const g = parseInt(hex.slice(3,5), 16);
  const b = parseInt(hex.slice(5,7), 16);
  const luminance = (0.2126*r + 0.7152*g + 0.0722*b) / 255;
  return luminance > 0.6 ? "#111" : "#fff";
}

/* ✅ tab별 공통 필드 추출(키 이름 달라도 동작) */
function getParty(r, tab){
  if (tab === "people"){
    return normStr(pickFirst(r, ["정당","party","소속정당","요구자정당"])) || "";
  }
  if (tab === "data"){
    return normStr(pickFirst(r, ["정당","party","요구자정당","소속정당"])) || "";
  }
  return "";
}

function getSpeaker(r){
  return normStr(pickFirst(r, ["발언자명","의원명","발언자","speaker_name","speaker"])) || "";
}

function getPeopleBody(r){
  return normStr(pickFirst(r, ["발언요약","발화내용 요약","요약","summary","text","본문"])) || "";
}

function getDataName(r){
  return normStr(pickFirst(r, ["요구자명","요구자","요청 의원","requester","speaker_name"])) || "";
}

function getDataTarget(r){
  return normStr(pickFirst(r, ["대상","대상 기관","target","기관","부처"])) || "";
}

function getDataReq(r){
  return normStr(pickFirst(r, ["실제요구자료","요구자료","요구내용","request","text","본문"])) || "";
}

/* =========================
   1) 회차 초기화
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

/* =========================
   2) 회의요약(text_recap) + WordCloud
   ========================= */
function splitAgenda(text){
  const t = (text || "").replace(/\s+/g, " ").trim();
  if (!t) return [];
  return t.split(";").map(x => x.trim()).filter(Boolean);
}

function safeParseJSON(s){
  if (!s) return null;
  if (typeof s === "object") return s; // ✅ 이미 object면 그대로
  if (typeof s !== "string") return null;
  try { return JSON.parse(s); } catch(e){ return null; }
}

function buildKeywordsFromRow(row){
  // 1) RAW JSON (array) 우선
  const raw = safeParseJSON(row["키워드_RAW_JSON"]);
  if (Array.isArray(raw) && raw.length){
    const arr = raw
      .filter(x => x && (x.keyword != null || x.text != null))
      .map(x => ({
        text: String(x.keyword ?? x.text ?? x.word ?? "").trim(),
        weight: Number(x.weight ?? x.w ?? x.value ?? 0),
        reason: x.reason ? String(x.reason) : ""
      }))
      .filter(x => x.text && Number.isFinite(x.weight) && x.weight > 0);
    if (arr.length) return arr;
  }

  // 2) 가중치맵(JSON string or object)
  const mp = safeParseJSON(row["키워드_가중치맵"]);
  if (mp && typeof mp === "object" && !Array.isArray(mp)){
    const arr = Object.entries(mp)
      .map(([k,v]) => ({ text: String(k).trim(), weight: Number(v ?? 0), reason:"" }))
      .filter(x => x.text && Number.isFinite(x.weight) && x.weight > 0);
    if (arr.length) return arr;
  }

  // 3) "단어(숫자)" fallback
  const s = String(row["키워드(가중치포함)"] || "");
  const m = [...s.matchAll(/([^,]+)\(([\d.]+)\)/g)]
    .map(x => ({ text: x[1].trim(), weight: Number(x[2]), reason:"" }))
    .filter(x => x.text && Number.isFinite(x.weight) && x.weight > 0);
  return m;
}

function renderWordCloud(divId, kwList){
  const el = document.getElementById(divId);
  if (!el) return;

  el.innerHTML = "";

  const w = el.clientWidth || 260;
  const h = el.clientHeight || 180;

  if (!kwList || kwList.length === 0){
    el.innerHTML = `<div style="padding:12px;color:#666;">키워드 데이터 없음</div>`;
    return;
  }

  // 상위 80개 제한(너무 많으면 깨짐/느려짐)
  const words0 = kwList.slice().sort((a,b)=>b.weight-a.weight).slice(0, 80);

  const maxW = Math.max(...words0.map(k => k.weight));
  const minW = Math.min(...words0.map(k => k.weight));

  const scale = (x) => {
    if (maxW === minW) return 18;
    return 12 + (x - minW) * (40 - 12) / (maxW - minW);
  };

  const words = words0.map(k => ({
    text: k.text,
    size: scale(k.weight),
    weight: k.weight,
    reason: k.reason || ""
  }));

  // ✅ 알록달록
  const color = d3.scaleOrdinal(d3.schemeTableau10 || d3.schemeCategory10);

  const svg = d3.select(el)
    .append("svg")
    .attr("width", w)
    .attr("height", h);

  const g = svg.append("g")
    .attr("transform", `translate(${w/2},${h/2})`);

  const layout = d3.layout.cloud()
    .size([w, h])
    .words(words)
    .padding(3)
    .rotate(() => 0)
    .font("Arial")
    .fontSize(d => d.size)
    .on("end", draw);

  layout.start();

  function draw(out){
    const texts = g.selectAll("text")
      .data(out)
      .enter().append("text")
      .style("font-family", "Arial")
      .style("font-weight", 900)
      .style("fill", d => color(d.text))
      .style("opacity", d => {
        if (maxW === minW) return 0.9;
        return 0.55 + (d.weight - minW) * (1.0 - 0.55) / (maxW - minW);
      })
      .attr("text-anchor", "middle")
      .attr("transform", d => `translate(${d.x},${d.y})rotate(${d.rotate})`)
      .style("font-size", d => `${d.size}px`)
      .text(d => d.text);

    // 중심 보정(박스 밀림 방지)
    const bbox = g.node().getBBox();
    const dx = (w / 2) - (bbox.x + bbox.width / 2);
    const dy = (h / 2) - (bbox.y + bbox.height / 2);
    g.attr("transform", `translate(${dx},${dy})`);

    texts.append("title")
      .text(d => `가중치: ${d.weight}` + (d.reason ? `\n${d.reason}` : ""));
  }
}

function renderTextRecap(rows){
  if (!rows || rows.length === 0){
    return `<div class="recapBox">데이터 없음</div>`;
  }

  const r = rows[0];

  const agendas = splitAgenda(pickFirst(r, ["주요안건","안건","agenda","main_agenda"]) || "");
  const summary = String(pickFirst(r, ["회의내용 요약","회의요약","요약","summary","text","본문"]) || "");
  const kw = buildKeywordsFromRow(r).sort((a,b)=>b.weight-a.weight);

  const agendaHtml = agendas.length
    ? `<ul class="bulletList">${agendas.map(x=>`<li>${x}</li>`).join("")}</ul>`
    : `<div class="summaryText">데이터 없음</div>`;

  const html = `
    <div class="recapBox">
      <div class="textGrid">
        <div class="leftTop recapSection" style="margin-top:0;">
          <div class="secTitle">주요안건</div>
          ${agendaHtml}
        </div>

        <div class="leftBottom recapSection" style="margin-top:0;">
          <div class="secTitle">회의내용 요약</div>
          <div class="summaryText">${summary}</div>
        </div>

        <div class="rightKw recapSection" style="margin-top:0;">
          <div class="secTitle">키워드</div>
          <div id="wc_keywords" class="kwCloud"></div>
        </div>
      </div>
    </div>
  `;

  state.__pendingWordcloud = kw;
  return html;
}

/* =========================
   3) 발언요약(people_recap) 카드  ✅ 키 호환 강화
   ========================= */
function filterRows(rows, tab){
  let out = rows || [];

  const q = (state.q || "").trim().toLowerCase();
  const partySel = (state.party || "").trim(); // "" = 전체

  if (partySel){
    out = out.filter(r => getParty(r, tab) === partySel);
  }
  if (q){
    out = out.filter(r => JSON.stringify(r).toLowerCase().includes(q));
  }
  return out;
}

function renderPeopleCards(rows){
  const filtered = filterRows(rows, "people");
  if (!filtered || filtered.length === 0) return "<div class='recapBox'>데이터 없음</div>";

  const shown = filtered.slice(0, state.shown.people);

  const cards = shown.map(r => {
    const name = getSpeaker(r);
    const party = getParty(r, "people");
    const body = getPeopleBody(r);

    const bg = party ? partyColor(party) : "#f4f4f4";
    const fg = party ? textColorForBg(bg) : "#111";

    const partyTag = party
      ? `<span class="badge" style="background:${bg};border-color:${bg};color:${fg};font-weight:900;">${party}</span>`
      : "";

    return `
      <div class="req-card">
        <div class="req-name">${name || "(이름 없음)"}${partyTag}</div>
        <div class="req-body">${body || "(요약 없음)"}</div>
      </div>
    `;
  }).join("");

  const canMore = filtered.length > state.shown.people;
  document.getElementById("moreWrap").innerHTML = canMore
    ? `<button class="moreBtn" id="moreBtnPeople">더보기</button>`
    : "";

  document.getElementById("moreBtnPeople")?.addEventListener("click", () => {
    state.shown.people += state.more.people;
    renderRecapFromLast(); // ✅ 재호출 없이 렌더만
  });

  return cards;
}

/* =========================
   4) 요구자료(data_request_recap) 카드  ✅ 키 호환 강화
   ========================= */
function renderDataCards(rows){
  const filtered = filterRows(rows, "data");
  if (!filtered || filtered.length === 0) return "<div class='recapBox'>데이터 없음</div>";

  const shown = filtered.slice(0, state.shown.data);

  const cards = shown.map(r => {
    const name = getDataName(r);
    const target = getDataTarget(r);
    const req = getDataReq(r);
    const cat = normStr(pickFirst(r, ["카테고리","category"])) || "";

    const party = getParty(r, "data");
    let partyTag = "";
    if (party){
      const bg = partyColor(party);
      const fg = textColorForBg(bg);
      partyTag = `<span class="badge" style="background:${bg};border-color:${bg};color:${fg};font-weight:900;">${party}</span>`;
    }

    const catTag = cat ? `<span class="badge">${cat}</span>` : "";

    return `
      <div class="req-card">
        <div class="req-name">${name || "(이름 없음)"}${partyTag}${catTag}</div>
        <div class="req-target">대상: ${target || "-"}</div>
        <div class="req-body">${req || "-"}</div>
      </div>
    `;
  }).join("");

  const canMore = filtered.length > state.shown.data;
  document.getElementById("moreWrap").innerHTML = canMore
    ? `<button class="moreBtn" id="moreBtnData">더보기</button>`
    : "";

  document.getElementById("moreBtnData")?.addEventListener("click", () => {
    state.shown.data += state.more.data;
    renderRecapFromLast(); // ✅ 재호출 없이 렌더만
  });

  return cards;
}

/* =========================
   5) 정당 옵션 채우기 ✅ 키 호환 강화
   ========================= */
function fillPartyOptions(rows, tab){
  const sel = document.getElementById("partySel");
  sel.innerHTML = "";

  const parties = uniq((rows || []).map(r => getParty(r, tab)).filter(Boolean)).sort();

  // 전체
  sel.appendChild(new Option("전체", ""));

  // 없으면 전체만 남김
  for (const p of parties){
    sel.appendChild(new Option(p, p));
  }

  // 현재 선택값 복원(가능하면)
  const wanted = state.party || "";
  const opts = [...sel.options].map(o => o.value);
  if (opts.includes(wanted)) sel.value = wanted;
  else { sel.value = ""; state.party = ""; }
}

/* =========================
   6) 회차별 요약 로드
   ========================= */
async function loadRecap(){
  if (!state.sessionNo){
    document.getElementById("tableWrap").innerHTML = "<div class='recapBox'>회차를 선택하세요</div>";
    document.getElementById("moreWrap").innerHTML = "";
    return;
  }

  const urlMap = {
    text: `/api/recap/text?session_no=${state.sessionNo}&limit=50&offset=0`,
    people: `/api/recap/people?session_no=${state.sessionNo}&limit=5000&offset=0`,
    data: `/api/recap/data?session_no=${state.sessionNo}&limit=5000&offset=0`,
  };

  try {
    const rows = await fetchJSON(urlMap[state.tab]);
    state.lastRows = rows || [];

    // 탭별 UI
    const filterRow = document.getElementById("filterRow");
    const moreWrap = document.getElementById("moreWrap");

    if (state.tab === "text"){
      filterRow.style.display = "none";
      moreWrap.innerHTML = "";
      state.q = "";
      state.party = "";
      document.getElementById("q").value = "";
      document.getElementById("partySel").innerHTML = "";

      document.getElementById("tableWrap").innerHTML = renderTextRecap(state.lastRows);

      setTimeout(() => {
        renderWordCloud("wc_keywords", state.__pendingWordcloud || []);
      }, 0);
      return;
    }

    // people/data
    filterRow.style.display = "flex";
    fillPartyOptions(state.lastRows, state.tab);
    renderRecapFromLast();

  } catch (e){
    document.getElementById("tableWrap").innerHTML = `<div class="err">${String(e)}</div>`;
    document.getElementById("moreWrap").innerHTML = "";
  }
}

/* ✅ 필터 입력 시 재호출 없이 렌더만(원래 잘되던 흐름 유지) */
function renderRecapFromLast(){
  const rows = state.lastRows || [];
  if (state.tab === "people"){
    document.getElementById("tableWrap").innerHTML = renderPeopleCards(rows);
    return;
  }
  if (state.tab === "data"){
    document.getElementById("tableWrap").innerHTML = renderDataCards(rows);
    return;
  }
}

/* =========================
   7) 트렌드/정당별 시각화
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
    hovertemplate: "%{x}<br>"+p+"<br>건수: %{y}<extra></extra>",
    marker: { color: partyColor(p) }
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

/* =========================
   8) 주요 질의의원
   ========================= */
function buildQuestionAgg(qRows){
  const m = new Map();
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
    marker: { color: partyColor(p) }
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
    `<tr><td>${start+i+1}</td><td>${r.speaker}</td><td>${r.party}</td><td>${r.num_questions}</td></tr>`
  ).join("");

  const pager = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin:8px 0;">
      <div>${total===0?0:(start+1)} - ${end} / ${total}</div>
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
    renderTop10("plot_q_top10", __qAll.slice(0, 10));
    __qPage = 0;
    renderQuestionTable("tbl_q_all", __qAll, __qPage, __qPageSize);
  } catch(e){
    setErr("plot_q_top10", String(e));
    document.getElementById("tbl_q_all").innerHTML = `<div class="err">${String(e)}</div>`;
  }
}

/* =========================
   9) 법 개정/제도개선/규정변경
   ========================= */
function regVal(r){
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
    margin:{t:50, r:20, b:170, l:70},
    legend:{orientation:"h", x:0, y:-0.25, xanchor:"left", yanchor:"top"},
  }, {responsive:true, displaylogo:false});
}

function numPick(r, keys, def=0){
  for (const k of keys){
    const v = r?.[k];
    if (v !== undefined && v !== null && String(v).trim() !== ""){
      const n = Number(v);
      return Number.isFinite(n) ? n : def;
    }
  }
  return def;
}

async function loadLaw(){
  try{
    const [policyRows, sessionRows] = await Promise.all([
      fetchJSON("/api/law/stats/policy?limit=5000"),
      fetchJSON("/api/law/stats/session?limit=5000"),
    ]);

    // ✅ 변경된 컬럼명 반영(한글/기존 영문 둘 다 대응)
    const getLaw = (r) => numPick(r, ["num_scope_법개정", "num_scope_law"], 0);
    const getSys = (r) => numPick(r, ["num_scope_제도개선", "num_scope_system"], 0);
    const getReg = (r) => numPick(r, ["num_scope_규정변경", "num_scope_regulation", "num_scope_rule"], 0);

    // ✅ 카테고리 라벨도 바뀌었으면 여기만 바꾸면 됨
    // 샘플 기준: policy_mid (기존: policy_enum)
    const policyLabelField =
      (policyRows?.[0] && ("policy_mid" in policyRows[0])) ? "policy_mid" :
      (policyRows?.[0] && ("policy_enum" in policyRows[0])) ? "policy_enum" :
      "policy_mid";

    const cat = buildStack(
      policyRows,
      policyLabelField,
      getLaw,
      getSys,
      getReg
    );
    renderStacked("plot_law_by_category", "카테고리별", cat.labels, cat.yLaw, cat.ySys, cat.yReg);

    const party = buildStack(
      sessionRows,
      "party",
      getLaw,
      getSys,
      getReg
    );
    renderStacked("plot_law_by_party", "정당별", party.labels, party.yLaw, party.ySys, party.yReg);

  } catch(e){
    setErr("plot_law_by_category", String(e));
    setErr("plot_law_by_party", String(e));
  }
}


/* =========================
   10) 트렌드/정당별 로드
   ========================= */
async function loadTrendParty(){
  try{
    const [trendRows, partyRows] = await Promise.all([
      fetchJSON("/api/trend?limit=5000"),
      fetchJSON("/api/party-domain-metrics?limit=5000"),
    ]);
    renderTrendLineAll("plot_trend", trendRows);
    renderPartyBarAll("plot_party", partyRows);
  } catch(e){
    setErr("plot_trend", String(e));
    setErr("plot_party", String(e));
  }
}

/* =========================
   이벤트
   ========================= */
document.getElementById("sessionSel").addEventListener("change", async (e) => {
  state.sessionNo = Number(e.target.value);

  state.shown.people = state.more.people;
  state.shown.data = state.more.data;

  state.party = "";
  state.q = "";
  document.getElementById("q").value = "";

  await loadRecap();
});

document.getElementById("partySel").addEventListener("change", (e) => {
  state.party = String(e.target.value || "");
  renderRecapFromLast(); // ✅ 재호출 X
});

document.getElementById("q").addEventListener("input", (e) => {
  state.q = String(e.target.value || "");
  renderRecapFromLast(); // ✅ 재호출 X
});

for (const btn of document.querySelectorAll(".tabbtn")){
  btn.addEventListener("click", async () => {
    for (const b of document.querySelectorAll(".tabbtn")) b.classList.remove("active");
    btn.classList.add("active");

    state.tab = btn.dataset.tab;

    state.shown.people = state.more.people;
    state.shown.data = state.more.data;
    state.party = "";
    state.q = "";
    document.getElementById("q").value = "";

    await loadRecap(); // ✅ 탭 바뀔 때만 재호출
  });
}

/* =========================
   초기 로드
   ========================= */
(async () => {
  await initSessions();
  await loadRecap();
  await loadQuestions();
  await loadLaw();
  await loadTrendParty();
})();
</script>

</body>
</html>
"""
