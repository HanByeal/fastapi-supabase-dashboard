from typing import Optional, Dict, Any
from fastapi import APIRouter, Query

from core.config import TABLES
from core.supabase import sb_select


router = APIRouter()

@router.get("/api/law/stats/policy")
async def api_law_stats_policy(limit: int = 5000, offset: int = 0):
    params = {"select": "*", "limit": limit, "offset": offset}
    return await sb_select(TABLES["law_reform_stats_row"], params)

@router.get("/api/law/stats/session")
async def api_law_stats_session(limit: int = 5000, offset: int = 0):
    params = {"select": "*", "limit": limit, "offset": offset}
    return await sb_select(TABLES["law_reform_stats_row"], params)

@router.get("/api/law2/options")
async def law2_options(
    assembly: str = Query("22"),   # "20","21","22","전체"
    limit: int = 200000,
    offset: int = 0,
):
    # law2 테이블에서 assembly/l2/l3만 가져와서
    # L2 목록 + (L2별 L3 목록) 구성
    params: Dict[str, Any] = {
        "select": "assembly,l2,l3",
        "limit": limit,
        "offset": offset,
    }

    # ✅ "전체"면 assembly 필터를 걸지 않음
    if assembly != "전체":
        params["assembly"] = f"eq.{int(assembly)}"

    rows = await sb_select(TABLES["law2"], params)

    l2_set = set()
    l3_by_l2: Dict[str, set] = {}

    for r in rows:
        l2v = r.get("l2")
        l3v = r.get("l3")

        if not l2v:
            continue

        l2_set.add(l2v)
        l3_by_l2.setdefault(l2v, set())

        if l3v:
            l3_by_l2[l2v].add(l3v)

    return {
        "assemblies": ["전체", "20", "21", "22"],
        "l2": sorted(l2_set),
        "l3_by_l2": {k: sorted(v) for k, v in l3_by_l2.items()},
    }

def _scope_key(s: Optional[str]) -> str:
    # '법 개정' -> '법개정' 처럼 공백 제거해서 키 통일
    return (s or "").replace(" ", "")

def _base_category_row(category: str) -> Dict[str, Any]:
    return {
        "category": category,
        "num_scope_법개정": 0,
        "num_scope_제도개선": 0,
        "num_scope_규정변경": 0,
    }

@router.get("/api/law2/stack/category")
async def law2_stack_category(
    assembly: str = Query("22"),          # "20","21","22","전체"
    l2: str = Query("전체"),              # "전체" or 특정 L2
    l3: str = Query("전체"),              # "전체" or 특정 L3
    limit: int = 200000,
    offset: int = 0,
):
    """
    카테고리별(좌측 그래프) 스택 데이터
    - L2가 "전체"면: x축 = L2
    - L2가 특정값이면: x축 = L3 (해당 L2 내부를 L3로 분해)
      (L3가 특정값이면 사실상 한 막대만 남는 구조라, 그래프는 그대로 그려지되 단일 항목)
    """
    params: Dict[str, Any] = {
        "select": "assembly,l2,l3,scope,count",
        "limit": limit,
        "offset": offset,
    }

    if assembly != "전체":
        params["assembly"] = f"eq.{int(assembly)}"

    if l2 != "전체":
        params["l2"] = f"eq.{l2}"

    if l3 != "전체":
        params["l3"] = f"eq.{l3}"

    rows = await sb_select(TABLES["law2"], params)

    # ✅ 축 결정
    group_key = "l2" if l2 == "전체" else "l3"

    out: Dict[str, Dict[str, Any]] = {}

    for r in rows:
        key_val = r.get(group_key)
        if not key_val:
            continue

        scope = _scope_key(r.get("scope"))
        cnt = int(r.get("count") or 0)

        if key_val not in out:
            out[key_val] = _base_category_row(str(key_val))

        if scope == "법개정":
            out[key_val]["num_scope_법개정"] += cnt
        elif scope == "제도개선":
            out[key_val]["num_scope_제도개선"] += cnt
        elif scope == "규정변경":
            out[key_val]["num_scope_규정변경"] += cnt

    return [out[k] for k in sorted(out.keys())]

def _base_party_row(party: str) -> Dict[str, Any]:
    return {
        "party": party,
        "num_scope_법개정": 0,
        "num_scope_제도개선": 0,
        "num_scope_규정변경": 0,
    }

@router.get("/api/law2/stack/party")
async def law2_stack_party(
    assembly: str = Query("22"),     # "20","21","22","전체"
    limit: int = 200000,
    offset: int = 0,
):

    """
    정당별(우측 그래프) 스택 데이터
    - 정당은 선택 UI 없이, 선택한 대수 범위에서 존재하는 정당 전체를 자동으로 반환
    - L2/L3는 필터로만 적용
    """
    params: Dict[str, Any] = {
        "select": "assembly,l2,l3,party,scope,count",
        "limit": limit,
        "offset": offset,
    }

    if assembly != "전체":
        params["assembly"] = f"eq.{int(assembly)}"

    rows = await sb_select(TABLES["law2"], params)

    out: Dict[str, Dict[str, Any]] = {}

    for r in rows:
        party = r.get("party")
        if not party:
            continue

        scope = _scope_key(r.get("scope"))
        cnt = int(r.get("count") or 0)

        if party not in out:
            out[party] = _base_party_row(str(party))

        if scope == "법개정":
            out[party]["num_scope_법개정"] += cnt
        elif scope == "제도개선":
            out[party]["num_scope_제도개선"] += cnt
        elif scope == "규정변경":
            out[party]["num_scope_규정변경"] += cnt

    return [out[k] for k in sorted(out.keys())]