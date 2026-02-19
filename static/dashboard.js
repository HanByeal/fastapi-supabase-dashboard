/* =========================
   공통 유틸
   ========================= */
const state = {
  tab: "text",

  assemblyNo: null,
  allSessions: [],
  sessionNo: null,

  qAssemblyNo: null,
  qSessionNo: null,

  more: { people: 20, data: 20 },
  shown: { people: 20, data: 20 },

  party: "",
  q: "",

  lastRows: [],
  __pendingWordcloud: [],
  qRawRows: null,

  // ✅ trend2 options cache
  trend2Options: null,

    // ✅ law2 options cache
    law2Options: null,

    // ✅ law2 선택 상태
    law2: { assembly: "22", l2: "전체", l3: "전체" },

  // ✅ 트렌드: 적용 버튼 방식(변경 시 dirty)
  trendDirty: false,
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

function pickFirst(obj, keys){
  for (const k of keys){
    if (obj && obj[k] != null){
      const v = obj[k];
      if (typeof v === "string"){
        const t = v.trim();
        if (t) return t;
      } else {
        return v;
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
   ✅ 로딩 표시
   ========================= */
function setLoading(which, on){
  const map = {
    recap: "loadingRecap",
    q: "loadingQ",
    trend: "loadingTrend",
    law2: "loadingLaw2",
  };
  const el = document.getElementById(map[which]);
  if (!el) return;
  el.style.display = on ? "inline-flex" : "none";
}

async function refreshBoth(){
  setLoading("recap", true);
  setLoading("q", true);
  try{
    await Promise.allSettled([ loadRecap(), loadQuestions() ]);
  } finally {
    setLoading("recap", false);
    setLoading("q", false);
  }
}

/* =========================
   대수 매핑(프론트)
   ========================= */
function getAssemblyBySession(n){
  const x = Number(n);
  if (!Number.isFinite(x)) return null;
  if (x >= 353 && x <= 378) return 20;
  if (x >= 379 && x <= 414) return 21;
  if (x >= 415) return 22;
  return null;
}

function initAssemblyOptions(selId){
  const sel = document.getElementById(selId);
  if (!sel) return;
  sel.innerHTML = "";
  [20, 21, 22].forEach(a => sel.appendChild(new Option(`${a}대`, String(a))));
}
function session_label(n){ return `${n}회`; }

/* 상단: 대수에 맞춰 회차 렌더 */
function renderSessionOptions(){
  const sessionSel = document.getElementById("sessionSel");
  sessionSel.innerHTML = "";

  const a = Number(state.assemblyNo);
  const filtered = (state.allSessions || []).filter(s => getAssemblyBySession(s) === a).sort((x,y)=>x-y);

  if (!filtered.length){
    sessionSel.innerHTML = `<option value="">(회차 없음)</option>`;
    state.sessionNo = null;
    return;
  }

  for (const s of filtered){
    sessionSel.appendChild(new Option(session_label(s), String(s)));
  }

  const wanted = Number(state.sessionNo);
  const optVals = [...sessionSel.options].map(o => Number(o.value));
  if (wanted && optVals.includes(wanted)){
    sessionSel.value = String(wanted);
    state.sessionNo = wanted;
  } else {
    state.sessionNo = Number(sessionSel.value) || null;
  }
}

/* 하단(질의의원): 대수에 맞춰 회차 렌더 */
function renderQSessionOptions(){
  const sel = document.getElementById("qSessionSel");
  sel.innerHTML = "";

  const a = Number(state.qAssemblyNo);
  const filtered = (state.allSessions || []).filter(s => getAssemblyBySession(s) === a).sort((x,y)=>x-y);

  if (!filtered.length){
    sel.innerHTML = `<option value="">(회차 없음)</option>`;
    state.qSessionNo = null;
    return;
  }

  for (const s of filtered){
    sel.appendChild(new Option(session_label(s), String(s)));
  }

  const wanted = Number(state.qSessionNo);
  const optVals = [...sel.options].map(o => Number(o.value));
  if (wanted && optVals.includes(wanted)){
    sel.value = String(wanted);
    state.qSessionNo = wanted;
  } else {
    state.qSessionNo = Number(sel.value) || null;
  }
}

/* 상단 ↔ 하단 동기화 */
let __syncLock = false;

function syncTopToQ(){
  if (__syncLock) return;
  __syncLock = true;
  try{
    state.qAssemblyNo = state.assemblyNo;
    state.qSessionNo = state.sessionNo;

    document.getElementById("qAssemblySel").value = String(state.qAssemblyNo);
    renderQSessionOptions();
    if (state.qSessionNo) document.getElementById("qSessionSel").value = String(state.qSessionNo);
  } finally {
    __syncLock = false;
  }
}

function syncQToTop(){
  if (__syncLock) return;
  __syncLock = true;
  try{
    state.assemblyNo = state.qAssemblyNo;
    state.sessionNo = state.qSessionNo;

    document.getElementById("assemblySel").value = String(state.assemblyNo);
    renderSessionOptions();
    if (state.sessionNo) document.getElementById("sessionSel").value = String(state.sessionNo);
  } finally {
    __syncLock = false;
  }
}

/* =========================
   정당 색상
   ========================= */
function partyColor(party){
  const p = (party || "").trim();

  const OPEN_HEX  = "#003E98";
  const OPEN_GRAD = "linear-gradient(90deg, #003E98 0% 50%, #FBC700 50% 100%)";
  const OPEN = (
    typeof CSS !== "undefined" &&
    CSS.supports &&
    (CSS.supports("background-image", OPEN_GRAD) || CSS.supports("background", OPEN_GRAD))
  ) ? OPEN_GRAD : OPEN_HEX;

  const map = new Map([
    ["더불어민주당", "#003B96"], ["민주당", "#003B96"],
    ["국민의힘", "#E61E2B"],
    ["기본소득당", "#00D2C3"],
    ["조국혁신당", "#0073CF"],
    ["미래통합당", "#EF426F"],
    ["미래한국당", "#B4065F"],
    ["정의당", "#FFED00"],
    ["더불어시민당", "#006CB7"],
    ["열린민주당", OPEN],
    ["새누리당", "#C9252B"],
    ["국민의당", "#006241"],
    ["무소속", "#9ca3af"],
  ]);
  if (map.has(p)) return map.get(p);

  if (p.includes("열린민주")) return OPEN;
  if (p.includes("더불어시민")) return "#006CB7";
  if (p.includes("미래한국")) return "#B4065F";
  if (p.includes("미래통합")) return "#EF426F";
  if (p.includes("새누리")) return "#C9252B";
  if (p.includes("국민의당")) return "#006241";
  if (p.includes("정의")) return "#FFED00";

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

/* =========================
   회차 초기화
   ========================= */
async function initSessions(){
  initAssemblyOptions("assemblySel");
  initAssemblyOptions("qAssemblySel");

  const sessions = await fetchJSON("/api/sessions");
  state.allSessions = (sessions || []).map(Number).filter(Number.isFinite);

  if (!state.allSessions.length){
    document.getElementById("assemblySel").innerHTML = `<option value="22">22대</option>`;
    document.getElementById("sessionSel").innerHTML = `<option value="">(회차 없음)</option>`;
    document.getElementById("qAssemblySel").innerHTML = `<option value="22">22대</option>`;
    document.getElementById("qSessionSel").innerHTML = `<option value="">(회차 없음)</option>`;
    state.assemblyNo = 22;
    state.sessionNo = null;
    state.qAssemblyNo = 22;
    state.qSessionNo = null;
    return;
  }

  const maxS = Math.max(...state.allSessions);
  const baseAssembly = getAssemblyBySession(maxS) || 22;

  state.assemblyNo = baseAssembly;
  state.sessionNo = maxS;

  document.getElementById("assemblySel").value = String(state.assemblyNo);
  renderSessionOptions();
  state.sessionNo = Number(document.getElementById("sessionSel").value) || null;

  state.qAssemblyNo = state.assemblyNo;
  state.qSessionNo = state.sessionNo;
  document.getElementById("qAssemblySel").value = String(state.qAssemblyNo);
  renderQSessionOptions();
  state.qSessionNo = Number(document.getElementById("qSessionSel").value) || null;
}

/* =========================
   회의요약 + WordCloud (기존 그대로)
   ========================= */
function splitAgenda(text){
  const t = (text || "").replace(/\s+/g, " ").trim();
  if (!t) return [];
  return t.split(";").map(x => x.trim()).filter(Boolean);
}
function safeParseJSON(s){
  if (!s) return null;
  if (typeof s === "object") return s;
  if (typeof s !== "string") return null;
  try { return JSON.parse(s); } catch(e){ return null; }
}
function buildKeywordsFromRow(row){
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
  const mp = safeParseJSON(row["키워드_가중치맵"]);
  if (mp && typeof mp === "object" && !Array.isArray(mp)){
    const arr = Object.entries(mp)
      .map(([k,v]) => ({ text: String(k).trim(), weight: Number(v ?? 0), reason:"" }))
      .filter(x => x.text && Number.isFinite(x.weight) && x.weight > 0);
    if (arr.length) return arr;
  }
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

  const words0 = kwList.slice().sort((a,b)=>b.weight-a.weight).slice(0, 80);
  const maxW = Math.max(...words0.map(k => k.weight));
  const minW = Math.min(...words0.map(k => k.weight));
  const scale = (x) => {
    if (maxW === minW) return 18;
    return 12 + (x - minW) * (52 - 12) / (maxW - minW);
  };

  const words = words0.map(k => ({
    text: k.text,
    size: scale(k.weight),
    weight: k.weight,
    reason: k.reason || ""
  }));

  const color = d3.scaleOrdinal(d3.schemeTableau10 || d3.schemeCategory10);

  const svg = d3.select(el).append("svg").attr("width", w).attr("height", h);
  const g = svg.append("g").attr("transform", `translate(${w/2},${h/2})`);

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

/* people/data 렌더 (기존) */
function getParty(r, tab){
  if (tab === "people") return normStr(pickFirst(r, ["정당","party","소속정당","요구자정당"])) || "";
  if (tab === "data") return normStr(pickFirst(r, ["정당","party","요구자정당","소속정당"])) || "";
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

function filterRows(rows, tab){
  let out = rows || [];
  const q = (state.q || "").trim().toLowerCase();
  const partySel = (state.party || "").trim();
  if (partySel) out = out.filter(r => getParty(r, tab) === partySel);
  if (q) out = out.filter(r => JSON.stringify(r).toLowerCase().includes(q));
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
    renderRecapFromLast();
  });

  return cards;
}

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
    renderRecapFromLast();
  });

  return cards;
}

function fillPartyOptions(rows, tab){
  const sel = document.getElementById("partySel");
  sel.innerHTML = "";

  const parties = uniq((rows || []).map(r => getParty(r, tab)).filter(Boolean)).sort();
  sel.appendChild(new Option("전체", ""));
  for (const p of parties) sel.appendChild(new Option(p, p));

  const wanted = state.party || "";
  const opts = [...sel.options].map(o => o.value);
  if (opts.includes(wanted)) sel.value = wanted;
  else { sel.value = ""; state.party = ""; }
}

/* 회차별 요약 로드 */
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

  const rows = await fetchJSON(urlMap[state.tab]);
  state.lastRows = rows || [];

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

  filterRow.style.display = "flex";
  fillPartyOptions(state.lastRows, state.tab);
  renderRecapFromLast();
}

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
   ✅ trend2: 적용 버튼 방식
   ========================= */
function getMultiSelectedValues(sel){
  return [...sel.selectedOptions].map(o => o.value);
}
function fillSelectOptions(sel, values, keepSelected=false){
  const prev = keepSelected ? new Set(getMultiSelectedValues(sel)) : new Set();
  sel.innerHTML = "";
  for (const v of values){
    const opt = new Option(v, v);
    sel.appendChild(opt);
    if (keepSelected && prev.has(v)) opt.selected = true;
  }
}

function markTrendDirty(){
  state.trendDirty = true;
  document.getElementById("trendApply").disabled = false;
}

function buildTrend2Query(){
  // 1) 고급: 대수 제한
  const useAssembly = document.getElementById("trendUseAssembly").checked;
  let assemblies = [];
  if (useAssembly){
    assemblies = getMultiSelectedValues(document.getElementById("trendAssembly"))
      .map(Number).filter(n => [20,21,22].includes(n));
  }

  // 2) 그룹
  const group_by = document.querySelector('input[name="trendGroup"]:checked')?.value || "l2";

  // 3) 기간
  const preset = document.getElementById("trendPreset").value;
  let recent_n_quarters = null;
  let start_year=null, start_quarter=null, end_year=null, end_quarter=null;

  if (preset.startsWith("recent_")){
    recent_n_quarters = Number(preset.replace("recent_","")) || 8;
  } else {
    start_year = Number(document.getElementById("trendStartY").value);
    start_quarter = Number(document.getElementById("trendStartQ").value);
    end_year = Number(document.getElementById("trendEndY").value);
    end_quarter = Number(document.getElementById("trendEndQ").value);
  }

  // 4) 카테고리
  let l2_in = null, l2_eq = null, l3_in = null;

  if (group_by === "l2"){
    const l2s = getMultiSelectedValues(document.getElementById("trendL2Multi")).filter(Boolean);
    if (l2s.length) l2_in = l2s.join(",");
  } else {
    l2_eq = (document.getElementById("trendL2One").value || "").trim() || null;
    const l3s = getMultiSelectedValues(document.getElementById("trendL3Multi")).filter(Boolean);
    if (l3s.length) l3_in = l3s.join(",");
  }

  const p = new URLSearchParams();
  if (assemblies.length) p.set("assemblies", assemblies.join(","));
  p.set("group_by", group_by);

  if (recent_n_quarters){
    p.set("recent_n_quarters", String(recent_n_quarters));
  } else {
    p.set("start_year", String(start_year));
    p.set("start_quarter", String(start_quarter));
    p.set("end_year", String(end_year));
    p.set("end_quarter", String(end_quarter));
  }

  if (l2_in) p.set("l2_in", l2_in);
  if (l2_eq) p.set("l2_eq", l2_eq);
  if (l3_in) p.set("l3_in", l3_in);

  return p.toString();
}

function renderTrend2Line(divId, rows){
  const enriched = (rows || []).map(r => ({
    period: String(r.period || ""),
    label: String(r.label || "미분류"),
    count: Number(r.count || 0),
  }));

  if (!enriched.length){
    document.getElementById(divId).innerHTML =
      `<div class="err">선택한 조건에 해당하는 데이터가 없습니다.</div>`;
    return;
  }

  const periods = uniq(enriched.map(r=>r.period)).sort();
  const labels = uniq(enriched.map(r=>r.label)).sort();

  const byLabel = new Map(labels.map(l => [l, new Map()]));
  for (const r of enriched){
    byLabel.get(r.label).set(r.period, r.count);
  }

  const data = labels.map(l => ({
    type:"scatter",
    mode:"lines+markers",
    name:l,
    x: periods,
    y: periods.map(p => byLabel.get(l).get(p) ?? 0),
    hovertemplate: "%{x}<br>"+l+"<br>건수: %{y}<extra></extra>"
  }));

  Plotly.newPlot(divId, data, {
    title:{text:"분기별 트렌드(건수)", x:0},
    xaxis:{tickangle:-20, automargin:true},
    yaxis:{title:"건수", automargin:true},
    margin:{t:50, r:20, b:210, l:70},
    legend:{ orientation:"h", x:0, y:-0.45, xanchor:"left", yanchor:"top" },
  }, {responsive:true, displaylogo:false});
}

async function initTrend2Controls(){
  const opts = await fetchJSON("/api/trend2/options");
  state.trend2Options = opts;

  const years = (opts.years || []).map(String);
  const startY = document.getElementById("trendStartY");
  const endY = document.getElementById("trendEndY");
  startY.innerHTML = ""; endY.innerHTML = "";
  for (const y of years){
    startY.appendChild(new Option(y, y));
    endY.appendChild(new Option(y, y));
  }

  // 기본값: min/max
  if (opts.min && opts.max){
    startY.value = String(opts.min.year);
    document.getElementById("trendStartQ").value = String(opts.min.quarter);
    endY.value = String(opts.max.year);
    document.getElementById("trendEndQ").value = String(opts.max.quarter);
  } else if (years.length){
    startY.value = years[0];
    endY.value = years[years.length-1];
  }

  // L2 옵션
  fillSelectOptions(document.getElementById("trendL2Multi"), opts.l2 || []);
  fillSelectOptions(document.getElementById("trendL2One"), opts.l2 || []);

  if ((opts.l2 || []).length){
    document.getElementById("trendL2One").value = opts.l2[0];
  }

  await reloadL3Options();
}

async function reloadL3Options(){
  const l2 = (document.getElementById("trendL2One").value || "").trim();
  if (!l2){
    fillSelectOptions(document.getElementById("trendL3Multi"), []);
    return;
  }
  const l3 = await fetchJSON(`/api/trend2/options/l3?label_l2=${encodeURIComponent(l2)}`);
  fillSelectOptions(document.getElementById("trendL3Multi"), l3 || []);
}

async function loadTrend2(){
  setLoading("trend", true);
  try{
    const qs = buildTrend2Query();
    const rows = await fetchJSON(`/api/trend2/series?${qs}`);
    renderTrend2Line("plot_trend", rows);
    state.trendDirty = false;
    document.getElementById("trendApply").disabled = true;
  } catch(e){
    setErr("plot_trend", String(e));
  } finally {
    setLoading("trend", false);
  }
}

/* =========================
   정당별 관심(기존 유지)
   ========================= */
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
    title:{text:"정당별 관심 (안건 등장 수)", x:0},
    barmode:"group",
    xaxis:{tickangle:-20, automargin:true},
    yaxis:{title:"건수", automargin:true},
    margin:{t:50, r:20, b:210, l:70},
    legend:{ orientation:"h", x:0, y:-0.45, xanchor:"left", yanchor:"top" },
  }, {responsive:true, displaylogo:false});
}

async function loadPartyMetrics(){
  try{
    const partyRows = await fetchJSON("/api/party-domain-metrics?limit=5000");
    renderPartyBarAll("plot_party", partyRows);
  } catch(e){
    setErr("plot_party", String(e));
  }
}

/* =========================
   주요 질의의원(기존)
   ========================= */
function getQuestionSessionNo(r){
  const v = pickFirst(r, ["session_no","회차","회의회차","session","meeting_session","sessionNo"]);
  if (v == null) return null;
  const m = String(v).match(/(\d+)/);
  return m ? Number(m[1]) : null;
}
function buildQuestionAggFiltered(qRows, sessionNo){
  const ses = Number(sessionNo);
  const m = new Map();

  for (const r of (qRows || [])){
    const sNo = getQuestionSessionNo(r);
    if (ses && sNo !== ses) continue;

    const speaker = r.speaker_name ?? r.speaker ?? "";
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
  const x = rowsTop10.map(r => String(r.speaker).trim());
  const y = rowsTop10.map(r => Number(r.num_questions ?? 0));
  const parties = rowsTop10.map(r => r.party || "미분류");
  const colors = parties.map(p => partyColor(p));

  const data = [{
    type: "bar",
    x,
    y,
    marker: { color: colors },
    customdata: parties,
    hovertemplate: "%{x}<br>%{customdata}<br>질의 수: %{y}<extra></extra>",
    offset: -0.45,
  }];

  Plotly.newPlot(divId, data, {
    title:{text:`질의의원 Top ${x.length}`, x:0},
    xaxis:{tickangle:-20, automargin:true},
    yaxis:{title:"질의 수", automargin:true},
    margin:{t:50, r:20, b:120, l:70},
    showlegend:false,
    bargap: 0.55,
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
  const sessionNo = state.qSessionNo || state.sessionNo;
  if (!sessionNo){
    Plotly.purge("plot_q_top10");
    document.getElementById("tbl_q_all").innerHTML = "<div class='err'>회차를 선택하세요</div>";
    return;
  }

  state.qRawRows = await fetchJSON(
    `/api/questions/stats/session?session_no=${sessionNo}&limit=5000&offset=0`
  );

  __qAll = buildQuestionAggFiltered(state.qRawRows, sessionNo);

  renderTop10("plot_q_top10", __qAll.slice(0, 15));
  __qPage = 0;
  renderQuestionTable("tbl_q_all", __qAll, __qPage, __qPageSize);
}

/* =========================
   법 개정/제도개선(기존)
   ========================= */
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
        {
          type: "bar", name: "법 개정", x: xLabels, y: yLaw,
          marker: { color: "#3B82F6" } // 블루
        },
        {
          type: "bar", name: "제도 개선", x: xLabels, y: ySys,
          marker: { color: "#F97316" } // 오렌지
        },
        {
          type: "bar", name: "규정 변경", x: xLabels, y: yReg,
          marker: { color: "#22C55E" } // 그린
        },
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
      const asm = state.law2?.assembly || "22";
      const l2  = state.law2?.l2 || "전체";
      const l3  = state.law2?.l3 || "전체";
  
      const qsCat = new URLSearchParams({
        assembly: asm, l2: l2, l3: l3, limit: "200000", offset: "0"
      }).toString();
  
      const qsParty = new URLSearchParams({
        assembly: asm, limit: "200000", offset: "0"
      }).toString();
  
      const [catRows, partyRows] = await Promise.all([
        fetchJSON(`/api/law2/stack/category?${qsCat}`),
        fetchJSON(`/api/law2/stack/party?${qsParty}`),
      ]);
  
      const getLaw = (r) => numPick(r, ["num_scope_법개정"], 0);
      const getSys = (r) => numPick(r, ["num_scope_제도개선"], 0);
      const getReg = (r) => numPick(r, ["num_scope_규정변경"], 0);
  
      const cat = buildStack(catRows, "category", getLaw, getSys, getReg);
      renderStacked("plot_law_by_category", "카테고리별", cat.labels, cat.yLaw, cat.ySys, cat.yReg);
  
      const party = buildStack(partyRows, "party", getLaw, getSys, getReg);
      renderStacked("plot_law_by_party", "정당별", party.labels, party.yLaw, party.ySys, party.yReg);
  
    } catch(e){
      setErr("plot_law_by_category", String(e));
      setErr("plot_law_by_party", String(e));
    }
  }

  async function initLaw2Controls(){
    const asmSel = document.getElementById("law2AssemblySel");
    const l2Sel  = document.getElementById("law2L2Sel");
    const l3Sel  = document.getElementById("law2L3Sel");
    if (!asmSel || !l2Sel || !l3Sel) return;
  
    // state 기본
    state.law2 = state.law2 || { assembly: "22", l2: "전체", l3: "전체" };
  
    // 대수 옵션
    asmSel.innerHTML = "";
    ["전체","20","21","22"].forEach(v => {
      asmSel.appendChild(new Option(v === "전체" ? "전체" : `${v}대`, v));
    });
    asmSel.value = state.law2.assembly || "22";
  
    // 옵션 로드 + L2/L3 세팅
    await reloadLaw2Options();
  
    // 대수 변경: 두 그래프 다
    asmSel.addEventListener("change", async () => {
      state.law2.assembly = asmSel.value || "22";
      state.law2.l2 = "전체";
      state.law2.l3 = "전체";
      await reloadLaw2Options();
      await loadLaw();
    });
  
    // L2 변경: 카테고리만
    l2Sel.addEventListener("change", async () => {
      state.law2.l2 = l2Sel.value || "전체";
      state.law2.l3 = "전체";
      fillLaw2L3ByCurrentL2();
      await loadLawCategoryOnly();
    });
  
    // L3 변경: 카테고리만
    l3Sel.addEventListener("change", async () => {
      state.law2.l3 = l3Sel.value || "전체";
      await loadLawCategoryOnly();
    });
  }
  
  async function reloadLaw2Options(){
    const asmSel = document.getElementById("law2AssemblySel");
    const l2Sel  = document.getElementById("law2L2Sel");
    const l3Sel  = document.getElementById("law2L3Sel");
    if (!asmSel || !l2Sel || !l3Sel) return;
  
    const asm = asmSel.value || "22";
    const qs = new URLSearchParams({ assembly: asm, limit: "200000", offset: "0" }).toString();
    const opts = await fetchJSON(`/api/law2/options?${qs}`);
    state.law2Options = opts;
  
    // L2 채우기
    l2Sel.innerHTML = "";
    ["전체", ...(opts.l2 || [])].forEach(v => l2Sel.appendChild(new Option(v, v)));
    l2Sel.value = state.law2.l2 || "전체";
  
    // L3 채우기
    fillLaw2L3ByCurrentL2();
  }
  
  function fillLaw2L3ByCurrentL2(){
    const l2Sel  = document.getElementById("law2L2Sel");
    const l3Sel  = document.getElementById("law2L3Sel");
    if (!l2Sel || !l3Sel) return;
  
    const curL2 = l2Sel.value || "전체";
    const map = state.law2Options?.l3_by_l2 || {};
  
    l3Sel.innerHTML = "";
    if (curL2 === "전체"){
      l3Sel.appendChild(new Option("전체", "전체"));
    } else {
     ["전체", ...((map[curL2] || []))].forEach(v => l3Sel.appendChild(new Option(v, v)));
    }
    l3Sel.value = "전체";
    state.law2.l3 = "전체";
  }
  
  async function loadLawCategoryOnly(){
    try{
      const asm = state.law2?.assembly || "22";
      const l2  = state.law2?.l2 || "전체";
      const l3  = state.law2?.l3 || "전체";
  
      const qsCat = new URLSearchParams({
        assembly: asm, l2: l2, l3: l3, limit: "200000", offset: "0"
      }).toString();
  
      const catRows = await fetchJSON(`/api/law2/stack/category?${qsCat}`);
  
      const getLaw = (r) => numPick(r, ["num_scope_법개정"], 0);
      const getSys = (r) => numPick(r, ["num_scope_제도개선"], 0);
      const getReg = (r) => numPick(r, ["num_scope_규정변경"], 0);
  
      const cat = buildStack(catRows, "category", getLaw, getSys, getReg);
      renderStacked("plot_law_by_category", "카테고리별", cat.labels, cat.yLaw, cat.ySys, cat.yReg);
    } catch(e){
      setErr("plot_law_by_category", String(e));
    }
  }
  

/* =========================
   이벤트(상단)
   ========================= */
document.getElementById("assemblySel")?.addEventListener("change", async (e) => {
  state.assemblyNo = Number(e.target.value);
  state.sessionNo = null;

  state.shown.people = state.more.people;
  state.shown.data = state.more.data;
  state.party = "";
  state.q = "";
  document.getElementById("q").value = "";

  renderSessionOptions();
  state.sessionNo = Number(document.getElementById("sessionSel").value) || null;

  syncTopToQ();
  await refreshBoth();
});

document.getElementById("sessionSel").addEventListener("change", async (e) => {
  state.sessionNo = Number(e.target.value);

  state.shown.people = state.more.people;
  state.shown.data = state.more.data;

  state.party = "";
  state.q = "";
  document.getElementById("q").value = "";

  syncTopToQ();
  await refreshBoth();
});

document.getElementById("partySel").addEventListener("change", (e) => {
  state.party = String(e.target.value || "");
  renderRecapFromLast();
});

document.getElementById("q").addEventListener("input", (e) => {
  state.q = String(e.target.value || "");
  renderRecapFromLast();
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

    setLoading("recap", true);
    try { await loadRecap(); }
    finally { setLoading("recap", false); }
  });
}

/* 이벤트(하단: 질의의원) */
document.getElementById("qAssemblySel")?.addEventListener("change", async (e) => {
  if (__syncLock) return;

  state.qAssemblyNo = Number(e.target.value);
  state.qSessionNo = null;

  renderQSessionOptions();
  state.qSessionNo = Number(document.getElementById("qSessionSel").value) || null;

  syncQToTop();

  state.shown.people = state.more.people;
  state.shown.data = state.more.data;
  state.party = "";
  state.q = "";
  document.getElementById("q").value = "";

  await refreshBoth();
});

document.getElementById("qSessionSel")?.addEventListener("change", async (e) => {
  if (__syncLock) return;

  state.qSessionNo = Number(e.target.value) || null;

  syncQToTop();

  state.shown.people = state.more.people;
  state.shown.data = state.more.data;
  state.party = "";
  state.q = "";
  document.getElementById("q").value = "";

  await refreshBoth();
});

/* =========================
   ✅ trend2 UI 동작(적용 버튼)
   ========================= */
function setTrendGroupUI(group){
  const isL2 = (group === "l2");
  document.getElementById("wrapL2Multi").style.display = isL2 ? "inline-flex" : "none";
  document.getElementById("wrapL2One").style.display   = isL2 ? "none" : "inline-flex";
  document.getElementById("wrapL3Multi").style.display = isL2 ? "none" : "inline-flex";
}

function setTrendPresetDisabled(){
  const preset = document.getElementById("trendPreset").value;
  const isCustom = (preset === "custom");
  document.getElementById("trendStartY").disabled = !isCustom;
  document.getElementById("trendStartQ").disabled = !isCustom;
  document.getElementById("trendEndY").disabled = !isCustom;
  document.getElementById("trendEndQ").disabled = !isCustom;
}

document.getElementById("trendApply").addEventListener("click", loadTrend2);

document.getElementById("trendPreset").addEventListener("change", () => {
  setTrendPresetDisabled();
  markTrendDirty();
});

document.getElementById("trendStartY").addEventListener("change", markTrendDirty);
document.getElementById("trendStartQ").addEventListener("change", markTrendDirty);
document.getElementById("trendEndY").addEventListener("change", markTrendDirty);
document.getElementById("trendEndQ").addEventListener("change", markTrendDirty);

for (const r of document.querySelectorAll('input[name="trendGroup"]')){
  r.addEventListener("change", async () => {
    const g = document.querySelector('input[name="trendGroup"]:checked')?.value || "l2";
    setTrendGroupUI(g);
    if (g === "l3"){
      await reloadL3Options();
    }
    markTrendDirty();
  });
}

document.getElementById("trendL2Multi").addEventListener("change", markTrendDirty);

document.getElementById("trendL2One").addEventListener("change", async () => {
  await reloadL3Options();
  markTrendDirty();
});

document.getElementById("trendL3Multi").addEventListener("change", markTrendDirty);

// 고급옵션: 대수 제한 토글
document.getElementById("trendUseAssembly").addEventListener("change", (e) => {
  const on = !!e.target.checked;
  document.getElementById("wrapAssembly").style.display = on ? "inline-flex" : "none";
  markTrendDirty();
});

document.getElementById("trendAssembly").addEventListener("change", markTrendDirty);

/* =========================
   초기 로드
   ========================= */
(async () => {
  await initSessions();

  setLoading("recap", true);
  try { await loadRecap(); }
  finally { setLoading("recap", false); }

  setLoading("q", true);
  try { await loadQuestions(); }
  finally { setLoading("q", false); }

  setLoading("law2", true);
  try{
    await initLaw2Controls();
    await loadLaw();
  } finally {
    setLoading("law2", false);
  }
  
  // ✅ trend2 UI 초기화
  await initTrend2Controls();
  setTrendGroupUI("l2");

  // preset 기본: 최근 8분기 → 직접선택 비활성
  setTrendPresetDisabled();

  // 초기 1회 렌더(바로 보여주기)
  await loadTrend2();

  // 정당별 관심은 기존 그대로
  await loadPartyMetrics();
})();
