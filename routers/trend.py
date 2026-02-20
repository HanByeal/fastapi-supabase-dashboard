from typing import Optional, Dict, Any, List, Tuple
from collections import defaultdict

from fastapi import APIRouter, Query

from core.config import TABLES
from core.supabase import sb_select

router = APIRouter()

# =========================
# 고정 분류체계 (UI용)
# =========================
L2_LIST = [
    "인공지능·디지털 정부",
    "재난·안전",
    "정부혁신·행정지원",
    "지방행정",
    "지방재정·기타",
]

L3_BY_L2: Dict[str, List[str]] = {
    "인공지능·디지털 정부": ["국가기록물", "전자정부", "정보시스템통합관리"],
    "재난·안전": ["복구지원", "비상대비", "안전및재난", "재난예방", "재난안전교육·연구", "재난지원및구호", "자연재난"],
    "정부혁신·행정지원": ["국가중장기과제", "정부의전", "정부혁신", "조직관리", "청사관리", "행정지원"],
    "지방행정": ["선거및정당", "지방행정"],
    "지방재정·기타": ["지역발전", "지방재정", "특수정책"],
}

# =========================
# helpers
# =========================
def _safe_int(v: Any) -> Optional[int]:
    try:
        if v is None:
            return None
        return int(v)
    except:
        return None

def _parse_csv_list(s: Optional[str]) -> List[str]:
    if not s:
        return []
    return [x.strip() for x in str(s).split(",") if x.strip()]

def _session_in_assemblies(session: Any, assemblies: List[int]) -> bool:
    if not assemblies:
        return True
    try:
        s = int(session)
    except:
        return False

    ok = False
    if 20 in assemblies:
        ok = ok or (353 <= s <= 378)
    if 21 in assemblies:
        ok = ok or (379 <= s <= 414)
    if 22 in assemblies:
        ok = ok or (415 <= s)
    return ok

def _prev_quarter(y: int, q: int) -> Tuple[int, int]:
    q -= 1
    if q <= 0:
        y -= 1
        q = 4
    return y, q

def _shift_back_quarters(y: int, q: int, n_back: int) -> Tuple[int, int]:
    for _ in range(n_back):
        y, q = _prev_quarter(y, q)
    return y, q

def _yq_le(y1: int, q1: int, y2: int, q2: int) -> bool:
    return (y1, q1) <= (y2, q2)

def _in_yq_range(y: int, q: int, y1: int, q1: int, y2: int, q2: int) -> bool:
    return (y1, q1) <= (y, q) <= (y2, q2)

def _quote_in(values: List[str]) -> str:
    # PostgREST: in.("a","b")
    def esc(v: str) -> str:
        return '"' + v.replace('"', '\\"') + '"'
    return f'in.({",".join(esc(v) for v in values)})'

async def _sb_select_all(table: str, base_params: Dict[str, Any], page_size: int = 50000, max_pages: int = 200):
    out: List[Dict[str, Any]] = []
    offset = 0
    for _ in range(max_pages):
        params = dict(base_params)
        params["limit"] = page_size
        params["offset"] = offset
        rows = await sb_select(table, params)
        out.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size
    return out

# =========================
# 1) options (dashboard.js가 기대하는 형태)
#   { years:[...], min:{year,quarter}, max:{year,quarter}, l2:[...] }
# =========================
@router.get("/api/trend2/options")
async def api_trend2_options():
    TABLE = TABLES["trend2"]

    rows_min = await sb_select(TABLE, {
        "select": "year,quarter",
        "year": "not.is.null",
        "quarter": "not.is.null",
        "order": "year.asc,quarter.asc",
        "limit": 1,
        "offset": 0,
    })
    rows_max = await sb_select(TABLE, {
        "select": "year,quarter",
        "year": "not.is.null",
        "quarter": "not.is.null",
        "order": "year.desc,quarter.desc",
        "limit": 1,
        "offset": 0,
    })

    if not rows_min or not rows_max:
        return {"years": [], "min": None, "max": None, "l2": L2_LIST}

    mn = {"year": int(rows_min[0]["year"]), "quarter": int(rows_min[0]["quarter"])}
    mx = {"year": int(rows_max[0]["year"]), "quarter": int(rows_max[0]["quarter"])}

    years = list(range(mn["year"], mx["year"] + 1))
    return {"years": years, "min": mn, "max": mx, "l2": L2_LIST}

@router.get("/api/trend2/options/l3")
async def api_trend2_options_l3(label_l2: str = Query(...)):
    l2 = (label_l2 or "").strip()
    return L3_BY_L2.get(l2, [])

# =========================
# 2) series
# - 최신 누락 해결: 기간(year 범위) DB 필터 + 페이지네이션으로 전량 로딩
# - rows 컬럼 없음: "레코드 1건 = count 1" 로 집계
#
# 반환: [{period:"2026-Q1", label:"재난·안전", count:123}, ...]
# =========================
@router.get("/api/trend2/series")
async def api_trend2_series(
    group_by: str = Query("l2"),                 # "l2" or "l3"
    assemblies: Optional[str] = Query(None),     # "20,21,22"
    recent_n_quarters: Optional[int] = Query(None),

    start_year: Optional[int] = Query(None),
    start_quarter: Optional[int] = Query(None),
    end_year: Optional[int] = Query(None),
    end_quarter: Optional[int] = Query(None),

    l2_in: Optional[str] = Query(None),
    l2_eq: Optional[str] = Query(None),
    l3_in: Optional[str] = Query(None),
):
    TABLE = TABLES["trend2"]
    group_by = (group_by or "l2").strip().lower()
    if group_by not in ("l2", "l3"):
        group_by = "l2"

    # ---- 필터 파싱
    asm_list = []
    for x in _parse_csv_list(assemblies):
        xi = _safe_int(x)
        if xi in (20, 21, 22):
            asm_list.append(xi)

    l2_in_list = _parse_csv_list(l2_in)
    l3_in_list = _parse_csv_list(l3_in)
    l2_eq = (l2_eq or "").strip() or None

    # ---- 최신 분기 계산(최근 N분기)
    if recent_n_quarters:
        # 최신부터 내려오면서 "필터(특히 assemblies)" 통과하는 첫 row를 최신으로 확정
        probe_params: Dict[str, Any] = {
            "select": "year,quarter,session,label_l2,label_l3",
            "year": "not.is.null",
            "quarter": "not.is.null",
            "order": "year.desc,quarter.desc",
            "limit": 5000,
            "offset": 0,
        }
        # 카테고리 필터는 DB에서 먼저 좁힘
        if group_by == "l2":
            if l2_in_list:
                probe_params["label_l2"] = _quote_in(l2_in_list)
        else:
            if l2_eq:
                probe_params["label_l2"] = f"eq.{l2_eq}"
            if l3_in_list:
                probe_params["label_l3"] = _quote_in(l3_in_list)

        probe = await sb_select(TABLE, probe_params)

        y2 = q2 = None
        for r in probe:
            if not _session_in_assemblies(r.get("session"), asm_list):
                continue
            y = _safe_int(r.get("year"))
            q = _safe_int(r.get("quarter"))
            if y is None or q is None:
                continue
            y2, q2 = y, q
            break

        if y2 is None or q2 is None:
            return []

        n = max(1, int(recent_n_quarters))
        y1, q1 = _shift_back_quarters(y2, q2, n - 1)

    else:
        # ---- 직접 구간
        if None in (start_year, start_quarter, end_year, end_quarter):
            return []
        y1, q1, y2, q2 = int(start_year), int(start_quarter), int(end_year), int(end_quarter)
        if not _yq_le(y1, q1, y2, q2):
            y1, q1, y2, q2 = y2, q2, y1, q1

    # ---- DB에서 "최신부터" 페이지네이션 (핵심)
    base_params: Dict[str, Any] = {
        "select": "year,quarter,label_l2,label_l3,session,meeting_key",
        "year": f"lte.{y2}",                    # end_year까지만 DB에서 컷(최신 누락 방지 + 범위 축소)
        "order": "year.desc,quarter.desc",      # 최신부터 내려오기
    }

    # 카테고리 필터(DB 선필터)
    if group_by == "l2":
        if l2_in_list:
            base_params["label_l2"] = _quote_in(l2_in_list)
    else:
        if l2_eq:
            base_params["label_l2"] = f"eq.{l2_eq}"
        if l3_in_list:
            base_params["label_l3"] = _quote_in(l3_in_list)

    page_size = 50000
    offset = 0
    agg = defaultdict(int)
    stop = False

    while True:
        params = dict(base_params)
        params["limit"] = page_size
        params["offset"] = offset
        page = await sb_select(TABLE, params)

        if not page:
            break

        for r in page:
            y = _safe_int(r.get("year"))
            q = _safe_int(r.get("quarter"))
            if y is None or q is None:
                continue

            # start보다 과거면(정렬이 desc라) 여기부터 끝까지 다 과거 -> 종료
            if (y, q) < (y1, q1):
                stop = True
                break

            # end 분기 경계(같은 연도에서 Q가 더 큰 것 제거)
            if (y, q) > (y2, q2):
                continue

            # assemblies 보정
            if not _session_in_assemblies(r.get("session"), asm_list):
                continue

            # 범위 내인지 최종 확인
            if not _in_yq_range(y, q, y1, q1, y2, q2):
                continue

            period = f"{y}-Q{q}"
            label = (r.get("label_l3") if group_by == "l3" else r.get("label_l2")) or "미분류"
            agg[(period, str(label))] += 1  # ✅ rows 컬럼 없음 -> 레코드 1건=1

        if stop:
            break

        if len(page) < page_size:
            break

        offset += page_size

    out = [{"period": p, "label": l, "count": c} for (p, l), c in agg.items()]
    out.sort(key=lambda x: (x["period"], x["label"]))
    return out

# =========================
# 3) 정당별 관심
# =========================
@router.get("/api/party-domain-metrics")
async def api_party_domain_metrics(limit: int = 5000, offset: int = 0):
    rows = await sb_select(TABLES["party_domain_metrics"], {"select": "*", "limit": limit, "offset": offset})

    fixed = []
    for r in rows:
        l2 = r.get("l2") or r.get("label_l2") or r.get("domain_l2") or r.get("domain") or r.get("대분류")
        party = r.get("party") or r.get("party_name") or r.get("정당") or r.get("소속")
        mc = r.get("meeting_count")
        if mc is None:
            mc = r.get("count") or r.get("cnt") or r.get("n")

        fixed.append({
            "l2": l2,
            "party": party,
            "meeting_count": _safe_int(mc) or 0,
        })

    return fixed