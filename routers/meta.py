import re
from typing import Any, Optional

from fastapi import APIRouter

from core.config import TABLES
from core.supabase import sb_select

router = APIRouter()

def parse_session_no(s: Any) -> Optional[int]:
    if s is None:
        return None
    m = re.search(r"(\d+)", str(s))
    return int(m.group(1)) if m else None

@router.get("/api/sessions")
async def api_sessions():
    rows_text = await sb_select(TABLES["text_recap"], {"select": "회차", "limit": 10000, "offset": 0})
    rows_people = await sb_select(TABLES["people_recap"], {"select": "회차", "limit": 10000, "offset": 0})
    rows_data = await sb_select(TABLES["data_request_recap"], {"select": "회의회차", "limit": 10000, "offset": 0})

    ses = set()
    for r in rows_text:
        n = parse_session_no(r.get("회차"))
        if n:
            ses.add(n)
    for r in rows_people:
        n = parse_session_no(r.get("회차"))
        if n:
            ses.add(n)
    for r in rows_data:
        n = parse_session_no(r.get("회의회차"))
        if n:
            ses.add(n)

    return sorted(ses)
