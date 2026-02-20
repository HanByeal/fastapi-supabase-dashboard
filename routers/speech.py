# routers/speech.py
import re
from collections import Counter
from typing import Optional, Dict, Any, List, Tuple

from fastapi import APIRouter, Query, HTTPException

from core.config import TABLES
from core.supabase import sb_select

router = APIRouter(prefix="/api/speech", tags=["speech"])

# ✅ TABLES에 키가 없으면 그냥 "speeches"를 사용 (KeyError로 서버 죽는 것 방지)
TABLE = TABLES.get("speeches", "speeches")


def _validate_date(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        raise HTTPException(status_code=400, detail=f"Invalid date format: {s} (expected YYYY-MM-DD)")
    return s


async def _min_max_date_for_kw(kw: str) -> Tuple[Optional[str], Optional[str]]:
    like = f"%{kw}%"

    rows_min = await sb_select(TABLE, {
        "select": "date",
        "speech_text": f"ilike.{like}",
        "date": "not.is.null",
        "order": "date.asc",
        "limit": 1,
        "offset": 0,
    })
    min_date = rows_min[0]["date"] if rows_min else None

    rows_max = await sb_select(TABLE, {
        "select": "date",
        "speech_text": f"ilike.{like}",
        "date": "not.is.null",
        "order": "date.desc",
        "limit": 1,
        "offset": 0,
    })
    max_date = rows_max[0]["date"] if rows_max else None

    return min_date, max_date


@router.get("/range")
async def speech_range(kw: str = Query(..., min_length=1)):
    try:
        mn, mx = await _min_max_date_for_kw(kw)
        return {"keyword": kw, "min_date": mn, "max_date": mx}
    except HTTPException:
        raise
    except Exception as e:
        # ✅ 파이썬 내부 에러는 메시지 포함해서 500으로
        raise HTTPException(status_code=500, detail=f"speech_range failed: {type(e).__name__}: {e}")


@router.get("/search")
async def speech_search(
    kw: str = Query(..., min_length=1),
    start: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="YYYY-MM-DD"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    try:
        start = _validate_date(start)
        end = _validate_date(end)

        # start/end 없으면 자동 세팅
        if not start or not end:
            mn, mx = await _min_max_date_for_kw(kw)
            if not mn or not mx:
                return {"keyword": kw, "start": None, "end": None, "bucket": "month", "series": [], "speeches": []}
            start = start or mn
            end = end or mx

        like = f"%{kw}%"

        # 1) 발언 목록(최신순)
        cols = "speech_id,session,session_dir,meeting_no,date,speaker_name,speaker_position,party,speech_text,speech_order"
        speeches = await sb_select(TABLE, {
            "select": cols,
            "speech_text": f"ilike.{like}",
            "date": f"gte.{start}",
            "order": "date.desc,speech_order.desc",
            "limit": limit,
            "offset": offset,
        })
        # dict params 한계 때문에 lte는 서버에서 post-filter
        if end:
            speeches = [r for r in speeches if (r.get("date") or "") <= end]

        # 2) 월별 집계
        agg_limit = 20000
        dates_only = await sb_select(TABLE, {
            "select": "date",
            "speech_text": f"ilike.{like}",
            "date": f"gte.{start}",
            "order": "date.asc",
            "limit": agg_limit,
            "offset": 0,
        })
        if end:
            dates_only = [r for r in dates_only if (r.get("date") or "") <= end]

        c = Counter()
        for r in dates_only:
            d = r.get("date")
            if d:
                c[d[:7]] += 1
        series = [{"month": m, "count": c[m]} for m in sorted(c.keys())]

        return {
            "keyword": kw,
            "start": start,
            "end": end,
            "bucket": "month",
            "series": series,
            "speeches": speeches,
            "note": {"agg_limit": agg_limit, "agg_truncated": len(dates_only) >= agg_limit},
        }

    except HTTPException:
        # ✅ Supabase에서 4xx/5xx가 오면 sb_select가 HTTPException으로 올리니까 그대로 내려감
        raise
    except Exception as e:
        # ✅ 파이썬 내부 에러는 메시지 포함해서 500으로
        raise HTTPException(status_code=500, detail=f"speech_search failed: {type(e).__name__}: {e}")