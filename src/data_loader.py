"""
تحميل مباريات كرة القدم من football-data.org.

- يجيب نتائج تاريخية للدوريات المحددة (PL, PD)
- يصفّي المباريات المنتهية فقط
- يوحّد الأعمدة ويحفظها محليًا في data/matches.csv
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

import config

# آخر وقت تم فيه إرسال طلب للـ API (rate limit عام على كل الاستدعاءات)
_last_api_call_at = 0.0


def _headers() -> dict[str, str]:
    return {"X-Auth-Token": config.require_api_token()}


def _respect_rate_limit() -> None:
    """
    تأخير بسيط بين الطلبات لاحترام حد الخطة المجانية (~10 طلب/دقيقة).

    يُطبَّق مركزيًا قبل كل request حتى لو نُسي sleep في الحلقات الخارجية.
    """
    global _last_api_call_at

    delay = float(config.API_REQUEST_DELAY_SECONDS)
    if delay <= 0:
        _last_api_call_at = time.monotonic()
        return

    now = time.monotonic()
    if _last_api_call_at > 0:
        elapsed = now - _last_api_call_at
        remaining = delay - elapsed
        if remaining > 0:
            print(f"  انتظار {remaining:.1f}s احترامًا لحد الـ API...")
            time.sleep(remaining)

    _last_api_call_at = time.monotonic()


def _result_from_score(home_goals: int, away_goals: int) -> int:
    """تحويل نتيجة المباراة لترميز رقمي موحّد."""
    if home_goals > away_goals:
        return config.RESULT_HOME_WIN
    if home_goals < away_goals:
        return config.RESULT_AWAY_WIN
    return config.RESULT_DRAW


def _get_matches(
    competition_code: str,
    params: dict,
    session: requests.Session | None = None,
) -> list[dict]:
    """طلب عام لمباريات مسابقة مع rate limit + إعادة محاولة عند 429."""
    url = f"{config.API_BASE_URL}/competitions/{competition_code}/matches"
    http = session or requests.Session()
    max_retries = int(config.API_MAX_RETRIES_ON_429)

    for attempt in range(max_retries + 1):
        _respect_rate_limit()
        response = http.get(url, headers=_headers(), params=params, timeout=30)

        if response.status_code == 429:
            if attempt >= max_retries:
                raise RuntimeError(
                    "تم تجاوز حد الطلبات (429) بعد عدة محاولات. "
                    "انتظر دقيقة ثم أعد المحاولة."
                )
            backoff = float(config.API_RETRY_BACKOFF_SECONDS) * (attempt + 1)
            print(
                f"  429 Too Many Requests — إعادة المحاولة بعد {backoff:.0f}s "
                f"(محاولة {attempt + 1}/{max_retries})..."
            )
            time.sleep(backoff)
            # صفّر المؤقت ليبدأ التباعد من جديد بعد الـ backoff
            global _last_api_call_at
            _last_api_call_at = 0.0
            continue

        if response.status_code == 403:
            raise RuntimeError(
                f"الوصول مرفوض للمسابقة {competition_code} بالمعاملات {params} "
                f"(قد لا يكون متاحًا في الخطة المجانية)."
            )
        response.raise_for_status()

        payload = response.json()
        return payload.get("matches", [])

    # لن نصل هنا عادةً
    raise RuntimeError("فشل جلب المباريات من الـ API.")


def fetch_competition_matches(
    competition_code: str,
    season: int,
    session: requests.Session | None = None,
) -> list[dict]:
    """
    جلب مباريات دوري واحد لموسم واحد من الـ API.

    Endpoint:
      GET /v4/competitions/{code}/matches?season={year}
    """
    return _get_matches(
        competition_code,
        params={"season": season},
        session=session,
    )


def fetch_upcoming_competition_matches(
    competition_code: str,
    session: requests.Session | None = None,
) -> list[dict]:
    """
    جلب المباريات القادمة لدوري واحد (schedule).

    Endpoint:
      GET /v4/competitions/{code}/matches?status=SCHEDULED,TIMED,IN_PLAY
    """
    return _get_matches(
        competition_code,
        params={"status": config.UPCOMING_STATUSES},
        session=session,
    )


def matches_to_rows(matches: Iterable[dict], competition_code: str, season: int) -> list[dict]:
    """تحويل استجابة الـ API إلى صفوف جدول موحّدة (نتائج منتهية فقط)."""
    rows: list[dict] = []

    for match in matches:
        # نستخدم المباريات المنتهية فقط (فيها أهداف نهائية)
        if match.get("status") != "FINISHED":
            continue

        score = (match.get("score") or {}).get("fullTime") or {}
        home_goals = score.get("home")
        away_goals = score.get("away")

        if home_goals is None or away_goals is None:
            continue

        home_team = (match.get("homeTeam") or {}).get("name")
        away_team = (match.get("awayTeam") or {}).get("name")
        if not home_team or not away_team:
            continue

        rows.append(
            {
                "date": match.get("utcDate"),
                "competition": competition_code,
                "season": season,
                "matchday": match.get("matchday"),
                "home_team": home_team,
                "away_team": away_team,
                "home_goals": int(home_goals),
                "away_goals": int(away_goals),
                "result": _result_from_score(int(home_goals), int(away_goals)),
            }
        )

    return rows


def schedule_to_rows(matches: Iterable[dict], competition_code: str) -> list[dict]:
    """تحويل المباريات القادمة إلى صفوف جدول (بدون نتيجة بعد)."""
    rows: list[dict] = []

    for match in matches:
        status = match.get("status")
        if status not in {"SCHEDULED", "TIMED", "IN_PLAY"}:
            continue

        home_team = (match.get("homeTeam") or {}).get("name")
        away_team = (match.get("awayTeam") or {}).get("name")
        # أحيانًا يظهر السطر قبل تحديد الفرق رسميًا
        if not home_team or not away_team:
            continue

        season_info = match.get("season") or {}
        season_start = season_info.get("startDate") or ""
        season_year = int(season_start[:4]) if season_start else None

        rows.append(
            {
                "date": match.get("utcDate"),
                "competition": competition_code,
                "season": season_year,
                "matchday": match.get("matchday"),
                "status": status,
                "home_team": home_team,
                "away_team": away_team,
            }
        )

    return rows


def fetch_all_matches(
    competitions: list[str] | None = None,
    seasons: list[int] | None = None,
) -> pd.DataFrame:
    """
    جلب كل المباريات من الدوريات والمواسم المحددة وإرجاع DataFrame.
    فيه تأخير بسيط بين الطلبات لتجنب 429.
    """
    competitions = competitions or config.COMPETITIONS
    seasons = seasons or config.SEASONS

    all_rows: list[dict] = []
    session = requests.Session()

    for competition in competitions:
        for season in seasons:
            # التأخير مركزي داخل _get_matches عبر _respect_rate_limit()
            print(f"جلب {competition} موسم {season}...")
            try:
                matches = fetch_competition_matches(competition, season, session=session)
            except Exception as exc:  # نكمل باقي الطلبات لو موسم/دوري فشل
                print(f"  تعذّر الجلب: {exc}")
                continue

            rows = matches_to_rows(matches, competition, season)
            print(f"  تم: {len(rows)} مباراة منتهية")
            all_rows.extend(rows)

    if not all_rows:
        raise RuntimeError("لم يتم جلب أي مباريات. تحقق من المفتاح أو توفر المواسم.")

    df = pd.DataFrame(all_rows)
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.sort_values("date").reset_index(drop=True)
    return df


def save_matches(df: pd.DataFrame, path: Path | None = None) -> Path:
    """حفظ البيانات محليًا حتى ما نحتاج نطلب الـ API كل مرة."""
    path = path or config.DATA_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"تم الحفظ في: {path} ({len(df)} صف)")
    return path


def load_matches_csv(path: Path | None = None) -> pd.DataFrame:
    """قراءة البيانات المحفوظة محليًا."""
    path = path or config.DATA_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"ملف البيانات غير موجود: {path}\n"
            "شغّل جلب البيانات أولًا (fetch)."
        )

    df = pd.read_csv(path, parse_dates=["date"])
    missing = [col for col in config.REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"أعمدة ناقصة في ملف البيانات: {missing}")

    return df.sort_values("date").reset_index(drop=True)


def get_matches(force_refresh: bool = False) -> pd.DataFrame:
    """
    الواجهة الرئيسية:
    - إذا الملف المحلي موجود ولم نطلب تحديثًا إجباريًا -> نقرأ منه
    - وإلا نجلب من الـ API ونحفظ
    """
    if not force_refresh and config.DATA_FILE.exists():
        print(f"قراءة البيانات المحلية من {config.DATA_FILE}")
        return load_matches_csv()

    df = fetch_all_matches()
    save_matches(df)
    return df


def fetch_last_n_matches_per_league(
    n: int | None = None,
    competitions: list[str] | None = None,
    seasons: list[int] | None = None,
) -> pd.DataFrame:
    """
    جلب آخر n مباراة منتهية (نتائج فعلية) لكل دوري.

    يعتمد على مواسم config لتجميع مباريات كافية، ثم يأخذ الأحدث فقط.
    """
    n = n if n is not None else config.LAST_N_MATCHES_PER_LEAGUE
    competitions = competitions or config.COMPETITIONS

    full_df = fetch_all_matches(competitions=competitions, seasons=seasons)
    if full_df.empty:
        raise RuntimeError("لا توجد مباريات منتهية للاختيار منها.")

    # آخر n لكل دوري حسب التاريخ
    recent = (
        full_df.sort_values("date")
        .groupby("competition", group_keys=False)
        .tail(n)
        .reset_index(drop=True)
    )

    for competition, count in recent.groupby("competition").size().items():
        print(f"{competition}: تم اختيار آخر {count} مباراة")

    return recent


def fetch_schedule(
    n: int | None = None,
    competitions: list[str] | None = None,
) -> pd.DataFrame:
    """
    جلب جدول المباريات القادمة (schedule) لكل دوري.

    يأخذ أقرب n مباراة (حسب التاريخ) لكل مسابقة.
    """
    n = n if n is not None else config.NEXT_N_MATCHES_PER_LEAGUE
    competitions = competitions or config.COMPETITIONS

    all_rows: list[dict] = []
    session = requests.Session()

    for competition in competitions:
        # التأخير مركزي داخل _get_matches عبر _respect_rate_limit()
        print(f"جلب جدول {competition} (مباريات قادمة)...")
        try:
            matches = fetch_upcoming_competition_matches(competition, session=session)
        except Exception as exc:
            print(f"  تعذّر الجلب: {exc}")
            continue

        rows = schedule_to_rows(matches, competition)
        print(f"  تم: {len(rows)} مباراة مجدولة")
        all_rows.extend(rows)

    if not all_rows:
        raise RuntimeError("لم يتم جلب أي مباريات قادمة.")

    df = pd.DataFrame(all_rows)
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.sort_values("date").reset_index(drop=True)

    # أقرب n مباراة لكل دوري
    upcoming = (
        df.groupby("competition", group_keys=False)
        .head(n)
        .reset_index(drop=True)
    )

    for competition, count in upcoming.groupby("competition").size().items():
        print(f"{competition}: تم اختيار أقرب {count} مباراة قادمة")

    return upcoming


if __name__ == "__main__":
    # تشغيل مباشر: python -m src.data_loader
    matches = get_matches(force_refresh=True)
    print(matches.head())
    print("...")
    print(matches.tail())
    print(f"\nالإجمالي: {len(matches)} مباراة")
    print(matches["competition"].value_counts().to_string())
