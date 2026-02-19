from typing import Optional
from fastapi import APIRouter, Query

from core.config import TABLES
from core.supabase import sb_select

router = APIRouter()

def session_label(n: int) -> str:
    return f"{n}회"

@router.get("/api/recap/text")
async def api_recap_text(
    session_no: Optional[int] = Query(None),
    meeting_no: Optional[str] = Query(None),
    limit: int = 1000,
    offset: int = 0,
):
    params = {"select": "*", "limit": limit, "offset": offset}
    if session_no is not None:
        params["회차"] = f"eq.{session_label(session_no)}"   # ✅ 핵심
    if meeting_no is not None:
        params["meeting_no"] = f"eq.{meeting_no}"
    return await sb_select(TABLES["text_recap"], params)


@router.get("/api/recap/people")
async def api_recap_people(
    session_no: Optional[int] = Query(None),
    meeting_no: Optional[str] = Query(None),
    limit: int = 1000,
    offset: int = 0,
):
    params = {"select": "*", "limit": limit, "offset": offset}
    if session_no is not None:
        params["회차"] = f"eq.{session_label(session_no)}"   # ✅ 핵심
    if meeting_no is not None:
        params["meeting_no"] = f"eq.{meeting_no}"
    return await sb_select(TABLES["people_recap"], params)


@router.get("/api/recap/data")
async def api_recap_data(
    session_no: Optional[int] = Query(None),
    meeting_no: Optional[str] = Query(None),
    limit: int = 1000,
    offset: int = 0,
):
    params = {"select": "*", "limit": limit, "offset": offset}
    if session_no is not None:
        params["회의회차"] = f"eq.{session_label(session_no)}"  # ✅ 핵심(테이블 컬럼명 다름)
    if meeting_no is not None:
        params["meeting_no"] = f"eq.{meeting_no}"
    return await sb_select(TABLES["data_request_recap"], params)
