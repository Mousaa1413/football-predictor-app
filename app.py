#!/usr/bin/env python3
"""
Modern Kivy football predictor app (logic layer).

Separation of concerns:
  - ui.kv     → layout / styles (KV language)
  - theme.py  → colors and pure UI helpers
  - app.py    → widgets, screens, prediction wiring

Prediction engine: src.predictor (predict.py unchanged).
UI language: English.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config  # noqa: F401  — يحمّل .env

from theme import (  # visual tokens for UI logic
    PLACEHOLDER_HOME,
    PLACEHOLDER_AWAY,
    EMPTY_TEAMS_MSG,
    RESULT_LABEL_EN,
    _AVATAR_SKIP_WORDS,
    C_BG, C_BG_MID, C_BG_TOP,
    C_SURFACE, C_SURFACE_SOLID,
    C_CARD, C_CARD_SOLID, C_CARD_ALT, C_ELEVATED,
    C_BORDER, C_BORDER_SOFT,
    C_ACCENT, C_ACCENT_DIM, C_ACCENT_SOFT,
    C_GLOW_TEAL, C_GLOW_BLUE,
    C_WIN, C_DRAW, C_LOSS, C_HOME, C_AWAY,
    C_TEXT, C_MUTED, C_HINT, C_DANGER, C_OK, C_SHADOW,
    is_team_placeholder,
    team_color,
    team_initials,
)

from kivy.animation import Animation
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import (
    BooleanProperty,
    ListProperty,
    NumericProperty,
    StringProperty,
)
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import FadeTransition, Screen
from kivy.uix.spinner import Spinner, SpinnerOption
from kivy.uix.widget import Widget

Window.clearcolor = C_BG

# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------
class TeamAvatar(FloatLayout):
    """أيقونة دائرية ملونة بأحرف الفريق (ثابتة لكل اسم)."""

    team_name = StringProperty("")
    avatar_size = NumericProperty(dp(40))
    initials = StringProperty("?")
    bg_color = ListProperty(list(C_HINT))
    ring_color = ListProperty([0.12, 0.84, 0.58, 0.22])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.bind(team_name=self._sync_identity, avatar_size=self._sync_size)
        self._sync_size()
        self._sync_identity()

    def _sync_size(self, *_args) -> None:
        s = float(self.avatar_size)
        self.width = s
        self.height = s

    def _sync_identity(self, *_args) -> None:
        name = self.team_name or ""
        self.initials = team_initials(name)
        color = team_color(name)
        self.bg_color = list(color)
        # حلقة بلون الفريق بشفافية
        self.ring_color = [color[0], color[1], color[2], 0.35]


class TeamSpinnerOption(SpinnerOption):
    """خيار داخل القائمة المنسدلة مع أيقونة دائرية."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.halign = "left"
        self.valign = "middle"
        self.padding = [dp(52), 0, dp(12), 0]
        self._avatar = TeamAvatar(avatar_size=dp(32))
        self.add_widget(self._avatar)
        self.bind(pos=self._layout_avatar, size=self._layout_avatar, text=self._update_avatar)
        self._update_avatar()

    def _update_avatar(self, *_args) -> None:
        self._avatar.team_name = self.text or ""
        self._layout_avatar()

    def _layout_avatar(self, *_args) -> None:
        size = float(self._avatar.avatar_size)
        self._avatar.pos = (self.x + dp(12), self.y + (self.height - size) / 2.0)


class TeamSpinner(Spinner):
    """قائمة منسدلة للفرق بثيم التطبيق."""

    def _create_dropdown(self, *largs):
        super()._create_dropdown(*largs)
        dropdown = getattr(self, "_dropdown", None)
        if dropdown is None or getattr(dropdown, "_fp_styled", False):
            return
        dropdown._fp_styled = True
        dropdown.container.spacing = dp(0)
        with dropdown.canvas.before:
            Color(*C_SHADOW)
            dropdown._sh = RoundedRectangle(radius=[dp(16)])
            Color(*C_SURFACE_SOLID)
            dropdown._bg_rect = RoundedRectangle(radius=[dp(16)])
            Color(*C_BORDER)
            dropdown._bd = Line(width=1)

        def _sync(*_a):
            if getattr(dropdown, "_bg_rect", None) is not None:
                dropdown._sh.pos = (dropdown.x, dropdown.y - dp(3))
                dropdown._sh.size = dropdown.size
                dropdown._bg_rect.pos = dropdown.pos
                dropdown._bg_rect.size = dropdown.size
                dropdown._bd.rounded_rectangle = (
                    dropdown.x,
                    dropdown.y,
                    dropdown.width,
                    dropdown.height,
                    dp(16),
                )

        dropdown.bind(pos=_sync, size=_sync)
        _sync()


class PrimaryButton(ButtonBehavior, FloatLayout):
    text = StringProperty("OK")
    disabled = BooleanProperty(False)


class PredictButton(ButtonBehavior, FloatLayout):
    """زر التوقع البارز — لون emerald قوي + تغذية راجعة عند الضغط."""

    text = StringProperty("Predict")
    disabled = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(state=self._on_state_change, disabled=self._on_disabled)

    def _on_disabled(self, *_args) -> None:
        if self.disabled:
            Animation.cancel_all(self, "opacity")
            self.opacity = 0.55
        else:
            Animation(opacity=1.0, d=0.15, t="out_quad").start(self)

    def _on_state_change(self, *_args) -> None:
        if self.disabled:
            return
        # تكبير/تصغير خفيف + وميض شفافية عند الضغط
        Animation.cancel_all(self, "opacity")
        if self.state == "down":
            Animation(opacity=0.92, d=0.06, t="out_quad").start(self)
        else:
            Animation(opacity=1.0, d=0.12, t="out_quad").start(self)


class GhostButton(ButtonBehavior, FloatLayout):
    text = StringProperty("")


class NavItem(ButtonBehavior, BoxLayout):
    icon = StringProperty("")
    label = StringProperty("")
    active = BooleanProperty(False)


class ProbBar(BoxLayout):
    """شريط تقدم لنسبة احتمال واحدة مع حركة سلسة."""

    side_label = StringProperty("")
    bar_color = ListProperty(list(C_WIN))
    value = NumericProperty(0.0)
    display_value = NumericProperty(0.0)
    pct_text = StringProperty("0%")

    def on_value(self, _instance, val: float) -> None:
        target = max(0.0, min(1.0, float(val or 0.0)))
        Animation.cancel_all(self, "display_value")
        Animation(display_value=target, d=0.55, t="out_cubic").start(self)


class ProbStack(BoxLayout):
    """شريط مكدّس واحد يعرض فوز/تعادل/خسارة معًا."""

    p_home = NumericProperty(0.0)
    p_draw = NumericProperty(0.0)
    p_away = NumericProperty(0.0)
    d_home = NumericProperty(0.0)
    d_draw = NumericProperty(0.0)
    d_away = NumericProperty(0.0)
    home_txt = StringProperty("—")
    draw_txt = StringProperty("—")
    away_txt = StringProperty("—")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._track = None
        self._seg_h = None
        self._seg_d = None
        self._seg_a = None
        self._col_h = None
        self._col_d = None
        self._col_a = None
        self._bg = None
        Clock.schedule_once(self._init_canvas, 0)

    def _init_canvas(self, *_args) -> None:
        track = self.ids.get("stack_track") if self.ids else None
        if track is None:
            return
        self._track = track
        with track.canvas.after:
            Color(0.06, 0.07, 0.10, 1)
            self._bg = RoundedRectangle(radius=[dp(8)])
            self._col_h = Color(*C_WIN)
            self._seg_h = RoundedRectangle(radius=[dp(8), 0, 0, dp(8)])
            self._col_d = Color(*C_DRAW)
            self._seg_d = Rectangle()
            self._col_a = Color(*C_LOSS)
            self._seg_a = RoundedRectangle(radius=[0, dp(8), dp(8), 0])
        track.bind(pos=self._redraw, size=self._redraw)
        self.bind(
            d_home=self._redraw,
            d_draw=self._redraw,
            d_away=self._redraw,
        )
        self._redraw()

    def on_p_home(self, *_args) -> None:
        self._animate_stack()

    def on_p_draw(self, *_args) -> None:
        self._animate_stack()

    def on_p_away(self, *_args) -> None:
        self._animate_stack()

    def _animate_stack(self) -> None:
        Animation.cancel_all(self, "d_home", "d_draw", "d_away")
        Animation(
            d_home=max(0.0, float(self.p_home or 0.0)),
            d_draw=max(0.0, float(self.p_draw or 0.0)),
            d_away=max(0.0, float(self.p_away or 0.0)),
            d=0.55,
            t="out_cubic",
        ).start(self)

    def _redraw(self, *_args) -> None:
        track = self._track
        if track is None or self._bg is None:
            return
        x, y = track.pos
        w, h = track.size
        if w <= 0 or h <= 0:
            return
        self._bg.pos = (x, y)
        self._bg.size = (w, h)

        # طبّع النسب لو المجموع > 0
        total = self.d_home + self.d_draw + self.d_away
        if total <= 1e-9:
            wh = wd = wa = 0.0
        else:
            wh = w * (self.d_home / total)
            wd = w * (self.d_draw / total)
            wa = w * (self.d_away / total)

        gap = dp(2) if (wh > 0 and wd > 0) or (wd > 0 and wa > 0) or (wh > 0 and wa > 0) else 0
        # وزّع الفجوات
        segs = [(wh, self._seg_h), (wd, self._seg_d), (wa, self._seg_a)]
        active = sum(1 for width, _ in segs if width > 0.5)
        if active > 1:
            shrink = gap * (active - 1) / active
            wh = max(0.0, wh - shrink) if wh > 0.5 else 0.0
            wd = max(0.0, wd - shrink) if wd > 0.5 else 0.0
            wa = max(0.0, wa - shrink) if wa > 0.5 else 0.0

        cursor = x
        for width, seg in ((wh, self._seg_h), (wd, self._seg_d), (wa, self._seg_a)):
            if width <= 0.5:
                seg.size = (0, 0)
                seg.pos = (cursor, y)
                continue
            seg.pos = (cursor, y)
            seg.size = (width, h)
            cursor += width + (gap if active > 1 else 0)


class ResultBadge(FloatLayout):
    text = StringProperty("—")
    badge_color = ListProperty(list(C_MUTED))
    soft_color = ListProperty([0.58, 0.62, 0.70, 0.16])

    def on_badge_color(self, *_args) -> None:
        c = self.badge_color
        if len(c) >= 3:
            self.soft_color = [c[0], c[1], c[2], 0.16]


class MatchCard(BoxLayout):
    """بطاقة مباراة حديثة في الجدول مع أشرطة احتمالات."""

    def __init__(
        self,
        league: str = "",
        date: str = "",
        home: str = "",
        away: str = "",
        result_label: str = "",
        probs: str = "",
        reason: str = "",
        prob_home: float = 0.0,
        prob_draw: float = 0.0,
        prob_away: float = 0.0,
        **kwargs,
    ):
        super().__init__(orientation="vertical", size_hint_y=None, **kwargs)
        self.padding = [dp(18), dp(18), dp(18), dp(18)]
        self.spacing = dp(12)
        with self.canvas.before:
            Color(*C_SHADOW)
            self._sh = RoundedRectangle(radius=[dp(22)])
            Color(*C_CARD_SOLID)
            self._bg = RoundedRectangle(radius=[dp(20)])
            Color(*C_BORDER_SOFT)
            self._bd = Line(width=1.1)
        self.bind(pos=self._sync, size=self._sync)

        # header chips
        head = BoxLayout(size_hint_y=None, height=dp(28), spacing=dp(10))
        league_chip = Label(
            text=league or "—",
            size_hint=(None, None),
            height=dp(26),
            font_size="12sp",
            bold=True,
            color=C_ACCENT,
            halign="center",
            valign="middle",
            padding=(dp(10), 0),
        )
        league_chip.bind(
            texture_size=lambda *_: setattr(
                league_chip, "width", max(league_chip.texture_size[0] + dp(20), dp(40))
            )
        )
        with league_chip.canvas.before:
            Color(*C_ACCENT_SOFT)
            league_chip._bg = RoundedRectangle(radius=[dp(10)])
        league_chip.bind(
            pos=lambda *_: setattr(league_chip._bg, "pos", league_chip.pos),
            size=lambda *_: setattr(league_chip._bg, "size", league_chip.size),
        )
        date_lbl = Label(
            text=str(date),
            font_size="12sp",
            color=C_MUTED,
            halign="left",
            valign="middle",
        )
        date_lbl.bind(size=lambda *_: setattr(date_lbl, "text_size", date_lbl.size))
        head.add_widget(league_chip)
        head.add_widget(date_lbl)

        # teams face-off
        face = BoxLayout(size_hint_y=None, height=dp(70), spacing=dp(6))

        def team_col(name: str) -> BoxLayout:
            col = BoxLayout(orientation="vertical", spacing=dp(4))
            av = TeamAvatar(team_name=name, avatar_size=dp(42))
            av.pos_hint = {"center_x": 0.5}
            nm = Label(
                text=name,
                size_hint_y=None,
                height=dp(20),
                font_size="12sp",
                bold=True,
                color=C_TEXT,
                halign="center",
                valign="middle",
                shorten=True,
                shorten_from="right",
            )
            nm.bind(size=lambda *_: setattr(nm, "text_size", nm.size))
            col.add_widget(av)
            col.add_widget(nm)
            return col

        vs = Label(
            text="VS",
            size_hint_x=None,
            width=dp(36),
            bold=True,
            font_size="12sp",
            color=C_ACCENT,
            halign="center",
            valign="middle",
        )
        vs.bind(size=lambda *_: setattr(vs, "text_size", vs.size))

        face.add_widget(team_col(home))
        face.add_widget(vs)
        face.add_widget(team_col(away))

        self.add_widget(head)
        self.add_widget(face)

        if result_label:
            res = Label(
                text=result_label,
                size_hint_y=None,
                height=dp(30),
                font_size="14sp",
                bold=True,
                color=_badge_color_for(result_label),
                halign="center",
                valign="middle",
            )
            res.bind(size=lambda *_: setattr(res, "text_size", res.size))
            with res.canvas.before:
                c = _badge_color_for(result_label)
                Color(c[0], c[1], c[2], 0.14)
                res._bg = RoundedRectangle(radius=[dp(12)])
            res.bind(
                pos=lambda *_: setattr(res._bg, "pos", (res.x + dp(20), res.y)),
                size=lambda *_: setattr(
                    res._bg, "size", (max(res.width - dp(40), dp(40)), res.height)
                ),
            )
            self.add_widget(res)

        has_probs = (prob_home + prob_draw + prob_away) > 0
        if has_probs:
            # شريط مكدّس + 3 أشرطة تقدم مصغّرة
            stack = ProbStack(
                p_home=float(prob_home),
                p_draw=float(prob_draw),
                p_away=float(prob_away),
                home_txt=f"{prob_home:.0%}",
                draw_txt=f"{prob_draw:.0%}",
                away_txt=f"{prob_away:.0%}",
            )
            self.add_widget(stack)
            for label, color, val in (
                ("Win", C_WIN, prob_home),
                ("Draw", C_DRAW, prob_draw),
                ("Loss", C_LOSS, prob_away),
            ):
                bar = ProbBar(
                    side_label=label,
                    bar_color=list(color),
                    value=float(val),
                    pct_text=f"{val:.0%}",
                )
                bar.height = dp(54)
                self.add_widget(bar)
        elif probs:
            pr = Label(
                text=probs,
                size_hint_y=None,
                height=dp(20),
                font_size="13sp",
                color=C_MUTED,
                halign="center",
                valign="middle",
            )
            pr.bind(size=lambda *_: setattr(pr, "text_size", pr.size))
            self.add_widget(pr)

        if reason:
            rs = Label(
                text=reason,
                size_hint_y=None,
                height=dp(36),
                font_size="12sp",
                color=C_HINT,
                halign="left",
                valign="top",
            )
            rs.bind(
                size=lambda *_: setattr(rs, "text_size", (rs.width, None)),
                texture_size=lambda *_: setattr(
                    rs, "height", max(rs.texture_size[1], dp(20))
                ),
            )
            self.add_widget(rs)

        # ارتفاع ديناميكي حسب المحتوى
        self.bind(minimum_height=self.setter("height"))
        self.height = self.minimum_height

    def _sync(self, *_args):
        self._sh.pos = (self.x + dp(2), self.y - dp(4))
        self._sh.size = (self.width - dp(4), self.height)
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._bd.rounded_rectangle = (
            self.x,
            self.y,
            self.width,
            self.height,
            dp(20),
        )


class TeamRow(ButtonBehavior, BoxLayout):
    def __init__(self, name: str, on_pick=None, **kwargs):
        super().__init__(
            orientation="horizontal", size_hint_y=None, height=dp(62), **kwargs
        )
        self.padding = [dp(16), dp(10)]
        self.spacing = dp(14)
        self._name = name
        self._on_pick = on_pick
        with self.canvas.before:
            Color(*C_SHADOW)
            self._sh = RoundedRectangle(radius=[dp(18)])
            Color(*C_CARD_SOLID)
            self._bg = RoundedRectangle(radius=[dp(16)])
            Color(*C_BORDER_SOFT)
            self._bd = Line(width=1.1)
        self.bind(pos=self._sync, size=self._sync)

        avatar = TeamAvatar(team_name=name, avatar_size=dp(40))
        lab = Label(
            text=name,
            color=C_TEXT,
            font_size="15sp",
            bold=True,
            halign="left",
            valign="middle",
        )
        lab.bind(size=lambda *_: setattr(lab, "text_size", lab.size))
        chevron = Label(
            text="›",
            size_hint_x=None,
            width=dp(20),
            color=C_HINT,
            font_size="22sp",
            halign="center",
            valign="middle",
        )
        chevron.bind(size=lambda *_: setattr(chevron, "text_size", chevron.size))
        self.add_widget(avatar)
        self.add_widget(lab)
        self.add_widget(chevron)

    def _sync(self, *_args):
        self._sh.pos = (self.x + dp(1), self.y - dp(2))
        self._sh.size = (self.width - dp(2), self.height)
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._bd.rounded_rectangle = (
            self.x,
            self.y,
            self.width,
            self.height,
            dp(16),
        )

    def on_release(self):
        if self._on_pick:
            self._on_pick(self._name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _run_bg(fn, on_ok, on_err=None) -> None:
    def worker():
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
            Clock.schedule_once(lambda _dt: (on_err or on_ok)(err), 0)
            return
        Clock.schedule_once(lambda _dt: on_ok(result), 0)

    threading.Thread(target=worker, daemon=True).start()


def _result_label_en(label: str) -> str:
    """Translate engine result label to English for UI display."""
    if not label:
        return "—"
    return RESULT_LABEL_EN.get(label, label)


def _badge_color_for(result_label: str) -> list[float]:
    """
    Prediction colors (home perspective):
      Home win → green
      Draw     → yellow
      Away win → red
    """
    label = _result_label_en(result_label or "")
    s = label.lower()
    raw = result_label or ""
    if "خطأ" in raw or "error" in s:
        return list(C_DANGER)
    if "تعادل" in raw or "draw" in s:
        return list(C_DRAW)
    if "ضيف" in raw or "away" in s:
        return list(C_LOSS)
    if (
        "مضيف" in raw
        or "أرض" in raw
        or "home" in s
        or "فوز" in raw
        or "win" in s
    ):
        return list(C_WIN)
    return list(C_MUTED)


def _h2h_summary_en(d: dict) -> str:
    if not d.get("h2h_available"):
        return "No prior head-to-head matches in database"
    n = int(d.get("h2h_matches") or 0)
    hp = int(d.get("h2h_home_points") or 0)
    ap = int(d.get("h2h_away_points") or 0)
    home = d.get("home_team", "Home")
    away = d.get("away_team", "Away")
    return f"{n} meetings | {home}: {hp} pts | {away}: {ap} pts"


def _format_details(d: dict) -> str:
    lines = [
        f"Home : ATK {d['home_attack']:.2f}  ·  DEF {d['home_defense']:.2f}  ·  "
        f"Form {d['home_points']}/{d['home_max_points']} ({d['home_form_string']})",
        f"Away : ATK {d['away_attack']:.2f}  ·  DEF {d['away_defense']:.2f}  ·  "
        f"Form {d['away_points']}/{d['away_max_points']} ({d['away_form_string']})",
        f"H2H  : {_h2h_summary_en(d)}",
        (
            f"xG   : {d['expected_home_goals']:.2f} – {d['expected_away_goals']:.2f}"
            f"   |  goal={d['goal_score']:+.2f}  form={d['form_score']:+.2f}  h2h={d['h2h_score']:+.2f}"
        ),
    ]
    return "\n".join(lines)


def _format_reason_en(d: dict) -> str:
    """Build an English reason from prediction fields (UI-only)."""
    home = d.get("home_team", "Home")
    away = d.get("away_team", "Away")
    egh = float(d.get("expected_home_goals", 0.0))
    ega = float(d.get("expected_away_goals", 0.0))
    goal = float(d.get("goal_score", 0.0))
    form = float(d.get("form_score", 0.0))
    h2h = float(d.get("h2h_score", 0.0))
    parts: list[str] = []

    if abs(goal) < 0.15:
        parts.append(f"Expected goals are close ({egh:.2f}-{ega:.2f})")
    elif goal > 0:
        parts.append(f"Home attack/defense edge (xG {egh:.2f}-{ega:.2f})")
    else:
        parts.append(f"Away attack/defense edge (xG {egh:.2f}-{ega:.2f})")

    hp = d.get("home_points", 0)
    hmax = d.get("home_max_points", 0)
    ap = d.get("away_points", 0)
    amax = d.get("away_max_points", 0)
    hf = d.get("home_form_string", "")
    af = d.get("away_form_string", "")
    if abs(form) < 0.08:
        parts.append(f"Similar form ({hp}/{hmax} vs {ap}/{amax})")
    elif form > 0:
        parts.append(f"Better home form {hf} ({hp}/{hmax})")
    else:
        parts.append(f"Better away form {af} ({ap}/{amax})")

    h2h_txt = _h2h_summary_en(d)
    if not d.get("h2h_available"):
        parts.append("Not enough head-to-head data")
    elif abs(h2h) < 0.08:
        parts.append(f"H2H roughly even ({h2h_txt})")
    elif h2h > 0:
        parts.append(f"H2H leans toward {home} ({h2h_txt})")
    else:
        parts.append(f"H2H leans toward {away} ({h2h_txt})")

    label = _result_label_en(str(d.get("result_label", "")))
    if label == "Home Win":
        tail = f"So the lean is a win for {home}."
    elif label == "Away Win":
        tail = f"So the lean is a win for {away}."
    elif label == "Draw":
        tail = "So the closest outcome is a draw."
    else:
        tail = f"Predicted outcome: {label}."

    return "; ".join(parts) + ". " + tail


def _predict_dict(home_name: str, away_name: str) -> dict:
    """نفس مسار predict.py: list_known_teams → find_team → predict_match."""
    from src.predictor import find_team, list_known_teams, predict_match

    teams = list_known_teams()
    home = find_team(home_name, teams)
    away = find_team(away_name, teams)
    return predict_match(home, away).as_dict()


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------
class PredictScreen(Screen):
    home_text = StringProperty(PLACEHOLDER_HOME)
    away_text = StringProperty(PLACEHOLDER_AWAY)
    spinner_values = ListProperty([EMPTY_TEAMS_MSG])
    team_names = ListProperty([])
    busy = BooleanProperty(False)
    has_result = BooleanProperty(False)
    status_line = StringProperty("")
    match_title = StringProperty("Pick two teams, then tap Predict")
    result_home = StringProperty("")
    result_away = StringProperty("")
    result_home_short = StringProperty("Home")
    result_away_short = StringProperty("Away")
    result_badge = StringProperty("—")
    confidence_text = StringProperty("Probabilities will appear here")
    score_text = StringProperty("– : –")
    badge_color = ListProperty(list(C_MUTED))
    prob_home = NumericProperty(0.0)
    prob_draw = NumericProperty(0.0)
    prob_away = NumericProperty(0.0)
    prob_home_txt = StringProperty("—")
    prob_draw_txt = StringProperty("—")
    prob_away_txt = StringProperty("—")
    detail_text = StringProperty(
        "Predictions use recent form, attack/defense averages, and head-to-head results."
    )
    reason_text = StringProperty("—")

    def on_kv_post(self, base_widget) -> None:
        Clock.schedule_once(lambda _dt: self.reload_teams(), 0)

    def reload_teams(self) -> None:
        self.status_line = "Loading teams from database..."

        def job():
            from src.predictor import list_known_teams

            return list_known_teams()

        def ok(teams) -> None:
            if isinstance(teams, str):
                self.team_names = []
                self.spinner_values = [EMPTY_TEAMS_MSG]
                self.home_text = PLACEHOLDER_HOME
                self.away_text = PLACEHOLDER_AWAY
                self.status_line = f"Failed to load teams: {teams}"
                return

            names = [str(t) for t in teams if str(t).strip()]
            self.team_names = names
            if not names:
                self.spinner_values = [EMPTY_TEAMS_MSG]
                self.home_text = PLACEHOLDER_HOME
                self.away_text = PLACEHOLDER_AWAY
                self.status_line = "No teams in matches.db — update data from Status."
                return

            self.spinner_values = names
            if self.home_text not in names and self.home_text != PLACEHOLDER_HOME:
                self.home_text = PLACEHOLDER_HOME
            if self.away_text not in names and self.away_text != PLACEHOLDER_AWAY:
                self.away_text = PLACEHOLDER_AWAY
            if self.home_text not in self.spinner_values:
                self.ids.home_spinner.text = PLACEHOLDER_HOME
                self.home_text = PLACEHOLDER_HOME
            if self.away_text not in self.spinner_values:
                self.ids.away_spinner.text = PLACEHOLDER_AWAY
                self.away_text = PLACEHOLDER_AWAY
            self.status_line = f"{len(names)} teams ready"

        _run_bg(job, ok, ok)

    @staticmethod
    def _is_placeholder(value: str) -> bool:
        return is_team_placeholder(value)

    @staticmethod
    def _short_name(name: str, fallback: str = "") -> str:
        if is_team_placeholder(name):
            return fallback
        parts = [p for p in name.replace("-", " ").split() if p]
        core = [p for p in parts if p.upper().strip(".") not in _AVATAR_SKIP_WORDS]
        if not core:
            core = parts
        if not core:
            return fallback or name
        if len(core) == 1:
            return core[0][:14]
        return f"{core[0][:10]} {core[1][:1]}."

    def selected_home(self) -> str:
        return "" if self._is_placeholder(self.home_text) else self.home_text.strip()

    def selected_away(self) -> str:
        return "" if self._is_placeholder(self.away_text) else self.away_text.strip()

    def swap_teams(self) -> None:
        home, away = self.home_text, self.away_text
        if self._is_placeholder(home) and self._is_placeholder(away):
            return
        self.home_text = away if not self._is_placeholder(away) else PLACEHOLDER_HOME
        self.away_text = home if not self._is_placeholder(home) else PLACEHOLDER_AWAY

    def clear_inputs(self) -> None:
        self.home_text = PLACEHOLDER_HOME
        self.away_text = PLACEHOLDER_AWAY
        self.has_result = False
        self.status_line = ""
        self.match_title = "Pick two teams, then tap Predict"
        self.result_home = ""
        self.result_away = ""
        self.result_home_short = "Home"
        self.result_away_short = "Away"
        self.result_badge = "—"
        self.confidence_text = "Probabilities will appear here"
        self.score_text = "– : –"
        self.badge_color = list(C_MUTED)
        self.prob_home = self.prob_draw = self.prob_away = 0.0
        self.prob_home_txt = self.prob_draw_txt = self.prob_away_txt = "—"
        self.detail_text = (
            "Predictions use recent form, attack/defense averages, and head-to-head results."
        )
        self.reason_text = "—"

    def apply_team(self, name: str) -> None:
        name = (name or "").strip()
        if not name:
            return
        if self._is_placeholder(self.home_text):
            self.home_text = name
        elif self._is_placeholder(self.away_text):
            self.away_text = name
        else:
            self.home_text = name

    def _set_predict_btn_text(self, text: str) -> None:
        btn = self.ids.get("predict_btn")
        if btn is not None:
            btn.text = text

    def _on_predict_press(self) -> None:
        """تغذية راجعة فورية عند لمس الزر (قبل انتهاء الحساب)."""
        if self.busy:
            return
        # اللمسة البصرية الأساسية من PredictButton.state

    def on_predict(self) -> None:
        if self.busy:
            return
        home = self.selected_home()
        away = self.selected_away()
        if not home or not away:
            self.status_line = "Select both home and away teams."
            return
        if home.lower() == away.lower():
            self.status_line = "Cannot predict a match between the same team."
            return

        self.busy = True
        self._set_predict_btn_text("⏳  Predicting...")
        self.status_line = "Calculating prediction..."
        self.has_result = False

        def job():
            return _predict_dict(home, away)

        def ok(d: dict) -> None:
            if isinstance(d, str):
                self._fail(d)
                return
            self.result_home = d["home_team"]
            self.result_away = d["away_team"]
            self.result_home_short = self._short_name(d["home_team"], "Home")
            self.result_away_short = self._short_name(d["away_team"], "Away")
            self.match_title = f"{d['home_team']}   vs   {d['away_team']}"
            self.result_badge = _result_label_en(d["result_label"])
            self.badge_color = _badge_color_for(d["result_label"])
            self.confidence_text = f"Confidence  ·  {d['confidence']:.0%}"
            self.score_text = (
                f"{d['expected_home_goals']:.1f} : {d['expected_away_goals']:.1f}"
            )
            self.prob_home = float(d["prob_home"])
            self.prob_draw = float(d["prob_draw"])
            self.prob_away = float(d["prob_away"])
            self.prob_home_txt = f"{d['prob_home']:.0%}"
            self.prob_draw_txt = f"{d['prob_draw']:.0%}"
            self.prob_away_txt = f"{d['prob_away']:.0%}"
            self.detail_text = _format_details(d)
            self.reason_text = _format_reason_en(d)
            self.has_result = True
            self.status_line = "Prediction ready"
            self.busy = False
            self._set_predict_btn_text("⚡  Predict")

        def err(msg: str) -> None:
            self._fail(msg)

        _run_bg(job, ok, err)

    def _fail(self, msg: str) -> None:
        self._set_predict_btn_text("⚡  Predict")
        self.status_line = ""
        self.has_result = False
        self.result_home = self.selected_home()
        self.result_away = self.selected_away()
        self.result_home_short = self._short_name(self.result_home, "Home")
        self.result_away_short = self._short_name(self.result_away, "Away")
        self.match_title = "Prediction failed"
        self.result_badge = "Error"
        self.badge_color = list(C_DANGER)
        self.confidence_text = ""
        self.score_text = "– : –"
        self.detail_text = msg
        self.reason_text = "Check team names or update data from the Status tab."
        self.prob_home = self.prob_draw = self.prob_away = 0.0
        self.prob_home_txt = self.prob_draw_txt = self.prob_away_txt = "—"
        self.busy = False


class ScheduleScreen(Screen):
    busy = BooleanProperty(False)
    status_line = StringProperty("Tap Refresh to load fixtures")

    def on_enter(self, *_args) -> None:
        if not self.ids.list_box.children:
            self.load_schedule()

    def load_schedule(self) -> None:
        if self.busy:
            return
        self.busy = True
        self.status_line = "Loading schedule..."
        self.ids.list_box.clear_widgets()

        def job():
            from src.database import load_schedule_from_db
            from src.predictor import find_team, list_known_teams, predict_match

            schedule = load_schedule_from_db()
            if schedule is None or schedule.empty:
                return []

            teams = list_known_teams()
            rows = []
            for row in schedule.sort_values("date").itertuples(index=False):
                if len(rows) >= 12:
                    break
                item = {
                    "league": getattr(row, "league", ""),
                    "date": str(getattr(row, "date", "")),
                    "home": getattr(row, "home_team", ""),
                    "away": getattr(row, "away_team", ""),
                    "result_label": "",
                    "probs": "",
                    "reason": "",
                    "prob_home": 0.0,
                    "prob_draw": 0.0,
                    "prob_away": 0.0,
                }
                try:
                    h = find_team(item["home"], teams)
                    a = find_team(item["away"], teams)
                    d = predict_match(h, a).as_dict()
                    item["result_label"] = _result_label_en(d["result_label"])
                    item["prob_home"] = float(d["prob_home"])
                    item["prob_draw"] = float(d["prob_draw"])
                    item["prob_away"] = float(d["prob_away"])
                    item["reason"] = _format_reason_en(d)
                except Exception:
                    item["result_label"] = "No prediction"
                    item["probs"] = "Team missing from recent results"
                rows.append(item)
            return rows

        def ok(rows):
            self.busy = False
            box = self.ids.list_box
            box.clear_widgets()
            if isinstance(rows, str):
                self.status_line = f"Error: {rows}"
                return
            if not rows:
                self.status_line = "Schedule empty — update data from Status."
                empty = Label(
                    text="No upcoming matches stored locally.",
                    size_hint_y=None,
                    height=dp(48),
                    color=C_MUTED,
                    font_size="13sp",
                )
                box.add_widget(empty)
                return
            self.status_line = f"{len(rows)} matches"
            for item in rows:
                box.add_widget(MatchCard(**item))

        _run_bg(job, ok, ok)


class TeamsScreen(Screen):
    query = StringProperty("")
    count_text = StringProperty("")
    _all_teams: list[str]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._all_teams = []

    def on_enter(self, *_args) -> None:
        if not self._all_teams:
            self.load_teams()

    def load_teams(self) -> None:
        self.count_text = "Loading..."

        def job():
            from src.predictor import list_known_teams

            return list_known_teams()

        def ok(teams):
            if isinstance(teams, str):
                self.count_text = f"Error: {teams}"
                self._all_teams = []
                self._render([])
                return
            self._all_teams = list(teams)
            self.on_query(self.query)

        _run_bg(job, ok, ok)

    def on_query(self, text: str) -> None:
        self.query = text
        q = (text or "").strip().lower()
        if not q:
            filtered = self._all_teams
        else:
            filtered = [t for t in self._all_teams if q in t.lower()]
        self.count_text = f"{len(filtered)} / {len(self._all_teams)} teams"
        self._render(filtered)

    def _render(self, teams: list[str]) -> None:
        box = self.ids.teams_box
        box.clear_widgets()
        if not teams:
            box.add_widget(
                Label(
                    text="No results.",
                    size_hint_y=None,
                    height=dp(40),
                    color=C_MUTED,
                )
            )
            return

        app = App.get_running_app()

        def pick(name: str) -> None:
            root = app.root
            if root is None:
                return
            sm = root.ids.sm
            pred: PredictScreen = sm.get_screen("predict")
            pred.apply_team(name)
            root.switch_tab("predict")

        for name in teams:
            box.add_widget(TeamRow(name, on_pick=pick))


class StatusScreen(Screen):
    summary_text = StringProperty("Reading...")
    update_status = StringProperty("")
    busy = BooleanProperty(False)

    def on_enter(self, *_args) -> None:
        self.refresh_summary()

    def refresh_summary(self) -> None:
        def job():
            from src.database import db_summary

            lines = [db_summary(), ""]
            for label, path in [
                ("matches.csv", config.DATA_FILE),
                ("last_matches.csv", config.RECENT_DATA_FILE),
                ("schedule.csv", config.SCHEDULE_FILE),
                ("matches.db", config.DB_FILE),
            ]:
                if path.exists():
                    try:
                        size = path.stat().st_size
                        state = f"{size:,} bytes"
                    except OSError:
                        state = "present"
                else:
                    state = "missing"
                lines.append(f"• {label}: {state}")
            token_ok = bool(getattr(config, "API_TOKEN", "") or "")
            lines.append("")
            lines.append("• API token: " + ("set ✓" if token_ok else "not set ✗"))
            return "\n".join(lines)

        def ok(text):
            self.summary_text = text if isinstance(text, str) else str(text)

        _run_bg(job, ok, ok)

    def do_update(self) -> None:
        if self.busy:
            return
        self.busy = True
        self.update_status = "Updating from API (may take a minute)..."

        def job():
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
            return "Update complete.\n" + db_summary()

        def ok(text):
            self.busy = False
            self.update_status = text if isinstance(text, str) else str(text)
            self.refresh_summary()
            app = App.get_running_app()
            if app and app.root:
                try:
                    app.root.ids.sm.get_screen("predict").reload_teams()
                except Exception:
                    pass
                try:
                    app.root.ids.sm.get_screen("teams").load_teams()
                except Exception:
                    pass

        _run_bg(job, ok, ok)


class RootShell(BoxLayout):
    """الهيكل الرئيسي مع خلفية dark theme متدرجة وأنيقة."""

    current_tab = StringProperty("predict")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # شرائح التدرج + توهج محيطي
        with self.canvas.before:
            self._c_top = Color(*C_BG_TOP)
            self._r_top = Rectangle()
            self._c_mid = Color(*C_BG_MID)
            self._r_mid = Rectangle()
            self._c_bot = Color(*C_BG)
            self._r_bot = Rectangle()
            self._c_glow_b = Color(*C_GLOW_BLUE)
            self._e_glow_b = Ellipse()
            self._c_glow_t = Color(*C_GLOW_TEAL)
            self._e_glow_t = Ellipse()
        self.bind(pos=self._sync_bg, size=self._sync_bg)
        Clock.schedule_once(lambda _dt: self._sync_bg(), 0)

    def _sync_bg(self, *_args) -> None:
        x, y = self.pos
        w, h = self.size
        if w <= 0 or h <= 0:
            return
        # تدرج عمودي ناعم: أعلى أفتح قليلًا → قاعدة أعمق
        self._r_top.pos = (x, y + h * 0.52)
        self._r_top.size = (w, h * 0.48)
        self._r_mid.pos = (x, y + h * 0.22)
        self._r_mid.size = (w, h * 0.40)
        self._r_bot.pos = (x, y)
        self._r_bot.size = (w, h * 0.35)
        # توهجات محيطية (عمق بصري)
        self._e_glow_b.pos = (x + w * 0.30, y + h - dp(200))
        self._e_glow_b.size = (w * 0.90, dp(240))
        self._e_glow_t.pos = (x - w * 0.28, y + h * 0.12)
        self._e_glow_t.size = (w * 0.80, dp(280))

    def switch_tab(self, name: str) -> None:
        self.current_tab = name
        self.ids.sm.current = name


class FootballApp(App):
    """App entry. UI layout is declared in ui.kv (KV language)."""

    title = "Football Predictor"

    def load_kv(self, filename=None):
        # Disable Kivy auto-KV (FootballApp → football.kv); we load ui.kv explicitly.
        return False

    def build(self):
        kv_path = ROOT / "ui.kv"
        if not kv_path.exists():
            raise FileNotFoundError(f"Missing UI file: {kv_path}")
        Builder.load_file(str(kv_path))
        return RootShell()


if __name__ == "__main__":
    FootballApp().run()
