from typing import Optional, Dict, Any, List
from collections import defaultdict

from fastapi import APIRouter, Query

from core.config import TABLES
from core.supabase import sb_select

router = APIRouter()

@router.get("/api/trend2/options")
async def api_trend2_options():
    rows = await sb_select(TABLES["trend2"], {"select": "year,quarter,label_l2", "limit": 200000, "offset": 0})

    years = [r.get("year") for r in rows if r.get("year") is not None]
    quarters = [r.get("quarter") for r in rows if r.get("quarter") is not None]
    y_min = min(years) if years else None
    y_max = max(years) if years else None
    q_min = min(quarters) if quarters else None
    q_max = max(quarters) if quarters else None

    l2_set = set()
    for r in rows:
        v = r.get("label_l2")
        if v:
            l2_set.add(v)

    return {
        "year_min": y_min,
        "year_max": y_max,
        "quarter_min": q_min,
        "quarter_max": q_max,
        "l2_list": sorted(l2_set),
    }

@router.get("/api/trend2/series")
async def api_trend2_series(
    y_from: int = Query(...),
    q_from: int = Query(...),
    y_to: int = Query(...),
    q_to: int = Query(...),
    group: str = Query("l2"),              # l2 or l3
    l2: Optional[str] = Query(None),       # when group=l3
    category: str = Query("count"),        # count|share|docshare
    assembly: Optional[int] = Query(None), # 20/21/22
):
    # 원본이 main.py에 있던 로직 그대로 옮기는 게 목표입니다.
    # 아래는 main.py 로직을 그대로 가져온 형태입니다.

    rows = await sb_select(TABLES["trend2"], {
        "select": "year,quarter,label_l2,label_l3,rows,docs,session",
        "limit": 200000,
        "offset": 0,
    })

    def in_range(y: int, q: int) -> bool:
        a = y * 10 + q
        b1 = y_from * 10 + q_from
        b2 = y_to * 10 + q_to
        return b1 <= a <= b2

    bucket = defaultdict(lambda: defaultdict(lambda: {"rows": 0, "docs": 0}))

    for r in rows:
        y = r.get("year")
        q = r.get("quarter")
        if y is None or q is None:
            continue
        if not in_range(int(y), int(q)):
            continue

        # 대수 제한(옵션)
        if assembly is not None:
            s = r.get("session")
            if s is None:
                continue
            try:
                s = int(s)
            except:
                continue
            if assembly == 20 and not (353 <= s <= 378):
                continue
            if assembly == 21 and not (379 <= s <= 414):
                continue
            if assembly == 22 and not (415 <= s):
                continue

        l2v = r.get("label_l2")
        l3v = r.get("label_l3")
        if group == "l3":
            if not l2 or l2v != l2:
                continue
            key = l3v or "(none)"
        else:
            key = l2v or "(none)"

        ym = f"{int(y)}-Q{int(q)}"
        bucket[key][ym]["rows"] += int(r.get("rows") or 0)
        bucket[key][ym]["docs"] += int(r.get("docs") or 0)

    # 전체 분모(share/docshare 계산용)
    total_by_time = defaultdict(lambda: {"rows": 0, "docs": 0})
    for key, series in bucket.items():
        for t, v in series.items():
            total_by_time[t]["rows"] += v["rows"]
            total_by_time[t]["docs"] += v["docs"]

    out: List[Dict[str, Any]] = []
    for key, series in bucket.items():
        points = []
        for t in sorted(series.keys()):
            v = series[t]
            if category == "share":
                denom = total_by_time[t]["rows"] or 1
                val = v["rows"] / denom
            elif category == "docshare":
                denom = total_by_time[t]["docs"] or 1
                val = v["docs"] / denom
            else:
                val = v["rows"]
            points.append({"t": t, "v": val})
        out.append({"name": key, "points": points})

    return {"series": out}


@router.get("/api/party-domain-metrics")
async def api_party_domain_metrics(limit: int = 5000, offset: int = 0):
    return await sb_select(TABLES["party_domain_metrics"], {"select": "*", "limit": limit, "offset": offset})

def _safe_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    # bool은 int의 서브클래스라 제외
    if isinstance(v, bool):
        return None
    try:
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            return int(v) if v.is_integer() else None
        s = str(v).strip()
        if not s:
            return None
        return int(float(s))  # "2017", "2017.0" 모두 처리
    except:
        return None