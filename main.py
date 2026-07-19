#!/usr/bin/env python3
"""
واجهة CLI الرئيسية لمشروع توقع نتائج كرة القدم.

الأوامر:
  python main.py update
  python main.py update --results
  python main.py update --schedule

  python main.py predict "Team A" "Team B"
  python main.py predict Arsenal Chelsea

  python main.py teams
  python main.py schedule
  python main.py status
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from src.data_loader import (
    fetch_all_matches,
    fetch_last_n_matches_per_league,
    fetch_schedule,
    save_matches,
)
from src.database import (
    db_summary,
    init_db,
    load_schedule_from_db,
    save_results_to_db,
    save_schedule_to_db,
)
from src.predictor import find_team, list_known_teams, predict_match


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="CLI لتحديث بيانات المباريات وتوقع النتائج",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ---- update ----
    update_p = sub.add_parser(
        "update",
        help="تحديث البيانات من football-data.org وحفظها في SQLite",
    )
    update_p.add_argument(
        "--n",
        type=int,
        default=config.LAST_N_MATCHES_PER_LEAGUE,
        help=f"آخر N نتيجة لكل دوري (افتراضي: {config.LAST_N_MATCHES_PER_LEAGUE})",
    )
    update_p.add_argument(
        "--next",
        dest="next_n",
        type=int,
        default=config.NEXT_N_MATCHES_PER_LEAGUE,
        help=f"أقرب N مباراة قادمة لكل دوري (افتراضي: {config.NEXT_N_MATCHES_PER_LEAGUE})",
    )
    update_p.add_argument(
        "--competitions",
        nargs="+",
        default=config.COMPETITIONS,
        help="رموز الدوريات (افتراضي: PL PD)",
    )
    update_p.add_argument(
        "--results",
        action="store_true",
        help="تحديث النتائج السابقة فقط",
    )
    update_p.add_argument(
        "--schedule",
        action="store_true",
        help="تحديث جدول المباريات القادمة فقط",
    )
    update_p.add_argument(
        "--full-history",
        action="store_true",
        help="جلب المواسم الكاملة أيضًا إلى data/matches.csv (مفيد لـ H2H)",
    )
    update_p.add_argument(
        "--no-csv",
        action="store_true",
        help="عدم كتابة ملفات CSV (SQLite فقط)",
    )
    update_p.add_argument(
        "--db",
        type=Path,
        default=config.DB_FILE,
        help=f"مسار قاعدة البيانات (افتراضي: {config.DB_FILE})",
    )

    # ---- predict ----
    predict_p = sub.add_parser(
        "predict",
        help='توقع مباراة: python main.py predict "Team A" "Team B"',
    )
    predict_p.add_argument(
        "home",
        type=str,
        help="اسم الفريق المضيف (يدعم اسم مختصر)",
    )
    predict_p.add_argument(
        "away",
        type=str,
        help="اسم الفريق الضيف (يدعم اسم مختصر)",
    )
    predict_p.add_argument(
        "--last-n",
        type=int,
        default=config.FORM_LAST_N,
        help=f"عدد آخر المباريات للفورم (افتراضي: {config.FORM_LAST_N})",
    )
    predict_p.add_argument(
        "--h2h-n",
        type=int,
        default=config.H2H_LAST_N,
        help=f"عدد المواجهات المباشرة (افتراضي: {config.H2H_LAST_N})",
    )
    predict_p.add_argument(
        "--draw-margin",
        type=float,
        default=config.DRAW_MARGIN,
        help=f"هامش التعادل (افتراضي: {config.DRAW_MARGIN})",
    )

    # ---- teams ----
    sub.add_parser("teams", help="عرض الفرق المعروفة في قاعدة البيانات")

    # ---- schedule ----
    schedule_p = sub.add_parser(
        "schedule",
        help="عرض/توقع المباريات القادمة المخزّنة محليًا",
    )
    schedule_p.add_argument(
        "--limit",
        type=int,
        default=10,
        help="عدد المباريات المعروضة (افتراضي: 10)",
    )
    schedule_p.add_argument(
        "--no-predict",
        action="store_true",
        help="عرض الجدول فقط بدون توقع",
    )

    # ---- status ----
    sub.add_parser("status", help="ملخص قاعدة البيانات والملفات المحلية")

    return parser


def cmd_update(args: argparse.Namespace) -> int:
    if args.results and args.schedule:
        print("استخدم --results أو --schedule فقط، وليس الاثنين معًا.", file=sys.stderr)
        return 2

    do_results = not args.schedule
    do_schedule = not args.results

    print("=" * 50)
    print("تحديث البيانات من football-data.org")
    print(f"الدوريات : {', '.join(args.competitions)}")
    print(f"قاعدة DB : {args.db}")
    if do_results:
        print(f"نتائج    : آخر {args.n} لكل دوري")
    if do_schedule:
        print(f"جدول     : أقرب {args.next_n} لكل دوري")
    if args.full_history:
        print("تاريخ    : جلب المواسم الكاملة -> matches.csv")
    print("=" * 50)

    init_db(args.db)

    try:
        if args.full_history:
            print("\n[تاريخ كامل]")
            history = fetch_all_matches(competitions=args.competitions)
            save_matches(history, path=config.DATA_FILE)

        if do_results:
            print("\n[نتائج]")
            results = fetch_last_n_matches_per_league(
                n=args.n,
                competitions=args.competitions,
            )
            if not args.no_csv:
                save_matches(results, path=config.RECENT_DATA_FILE)
            save_results_to_db(results, db_path=args.db)
            print(results.groupby("competition").size().rename("matches").to_string())

        if do_schedule:
            print("\n[جدول قادم]")
            schedule = fetch_schedule(
                n=args.next_n,
                competitions=args.competitions,
            )
            if not args.no_csv:
                save_matches(schedule, path=config.SCHEDULE_FILE)
            save_schedule_to_db(schedule, db_path=args.db)
            print(schedule.groupby("competition").size().rename("matches").to_string())

    except Exception as exc:
        print(f"فشل التحديث: {exc}", file=sys.stderr)
        return 1

    print("\nتم التحديث بنجاح.")
    print(db_summary(args.db))
    return 0


def _print_prediction(pred) -> None:
    d = pred.as_dict()
    print(f"المباراة : {d['home_team']}  vs  {d['away_team']}")
    print(
        f"المضيف   : هجوم {d['home_attack']:.2f} | دفاع {d['home_defense']:.2f} | "
        f"فورم {d['home_points']}/{d['home_max_points']} ({d['home_form_string']})"
    )
    print(
        f"الضيف    : هجوم {d['away_attack']:.2f} | دفاع {d['away_defense']:.2f} | "
        f"فورم {d['away_points']}/{d['away_max_points']} ({d['away_form_string']})"
    )
    if d["h2h_available"]:
        print(
            f"H2H      : {d['h2h_summary']} | "
            f"سجل المضيف ({d['h2h_form_string']}) | h2h={d['h2h_score']:+.2f}"
        )
    else:
        print(f"H2H      : {d['h2h_summary']}")
    print(
        f"متوقع    : {d['expected_home_goals']:.2f} - {d['expected_away_goals']:.2f} "
        f"| goal={d['goal_score']:+.2f} | form={d['form_score']:+.2f} | h2h={d['h2h_score']:+.2f}"
    )
    print(
        f"احتمال   : فوز المضيف {d['prob_home']:.0%} | "
        f"تعادل {d['prob_draw']:.0%} | "
        f"فوز الضيف {d['prob_away']:.0%}"
    )
    print(f"التوقع   : {d['result_label']}  (أعلى احتمال {d['confidence']:.0%})")
    print(f"السبب    : {d['reason']}")


def cmd_predict(args: argparse.Namespace) -> int:
    try:
        teams = list_known_teams()
        home = find_team(args.home, teams)
        away = find_team(args.away, teams)
        pred = predict_match(
            home,
            away,
            last_n=args.last_n,
            h2h_last_n=args.h2h_n,
            draw_margin=args.draw_margin,
        )
    except Exception as exc:
        print(f"فشل التوقع: {exc}", file=sys.stderr)
        return 1

    print("=" * 50)
    print("توقع المباراة (هجوم/دفاع + فورم + H2H)")
    print("=" * 50)
    _print_prediction(pred)
    print("=" * 50)
    return 0


def cmd_teams(_args: argparse.Namespace) -> int:
    try:
        teams = list_known_teams()
    except Exception as exc:
        print(f"تعذّر قراءة الفرق: {exc}", file=sys.stderr)
        return 1

    print(f"عدد الفرق المعروفة: {len(teams)}")
    for team in teams:
        print(f" - {team}")
    return 0


def cmd_schedule(args: argparse.Namespace) -> int:
    try:
        schedule = load_schedule_from_db()
    except Exception as exc:
        print(f"تعذّر قراءة الجدول: {exc}", file=sys.stderr)
        print("شغّل: python main.py update --schedule", file=sys.stderr)
        return 1

    if schedule.empty:
        print("الجدول فارغ. شغّل: python main.py update --schedule")
        return 1

    teams = []
    if not args.no_predict:
        try:
            teams = list_known_teams()
        except Exception:
            teams = []

    print("=" * 50)
    print("المباريات القادمة")
    print("=" * 50)

    shown = 0
    skipped = 0
    for row in schedule.sort_values("date").itertuples(index=False):
        if shown >= args.limit:
            break

        print(f"[{row.league}] {row.date} | {row.home_team} vs {row.away_team}")

        if args.no_predict or not teams:
            shown += 1
            print("-" * 50)
            continue

        try:
            home = find_team(row.home_team, teams)
            away = find_team(row.away_team, teams)
            pred = predict_match(home, away)
            d = pred.as_dict()
            print(
                f"  احتمال: مضيف {d['prob_home']:.0%} | "
                f"تعادل {d['prob_draw']:.0%} | ضيف {d['prob_away']:.0%}"
            )
            print(f"  التوقع: {d['result_label']}")
            print(f"  السبب : {d['reason']}")
        except Exception:
            skipped += 1
            print("  (لا يتوفر توقع — فريق غير موجود في النتائج الحديثة)")

        print("-" * 50)
        shown += 1

    print(f"عرض {shown} مباراة")
    if skipped:
        print(f"تخطي التوقع لـ {skipped} مباراة")
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    print(db_summary())
    print()
    for label, path in [
        ("matches.csv", config.DATA_FILE),
        ("last_matches.csv", config.RECENT_DATA_FILE),
        ("schedule.csv", config.SCHEDULE_FILE),
        ("matches.db", config.DB_FILE),
    ]:
        state = f"{path.stat().st_size} bytes" if path.exists() else "غير موجود"
        print(f"{label}: {state}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    handlers = {
        "update": cmd_update,
        "predict": cmd_predict,
        "teams": cmd_teams,
        "schedule": cmd_schedule,
        "status": cmd_status,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.error(f"أمر غير معروف: {args.command}")
        return 2
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
