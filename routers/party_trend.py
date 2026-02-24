from typing import Optional, Dict, Any, List, Tuple
from collections import defaultdict

from fastapi import APIRouter, Query

from core.supabase import sb_select

router = APIRouter()

TABLE = "party_trend"


def _period(y: int, q: int) -> str:
    return f"{int(y)}-Q{int(q)}"


async def _select_pages_lte_end(
    end_period: str,
    page_size: int = 1000,
    max_pages: int = 500,
) -> List[Dict[str, Any]]:
    """period <= end_period 를 DB에서 자르고(period desc),
    페이지를 내려오면서 필요한 범위를 상위 로직에서 컷할 수 있게 rows를 반환."""
    out: List[Dict[str, Any]] = []
    offset = 0
    base = {
        "select": "period,party,label_l2,label_l3,meeting_count,mention_count",
        "order": "period.desc",
        "period": f"lte.{end_period}",
        "party": "neq.미분류",
    }
    for _ in range(max_pages):
        params = dict(base)
        params["limit"] = page_size
        params["offset"] = offset
        rows = await sb_select(TABLE, params)
        if not rows:
            break
        out.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size
    return out


@router.get("/api/party-trend/metrics")
async def api_party_trend_metrics(
    start_year: int = Query(...),
    start_quarter: int = Query(...),
    end_year: int = Query(...),
    end_quarter: int = Query(...),
    group_by: str = Query("l2"),          # "l2" or "l3"
    l2_eq: Optional[str] = Query(None),   # group_by="l3"일 때 필수(드릴다운)
    metric: str = Query("meeting"),       # "meeting" or "mention"
):
    """대시보드 오른쪽(정당별 관심)용.
    - 기간(start~end)은 대시보드와 동일
    - L2 모드: party × label_l2 합산 → {party, l2, meeting_count}
    - L3 모드: party × label_l3 합산(단, 특정 label_l2로 제한) → {party, l3, meeting_count}
    """

    group_by = (group_by or "l2").strip().lower()
    if group_by not in ("l2", "l3"):
        group_by = "l2"

    metric = (metric or "meeting").strip().lower()
    val_col = "mention_count" if metric == "mention" else "meeting_count"

    p1 = _period(start_year, start_quarter)
    p2 = _period(end_year, end_quarter)
    if p2 < p1:
        p1, p2 = p2, p1

    # L3 드릴다운이면 L2 값이 있어야 의미가 있음
    if group_by == "l3":
        if not l2_eq:
            # L3 모드인데 기준 L2가 없으면 빈 결과
            return []

    rows = await _select_pages_lte_end(p2)

    agg = defaultdict(int)

    for r in rows:
        per = str(r.get("period") or "")
        if not per:
            continue

        # period desc로 내려오는 중이라 start보다 과거면 더 볼 필요 없음
        if per < p1:
            break
        if per > p2:
            continue

        party = (r.get("party") or "").strip()
        if not party or party == "미분류":
            continue

        l2 = (r.get("label_l2") or "").strip() or "미분류"
        l3 = (r.get("label_l3") or "").strip() or "미분류"

        if group_by == "l3":
            if l2_eq and l2 != l2_eq:
                continue
            key = (party, l3)
        else:
            key = (party, l2)

        v = r.get(val_col) or 0
        try:
            agg[key] += int(v)
        except:
            pass

    out = []
    if group_by == "l3":
        for (party, l3), c in agg.items():
            out.append({"party": party, "l3": l3, "meeting_count": c})
    else:
        for (party, l2), c in agg.items():
            out.append({"party": party, "l2": l2, "meeting_count": c})

    # 프론트에서 정렬/Top-N 처리 가능. 일단 count desc로 정렬만.
    out.sort(key=lambda x: (-int(x.get("meeting_count") or 0), x.get("party") or ""))
    return out
