from typing import Dict, Any, List

import httpx
from fastapi import HTTPException

from core.config import SUPABASE_URL, SUPABASE_KEY


def _headers() -> Dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }


async def sb_select(table: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_URL / SUPABASE_KEY 가 설정되지 않았습니다. (.env 또는 run.cmd 확인)",
        )

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.get(url, headers=_headers(), params=params)

    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    return r.json()