#!/usr/bin/env python3
"""
سكربت جلب البيانات من football-data.org

يجيب:
  1) آخر 50 مباراة منتهية لكل دوري (نتائج فعلية)
  2) المباريات القادمة (schedule)

التخزين:
  - CSV: data/last_matches.csv و data/schedule.csv
  - SQLite: data/matches.db
      جدول matches  (date, league, home_team, away_team, home_goals, away_goals, result)
      جدول schedule (date, league, home_team, away_team, matchday, status)

الاستخدام:
  python fetch_data.py
  python fetch_data.py --n 50 --next 20
  python fetch_data.py --results-only
  python fetch_data.py --schedule-only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ضمان أن جذر المشروع على sys.path عند التشغيل المباشر
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from src.data_loader import (
    fetch_last_n_matches_per_league,
    fetch_schedule,
    save_matches,
)
from src.database import db_summary, init_db, save_results_to_db, save_schedule_to_db


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="جلب آخر النتائج + جدول المباريات القادمة وتخزينها في SQLite",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=config.LAST_N_MATCHES_PER_LEAGUE,
        help=f"عدد آخر المباريات المنتهية لكل دوري (افتراضي: {config.LAST_N_MATCHES_PER_LEAGUE})",
    )
    parser.add_argument(
        "--next",
        type=int,
        default=config.NEXT_N_MATCHES_PER_LEAGUE,
        dest="next_n",
        help=f"عدد المباريات القادمة لكل دوري (افتراضي: {config.NEXT_N_MATCHES_PER_LEAGUE})",
    )
    parser.add_argument(
        "--competitions",
        nargs="+",
        default=config.COMPETITIONS,
        help="رموز الدوريات (افتراضي: PL PD)",
    )
    parser.add_argument(
        "--results-only",
        action="store_true",
        help="جلب النتائج السابقة فقط",
    )
    parser.add_argument(
        "--schedule-only",
        action="store_true",
        help="جلب جدول المباريات القادمة فقط",
    )
    parser.add_argument(
        "--results-output",
        type=Path,
        default=config.RECENT_DATA_FILE,
        help=f"مسار حفظ نتائج CSV (افتراضي: {config.RECENT_DATA_FILE})",
    )
    parser.add_argument(
        "--schedule-output",
        type=Path,
        default=config.SCHEDULE_FILE,
        help=f"مسار حفظ جدول CSV (افتراضي: {config.SCHEDULE_FILE})",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=config.DB_FILE,
        help=f"مسار قاعدة SQLite (افتراضي: {config.DB_FILE})",
    )
    parser.add_argument(
        "--no-csv",
        action="store_true",
        help="عدم حفظ ملفات CSV (SQLite فقط)",
    )
    return parser.parse_args()


def _print_results_sample(df) -> None:
    cols = [
        "date",
        "competition",
        "home_team",
        "away_team",
        "home_goals",
        "away_goals",
        "result",
    ]
    print(df[cols].tail(8).to_string(index=False))


def _print_schedule_sample(df) -> None:
    cols = [
        "date",
        "competition",
        "matchday",
        "status",
        "home_team",
        "away_team",
    ]
    print(df[cols].head(8).to_string(index=False))


def main() -> int:
    args = parse_args()

    if args.results_only and args.schedule_only:
        print("اختر إما --results-only أو --schedule-only وليس الاثنين معًا.", file=sys.stderr)
        return 2

    fetch_results = not args.schedule_only
    fetch_upcoming = not args.results_only

    print("=" * 50)
    print("جلب البيانات من football-data.org")
    print(f"الدوريات: {', '.join(args.competitions)}")
    print(f"قاعدة البيانات: {args.db}")
    if fetch_results:
        print(f"نتائج: آخر {args.n} مباراة منتهية لكل دوري")
    if fetch_upcoming:
        print(f"جدول: أقرب {args.next_n} مباراة قادمة لكل دوري")
    print("=" * 50)

    # تجهيز قاعدة البيانات مبكرًا
    init_db(args.db)

    try:
        if fetch_results:
            print("\n[1/2] النتائج السابقة" if fetch_upcoming else "\n[1/1] النتائج السابقة")
            results_df = fetch_last_n_matches_per_league(
                n=args.n,
                competitions=args.competitions,
            )
            if not args.no_csv:
                save_matches(results_df, path=args.results_output)
            save_results_to_db(results_df, db_path=args.db)

            print("\nعينة من النتائج:")
            _print_results_sample(results_df)
            print("\nملخص النتائج:")
            print(results_df.groupby("competition").size().rename("matches").to_string())

        if fetch_upcoming:
            print("\n[2/2] المباريات القادمة" if fetch_results else "\n[1/1] المباريات القادمة")
            schedule_df = fetch_schedule(
                n=args.next_n,
                competitions=args.competitions,
            )
            if not args.no_csv:
                save_matches(schedule_df, path=args.schedule_output)
            save_schedule_to_db(schedule_df, db_path=args.db)

            print("\nعينة من الجدول:")
            _print_schedule_sample(schedule_df)
            print("\nملخص الجدول:")
            print(schedule_df.groupby("competition").size().rename("matches").to_string())

    except Exception as exc:
        print(f"فشل الجلب: {exc}", file=sys.stderr)
        return 1

    print("\nتم بنجاح.")
    if fetch_results and not args.no_csv:
        print(f"  CSV نتائج -> {args.results_output}")
    if fetch_upcoming and not args.no_csv:
        print(f"  CSV جدول  -> {args.schedule_output}")
    print(f"  SQLite    -> {args.db}")
    print()
    print(db_summary(args.db))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
