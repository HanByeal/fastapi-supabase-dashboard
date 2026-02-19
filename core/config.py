import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or ""

TABLES = {
    "trend2": "trend2",  
    "party_domain_metrics": "party_domain_metrics",
    "text_recap": "text_recap",
    "people_recap": "people_recap",
    "data_request_recap": "data_request_recap",
    "law_reform_stats_row": "law_reform_stats_row",
    "question_stats_session_rows": "question_stats_session_rows",
    "law2": "law2",
}
