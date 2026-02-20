"""
routers/news.py (예시)
- /news 페이지 + /api/news/issues, /api/news/issue 제공
- 테이블명에 특수문자(&)가 있으면 NEWS_TABLE 환경변수로 인코딩된 이름을 지정하세요.
  예) NEWS_TABLE="NEWS_Q%26A"
"""

import os
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

router = APIRouter()

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or ""
NEWS_TABLE = os.getenv("NEWS_TABLE") or "news_qa"  # ✅ 추천: 안전한 이름(뷰/테이블)

# news.html 위치(원하시는 경로로 변경 가능)
NEWS_HTML_PATH = os.getenv("NEWS_HTML_PATH") or os.path.join("static", "news.html")


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
        raise HTTPException(status_code=500, detail="SUPABASE_URL / SUPABASE_KEY 미설정")
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.get(url, headers=_headers(), params=params)
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()


@router.get("/news", response_class=HTMLResponse)
async def news_page():
    try:
        with open(NEWS_HTML_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail=f"news.html not found: {NEWS_HTML_PATH}")


@router.get("/api/news/issues")
async def api_news_issues(
    q: Optional[str] = Query(None, description="검색어(키워드/질문/배경)"),
    batch_id: Optional[str] = Query(None, description="배치 필터(선택)"),
    limit: int = 3000,
):
    params: Dict[str, Any] = {
        "select": "batch_id,created_at,keyword,background,question,answer",
        "order": "created_at.desc",
        "limit": min(max(limit, 100), 5000),
        "offset": 0,
    }
    if batch_id:
        params["batch_id"] = f"eq.{batch_id}"

    rows = await sb_select(NEWS_TABLE, params)

    if q:
        qq = q.strip().lower()

        def hit(r: Dict[str, Any]) -> bool:
            return any(qq in str(r.get(k, "")).lower() for k in ("keyword", "background", "question"))

        rows = [r for r in rows if hit(r)]

    # keyword 기준 group by
    agg: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        kw = (r.get("keyword") or "").strip() or "미분류"
        created_at = r.get("created_at")
        bg = (r.get("background") or "").strip()
        if kw not in agg:
            agg[kw] = {
                "keyword": kw,
                "qa_count": 0,
                "latest_at": created_at,
                "background_preview": (bg[:160] + "…") if len(bg) > 160 else bg,
            }
        agg[kw]["qa_count"] += 1
        # 문자열 비교(ISO/DB timestamp면 최신 비교에 충분)
        if created_at and (not agg[kw]["latest_at"] or str(created_at) > str(agg[kw]["latest_at"])):
            agg[kw]["latest_at"] = created_at

    out = list(agg.values())
    # ✅ 최신순( latest_at desc ) 확정 + 2차: qa_count desc + 3차: keyword asc
    out.sort(
        key=lambda x: (
            str(x.get("latest_at") or ""),   # 최신시간
            int(x.get("qa_count") or 0),     # QA 개수
            x.get("keyword") or "",          # 키워드
        ),
        reverse=True,
    )
    return out


@router.get("/api/news/issue")
async def api_news_issue(
    keyword: str = Query(...),
    batch_id: Optional[str] = Query(None),
    limit: int = 2000,
):
    kw = (keyword or "").strip()
    if not kw:
        return []

    params: Dict[str, Any] = {
        "select": "batch_id,created_at,keyword,background,question,answer",
        "keyword": f"eq.{kw}",
        "order": "created_at.desc",
        "limit": min(max(limit, 50), 5000),
        "offset": 0,
    }
    if batch_id:
        params["batch_id"] = f"eq.{batch_id}"

    rows = await sb_select(NEWS_TABLE, params)
    return rows
