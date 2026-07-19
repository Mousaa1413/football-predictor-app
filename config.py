"""
إعدادات المشروع المركزية.
كل المسارات والثوابت هنا عشان ما نكرّرها في باقي الملفات.
"""

from __future__ import annotations

import os
from pathlib import Path

# جذر المشروع (المجلد اللي فيه config.py)
BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv(path: Path | None = None) -> None:
    """تحميل بسيط لملف .env بدون اعتماد خارجي."""
    env_path = path or (BASE_DIR / ".env")
    if not env_path.exists():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            # لا نكتب فوق متغير مضبوط مسبقًا في البيئة
            os.environ.setdefault(key, value)
    except OSError:
        pass


_load_dotenv()

# مسارات البيانات والنموذج
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
DATA_FILE = DATA_DIR / "matches.csv"
RECENT_DATA_FILE = DATA_DIR / "last_matches.csv"
SCHEDULE_FILE = DATA_DIR / "schedule.csv"
DB_FILE = DATA_DIR / "matches.db"
MODEL_FILE = MODELS_DIR / "match_predictor.joblib"

# عدد آخر المباريات المنتهية لكل دوري
LAST_N_MATCHES_PER_LEAGUE = 50

# عدد المباريات القادمة لكل دوري في جدول الـ schedule
NEXT_N_MATCHES_PER_LEAGUE = 20

# حالات المباريات القادمة في الـ API
UPCOMING_STATUSES = "SCHEDULED,TIMED,IN_PLAY"

# ---- football-data.org API ----
API_BASE_URL = "https://api.football-data.org/v4"

# المفتاح من متغير بيئة (محليًا أو GitHub Secret) — لا تثبت مفتاحًا حقيقيًا هنا
API_TOKEN = os.environ.get("FOOTBALL_DATA_API_TOKEN", "").strip()

# PL = Premier League | PD = La Liga (Primera División)
COMPETITIONS = ["PL", "PD"]

# المواسم المطلوبة (حسب توفر خطتك المجانية)
SEASONS = [2023, 2024]

# حد الخطة المجانية ≈ 10 طلبات/دقيقة على football-data.org
# نترك هامش أمان: طلب كل 6.5 ثانية ≈ 9 طلبات/دقيقة
API_REQUEST_DELAY_SECONDS = 6.5
API_MAX_RETRIES_ON_429 = 3
API_RETRY_BACKOFF_SECONDS = 15

# أعمدة البيانات الموحّدة بعد التحميل
REQUIRED_COLUMNS = [
    "date",
    "competition",
    "season",
    "matchday",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
    "result",
]

# تسميات النتائج: 1 = فوز صاحب الأرض، 0 = تعادل، 2 = فوز الضيف
RESULT_HOME_WIN = 1
RESULT_DRAW = 0
RESULT_AWAY_WIN = 2

RESULT_LABELS = {
    RESULT_HOME_WIN: "فوز صاحب الأرض",
    RESULT_DRAW: "تعادل",
    RESULT_AWAY_WIN: "فوز الضيف",
}

# إعدادات النموذج (احتياطية إن أُضيف ML لاحقًا)
RANDOM_STATE = 42
TEST_SIZE = 0.2
N_ESTIMATORS = 100

# توقع بسيط مبني على آخر المباريات
FORM_LAST_N = 5          # عدد آخر مباريات لحساب الهجوم/الدفاع/النقاط
H2H_LAST_N = 5           # أقصى عدد مواجهات مباشرة تُحسب
DRAW_MARGIN = 0.30       # إذا |score| أقل من هذا -> تعادل
FORM_WEIGHT = 0.80       # وزن فورم النقاط داخل الدرجة النهائية
H2H_WEIGHT = 0.60        # وزن المواجهات المباشرة (0 إذا ما فيه H2H)
# نقاط الفورم/H2H: فوز=3، تعادل=1، خسارة=0
POINTS_WIN = 3
POINTS_DRAW = 1
POINTS_LOSS = 0


def require_api_token() -> str:
    """إرجاع مفتاح الـ API أو رفع خطأ واضح إن كان فارغًا."""
    if not API_TOKEN:
        raise RuntimeError(
            "مفتاح API غير مضبوط. عيّن المتغير FOOTBALL_DATA_API_TOKEN "
            "(محليًا في .env أو كـ GitHub Secret)."
        )
    return API_TOKEN
