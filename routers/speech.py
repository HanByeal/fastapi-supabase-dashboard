# routers/speech.py
import re
from functools import lru_cache
from collections import Counter, defaultdict
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

from fastapi import APIRouter, Query, HTTPException

from core.config import TABLES
from core.supabase import sb_select

router = APIRouter(prefix="/api/speech", tags=["speech"])

TABLE = TABLES.get("speeches", "speeches")
# ✅ XSN(접미사) 중 결합해도 자연스러운 경우만 표시용 토큰으로 합칩니다.
# 예) '투명'+'성' -> '투명성', '투표'+'권' -> '투표권'
_SUFFIX_NOUNS = {"성", "권", "화", "법", "제", "안"}


# -------------------------
# 검색 유틸
# -------------------------
def _nospace(s: str) -> str:
    return re.sub(r"\s+", "", (s or "")).strip()

# Kiwi(선택)
try:
    from kiwipiepy import Kiwi  # type: ignore
    _KIWI = Kiwi()
except Exception:
    _KIWI = None

# 접미사(선거 '투명' + '성' => '투명성', '투표'+'권' => '투표권')
_SUFFIX_XSN = {"성", "권"}

def _extract_and_tokens(kw: str, max_tokens: int = 3) -> List[str]:
    """AND(교집합) 폴백에 사용할 검색 토큰.
    - 기본: NNG/NNP 등 명사 토큰 사용
    - 예외: XSN 접미사(성/권)는 바로 앞 명사에 붙여 단어를 '복원' (투명성/투표권)
    """
    kw = (kw or "").strip()
    if not kw or not _KIWI:
        return []

    toks = _KIWI.tokenize(kw)

    out: List[str] = []
    for t in toks:
        form = getattr(t, "form", "")
        tag = getattr(t, "tag", "")
        if not form:
            continue
        if tag.startswith("NN"):
            out.append(form)
        elif out and tag == "XSN" and len(form) == 1 and form in _SUFFIX_XSN:
            out[-1] = out[-1] + form

    # 중복 제거(순서 유지) + 길이 2 이상
    dedup: List[str] = []
    seen = set()
    for x in out:
        x = (x or "").strip()
        if len(x) < 2:
            continue
        if x not in seen:
            dedup.append(x); seen.add(x)

    # 최소 2개 필요
    return dedup[:max_tokens] if len(dedup) >= 2 else []

def _build_and_param(tokens: List[str]) -> Optional[str]:
    toks = [t for t in (tokens or []) if t]
    if len(toks) < 2:
        return None
    parts = [f"speech_text.ilike.%{t}%" for t in toks]
    return "(" + ",".join(parts) + ")"

@lru_cache(maxsize=256)
def _extract_highlight_terms(kw: str) -> List[str]:
    """하이라이트용(표시용) 토큰/구문.
    - 가능한 한 '재외국민 투표권'처럼 구문도 포함
    - Kiwi가 있어도 항상 리스트 반환(절대 None 반환 금지)
    """
    kw = (kw or "").strip()
    if not kw:
        return []

    # Kiwi 없으면 원문만
    if not _KIWI:
        return [kw]

    toks = _KIWI.tokenize(kw)
    terms: List[str] = []

    # 1) 명사 토큰(2자 이상)
    nouns = []
    for t in toks:
        if getattr(t, "tag", "").startswith("NN") and len(getattr(t, "form", "")) >= 2:
            nouns.append(t.form)

    # 2) XSN 접미사(성/권 등)는 앞 명사와 결합해서 표시용 토큰 생성
    merged = []
    for t in toks:
        form = getattr(t, "form", "")
        tag = getattr(t, "tag", "")
        if not form:
            continue
        if tag.startswith("NN"):
            merged.append(form)
        elif merged and tag == "XSN" and len(form) == 1 and form in _SUFFIX_NOUNS:
            merged[-1] = merged[-1] + form

    # 3) 표시용 우선순위: 결합형(투명성/투표권) + 명사 + 원문
    for x in merged:
        if len(x) >= 2:
            terms.append(x)
    for x in nouns:
        terms.append(x)

    # 4) 'A B' 구문도 하나 추가(띄어쓰기 대응)
    if merged and len(merged) >= 2:
        terms.append(" ".join(merged[:2]))

    # 5) 원문과 공백 제거 버전도 추가
    terms.append(kw)
    ns = _nospace(kw)
    if ns != kw:
        terms.append(ns)

    # 중복 제거(순서 유지)
    out = []
    seen = set()
    for x in terms:
        x = (x or "").strip()
        if not x:
            continue
        if x not in seen:
            out.append(x); seen.add(x)

    return out[:8]
def _merge_highlight_terms(base_terms: List[str], fb_tokens: List[str]) -> List[str]:
    # 폴백(AND)로 검색된 경우, 실제 매칭 토큰도 하이라이트에 포함
    out: List[str] = []
    seen = set()
    for x in (fb_tokens or []):
        if x and x not in seen:
            out.append(x); seen.add(x)
    # 'A B' 구문도 추가(띄어쓰기 케이스)
    if fb_tokens and len(fb_tokens) >= 2:
        phrase = " ".join(fb_tokens[:2])
        if phrase not in seen:
            out.append(phrase); seen.add(phrase)
    for x in (base_terms or []):
        if x and x not in seen:
            out.append(x); seen.add(x)
    return out

    # 연속 명사를 합친 복합어도 만들기 (재외+국민 -> 재외국민)
    chunks: List[str] = []
    i = 0
    while i < len(units):
        cur = units[i]
        if i + 1 < len(units) and len(cur) <= 2:
            comb = cur + units[i+1]
            if len(comb) >= 3:
                chunks.append(comb)
                i += 2
                continue
        chunks.append(cur)
        i += 1

    phrases: List[str] = []
    if len(chunks) >= 2:
        phrases.append(" ".join(chunks))  # 구문

    # 긴 것부터 중복 제거
    cand = phrases + chunks + [kw]
    out2: List[str] = []
    seen2 = set()
    for x in sorted(cand, key=len, reverse=True):
        x = (x or "").strip()
        if len(x) < 2:
            continue
        if x not in seen2:
            out2.append(x); seen2.add(x)
    return out2[:5]

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
    # 1) ns 단일 매칭으로 범위 탐색
    kw_ns = _nospace(kw)
    like = f"%{kw_ns}%"

    rows_min = await sb_select(TABLE, {
        "select": "date",
        "speech_text_ns": f"ilike.{like}",
        "date": "not.is.null",
        "order": "date.asc",
        "limit": 1,
        "offset": 0,
    })
    min_date = rows_min[0]["date"] if rows_min else None

    rows_max = await sb_select(TABLE, {
        "select": "date",
        "speech_text_ns": f"ilike.{like}",
        "date": "not.is.null",
        "order": "date.desc",
        "limit": 1,
        "offset": 0,
    })
    max_date = rows_max[0]["date"] if rows_max else None

    if min_date and max_date:
        return min_date, max_date

    # 2) 0건이면 AND 폴백으로 범위 탐색 (예: 선거투명성 -> 선거 AND 투명성)
    tokens = _extract_and_tokens(kw, max_tokens=3)
    and_param = _build_and_param(tokens)
    if not and_param:
        return min_date, max_date

    rows_min2 = await sb_select(TABLE, {
        "select": "date",
        "and": and_param,
        "date": "not.is.null",
        "order": "date.asc",
        "limit": 1,
        "offset": 0,
    })
    min2 = rows_min2[0]["date"] if rows_min2 else None

    rows_max2 = await sb_select(TABLE, {
        "select": "date",
        "and": and_param,
        "date": "not.is.null",
        "order": "date.desc",
        "limit": 1,
        "offset": 0,
    })
    max2 = rows_max2[0]["date"] if rows_max2 else None

    return min2 or min_date, max2 or max_date



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

    truncated = (_nospace(clip) != _nospace(text))

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
        truncated = (_nospace(clip) != _nospace(text))
        return clip, truncated

    start_i = max(0, idx - window)
    end_i = min(len(sents), start_i + max_sent)
    start_i = max(0, end_i - max_sent)

    clip_sents = sents[start_i:end_i]
    clip = " ".join(clip_sents)
    truncated = (start_i > 0) or (end_i < len(sents))
    truncated = (_nospace(clip) != _nospace(text))
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

        kw_ns = _nospace(kw)
        like = f"%{kw_ns}%"

        cols = (
            "speech_id,session,session_dir,meeting_no,date,"
            "speaker_name,speaker_position,party,speech_text,speech_order"
        )

        base_where = {
            "speech_text_ns": f"ilike.{like}",
            "date": f"gte.{start}",
        }

        fb_tokens = _extract_and_tokens(kw, max_tokens=3)
        fb_and = _build_and_param(fb_tokens)
        used_fallback = False

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

            # ✅ 1차(붙여쓰기/ns 단일) 0건이면, 첫 페이지에서만 AND(교집합)로 1회 폴백
            if (not rows) and (not used_fallback) and (cur_offset == offset) and fb_and:
                used_fallback = True
                # ✅ 폴백(AND)로 검색 조건을 전환 (series/widgets/total_count도 동일 조건 사용)
                base_where = {
                    "and": fb_and,
                    "date": f"gte.{start}",
                }
                params = {
                    "select": cols,
                    "and": fb_and,
                    "date": f"gte.{start}",
                    "order": "date.desc,speech_order.desc",
                    "limit": chunk,
                    "offset": cur_offset,
                }
                rows = await sb_select(TABLE, params)
                pages += 1

            if not rows:
                break

            # end는 PostgREST 필터 조합 제약 때문에 서버에서 post-filter
            if end:
                rows = [r for r in rows if (r.get("date") or "") <= end]

            # 스니펫(원문 유지 + snippet_text/snippet_truncated)
            highlight_terms = (_merge_highlight_terms(_extract_highlight_terms(kw), fb_tokens)
                              if used_fallback else _extract_highlight_terms(kw))
            for r in rows:
                txt = r.get("speech_text") or ""
                snip_kw = kw
                for cand in (highlight_terms or []):
                    if cand and (cand in txt):
                        snip_kw = cand
                        break
                snippet, trunc = _make_snippet(txt, snip_kw, window=2, max_sent=5)
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
            "highlight_terms": highlight_terms,
            "search_mode": {"used_fallback": used_fallback, "fallback_tokens": fb_tokens if used_fallback else []},
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
