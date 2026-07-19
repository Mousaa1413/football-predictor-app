"""
طبقة قاعدة البيانات المحلية SQLite.

الملف: data/matches.db

الجداول:
  - matches  : نتائج المباريات المنتهية
  - schedule : المباريات القادمة (بدون نتيجة بعد)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

import config

# ---- SQL schema ----

CREATE_MATCHES_SQL = """
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    league TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    home_goals INTEGER NOT NULL,
    away_goals INTEGER NOT NULL,
    result INTEGER NOT NULL,
    UNIQUE (date, league, home_team, away_team)
);
"""

CREATE_SCHEDULE_SQL = """
CREATE TABLE IF NOT EXISTS schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    league TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    matchday INTEGER,
    status TEXT,
    UNIQUE (date, league, home_team, away_team)
);
"""

CREATE_MATCHES_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_matches_league_date
ON matches (league, date);
"""

CREATE_SCHEDULE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_schedule_league_date
ON schedule (league, date);
"""


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """فتح اتصال SQLite مع Row factory للوصول بالاسم."""
    path = db_path or config.DB_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | None = None) -> Path:
    """إنشاء الجداول والفهارس إن لم تكن موجودة."""
    path = db_path or config.DB_FILE
    with get_connection(path) as conn:
        conn.execute(CREATE_MATCHES_SQL)
        conn.execute(CREATE_SCHEDULE_SQL)
        conn.execute(CREATE_MATCHES_INDEX_SQL)
        conn.execute(CREATE_SCHEDULE_INDEX_SQL)
        conn.commit()
    return path


def _to_iso_date(value) -> str:
    """توحيد التاريخ كنص ISO للتخزين في SQLite."""
    ts = pd.to_datetime(value, utc=True)
    return ts.isoformat()


def save_results_to_db(
    df: pd.DataFrame,
    db_path: Path | None = None,
    replace_leagues: bool = True,
) -> int:
    """
    حفظ نتائج المباريات المنتهية في جدول matches.

    الأعمدة المتوقعة في df:
      date, competition, home_team, away_team, home_goals, away_goals, result

    إذا replace_leagues=True يتم حذف مباريات نفس الدوريات قبل الإدخال
    (مناسب لتحديث "آخر 50 مباراة").
    """
    if df.empty:
        return 0

    required = {
        "date",
        "competition",
        "home_team",
        "away_team",
        "home_goals",
        "away_goals",
        "result",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"أعمدة ناقصة قبل الحفظ في matches: {sorted(missing)}")

    path = init_db(db_path)
    rows = []
    for row in df.itertuples(index=False):
        rows.append(
            (
                _to_iso_date(row.date),
                str(row.competition),
                str(row.home_team),
                str(row.away_team),
                int(row.home_goals),
                int(row.away_goals),
                int(row.result),
            )
        )

    leagues = sorted({r[1] for r in rows})

    with get_connection(path) as conn:
        if replace_leagues and leagues:
            placeholders = ",".join("?" for _ in leagues)
            conn.execute(
                f"DELETE FROM matches WHERE league IN ({placeholders})",
                leagues,
            )

        conn.executemany(
            """
            INSERT OR REPLACE INTO matches
                (date, league, home_team, away_team, home_goals, away_goals, result)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()

    print(f"SQLite matches: تم حفظ {len(rows)} صف في {path}")
    return len(rows)


def save_schedule_to_db(
    df: pd.DataFrame,
    db_path: Path | None = None,
    replace_leagues: bool = True,
) -> int:
    """
    حفظ المباريات القادمة في جدول schedule.

    الأعمدة المتوقعة:
      date, competition, home_team, away_team, [matchday], [status]
    """
    if df.empty:
        return 0

    required = {"date", "competition", "home_team", "away_team"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"أعمدة ناقصة قبل الحفظ في schedule: {sorted(missing)}")

    path = init_db(db_path)
    rows = []
    for row in df.itertuples(index=False):
        matchday = getattr(row, "matchday", None)
        status = getattr(row, "status", None)
        rows.append(
            (
                _to_iso_date(row.date),
                str(row.competition),
                str(row.home_team),
                str(row.away_team),
                int(matchday) if matchday is not None and pd.notna(matchday) else None,
                str(status) if status is not None and pd.notna(status) else None,
            )
        )

    leagues = sorted({r[1] for r in rows})

    with get_connection(path) as conn:
        if replace_leagues and leagues:
            placeholders = ",".join("?" for _ in leagues)
            conn.execute(
                f"DELETE FROM schedule WHERE league IN ({placeholders})",
                leagues,
            )

        conn.executemany(
            """
            INSERT OR REPLACE INTO schedule
                (date, league, home_team, away_team, matchday, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()

    print(f"SQLite schedule: تم حفظ {len(rows)} صف في {path}")
    return len(rows)


def load_matches_from_db(
    db_path: Path | None = None,
    league: str | None = None,
) -> pd.DataFrame:
    """قراءة جدول matches كـ DataFrame."""
    path = db_path or config.DB_FILE
    if not path.exists():
        raise FileNotFoundError(f"قاعدة البيانات غير موجودة: {path}")

    query = """
        SELECT date, league, home_team, away_team, home_goals, away_goals, result
        FROM matches
    """
    params: list = []
    if league:
        query += " WHERE league = ?"
        params.append(league)
    query += " ORDER BY date ASC"

    with get_connection(path) as conn:
        df = pd.read_sql_query(query, conn, params=params)

    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], utc=True)
    return df


def load_schedule_from_db(
    db_path: Path | None = None,
    league: str | None = None,
) -> pd.DataFrame:
    """قراءة جدول schedule كـ DataFrame."""
    path = db_path or config.DB_FILE
    if not path.exists():
        raise FileNotFoundError(f"قاعدة البيانات غير موجودة: {path}")

    query = """
        SELECT date, league, home_team, away_team, matchday, status
        FROM schedule
    """
    params: list = []
    if league:
        query += " WHERE league = ?"
        params.append(league)
    query += " ORDER BY date ASC"

    with get_connection(path) as conn:
        df = pd.read_sql_query(query, conn, params=params)

    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], utc=True)
    return df


def db_summary(db_path: Path | None = None) -> str:
    """ملخص سريع لمحتوى قاعدة البيانات."""
    path = db_path or config.DB_FILE
    if not path.exists():
        return f"قاعدة البيانات غير موجودة: {path}"

    with get_connection(path) as conn:
        matches_count = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
        schedule_count = conn.execute("SELECT COUNT(*) FROM schedule").fetchone()[0]
        by_league = conn.execute(
            """
            SELECT league, COUNT(*) AS n
            FROM matches
            GROUP BY league
            ORDER BY league
            """
        ).fetchall()

    lines = [
        f"DB: {path}",
        f"matches: {matches_count} صف",
        f"schedule: {schedule_count} صف",
    ]
    if by_league:
        lines.append("matches حسب الدوري:")
        for row in by_league:
            lines.append(f"  {row['league']}: {row['n']}")
    return "\n".join(lines)
