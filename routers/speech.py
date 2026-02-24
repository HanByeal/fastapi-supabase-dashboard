# routers/speech.py
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

from fastapi import APIRouter, Query, HTTPException

from core.config import TABLES
from core.supabase import sb_select

router = APIRouter(prefix="/api/speech", tags=["speech"])

TABLE = TABLES.get("speeches", "speeches")

# Supabase(PostgREST)에서 1000행 cap이 걸리는 경우가 많아서 페이지로 끝까지 가져옴
PAGE_SIZE = 1000

# 서버 보호용 상한
MAX_AGG_ROWS = 300_000       # 차트/월집계용(date만) 최대 수집 행수
MAX_SPEECH_ROWS = 20_000     # 목록용 최대 수집 행수
MAX_WIDGET_ROWS = 120_000    # 위젯(Top 발언자) 계산용 최대 수집 행수


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

        if len(rows) < PAGE_SIZE:
            break

        offset += PAGE_SIZE

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


# ---- 스니펫 유틸: 키워드 기준 ±2문장 (총 5문장) ----
_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n+")

def _make_snippet(text: str, kw: str, window: int = 2, max_sent: int = 5, max_chars: int = 360) -> Tuple[str, bool]:
    """키워드 포함 스니펫 생성.
    - 기본: 키워드가 포함된 문장을 찾고 ±window 문장 범위에서 최대 max_sent 문장으로 구성
    - 예외(문장 분리/줄바꿈 등으로 매칭 실패): 키워드 위치 기준으로 문자 window를 잘라서 키워드 포함 보장
    - 프론트가 5줄(line-clamp)로 잘라 보여도 키워드가 안 보이는 문제를 줄이기 위해,
      결과 스니펫에서 키워드가 너무 뒤에 있으면(>120자) 앞부분을 잘라 키워드를 앞쪽으로 당김.
    반환: (snippet_text, truncated_flag)
    """
    if not text or not kw:
        return (text or ""), False

    t = str(text)
    pat = re.compile(re.escape(kw), re.IGNORECASE)

    sents = [s.strip() for s in _SENT_SPLIT.split(t) if s.strip()]
    # 1) 문장 기반
    idx = None
    for i, s in enumerate(sents):
        if pat.search(s):
            idx = i
            break

    truncated = False
    if idx is not None and sents:
        start_i = max(0, idx - window)
        end_i = min(len(sents), idx + window + 1)
        # 최대 max_sent 문장으로 제한(키워드가 가운데 오도록)
        clip_sents = sents[start_i:end_i]
        if len(clip_sents) > max_sent:
            # idx를 중심으로 max_sent 맞춤
            rel = idx - start_i
            left = max(0, rel - (max_sent // 2))
            right = left + max_sent
            clip_sents = clip_sents[left:right]
        clip = " ".join(clip_sents).strip()
        truncated = (start_i > 0) or (end_i < len(sents))
    else:
        # 2) fallback: 문자 window로 키워드 포함 보장
        m = pat.search(t)
        if not m:
            # 정말 못 찾으면 앞부분
            clip = " ".join(sents[:max_sent]).strip() if sents else t[:max_chars]
            return clip[:max_chars], True if len(clip) > max_chars else False

        pos = m.start()
        pre = 140
        post = max_chars - pre
        s0 = max(0, pos - pre)
        s1 = min(len(t), pos + post)
        clip = t[s0:s1].strip()
        if s0 > 0:
            clip = "… " + clip
        if s1 < len(t):
            clip = clip + " …"
        truncated = True

    # 3) 키워드를 앞쪽으로 당김(프론트 line-clamp 대비)
    m2 = pat.search(clip)
    if m2:
        kpos = m2.start()
        if kpos > 120:
            # 키워드 앞을 줄여서 키워드가 80~120자 근처에 오도록
            cut_from = max(0, kpos - 100)
            clip2 = clip[cut_from:].lstrip()
            clip = ("… " + clip2) if cut_from > 0 else clip2
            truncated = True

    # 4) max_chars 최종 제한(키워드 포함 구간 우선)
    if len(clip) > max_chars:
        m3 = pat.search(clip)
        if m3:
            pos = m3.start()
            pre = 100
            post = max_chars - pre
            s0 = max(0, pos - pre)
            s1 = min(len(clip), pos + post)
            piece = clip[s0:s1]
            clip = ("… " if s0 > 0 else "") + piece + (" …" if s1 < len(clip) else "")
            truncated = True
        else:
            clip = clip[:max_chars].rstrip() + "…"
            truncated = True

    return clip, truncated


    sents = [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]
    if not sents:
        return text, False

    pat = re.compile(re.escape(kw), re.IGNORECASE)
    idx = None
    for i, s in enumerate(sents):
        if pat.search(s):
            idx = i
            break

    if idx is None:
        clip = " ".join(sents[:max_sent])
        truncated = len(sents) > max_sent
        return clip, truncated

    start_i = max(0, idx - window)
    end_i = min(len(sents), start_i + max_sent)
    start_i = max(0, end_i - max_sent)

    clip_sents = sents[start_i:end_i]
    clip = " ".join(clip_sents)
    truncated = (start_i > 0) or (end_i < len(sents))
    return clip, truncated


def _build_widgets_from_series(series: List[Dict[str, Any]]) -> Dict[str, Any]:
    # 피크 월
    peak_month = None
    peak_count = 0
    if series:
        # 동률이면 "더 최신 월"을 피크로
        peak = max(series, key=lambda x: (int(x.get("count", 0)), x.get("month", "")))
        peak_month = peak.get("month")
        peak_count = int(peak.get("count", 0))

    # 최근 6개월(시리즈는 이미 전체 월이 들어오므로 뒤에서 6개)
    last6 = series[-6:] if series else []
    recent_6m = [{"month": x.get("month"), "count": int(x.get("count", 0))} for x in last6]

    return {
        "peak_month": {"month": peak_month, "count": peak_count},
        "recent_6m": recent_6m,
    }


async def _top_speakers_for_kw_range(
    base_where: Dict[str, Any],
    end: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    # speaker_name 기준 Top5 (party/position은 최빈값으로 붙임)
    rows, meta = await _paged_select_all(
        select_cols="date,speaker_name,speaker_position,party",
        where_params=base_where,
        order="date.asc",
        hard_cap=MAX_WIDGET_ROWS,
    )
    if end:
        rows = [r for r in rows if (r.get("date") or "") <= end]

    cnt = Counter()
    party_mode = defaultdict(Counter)
    pos_mode = defaultdict(Counter)

    for r in rows:
        name = (r.get("speaker_name") or "").strip()
        if not name:
            continue
        cnt[name] += 1
        party_mode[name][(r.get("party") or "").strip() or "-"] += 1
        pos_mode[name][(r.get("speaker_position") or "").strip() or "-"] += 1

    top = []
    for name, c in cnt.most_common(5):
        party = party_mode[name].most_common(1)[0][0] if party_mode[name] else "-"
        pos = pos_mode[name].most_common(1)[0][0] if pos_mode[name] else "-"
        top.append({"name": name, "party": party, "position": pos, "count": int(c)})

    note = {
        "used_rows": len(rows),
        "paging": meta,
        "truncated": bool(meta.get("truncated")),
    }
    return top, note


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
    limit: int = Query(200, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    include_series: bool = Query(True, description="차트 집계 포함 여부"),
    include_widgets: bool = Query(True, description="오른쪽 위젯(Top/피크/최근6개월) 계산 포함 여부"),
):
    try:
        start = _validate_date(start)
        end = _validate_date(end)

        # start/end 없으면 자동 세팅
        if not start or not end:
            mn, mx = await _min_max_date_for_kw(kw)
            if not mn or not mx:
                return {
                    "keyword": kw,
                    "start": None,
                    "end": None,
                    "bucket": "month",
                    "series": [],
                    "speeches": [],
                    "next_offset": offset,
                    "has_more": False,
                    "widgets": {"top_speakers": [], "peak_month": {"month": None, "count": 0}, "recent_6m": []},
                }
            start = start or mn
            end = end or mx

        like = f"%{kw}%"

        cols = (
            "speech_id,session,session_dir,meeting_no,date,"
            "speaker_name,speaker_position,party,speech_text,speech_order"
        )

        base_where = {
            "speech_text": f"ilike.{like}",
            "date": f"gte.{start}",
        }

        # -------------------------
        # 1) 발언 목록(최신순) - offset부터 limit개만
        # -------------------------
        need = limit
        collected: List[Dict[str, Any]] = []
        cur_offset = offset
        pages = 0
        hard_cap_hit = False

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

            # end는 PostgREST 필터 조합 제약 때문에 서버에서 post-filter
            if end:
                rows = [r for r in rows if (r.get("date") or "") <= end]

            # 스니펫(원문 유지 + snippet_text/snippet_truncated)
            for r in rows:
                txt = r.get("speech_text") or ""
                snippet, trunc = _make_snippet(txt, kw, window=2, max_sent=5)
                r["snippet_text"] = snippet
                r["snippet_truncated"] = trunc

            collected.extend(rows)

            if len(rows) < chunk:
                break

            cur_offset += chunk

            if len(collected) >= MAX_SPEECH_ROWS:
                collected = collected[:MAX_SPEECH_ROWS]
                hard_cap_hit = True
                break

        returned = len(collected)
        next_offset = offset + returned
        has_more = (returned == limit) and (not hard_cap_hit)

        speeches_note = {
            "requested_limit": limit,
            "requested_offset": offset,
            "returned": returned,
            "pages": pages,
            "page_size": PAGE_SIZE,
            "hard_cap": MAX_SPEECH_ROWS,
            "hard_cap_hit": hard_cap_hit,
        }

        # -------------------------
        # 2) 월별 집계(series)
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

            months = _month_range(start, end)
            series = [{"month": m, "count": int(c.get(m, 0))} for m in months]

            series_note = {
                "agg_rows_used": len(dates_only),
                "paging": meta,
            }

        # -------------------------
        # 3) 오른쪽 위젯(Top 발언자 / 피크 월 / 최근 6개월)
        #    - "첫 페이지 + include_widgets=true"일 때만 계산 권장(부하 방지)
        # -------------------------
        widgets = {
            "top_speakers": [],
            "peak_month": {"month": None, "count": 0},
            "recent_6m": [],
        }
        widgets_note: Dict[str, Any] = {}

        if include_series:
            widgets.update(_build_widgets_from_series(series))

        if include_widgets:
            top, top_note = await _top_speakers_for_kw_range(base_where=base_where, end=end)
            widgets["top_speakers"] = top
            widgets_note["top_speakers"] = top_note

        # ✅ total_count 추가 (series가 있으면 합계 = 전체 매칭 건수)
        total_count = sum(int(x.get("count", 0)) for x in (series or [])) if include_series else None
        
        return {
            "keyword": kw,
            "start": start,
            "end": end,
            "bucket": "month",
            "series": series,
            "total_count": total_count,
            "speeches": collected,
            "next_offset": next_offset,
            "has_more": has_more,
            "widgets": widgets,
            "note": {
                "speeches": speeches_note,
                "series": series_note,
                "widgets": widgets_note,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"speech_search failed: {type(e).__name__}: {e}")