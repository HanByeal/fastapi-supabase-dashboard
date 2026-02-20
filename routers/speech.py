# routers/speech.py
import re
from collections import Counter
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

from fastapi import APIRouter, Query, HTTPException

from core.config import TABLES
from core.supabase import sb_select

router = APIRouter(prefix="/api/speech", tags=["speech"])

TABLE = TABLES.get("speeches", "speeches")

# Supabase(PostgREST)에서 실질적으로 1000행 cap이 걸리는 경우가 많아서
# 안전하게 "페이지 단위"로 끝까지 가져오는 방식으로 고칩니다.
PAGE_SIZE = 1000

# 혹시 키워드가 너무 광범위해서 무한히 커질 수 있으니 서버 보호용 상한
MAX_AGG_ROWS = 300_000      # 집계용(날짜만) 최대 수집 행수
MAX_SPEECH_ROWS = 20_000    # 목록용 최대 수집 행수


def _validate_date(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        raise HTTPException(status_code=400, detail=f"Invalid date format: {s} (expected YYYY-MM-DD)")
    return s


def _month_range(start_ymd: str, end_ymd: str) -> List[str]:
    """YYYY-MM-DD ~ YYYY-MM-DD 사이 월(YYYY-MM) 리스트 생성(빈 달 0 채우기용)"""
    s = datetime.strptime(start_ymd, "%Y-%m-%d").replace(day=1)
    e = datetime.strptime(end_ymd, "%Y-%m-%d").replace(day=1)

    months = []
    cur = s
    while cur <= e:
        months.append(cur.strftime("%Y-%m"))
        # 다음 달로 이동
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)
    return months


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


async def _paged_select_all(
    select_cols: str,
    where_params: Dict[str, Any],
    order: str,
    hard_cap: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Supabase 결과 1000행 cap 대비: offset을 늘려가며 끝까지 수집.
    """
    out: List[Dict[str, Any]] = []
    offset = 0
    pages = 0
    truncated = False

    while True:
        params = dict(where_params)
        params.update({
            "select": select_cols,
            "order": order,
            "limit": PAGE_SIZE,
            "offset": offset,
        })

        rows = await sb_select(TABLE, params)
        pages += 1

        if not rows:
            break

        out.extend(rows)

        # 마지막 페이지면 종료
        if len(rows) < PAGE_SIZE:
            break

        offset += PAGE_SIZE

        # 서버 보호용 상한
        if len(out) >= hard_cap:
            out = out[:hard_cap]
            truncated = True
            break

    return out, {
        "page_size": PAGE_SIZE,
        "pages": pages,
        "rows": len(out),
        "truncated": truncated,
        "hard_cap": hard_cap,
    }


@router.get("/range")
async def speech_range(kw: str = Query(..., min_length=1)):
    try:
        mn, mx = await _min_max_date_for_kw(kw)
        return {"keyword": kw, "min_date": mn, "max_date": mx}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"speech_range failed: {type(e).__name__}: {e}")


@router.get("/search")
async def speech_search(
    kw: str = Query(..., min_length=1),
    start: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="YYYY-MM-DD"),
    limit: int = Query(200, ge=1, le=5000),   # 프론트에서 한 번에 많이 받고 싶으면 5000까지 허용
    offset: int = Query(0, ge=0),
    include_series: bool = Query(True, description="차트 집계 포함 여부"),
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

        # -------------------------
        # 1) 발언 목록(최신순) - "1000행 cap" 대비하여 내부에서 페이지로 수집
        # -------------------------
        cols = (
            "speech_id,session,session_dir,meeting_no,date,"
            "speaker_name,speaker_position,party,speech_text,speech_order"
        )

        base_where = {
            "speech_text": f"ilike.{like}",
            "date": f"gte.{start}",
        }

        # offset부터 limit개만 가져오되, PAGE_SIZE 단위로 반복 호출해서 채움
        # (Supabase가 limit를 1000으로 잘라도, 우리는 다음 offset으로 이어서 가져옴)
        need = limit
        collected: List[Dict[str, Any]] = []
        cur_offset = offset
        pages = 0
        truncated = False

        while len(collected) < need:
            chunk = min(PAGE_SIZE, need - len(collected))
            params = dict(base_where)
            params.update({
                "select": cols,
                "order": "date.desc,speech_order.desc",
                "limit": chunk,
                "offset": cur_offset,
            })
            rows = await sb_select(TABLE, params)
            pages += 1

            if not rows:
                break

            # end는 dict filter 한계 때문에 서버에서 post-filter
            if end:
                rows = [r for r in rows if (r.get("date") or "") <= end]

            collected.extend(rows)

            # 더 이상 가져올 게 없으면 종료
            if len(rows) < chunk:
                break

            cur_offset += chunk

            # 서버 보호용 상한
            if len(collected) >= MAX_SPEECH_ROWS:
                collected = collected[:MAX_SPEECH_ROWS]
                truncated = True
                break

        speeches_note = {
            "requested_limit": limit,
            "requested_offset": offset,
            "returned": len(collected),
            "pages": pages,
            "page_size": PAGE_SIZE,
            "hard_cap": MAX_SPEECH_ROWS,
            "hard_cap_hit": truncated,
        }

        # -------------------------
        # 2) 월별 집계(series) - 날짜만 "끝까지" 페이지로 수집 후 Counter
        # -------------------------
        series: List[Dict[str, Any]] = []
        series_note: Dict[str, Any] = {}

        if include_series:
            dates_only, meta = await _paged_select_all(
                select_cols="date",
                where_params=base_where,
                order="date.asc",
                hard_cap=MAX_AGG_ROWS,
            )

            if end:
                dates_only = [r for r in dates_only if (r.get("date") or "") <= end]

            c = Counter()
            for r in dates_only:
                d = r.get("date")
                if d:
                    c[d[:7]] += 1

            # 빈 달도 0으로 채워서 프론트에서 “뒤가 0으로만 보이는 착시” 방지
            months = _month_range(start, end)
            series = [{"month": m, "count": int(c.get(m, 0))} for m in months]

            series_note = {
                "agg_rows_used": len(dates_only),
                "paging": meta,
            }

        return {
            "keyword": kw,
            "start": start,
            "end": end,
            "bucket": "month",
            "series": series,
            "speeches": collected,
            "note": {
                "speeches": speeches_note,
                "series": series_note,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"speech_search failed: {type(e).__name__}: {e}")