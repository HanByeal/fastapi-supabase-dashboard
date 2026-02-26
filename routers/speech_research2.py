# routers/speech.py
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

from fastapi import APIRouter, Query, HTTPException
import meilisearch

import urllib3
import requests
import meilisearch

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

if not hasattr(requests.sessions.Session, "_original_request_for_meili"):
    requests.sessions.Session._original_request_for_meili = requests.sessions.Session.request

def patch_requests_for_meili():
    if requests.sessions.Session.request is not getattr(requests.sessions.Session, "_patched_request_for_meili", None):
        def _patched_request(self, method, url, **kwargs):
            kwargs.setdefault("verify", False)
            return requests.sessions.Session._original_request_for_meili(self, method, url, **kwargs)

        requests.sessions.Session._patched_request_for_meili = _patched_request
        requests.sessions.Session.request = _patched_request

patch_requests_for_meili()


# router = APIRouter(prefix="/api/speech", tags=["speech"]) # 원본 -> 실험페이지
router = APIRouter(prefix="/api/speech_research2", tags=["speech_research2"])

MEILI_HOST = (os.getenv("MEILI_HOST") or "").strip()
MEILI_API_KEY = (os.getenv("MEILI_API_KEY") or "").strip()
MEILI_INDEX = (os.getenv("MEILI_INDEX") or "speeches").strip()

if not MEILI_HOST or not MEILI_API_KEY:
    raise RuntimeError("MEILI_HOST / MEILI_API_KEY environment variables are required")

client = meilisearch.Client(MEILI_HOST, MEILI_API_KEY)
index = client.index(MEILI_INDEX)

# ✅ XSN(접미사) 중 결합해도 자연스러운 경우만 표시용 토큰으로 합칩니다.
_SUFFIX_NOUNS = {"성", "권", "화", "법", "제", "안"}
_SUFFIX_XSN = {"성", "권"}

PAGE_SIZE = 1000
MAX_AGG_ROWS = 300_000
MAX_SPEECH_ROWS = 20_000
MAX_WIDGET_ROWS = 120_000


def _nospace(s: str) -> str:
    return re.sub(r"\s+", "", (s or "")).strip()


def _extract_highlight_terms(kw: str) -> List[str]:
    kw = (kw or "").strip()
    if not kw:
        return []

    terms: List[str] = []

    # 원문 완전일치 우선
    terms.append(kw)

    # 공백 제거 버전도 함께 사용
    ns = _nospace(kw)
    if ns and ns != kw:
        terms.append(ns)

    # 공백 검색어면 토큰 단위도 추가
    parts = [x.strip() for x in re.split(r"\s+", kw) if x.strip()]
    for x in parts:
        if len(x) >= 2:
            terms.append(x)

    # 무공백 한글 검색어면 2~4글자 연속 조각을 추가
    # 예: '선거투명성' -> '선거', '투명', '투명성' 등
    if len(parts) <= 1 and len(ns) >= 2:
        max_n = min(4, len(ns))
        for n in range(max_n, 1, -1):
            for i in range(0, len(ns) - n + 1):
                chunk = ns[i:i+n]
                if len(chunk) >= 2:
                    terms.append(chunk)

    out: List[str] = []
    seen = set()
    for x in terms:
        x = (x or "").strip()
        if x and x not in seen:
            out.append(x)
            seen.add(x)
    return out[:12]


def _validate_date(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        raise HTTPException(status_code=400, detail=f"Invalid date format: {s} (expected YYYY-MM-DD)")
    return s


def _month_range(start_ymd: str, end_ymd: str) -> List[str]:
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


_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n+")


def _make_snippet(text: str, kw: str, window: int = 2, max_sent: int = 5, max_chars: int = 360) -> Tuple[str, bool]:
    if not text or not kw:
        return (text or ""), False

    t = str(text)
    pat = re.compile(re.escape(kw), re.IGNORECASE)
    sents = [s.strip() for s in _SENT_SPLIT.split(t) if s.strip()]

    idx = None
    for i, s in enumerate(sents):
        if pat.search(s):
            idx = i
            break

    truncated = False
    if idx is not None and sents:
        start_i = max(0, idx - window)
        end_i = min(len(sents), idx + window + 1)
        clip_sents = sents[start_i:end_i]
        if len(clip_sents) > max_sent:
            rel = idx - start_i
            left = max(0, rel - (max_sent // 2))
            right = left + max_sent
            clip_sents = clip_sents[left:right]
        clip = " ".join(clip_sents).strip()
        truncated = (start_i > 0) or (end_i < len(sents))
    else:
        m = pat.search(t)
        if not m:
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

    m2 = pat.search(clip)
    if m2:
        kpos = m2.start()
        if kpos > 120:
            cut_from = max(0, kpos - 100)
            clip2 = clip[cut_from:].lstrip()
            clip = ("… " + clip2) if cut_from > 0 else clip2
            truncated = True

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

    truncated = (_nospace(clip) != _nospace(text))
    return clip, truncated


def _build_widgets_from_series(series: List[Dict[str, Any]]) -> Dict[str, Any]:
    peak_month = None
    peak_count = 0
    if series:
        peak = max(series, key=lambda x: (int(x.get("count", 0)), x.get("month", "")))
        peak_month = peak.get("month")
        peak_count = int(peak.get("count", 0))
    last6 = series[-6:] if series else []
    recent_6m = [{"month": x.get("month"), "count": int(x.get("count", 0))} for x in last6]
    return {
        "peak_month": {"month": peak_month, "count": peak_count},
        "recent_6m": recent_6m,
    }


def _meili_filter(start: Optional[str], end: Optional[str]) -> Optional[str]:
    parts: List[str] = []
    if start:
        parts.append(f'date >= "{start}"')
    if end:
        parts.append(f'date <= "{end}"')
    return " AND ".join(parts) if parts else None


async def _meili_search_all(
    kw: str,
    *,
    start: Optional[str],
    end: Optional[str],
    attrs: List[str],
    hard_cap: int,
    sort: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    offset = 0
    pages = 0
    truncated = False
    filter_expr = _meili_filter(start, end)

    while True:
        remaining = hard_cap - len(out)
        if remaining <= 0:
            truncated = True
            break

        payload: Dict[str, Any] = {
            "limit": min(PAGE_SIZE, remaining),
            "offset": offset,
            "attributesToRetrieve": attrs,
        }
        if filter_expr:
            payload["filter"] = filter_expr
        if sort:
            payload["sort"] = sort

        res = index.search(kw, payload)
        rows = res.get("hits", []) or []
        pages += 1
        if not rows:
            break

        out.extend(rows)
        if len(rows) < payload["limit"]:
            break
        offset += payload["limit"]

    return out, {
        "page_size": PAGE_SIZE,
        "pages": pages,
        "rows": len(out),
        "truncated": truncated,
        "hard_cap": hard_cap,
    }


async def _min_max_date_for_kw(kw: str) -> Tuple[Optional[str], Optional[str]]:
    rows, _ = await _meili_search_all(
        kw,
        start=None,
        end=None,
        attrs=["date"],
        hard_cap=200_000,
        sort=["date:asc"],
    )
    dates = sorted([r.get("date") for r in rows if r.get("date")])
    if not dates:
        return None, None
    return dates[0], dates[-1]


async def _top_speakers_for_kw_range(
    kw: str,
    start: str,
    end: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows, meta = await _meili_search_all(
        kw,
        start=start,
        end=end,
        attrs=["date", "speaker_name", "speaker_position", "party"],
        hard_cap=MAX_WIDGET_ROWS,
        sort=["date:asc"],
    )

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
        rows, _ = await _meili_search_all(
            kw,
            start=None,
            end=None,
            attrs=["date"],
            hard_cap=200000,
            sort=["date:asc"],
        )

        dates = sorted([r.get("date") for r in rows if r.get("date")])
        if not dates:
            return {"keyword": kw, "min_date": None, "max_date": None}

        return {
            "keyword": kw,
            "min_date": dates[0],
            "max_date": dates[-1],
        }

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
    include_series: bool = Query(True),
    include_widgets: bool = Query(True),
):
    try:
        start = _validate_date(start)
        end = _validate_date(end)

        # start/end 자동 보정
        if not start or not end:
            all_dates, _ = await _meili_search_all(
                kw,
                start=None,
                end=None,
                attrs=["date"],
                hard_cap=200000,
                sort=["date:asc"],
            )
            dates = sorted([r.get("date") for r in all_dates if r.get("date")])
            if not dates:
                return {
                    "keyword": kw,
                    "start": None,
                    "end": None,
                    "bucket": "month",
                    "series": [],
                    "total_count": 0,
                    "speeches": [],
                    "next_offset": offset,
                    "has_more": False,
                    "widgets": {
                        "top_speakers": [],
                        "peak_month": {"month": None, "count": 0},
                        "recent_6m": [],
                    },
                    "highlight_terms": _extract_highlight_terms(kw),
                    "search_mode": {"used_fallback": False, "fallback_tokens": []},
                    "note": {},
                }
            start = start or dates[0]
            end = end or dates[-1]

        filter_expr = _meili_filter(start, end)

        # 1) 발언 목록 (페이지네이션)
        search_payload = {
            "limit": limit,
            "offset": offset,
            "attributesToRetrieve": [
                "speech_id", "session", "session_dir", "meeting_no", "date",
                "speaker_name", "speaker_position", "party",
                "speech_text", "speech_order"
            ],
            "attributesToHighlight": ["speech_text"],
            "sort": ["date:desc", "speech_order:desc"],
        }
        if filter_expr:
            search_payload["filter"] = filter_expr

        res = index.search(kw, search_payload)
        hits = res.get("hits", []) or []

        # fallback 값 (include_series=False일 때만 사용)
        total_count = int(res.get("estimatedTotalHits") or 0)

        highlight_terms = _extract_highlight_terms(kw)

        collected = []
        for r in hits:
            txt = r.get("speech_text") or ""
            snippet, trunc = _make_snippet(txt, kw, window=2, max_sent=5)

            item = dict(r)
            item["snippet_text"] = snippet
            item["snippet_truncated"] = trunc
            collected.append(item)

        # 2) 월별 집계 (전체 기준)
        series: List[Dict[str, Any]] = []
        series_note: Dict[str, Any] = {}
        if include_series:
            date_rows, meta = await _meili_search_all(
                kw,
                start=start,
                end=end,
                attrs=["date"],
                hard_cap=200000,
                sort=["date:asc"],
            )

            # 총건수는 전체 집계 기준으로 덮어씀
            total_count = len(date_rows)

            c = Counter()
            for r in date_rows:
                d = r.get("date")
                if d:
                    c[d[:7]] += 1

            months = _month_range(start, end)
            series = [{"month": m, "count": int(c.get(m, 0))} for m in months]
            series_note = {"agg_rows_used": len(date_rows), "paging": meta}

        next_offset = offset + len(collected)
        has_more = next_offset < total_count

        # 3) 위젯
        widgets = {
            "top_speakers": [],
            "peak_month": {"month": None, "count": 0},
            "recent_6m": [],
        }
        widgets_note: Dict[str, Any] = {}

        if include_series:
            widgets.update(_build_widgets_from_series(series))

        if include_widgets:
            speaker_rows, meta = await _meili_search_all(
                kw,
                start=start,
                end=end,
                attrs=["date", "speaker_name", "speaker_position", "party"],
                hard_cap=200000,
                sort=["date:asc"],
            )

            cnt = Counter()
            party_mode = defaultdict(Counter)
            pos_mode = defaultdict(Counter)

            for r in speaker_rows:
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

            widgets["top_speakers"] = top
            widgets_note["top_speakers"] = {
                "used_rows": len(speaker_rows),
                "paging": meta,
                "truncated": bool(meta.get("truncated")),
            }

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
            "highlight_terms": highlight_terms,
            "search_mode": {"used_fallback": False, "fallback_tokens": []},
            "note": {
                "speeches": {
                    "requested_limit": limit,
                    "requested_offset": offset,
                    "returned": len(collected),
                },
                "series": series_note,
                "widgets": widgets_note,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"speech_search failed: {type(e).__name__}: {e}")