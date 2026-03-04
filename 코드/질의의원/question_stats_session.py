import os
import ssl
from pathlib import Path

import pandas as pd
from supabase import Client, create_client


# -------------------------------------------------------------------
# 0. 환경 설정 (SSL 비검증 + 경로)
# -------------------------------------------------------------------

# 모든 HTTPS 요청에서 SSL 검증 비활성화 (개발/기관망 우회용)
ssl._create_default_https_context = ssl._create_unverified_context

DATA_DIR = Path(r"C:\sw\분석과제\국회회의록\4인\data_collection\data")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

print("DEBUG SUPABASE_URL =", SUPABASE_URL)
print("DEBUG SUPABASE_KEY set =", SUPABASE_KEY is not None)


def get_supabase_client() -> Client:
    """
    supabase-py 기본 초기화.
    http_client 옵션 없이 URL, KEY만 사용.[web:326]
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE_KEY 환경변수 설정 필요")

    client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return client


# -------------------------------------------------------------------
# 1. 원본 회의록 로드
# -------------------------------------------------------------------

def load_all_speeches() -> pd.DataFrame:
    """
    data 폴더 아래의 모든 회차 디렉터리에서
    *_minutes_speeches.csv 파일을 로드해 하나의 DF로 통합.
    """
    dfs = []

    for session_dir in DATA_DIR.iterdir():
        if not session_dir.is_dir():
            continue
        if not session_dir.name.startswith("제"):
            continue

        for csv_path in session_dir.glob("*_minutes_speeches.csv"):
            print(f"📂 로딩 중: {csv_path.relative_to(DATA_DIR)}")
            df = pd.read_csv(csv_path, encoding="utf-8")
            dfs.append(df)
            print(f"   ✓ {len(df)}행 로드")

    if not dfs:
        raise FileNotFoundError(f"speeches CSV를 하나도 못 찾음: {DATA_DIR}")

    all_df = pd.concat(dfs, ignore_index=True)
    print(f"\n✓ 총 {len(all_df)}행 통합\n")
    return all_df


# -------------------------------------------------------------------
# 2. 전처리 / 날짜 / 질의 필터
# -------------------------------------------------------------------

def parse_korean_date(series: pd.Series) -> pd.Series:
    """
    '2024년 6월 19일(수)' → datetime.
    """
    cleaned = series.astype(str)
    cleaned = cleaned.str.replace(r"\([^)]*\)", "", regex=True)
    cleaned = cleaned.str.strip()
    return pd.to_datetime(cleaned, format="%Y년 %m월 %d일", errors="coerce")


def filter_question_speeches(df: pd.DataFrame) -> pd.DataFrame:
    """
    speech_text에 ? 포함된 발언만 질의로 간주해서 필터링.
    """
    df = df.copy()
    df["speech_text"] = df["speech_text"].fillna("")

    is_question = df["speech_text"].str.contains("?", regex=False, na=False)
    q_df = df[is_question].copy()

    print("📊 질의 발언 필터링")
    print(f"   전체 발언: {len(df)}개")
    print(f"   질의 발언: {len(q_df)}개")
    if len(df) > 0:
        print(f"   비율: {len(q_df) / len(df) * 100:.1f}%\n")

    return q_df


# -------------------------------------------------------------------
# 3. 회차별 질의 집계 DF 생성
# -------------------------------------------------------------------

def compute_question_stats_by_session(all_df: pd.DataFrame) -> pd.DataFrame:
    """
    회차(session_no, meeting_no) + 의원별 질의 수 집계.
    public.question_stats_session 스키마에 맞는 DF 생성.
    """
    df = all_df.copy()

    # 날짜 파싱
    df["date"] = parse_korean_date(df["date"])

    # 연/월/분기
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["quarter"] = df["date"].dt.quarter

    # 회의 날짜: (session, meeting_no)별 최소 날짜
    df["meeting_date"] = df.groupby(["session", "meeting_no"])["date"].transform("min")

    # 질의만 필터
    q_df = filter_question_speeches(df)

    # 결측 처리
    q_df["speaker_name"] = q_df["speaker_name"].fillna("미상")
    q_df["party"] = q_df["party"].fillna("정보없음")
    q_df["speaker_area"] = q_df["speaker_area"].fillna("")

    grouped = (
        q_df.groupby(
            [
                "session",
                "session_type",
                "meeting_no",
                "meeting_date",
                "year",
                "month",
                "quarter",
                "speaker_name",
                "party",
                "speaker_area",
            ]
        )
        .agg(num_questions=("speech_order", "count"))
        .reset_index()
    )

    grouped = grouped.rename(columns={"session": "session_no"})

    result = grouped[
        [
            "session_no",
            "session_type",
            "meeting_no",
            "meeting_date",
            "year",
            "month",
            "quarter",
            "speaker_name",
            "party",
            "speaker_area",
            "num_questions",
        ]
    ].copy()

    # Supabase JSON 직렬화용 날짜 문자열화
    result["meeting_date"] = result["meeting_date"].dt.strftime("%Y-%m-%d")

    return result


# -------------------------------------------------------------------
# 4. Supabase에 bulk upsert
# -------------------------------------------------------------------

def upsert_question_stats_session(df: pd.DataFrame, batch_size: int = 500):
    """
    DataFrame → public.question_stats_session bulk upsert.
    """
    supabase = get_supabase_client()

    records = df.to_dict(orient="records")
    total = len(records)
    print(f"⬆️ Supabase 업로드 대상 행 수: {total}개")

    for i in range(0, total, batch_size):
        batch = records[i : i + batch_size]
        print(f"   → {i} ~ {i + len(batch) - 1} 행 업로드 중...")

        resp = (
            supabase.table("question_stats_session")
            .upsert(
                batch,
                on_conflict="session_no,meeting_no,speaker_name,party,speaker_area",
            )
            .execute()
        )

        print("   ✓ 배치 업로드 완료")

    print("✅ Supabase 업로드 완료")


# -------------------------------------------------------------------
# 5. main: 전체 파이프라인
# -------------------------------------------------------------------

def main():
    print(f"📁 DATA_DIR: {DATA_DIR} (exists={DATA_DIR.exists()})")

    # 1) 전체 발언 로드
    all_df = load_all_speeches()

    # 2) 회차·의원별 질의 집계
    stats_df = compute_question_stats_by_session(all_df)

    # 3) 로컬 CSV 백업
    out_path = DATA_DIR / "question_stats_session_sample.csv"
    stats_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"✓ 로컬 샘플 저장: {out_path}")

    # 4) Supabase 자동 업로드
    upsert_question_stats_session(stats_df)


if __name__ == "__main__":
    main()

