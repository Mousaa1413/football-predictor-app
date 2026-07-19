#!/usr/bin/env python3
"""
سكربت التوقع البسيط لنتائج المباريات.

يعتمد على:
  - متوسط أهداف الفريق المسجّلة (هجوم) في آخر مبارياته
  - متوسط أهداف الفريق المستقبلة (دفاع) في آخر مبارياته
  - فورم آخر 5 مباريات (نقاط: فوز=3، تعادل=1، خسارة=0)
  - نتائج المواجهات المباشرة السابقة (H2H) إن وُجدت

الاستخدام:
  python predict.py --home "Arsenal FC" --away "Chelsea FC"
  python predict.py --home Arsenal --away Chelsea
  python predict.py --schedule
  python predict.py --list-teams
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from src.database import load_matches_from_db, load_schedule_from_db
from src.predictor import find_team, list_known_teams, predict_match


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="توقع نتيجة مباراة من متوسط الهجوم/الدفاع لآخر المباريات",
    )
    parser.add_argument("--home", type=str, help="اسم الفريق المضيف")
    parser.add_argument("--away", type=str, help="اسم الفريق الضيف")
    parser.add_argument(
        "--last-n",
        type=int,
        default=config.FORM_LAST_N,
        help=f"عدد آخر المباريات لحساب المتوسط (افتراضي: {config.FORM_LAST_N})",
    )
    parser.add_argument(
        "--draw-margin",
        type=float,
        default=config.DRAW_MARGIN,
        help=f"هامش التعادل في فارق الأهداف المتوقعة (افتراضي: {config.DRAW_MARGIN})",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="توقّع كل المباريات القادمة المخزّنة في schedule",
    )
    parser.add_argument(
        "--list-teams",
        action="store_true",
        help="عرض الفرق المعروفة في قاعدة النتائج",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=15,
        help="حد أقصى لعدد مباريات الجدول عند --schedule (افتراضي: 15)",
    )
    return parser.parse_args()


def _print_prediction(pred, title: str | None = None) -> None:
    if title:
        print(title)
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
            f"سجل المضيف ({d['h2h_form_string']}) | h2h_score={d['h2h_score']:+.2f}"
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
    print("-" * 50)


def cmd_list_teams() -> int:
    try:
        teams = list_known_teams()
    except Exception as exc:
        print(f"تعذّر قراءة الفرق: {exc}", file=sys.stderr)
        return 1

    print(f"عدد الفرق: {len(teams)}")
    for team in teams:
        print(f" - {team}")
    return 0


def cmd_predict_pair(args: argparse.Namespace) -> int:
    if not args.home or not args.away:
        print("يجب تمرير --home و --away", file=sys.stderr)
        return 2

    try:
        matches = load_matches_from_db()
        teams = list_known_teams(matches)
        home = find_team(args.home, teams)
        away = find_team(args.away, teams)
        pred = predict_match(
            home,
            away,
            matches=matches,
            last_n=args.last_n,
            draw_margin=args.draw_margin,
        )
    except Exception as exc:
        print(f"فشل التوقع: {exc}", file=sys.stderr)
        return 1

    print("=" * 50)
    print("توقع بسيط (هجوم/دفاع + فورم + مواجهات مباشرة)")
    print("=" * 50)
    _print_prediction(pred)
    return 0


def cmd_predict_schedule(args: argparse.Namespace) -> int:
    try:
        matches = load_matches_from_db()
        schedule = load_schedule_from_db()
    except Exception as exc:
        print(f"تعذّر قراءة قاعدة البيانات: {exc}", file=sys.stderr)
        return 1

    if schedule.empty:
        print("جدول schedule فارغ. شغّل: python fetch_data.py --schedule-only")
        return 1

    teams = list_known_teams(matches)
    print("=" * 50)
    print("توقعات المباريات القادمة")
    print("=" * 50)

    shown = 0
    skipped = 0
    for row in schedule.sort_values("date").itertuples(index=False):
        if shown >= args.limit:
            break
        try:
            # قد تختلف أسماء بعض الفرق بين موسم وآخر
            home = find_team(row.home_team, teams)
            away = find_team(row.away_team, teams)
            pred = predict_match(
                home,
                away,
                matches=matches,
                last_n=args.last_n,
                draw_margin=args.draw_margin,
            )
        except ValueError:
            skipped += 1
            continue

        title = f"[{row.league}] {row.date} | matchday {row.matchday}"
        _print_prediction(pred, title=title)
        shown += 1

    print(f"تم عرض {shown} مباراة")
    if skipped:
        print(f"تم تخطي {skipped} مباراة (فرق غير موجودة في نتائج آخر المباريات)")
    return 0


def main() -> int:
    args = parse_args()

    if args.list_teams:
        return cmd_list_teams()
    if args.schedule:
        return cmd_predict_schedule(args)
    if args.home or args.away:
        return cmd_predict_pair(args)

    print(
        "استخدم:\n"
        "  python predict.py --home 'Arsenal FC' --away 'Chelsea FC'\n"
        "  python predict.py --schedule\n"
        "  python predict.py --list-teams",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
