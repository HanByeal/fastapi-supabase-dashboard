from typing import Optional
from fastapi import APIRouter, Query

from core.config import TABLES
from core.supabase import sb_select

router = APIRouter()

@router.get("/api/questions/stats/session")
async def api_questions_stats_session(
    session_no: Optional[int] = Query(None),
    limit: int = 5000,
    offset: int = 0,
):
    params = {"select": "*", "limit": limit, "offset": offset}
    if session_no is not None:
        params["session_no"] = f"eq.{session_no}"
    return await sb_select(TABLES["question_stats_session_rows"], params)
