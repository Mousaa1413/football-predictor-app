#!/usr/bin/env python3
"""
واجهة Kivy بسيطة لتوقع نتائج المباريات على Android.

تعمل على البيانات المحلية (SQLite/CSV) إن وُجدت.
تحديث البيانات من الـ API يحتاج FOOTBALL_DATA_API_TOKEN.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

# جذر المشروع على sys.path (مهم داخل APK/Buildozer)
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# تحميل .env محليًا إن وُجد (اختياري — لا يفشل إن غاب)
_env_path = ROOT / ".env"
if _env_path.exists():
    try:
        for line in _env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))
    except OSError:
        pass

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout

KV = """
#:import dp kivy.metrics.dp

<RootWidget>:
    orientation: "vertical"
    padding: dp(12)
    spacing: dp(8)

    Label:
        text: "Football Predictor"
        size_hint_y: None
        height: dp(36)
        bold: True
        font_size: "20sp"

    Label:
        text: "توقع نتائج المباريات (فورم + H2H)"
        size_hint_y: None
        height: dp(24)
        font_size: "14sp"

    BoxLayout:
        size_hint_y: None
        height: dp(44)
        spacing: dp(8)

        TextInput:
            id: home_input
            hint_text: "المضيف (مثال: Arsenal)"
            multiline: False
            font_size: "16sp"

        TextInput:
            id: away_input
            hint_text: "الضيف (مثال: Chelsea)"
            multiline: False
            font_size: "16sp"

    BoxLayout:
        size_hint_y: None
        height: dp(44)
        spacing: dp(8)

        Button:
            text: "توقّع"
            on_press: root.do_predict()

        Button:
            text: "الجدول"
            on_press: root.do_schedule()

        Button:
            text: "الفرق"
            on_press: root.do_teams()

        Button:
            text: "تحديث"
            on_press: root.do_update()

    ScrollView:
        bar_width: dp(6)
        Label:
            id: output
            text: root.status_text
            text_size: self.width, None
            size_hint_y: None
            height: self.texture_size[1]
            halign: "left"
            valign: "top"
            padding: dp(8), dp(8)
            font_size: "14sp"
"""


class RootWidget(BoxLayout):
    status_text = StringProperty(
        "جاهز.\n"
        "1) أدخل اسمي الفريقين ثم اضغط «توقّع».\n"
        "2) أو «الجدول» لعرض المباريات القادمة.\n"
        "3) «تحديث» يجلب بيانات جديدة (يحتاج API token)."
    )

    def _set_status(self, text: str) -> None:
        self.status_text = text
        if "output" in self.ids:
            self.ids.output.text = text

    def _run_bg(self, fn) -> None:
        """تشغيل مهمة في خيط خلفي ثم تحديث الواجهة."""

        def worker():
            try:
                result = fn()
            except Exception as exc:  # noqa: BLE001 — عرض الخطأ للمستخدم
                result = f"خطأ: {exc}"
            Clock.schedule_once(lambda _dt: self._set_status(str(result)), 0)

        threading.Thread(target=worker, daemon=True).start()

    def do_predict(self) -> None:
        home = (self.ids.home_input.text or "").strip()
        away = (self.ids.away_input.text or "").strip()
        if not home or not away:
            self._set_status("أدخل اسم الفريق المضيف والضيف.")
            return

        self._set_status("جارٍ التوقع...")

        def job() -> str:
            from src.predictor import find_team, list_known_teams, predict_match

            teams = list_known_teams()
            h = find_team(home, teams)
            a = find_team(away, teams)
            pred = predict_match(h, a)
            d = pred.as_dict()
            lines = [
                f"المباراة : {d['home_team']} vs {d['away_team']}",
                (
                    f"المضيف   : هجوم {d['home_attack']:.2f} | "
                    f"دفاع {d['home_defense']:.2f} | "
                    f"فورم {d['home_points']}/{d['home_max_points']} ({d['home_form_string']})"
                ),
                (
                    f"الضيف    : هجوم {d['away_attack']:.2f} | "
                    f"دفاع {d['away_defense']:.2f} | "
                    f"فورم {d['away_points']}/{d['away_max_points']} ({d['away_form_string']})"
                ),
                f"H2H      : {d['h2h_summary']}",
                (
                    f"متوقع    : {d['expected_home_goals']:.2f} - {d['expected_away_goals']:.2f}"
                ),
                (
                    f"احتمال   : مضيف {d['prob_home']:.0%} | "
                    f"تعادل {d['prob_draw']:.0%} | "
                    f"ضيف {d['prob_away']:.0%}"
                ),
                f"التوقع   : {d['result_label']} ({d['confidence']:.0%})",
                f"السبب    : {d['reason']}",
            ]
            return "\n".join(lines)

        self._run_bg(job)

    def do_teams(self) -> None:
        self._set_status("جارٍ قراءة الفرق...")

        def job() -> str:
            from src.predictor import list_known_teams

            teams = list_known_teams()
            return f"عدد الفرق: {len(teams)}\n" + "\n".join(f" - {t}" for t in teams)

        self._run_bg(job)

    def do_schedule(self) -> None:
        self._set_status("جارٍ قراءة الجدول...")

        def job() -> str:
            from src.database import load_schedule_from_db
            from src.predictor import find_team, list_known_teams, predict_match

            schedule = load_schedule_from_db()
            if schedule.empty:
                return "الجدول فارغ. اضغط «تحديث» أولًا."

            teams = list_known_teams()
            lines: list[str] = ["المباريات القادمة:", ""]
            shown = 0
            for row in schedule.sort_values("date").itertuples(index=False):
                if shown >= 10:
                    break
                header = f"[{row.league}] {row.date} | {row.home_team} vs {row.away_team}"
                try:
                    h = find_team(row.home_team, teams)
                    a = find_team(row.away_team, teams)
                    d = predict_match(h, a).as_dict()
                    lines.append(header)
                    lines.append(
                        f"  {d['result_label']} | "
                        f"H {d['prob_home']:.0%} / D {d['prob_draw']:.0%} / A {d['prob_away']:.0%}"
                    )
                except Exception:
                    lines.append(header)
                    lines.append("  (لا يتوفر توقع)")
                lines.append("")
                shown += 1
            return "\n".join(lines)

        self._run_bg(job)

    def do_update(self) -> None:
        self._set_status("جارٍ التحديث من الـ API (قد يستغرق دقيقة)...")

        def job() -> str:
            import config
            from src.data_loader import (
                fetch_last_n_matches_per_league,
                fetch_schedule,
                save_matches,
            )
            from src.database import (
                db_summary,
                init_db,
                save_results_to_db,
                save_schedule_to_db,
            )

            config.require_api_token()
            init_db()
            results = fetch_last_n_matches_per_league()
            save_matches(results, path=config.RECENT_DATA_FILE)
            save_results_to_db(results)
            schedule = fetch_schedule()
            save_matches(schedule, path=config.SCHEDULE_FILE)
            save_schedule_to_db(schedule)
            return "تم التحديث بنجاح.\n" + db_summary()

        self._run_bg(job)


class FootballPredictorApp(App):
    title = "Football Predictor"

    def build(self):
        Builder.load_string(KV)
        return RootWidget()


if __name__ == "__main__":
    FootballPredictorApp().run()
