#!/usr/bin/env python3
"""
واجهة Kivy بسيطة لتوقع نتيجة مباراة.

- حقلان لاسم الفريقين (مضيف / ضيف)
- زر «توقّع»
- عرض الاحتمالات والنتيجة والسبب

يستخدم نفس منطق predict.py عبر src.predictor.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# تحميل .env عبر config (مفتاح API إن لزم لاحقًا)
import config  # noqa: F401

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import BooleanProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout

KV = """
#:import dp kivy.metrics.dp

<PredictScreen>:
    orientation: "vertical"
    padding: dp(16)
    spacing: dp(10)

    Label:
        text: "Football Predictor"
        size_hint_y: None
        height: dp(40)
        bold: True
        font_size: "22sp"
        color: 0.95, 0.95, 0.95, 1

    Label:
        text: "أدخل اسم الفريقين ثم اضغط توقّع"
        size_hint_y: None
        height: dp(28)
        font_size: "14sp"
        color: 0.75, 0.75, 0.75, 1

    Label:
        text: "الفريق المضيف"
        size_hint_y: None
        height: dp(22)
        font_size: "13sp"
        halign: "right"
        text_size: self.size
        color: 0.85, 0.85, 0.85, 1

    TextInput:
        id: home_input
        hint_text: "مثال: Arsenal"
        multiline: False
        size_hint_y: None
        height: dp(48)
        font_size: "16sp"
        padding: dp(12), dp(12)
        write_tab: False

    Label:
        text: "الفريق الضيف"
        size_hint_y: None
        height: dp(22)
        font_size: "13sp"
        halign: "right"
        text_size: self.size
        color: 0.85, 0.85, 0.85, 1

    TextInput:
        id: away_input
        hint_text: "مثال: Chelsea"
        multiline: False
        size_hint_y: None
        height: dp(48)
        font_size: "16sp"
        padding: dp(12), dp(12)
        write_tab: False

    Button:
        id: predict_btn
        text: "توقّع"
        size_hint_y: None
        height: dp(52)
        font_size: "18sp"
        bold: True
        disabled: root.busy
        background_color: (0.15, 0.55, 0.35, 1) if not root.busy else (0.3, 0.3, 0.3, 1)
        on_press: root.on_predict()

    ScrollView:
        bar_width: dp(6)
        do_scroll_x: False

        Label:
            id: result_label
            text: root.result_text
            text_size: self.width, None
            size_hint_y: None
            height: max(self.texture_size[1], dp(120))
            halign: "left"
            valign: "top"
            padding: dp(10), dp(10)
            font_size: "15sp"
            color: 0.95, 0.95, 0.95, 1
"""


def _format_prediction(pred) -> str:
    """نفس أسلوب العرض تقريبًا في predict.py."""
    d = pred.as_dict()
    lines = [
        f"المباراة : {d['home_team']}  vs  {d['away_team']}",
        "",
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
        "",
        f"H2H      : {d['h2h_summary']}",
        (
            f"متوقع    : {d['expected_home_goals']:.2f} - {d['expected_away_goals']:.2f} "
            f"| goal={d['goal_score']:+.2f} | form={d['form_score']:+.2f} | h2h={d['h2h_score']:+.2f}"
        ),
        "",
        (
            f"احتمال   : فوز المضيف {d['prob_home']:.0%} | "
            f"تعادل {d['prob_draw']:.0%} | "
            f"فوز الضيف {d['prob_away']:.0%}"
        ),
        f"التوقع   : {d['result_label']}  (أعلى احتمال {d['confidence']:.0%})",
        f"السبب    : {d['reason']}",
    ]
    return "\n".join(lines)


def _run_predict(home_name: str, away_name: str) -> str:
    """
    نفس مسار predict.py:
      list_known_teams → find_team → predict_match
    """
    from src.predictor import find_team, list_known_teams, predict_match

    teams = list_known_teams()
    home = find_team(home_name, teams)
    away = find_team(away_name, teams)
    pred = predict_match(home, away)
    return _format_prediction(pred)


class PredictScreen(BoxLayout):
    result_text = StringProperty(
        "النتيجة ستظهر هنا بعد الضغط على «توقّع».\n"
        "تأكد أن البيانات محدّثة:\n"
        "  python main.py update"
    )
    busy = BooleanProperty(False)

    def on_predict(self) -> None:
        if self.busy:
            return

        home = (self.ids.home_input.text or "").strip()
        away = (self.ids.away_input.text or "").strip()

        if not home or not away:
            self.result_text = "أدخل اسم الفريق المضيف والضيف."
            return
        if home.lower() == away.lower():
            self.result_text = "لا يمكن توقع مباراة بين نفس الفريق."
            return

        self.busy = True
        self.result_text = "جارٍ التوقع..."

        def worker() -> None:
            try:
                text = _run_predict(home, away)
            except Exception as exc:  # noqa: BLE001 — عرض الخطأ في الواجهة
                text = f"فشل التوقع:\n{exc}"

            def apply(_dt) -> None:
                self.result_text = text
                self.busy = False

            Clock.schedule_once(apply, 0)

        threading.Thread(target=worker, daemon=True).start()


class FootballApp(App):
    title = "Football Predictor"

    def build(self):
        self.theme_cls = None  # لا نستخدم KivyMD
        Builder.load_string(KV)
        root = PredictScreen()
        # خلفية داكنة بسيطة عبر canvas على الجذر
        from kivy.graphics import Color, Rectangle

        with root.canvas.before:
            Color(0.12, 0.12, 0.14, 1)
            bg = Rectangle(pos=root.pos, size=root.size)

        def _sync_bg(*_args):
            bg.pos = root.pos
            bg.size = root.size

        root.bind(pos=_sync_bg, size=_sync_bg)
        return root


if __name__ == "__main__":
    FootballApp().run()
