import re
import pandas as pd
from pathlib import Path
from datetime import datetime
import warnings

# 정규표현식 관련 경고 무시
warnings.filterwarnings("ignore", category=UserWarning)

# -------------------------------------------------------------------
# 0. 경로 및 국회 임기 설정
# -------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"

SPEECH_PATTERN = "*_minutes_speeches.csv"
OUT_TAGGED_CSV = DATA_DIR / "law_reform_tagged_speeches.csv"

# 국회 임기 날짜 정의
ASSEMBLY_DATES = [
    (20, datetime(2016, 5, 30), datetime(2020, 5, 29)),
    (21, datetime(2020, 5, 30), datetime(2024, 5, 29)),
    (22, datetime(2024, 5, 30), datetime(2028, 5, 29)),
]

# -------------------------------------------------------------------
# 1. 강력한 키워드 및 패턴 설정 (사용자 요청 원본 100% 유지)
# -------------------------------------------------------------------
LAW_REFORM_KEYWORDS_STRONG = [
    "법을 개정", "법 개정이 필요", "법 개정을", "법 개정안", "법령을 정비", "법령 정비", "법령을 개정",
    "법률 개정이 필요", "법률을 개정", "법률 보완이 필요", "법률을 보완", "법률안을 마련해", 
    "법률안을 마련해야", "법률안을 준비해", "법률안을 준비해야", "개정안을 준비해", "개정안을 마련해", 
    "개정안을 제출", "개정안을 발의", "법을 정비해야", "법을 바꿔야", "법을 손봐야", "법을 새로 만들어야",
    "법률을 정비해야", "법률을 손질해야", "법률을 새로 만들어야", "제도 개선", "제도를 개선", 
    "제도 개편", "제도 보완", "제도 정비", "제도적으로 보완", "제도적 개선", "제도 정비가 시급", 
    "제도를 손봐야", "제도를 바꿔야", "제도를 새로 만들", "제도 신설", "제도를 신설", "입법 보완", 
    "입법적 조치", "입법 조치", "입법이 필요", "입법을 추진해야", "입법을 서둘러야", "입법을 검토해야",
    "입법을 통해 해결", "입법을 통해 개선", "입법으로 그걸 해결", "입법으로 해결해", "규정을 개정", 
    "규정 개정", "규정 변경", "규정을 손봐야", "시행령을 개정", "시행령 개정", "시행규칙을 개정", 
    "시행규칙 개정", "지침을 개정", "지침 개정", "고시를 개정", "고시 개정", "시행령을 정비", 
    "시행규칙을 정비", "지침을 정비", "고시를 정비", "법을 신설", "법률을 신설", "새로운 법을 만들어야",
    "제도를 신설해야", "새로운 제도를 도입해야", "법을 폐지해야", "법률을 폐지해야", 
    "불필요한 법을 정비해야", "불필요한 규제를 폐지해야", "페널티를 아예 폐지해야", "아예 폐지해야",
    "총괄 조정할 수 있는 규정", "총괄 조정할 수 있는 어떤 명확한 규정", "역할을 명확하게 부여",
    "제도개선을 요구하기로 하였습니다", "제도개선을 요구하기로 하였다", "제도개선을 요구하도록 하였습니다",
    "제도개선을 요구하도록 하였다", "제도개선을 요구하기로 하였으며", "제도화하는 데 연구",
    "제도화하는 데 대한 연구", "제도화 방안을 연구", "제도화하는 방안을 검토", "보상법을 따로 만드는",
    "입법 추가하는 거를 요청", "입법 추가하는 것을 요청", "입법 추가를 요청하자", "일부개정법률안에 대해",
    "일부개정법률안을 다루", "일부개정법률안 대안", "조사 범위에 확대", "조사대상 범위에 들어가는",
    "조사 범위에 포함되는", "조사 범위에 포함하는"
]
LAW_REFORM_PATTERN_STRONG = r"(?:" + "|".join(map(re.escape, LAW_REFORM_KEYWORDS_STRONG)) + ")"

LAW_TERMS = ["법", "법률", "법안", "법령", "입법", "제도", "제도적", "규정", "시행령", "시행규칙", "지침", "고시", "사업", "위원회", "소위원회", "법안소위"]
DEMAND_VERBS = ["개정해야", "개정할 필요", "개정이 필요", "개정할 것을", "정비해야", "정비할 필요", "정비가 필요", "보완해야", "보완할 필요", "보완이 필요", "바꿔야", "바꾸어야", "변경해야", "고쳐야", "신설해야", "신설이 필요", "새로 만들어야", "도입해야", "도입이 필요", "폐지해야", "폐지할 필요", "폐지하는 방안", "개선해야", "개선할 필요", "개선이 필요", "강화해야", "강화할 필요", "완화해야", "완화할 필요", "정비하고", "정비하는 방안", "마련되어야 한다", "마련되어야 된다", "조속한 심사가 필요", "심의할 수 있도록", "심의되어", "심의될 수 있도록", "조속히 심의", "조속한 심의가 필요", "조속한 처리가 필요", "조속히 처리", "조속히 통과", "통과될 수 있도록", "통과시켜야", "통과를 시켜야", "조속한 통과가 필요", "추진하실 생각이십니까", "추진해야 한다", "제도화하는 데 연구", "제도화 방안을 연구", "제도화하는 방안을 검토", "조정해야 한다", "조정하는 방안", "설계해야 한다", "구성해야 한다", "재구성해야 한다", "구성을 바꾸자", "구성을 조정하자"]

LAW_TERMS_PATTERN = r"(?:" + "|".join(map(re.escape, LAW_TERMS)) + ")"
DEMAND_VERBS_PATTERN = r"(?:" + "|".join(map(re.escape, DEMAND_VERBS)) + ")"
SENTENCE_SPLIT_REGEX = r"[\.?!…\n\r]|[가-힣]+\s*:\s*"

# -------------------------------------------------------------------
# 2. 데이터 분석 및 로드 로직
# -------------------------------------------------------------------
def get_assembly_no(date_str: str) -> int:
    if not isinstance(date_str, str) or not date_str: return 0
    try:
        clean_date = date_str.split('(')[0].strip()
        dt = datetime.strptime(clean_date, "%Y년 %m월 %d일")
        for no, start, end in ASSEMBLY_DATES:
            if start <= dt <= end: return no
        return 0
    except: return 0

def load_all_data() -> pd.DataFrame:
    dfs = []
    session_dirs = sorted([d for d in DATA_DIR.iterdir() if d.is_dir() and d.name.startswith("제")])
    for session_dir in session_dirs:
        for sp_path in session_dir.glob(SPEECH_PATTERN):
            hd_path = Path(str(sp_path).replace("_speeches.csv", "_header_summary.csv"))
            if not hd_path.exists(): continue
            df_sp = pd.read_csv(sp_path, encoding="utf-8-sig")
            df_hd = pd.read_csv(hd_path, encoding="utf-8-sig")
            df_sp.columns = df_sp.columns.str.strip()
            df_hd.columns = df_hd.columns.str.strip()
            for col in ['session', 'meeting_no']:
                if col in df_sp.columns: df_sp[col] = df_sp[col].astype(str).str.strip()
                if col in df_hd.columns: df_hd[col] = df_hd[col].astype(str).str.strip()
            needed_hd_cols = ['session', 'meeting_no', 'date', 'session_type']
            for col in needed_hd_cols:
                if col not in df_hd.columns: df_hd[col] = "정보없음"
            df_hd_sub = df_hd[needed_hd_cols].drop_duplicates()
            for drop_col in ['date', 'session_type']:
                if drop_col in df_sp.columns: df_sp = df_sp.drop(columns=[drop_col])
            merged = pd.merge(df_sp, df_hd_sub, on=['session', 'meeting_no'], how='left')
            merged['assembly_no'] = merged['date'].apply(get_assembly_no)
            dfs.append(merged)
    return pd.concat(dfs, ignore_index=True)

def has_law_and_demand_in_same_sentence(text) -> bool:
    if not isinstance(text, str) or not text: return False
    sentences = re.split(SENTENCE_SPLIT_REGEX, text)
    for sent in sentences:
        sent = sent.strip()
        if not sent: continue
        if re.search(LAW_TERMS_PATTERN, sent) and re.search(DEMAND_VERBS_PATTERN, sent):
            return True
    return False

# -------------------------------------------------------------------
# 3. 집계 및 저장 (수정 포인트: 전체 데이터 저장 추가)
# -------------------------------------------------------------------
def compute_and_save_stats(df: pd.DataFrame):
    df['is_law_reform'] = ((df['speech_text'].str.contains(LAW_REFORM_PATTERN_STRONG, regex=True, na=False)) | (df['speech_text'].apply(has_law_and_demand_in_same_sentence))).astype(int)
    
    # ★ 핵심 수정: assembly_no가 포함된 전체 태깅 데이터를 CSV로 저장함
    OUT_TAGGED_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_TAGGED_CSV, index=False, encoding="utf-8-sig")
    print(f"💾 통합 태깅 본 저장 완료 (assembly_no 포함): {OUT_TAGGED_CSV}")

    # 날짜 분석 및 분기 집계
    df['dt'] = pd.to_datetime(df['date'].astype(str).str.split('(').str[0].str.strip(), format="%Y년 %m월 %d일", errors='coerce')
    df['year'] = df['dt'].dt.year.fillna(0).astype(int)
    df['month'] = df['dt'].dt.month.fillna(0).astype(int)
    df['quarter'] = df['dt'].dt.quarter.fillna(0).astype(int)
    df['meeting_date'] = df['dt'].dt.strftime('%Y-%m-%d').fillna("정보없음")
    
    law_df = df[df['is_law_reform'] == 1].copy()
    law_df['speaker_name'] = law_df['speaker_name'].fillna("미상")
    law_df['party'] = law_df.get('party', "정보없음").fillna("정보없음")
    law_df['speaker_area'] = law_df.get('speaker_area', "정보없음").fillna("정보없음")
    law_df = law_df[law_df['party'] != "미분류"]

    grouped = law_df.groupby(["assembly_no", "session", "session_type", "meeting_no", "meeting_date", "year", "month", "quarter", "speaker_name", "party", "speaker_area"]).agg(num_law_reform_requests=("is_law_reform", "sum")).reset_index()
    grouped = grouped.rename(columns={"session": "session_no"})

    final_cols = ["session_no", "session_type", "meeting_no", "meeting_date", "year", "month", "quarter", "speaker_name", "party", "speaker_area", "num_law_reform_requests"]

    for assembly_no in [20, 21, 22]:
        output_path = DATA_DIR / f"law_reform_stats_{assembly_no}.csv"
        subset = grouped[grouped['assembly_no'] == assembly_no].drop(columns=['assembly_no'])
        if not subset.empty:
            subset[final_cols].to_csv(output_path, index=False, encoding="utf-8-sig")
            print(f"✅ {assembly_no}대 통계 요약 저장 완료: {output_path}")

# -------------------------------------------------------------------
# 4. Main
# -------------------------------------------------------------------
def main():
    print("🚀 국회 회의록 1단계 필터링 및 대수 판별 시작...")
    try:
        all_df = load_all_data()
        compute_and_save_stats(all_df)
        print("\n✨ 1단계 작업이 성공적으로 완료되었습니다!")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

if __name__ == "__main__":
    main()