import os
import re
from pathlib import Path
import pandas as pd

# -------------------------------------------------------------------
# 0. 환경 설정 (기존과 동일)
# -------------------------------------------------------------------
DATA_DIR = Path.cwd().parent / "데이터수집" / "data"
SCRIPT_DIR = Path(__file__).resolve().parent
# -------------------------------------------------------------------
# 1. 유틸: 회의번호 정제 (기존 로직 100% 동일)
# -------------------------------------------------------------------
def normalize_meeting_no(series: pd.Series) -> pd.Series:
    s = series.astype(str)
    s = s.str.replace("제", "", regex=False)
    s = s.str.replace("호", "", regex=False)
    s = s.str.strip()
    return pd.to_numeric(s, errors="coerce")

# -------------------------------------------------------------------
# 2. 원본 회의록 로드 (보정 추가)
# -------------------------------------------------------------------
def load_all_speeches() -> pd.DataFrame:
    dfs = []
    for session_dir in DATA_DIR.iterdir():
        if not session_dir.is_dir() or not session_dir.name.startswith("제"):
            continue

        for csv_path in session_dir.glob("*_minutes_speeches.csv"):
            try:
                # 22대 방식과 동일하게 로드
                df = pd.read_csv(csv_path, encoding="utf-8-sig")
                
                # [보정] 20/21대 수집본의 컬럼명이 22대와 다를 경우 자동으로 맞춰줌
                # 22대(date, speech_text) <-> 20/21대(meeting_date, content)
                rename_map = {}
                if 'meeting_date' in df.columns and 'date' not in df.columns:
                    rename_map['meeting_date'] = 'date'
                if 'content' in df.columns and 'speech_text' not in df.columns:
                    rename_map['content'] = 'speech_text'
                if rename_map:
                    df = df.rename(columns=rename_map)
                
                dfs.append(df)
            except Exception as e:
                print(f"⚠️ {csv_path.name} 로드 실패: {e}")

    if not dfs:
        raise FileNotFoundError(f"CSV 파일을 찾을 수 없습니다: {DATA_DIR}")

    all_df = pd.concat(dfs, ignore_index=True)
    return all_df

# -------------------------------------------------------------------
# 3. 전처리 / 날짜 / 질의 필터 (기존 로직 100% 동일 + 날짜 형식 보정)
# -------------------------------------------------------------------
def parse_korean_date(series: pd.Series) -> pd.Series:
    """기존 로직을 유지하면서 20/21대의 다른 날짜 형식도 경고 없이 읽도록 보완"""
    cleaned = series.astype(str).str.replace(r"\([^)]*\)", "", regex=True).str.strip()
    
    # 1단계: 22대 형식(%Y년 %m월 %d일)으로 시도
    dt_series = pd.to_datetime(cleaned, format="%Y년 %m월 %d일", errors="coerce")
    
    # 2단계: 실패한 경우(NaT) 20/21대 형식(YYYY-MM-DD)으로 시도 (경고 방지)
    mask = dt_series.isna() & (cleaned != "nan")
    if mask.any():
        dt_series.loc[mask] = pd.to_datetime(cleaned.loc[mask], errors="coerce")
        
    return dt_series

def filter_question_speeches(df: pd.DataFrame) -> pd.DataFrame:
    """speech_text에 ? 포함된 발언만 질의로 간주 (기존 로직 동일)"""
    df = df.copy()
    df["speech_text"] = df["speech_text"].fillna("")
    is_question = df["speech_text"].str.contains("?", regex=False, na=False)
    q_df = df[is_question].copy()
    return q_df

# -------------------------------------------------------------------
# 4. 회차별 질의 집계 (22대와 100% 동일한 로직)
# -------------------------------------------------------------------
def compute_question_stats_by_term(all_df: pd.DataFrame, term: str) -> pd.DataFrame:
    df = all_df.copy()

    # 날짜 파싱
    df["date"] = parse_korean_date(df["date"])
    df = df.dropna(subset=["date"])

    # [중요] 해당 대수(20대 또는 21대) 기간만 필터링
    if term == "20대":
        df = df[(df["date"] >= "2016-05-30") & (df["date"] <= "2020-05-29")]
    elif term == "21대":
        df = df[(df["date"] >= "2020-05-30") & (df["date"] <= "2024-05-29")]

    if df.empty:
        return pd.DataFrame()

    # 회의번호 정제, 연/월/분기, meeting_date 그룹화 (기존 로직 100% 동일)
    df["meeting_no"] = normalize_meeting_no(df["meeting_no"])
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["quarter"] = df["date"].dt.quarter
    df["meeting_date"] = df.groupby(["session", "meeting_no"])["date"].transform("min")

    # 질의 필터링
    q_df = filter_question_speeches(df)

    # 결측치 및 미분류 제외 (기존 로직 100% 동일)
    q_df["speaker_name"] = q_df["speaker_name"].fillna("미상")
    q_df["party"] = q_df["party"].fillna("정보없음")
    q_df["speaker_area"] = q_df["speaker_area"].fillna("")
    q_df = q_df[q_df["party"] != "미분류"]

    # 집계
    grouped = (
        q_df.groupby([
            "session", "session_type", "meeting_no", "meeting_date",
            "year", "month", "quarter", "speaker_name", "party", "speaker_area"
        ])
        .agg(num_questions=("speech_order", "count"))
        .reset_index()
    )

    grouped = grouped.rename(columns={"session": "session_no"})

    # 22대 결과물과 동일한 컬럼 순서
    result = grouped[[
        "session_no", "session_type", "meeting_no", "meeting_date",
        "year", "month", "quarter", "speaker_name", "party",
        "speaker_area", "num_questions"
    ]].copy()

    result["meeting_date"] = result["meeting_date"].dt.strftime("%Y-%m-%d")
    return result

# -------------------------------------------------------------------
# 5. Main: 20대, 21대 각각 저장
# -------------------------------------------------------------------
def main():
    print(f"📁 DATA_DIR: {DATA_DIR}")
    all_df = load_all_speeches()

    for term in ["20대", "21대"]:
        stats_df = compute_question_stats_by_term(all_df, term)
        if not stats_df.empty:
            #out_path = Path.cwd() / f"question_stats_{term}.csv"
            out_path = SCRIPT_DIR / f"question_stats_{term}.csv"
            stats_df.to_csv(out_path, index=False, encoding="utf-8-sig")
            print(f"✅ {term} 분석 완료: {out_path} ({len(stats_df)}건)")
        else:
            print(f"💡 {term} 기간의 데이터가 없습니다.")

if __name__ == "__main__":
    main()