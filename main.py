# main.py
from fastapi import FastAPI, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from routers.news import router as news_router
from routers.recap import router as recap_router
from routers.questions import router as questions_router
from routers.meta import router as meta_router
from routers.law import router as law_router
from routers.trend import router as trend_router
from routers.party_trend import router as party_trend_router
from routers import speech

app = FastAPI(title="FastAPI + Supabase Dashboard")

# 정적 파일 서빙 (/static/news.html 등)
app.mount("/static", StaticFiles(directory="static"), name="static")

# API 라우터들
app.include_router(news_router)
app.include_router(recap_router)
app.include_router(questions_router)
app.include_router(meta_router)
app.include_router(law_router)
app.include_router(trend_router)
app.include_router(party_trend_router)
app.include_router(speech.router)

# ✅ 루트로 들어오면 대시보드로
@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")

# ✅ Render/프록시 health-check 대응: HEAD / 는 200으로 응답
@app.head("/", include_in_schema=False)
async def root_head():
    return Response(status_code=200)

# ✅ 대시보드: static/dashboard.html을 “/dashboard”로 서빙
@app.get("/dashboard")
async def dashboard_page():
    return FileResponse("static/dashboard.html")

@app.head("/dashboard", include_in_schema=False)
async def dashboard_head():
    return Response(status_code=200)

from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

# ✅ 발언검색: 일단 임시 페이지(나중에 static/speech.html로 교체 가능)
@app.get("/speech")
def speech_page():
    return FileResponse(STATIC_DIR / "speech.html")

@app.head("/speech", include_in_schema=False)
async def speech_head():
    return Response(status_code=200)

# (news 페이지가 있을 때) HEAD /news 가 들어오면 200으로 응답
@app.head("/news", include_in_schema=False)
async def news_head():
    return Response(status_code=200)


from routers import speech_research2
app.include_router(speech_research2.router)

@app.get("/speech_2")
def speech_page():
    return FileResponse(STATIC_DIR / "speech_research2.html")

@app.head("/speech_2", include_in_schema=False)
async def speech_head():
    return Response(status_code=200)

