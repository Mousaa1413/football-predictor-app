"""
محرك توقع بسيط لنتائج المباريات.

يعتمد على:
  1) الهجوم/الدفاع من آخر N مباريات
       EGH = (home_attack + away_defense) / 2
       EGA = (away_attack + home_defense) / 2

  2) فورم النقاط من آخر N مباريات
       فوز=3، تعادل=1، خسارة=0

  3) المواجهات المباشرة السابقة (H2H) إن وُجدت
       نفس نظام النقاط من وجهة نظر المضيف في المباراة الحالية

الدرجة النهائية:
  score = (EGH - EGA)
        + FORM_WEIGHT * (home_points_ratio - away_points_ratio)
        + H2H_WEIGHT  * h2h_score   # 0 إذا لا توجد مواجهات
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

import config
from src.data_loader import load_matches_csv
from src.database import load_matches_from_db


def load_recent_matches() -> pd.DataFrame:
    """النتائج الحديثة من SQLite (للفورم والهجوم/الدفاع)."""
    return load_matches_from_db()


def load_history_matches() -> pd.DataFrame:
    """
    تاريخ أوسع للمواجهات المباشرة.
    يفضّل data/matches.csv الكامل إن وُجد، وإلا يرجع لـ SQLite.
    """
    if config.DATA_FILE.exists():
        try:
            df = load_matches_csv(config.DATA_FILE)
            # توحيد اسم عمود الدوري مع جدول SQLite إن لزم
            if "league" not in df.columns and "competition" in df.columns:
                df = df.rename(columns={"competition": "league"})
            return df
        except Exception:
            pass
    return load_matches_from_db()


@dataclass
class TeamForm:
    team: str
    matches_used: int
    attack: float
    defense: float
    goals_scored_total: int
    goals_conceded_total: int
    points: int
    max_points: int
    points_ratio: float
    form_string: str
    results: list[str]


@dataclass
class HeadToHead:
    home_team: str
    away_team: str
    matches_used: int
    home_points: int
    away_points: int
    max_points: int
    home_points_ratio: float
    away_points_ratio: float
    h2h_score: float  # home_ratio - away_ratio  (من منظور مضيف المباراة الحالية)
    form_string: str  # نتائج المضيف الحالي: W-D-L...
    summary: str
    available: bool = False
    details: list[dict] = field(default_factory=list)


@dataclass
class MatchPrediction:
    home_team: str
    away_team: str
    home_form: TeamForm
    away_form: TeamForm
    h2h: HeadToHead
    expected_home_goals: float
    expected_away_goals: float
    goal_score: float
    form_score: float
    h2h_score: float
    final_score: float
    result: int
    result_label: str
    confidence: float
    prob_home: float
    prob_draw: float
    prob_away: float
    reason: str

    def as_dict(self) -> dict:
        return {
            "home_team": self.home_team,
            "away_team": self.away_team,
            "home_attack": round(self.home_form.attack, 3),
            "home_defense": round(self.home_form.defense, 3),
            "home_points": self.home_form.points,
            "home_max_points": self.home_form.max_points,
            "home_form_string": self.home_form.form_string,
            "away_attack": round(self.away_form.attack, 3),
            "away_defense": round(self.away_form.defense, 3),
            "away_points": self.away_form.points,
            "away_max_points": self.away_form.max_points,
            "away_form_string": self.away_form.form_string,
            "h2h_available": self.h2h.available,
            "h2h_matches": self.h2h.matches_used,
            "h2h_home_points": self.h2h.home_points,
            "h2h_away_points": self.h2h.away_points,
            "h2h_form_string": self.h2h.form_string,
            "h2h_summary": self.h2h.summary,
            "expected_home_goals": round(self.expected_home_goals, 3),
            "expected_away_goals": round(self.expected_away_goals, 3),
            "goal_score": round(self.goal_score, 3),
            "form_score": round(self.form_score, 3),
            "h2h_score": round(self.h2h_score, 3),
            "final_score": round(self.final_score, 3),
            "result": self.result,
            "result_label": self.result_label,
            "confidence": round(self.confidence, 3),
            "prob_home": round(self.prob_home, 3),
            "prob_draw": round(self.prob_draw, 3),
            "prob_away": round(self.prob_away, 3),
            "reason": self.reason,
            "home_matches_used": self.home_form.matches_used,
            "away_matches_used": self.away_form.matches_used,
        }


def _team_match_mask(df: pd.DataFrame, team: str) -> pd.Series:
    return (df["home_team"] == team) | (df["away_team"] == team)


def _points_for_team_row(row, team: str) -> tuple[int, int, int, str]:
    """(scored, conceded, points, W/D/L) لفريق داخل صف مباراة."""
    if row.home_team == team:
        scored = int(row.home_goals)
        conceded = int(row.away_goals)
    else:
        scored = int(row.away_goals)
        conceded = int(row.home_goals)

    if scored > conceded:
        return scored, conceded, config.POINTS_WIN, "W"
    if scored < conceded:
        return scored, conceded, config.POINTS_LOSS, "L"
    return scored, conceded, config.POINTS_DRAW, "D"


def compute_team_form(
    matches: pd.DataFrame,
    team: str,
    last_n: int | None = None,
) -> TeamForm:
    """متوسط الهجوم/الدفاع + فورم النقاط من آخر last_n مباريات."""
    last_n = last_n if last_n is not None else config.FORM_LAST_N
    team_matches = (
        matches.loc[_team_match_mask(matches, team)]
        .sort_values("date")
        .tail(last_n)
    )

    if team_matches.empty:
        raise ValueError(
            f"لا توجد مباريات سابقة للفريق: {team}. "
            "حدّث القاعدة بـ: python fetch_data.py --results-only"
        )

    scored_list: list[int] = []
    conceded_list: list[int] = []
    points_total = 0
    results: list[str] = []

    for row in team_matches.itertuples(index=False):
        scored, conceded, pts, code = _points_for_team_row(row, team)
        scored_list.append(scored)
        conceded_list.append(conceded)
        points_total += pts
        results.append(code)

    n = len(scored_list)
    max_points = config.POINTS_WIN * n

    return TeamForm(
        team=team,
        matches_used=n,
        attack=sum(scored_list) / n,
        defense=sum(conceded_list) / n,
        goals_scored_total=sum(scored_list),
        goals_conceded_total=sum(conceded_list),
        points=points_total,
        max_points=max_points,
        points_ratio=points_total / max_points if max_points else 0.0,
        form_string="-".join(results),
        results=results,
    )


def compute_head_to_head(
    matches: pd.DataFrame,
    home_team: str,
    away_team: str,
    last_n: int | None = None,
) -> HeadToHead:
    """
    حساب سجل المواجهات المباشرة السابقة بين الفريقين.

    النقاط تُحسب من منظور home_team / away_team للمباراة المراد توقعها
    (وليس بالضرورة مضيف المواجهة التاريخية).
    """
    last_n = last_n if last_n is not None else config.H2H_LAST_N

    mask = (
        ((matches["home_team"] == home_team) & (matches["away_team"] == away_team))
        | ((matches["home_team"] == away_team) & (matches["away_team"] == home_team))
    )
    h2h_matches = matches.loc[mask].sort_values("date").tail(last_n)

    if h2h_matches.empty:
        return HeadToHead(
            home_team=home_team,
            away_team=away_team,
            matches_used=0,
            home_points=0,
            away_points=0,
            max_points=0,
            home_points_ratio=0.0,
            away_points_ratio=0.0,
            h2h_score=0.0,
            form_string="-",
            summary="لا توجد مواجهات مباشرة سابقة في القاعدة",
            available=False,
            details=[],
        )

    home_points = 0
    away_points = 0
    home_results: list[str] = []
    details: list[dict] = []

    for row in h2h_matches.itertuples(index=False):
        _, _, hp, hc = _points_for_team_row(row, home_team)
        _, _, ap, _ = _points_for_team_row(row, away_team)
        home_points += hp
        away_points += ap
        home_results.append(hc)
        details.append(
            {
                "date": str(row.date),
                "home_team": row.home_team,
                "away_team": row.away_team,
                "score": f"{int(row.home_goals)}-{int(row.away_goals)}",
                "result_for_current_home": hc,
            }
        )

    n = len(home_results)
    max_points = config.POINTS_WIN * n
    home_ratio = home_points / max_points if max_points else 0.0
    away_ratio = away_points / max_points if max_points else 0.0
    h2h_score = home_ratio - away_ratio

    summary = (
        f"{n} مواجهات | {home_team}: {home_points} نقطة | "
        f"{away_team}: {away_points} نقطة"
    )

    return HeadToHead(
        home_team=home_team,
        away_team=away_team,
        matches_used=n,
        home_points=home_points,
        away_points=away_points,
        max_points=max_points,
        home_points_ratio=home_ratio,
        away_points_ratio=away_ratio,
        h2h_score=h2h_score,
        form_string="-".join(home_results),
        summary=summary,
        available=True,
        details=details,
    )


def expected_goals(home_form: TeamForm, away_form: TeamForm) -> tuple[float, float]:
    egh = (home_form.attack + away_form.defense) / 2.0
    ega = (away_form.attack + home_form.defense) / 2.0
    return egh, ega


def combine_scores(
    egh: float,
    ega: float,
    home_form: TeamForm,
    away_form: TeamForm,
    h2h: HeadToHead,
    form_weight: float | None = None,
    h2h_weight: float | None = None,
) -> tuple[float, float, float, float]:
    """
    Returns:
      goal_score, form_score, h2h_score_weighted_input, final_score
    """
    form_weight = config.FORM_WEIGHT if form_weight is None else form_weight
    h2h_weight = config.H2H_WEIGHT if h2h_weight is None else h2h_weight

    goal_score = egh - ega
    form_score = home_form.points_ratio - away_form.points_ratio
    raw_h2h = h2h.h2h_score if h2h.available else 0.0
    applied_h2h_weight = h2h_weight if h2h.available else 0.0

    final_score = (
        goal_score
        + form_weight * form_score
        + applied_h2h_weight * raw_h2h
    )
    return goal_score, form_score, raw_h2h, final_score


def probabilities_from_score(
    final_score: float,
    temperature: float = 0.55,
    draw_bias: float = 0.28,
) -> tuple[float, float, float]:
    """
    تحويل الدرجة النهائية إلى احتمالات تقريبية (فوز مضيف / تعادل / فوز ضيف).

    Softmax على ثلاث logits:
      home ~ +score
      away ~ -score
      draw ~ يزداد عندما تكون الدرجة قريبة من الصفر
    """
    home_logit = final_score / temperature
    away_logit = -final_score / temperature
    # كل ما صغرت |score| زاد احتمال التعادل
    draw_logit = (draw_bias - abs(final_score)) / temperature

    max_logit = max(home_logit, draw_logit, away_logit)
    eh = math.exp(home_logit - max_logit)
    ed = math.exp(draw_logit - max_logit)
    ea = math.exp(away_logit - max_logit)
    total = eh + ed + ea
    return eh / total, ed / total, ea / total


def _decision_from_probabilities(
    prob_home: float,
    prob_draw: float,
    prob_away: float,
) -> tuple[int, str, float]:
    """اختيار النتيجة حسب أعلى احتمال."""
    best = max(prob_home, prob_draw, prob_away)
    if best == prob_draw:
        result = config.RESULT_DRAW
    elif best == prob_home:
        result = config.RESULT_HOME_WIN
    else:
        result = config.RESULT_AWAY_WIN
    return result, config.RESULT_LABELS[result], best


def build_reason(
    home_team: str,
    away_team: str,
    home_form: TeamForm,
    away_form: TeamForm,
    h2h: HeadToHead,
    egh: float,
    ega: float,
    goal_score: float,
    form_score: float,
    h2h_score: float,
    result: int,
) -> str:
    """سبب مختصر بالعربية يوضح أهم العوامل خلف التوقع."""
    parts: list[str] = []

    # قوة هجومية/دفاعية
    if abs(goal_score) < 0.15:
        parts.append(
            f"الأهداف المتوقعة متقاربة ({egh:.2f}-{ega:.2f})"
        )
    elif goal_score > 0:
        parts.append(
            f"تفوق هجومي/دفاعي للمضيف (متوقع {egh:.2f}-{ega:.2f})"
        )
    else:
        parts.append(
            f"تفوق هجومي/دفاعي للضيف (متوقع {egh:.2f}-{ega:.2f})"
        )

    # الفورم
    if abs(form_score) < 0.08:
        parts.append(
            f"فورم متقارب ({home_form.points}/{home_form.max_points} مقابل "
            f"{away_form.points}/{away_form.max_points})"
        )
    elif form_score > 0:
        parts.append(
            f"فورم أفضل للمضيف {home_form.form_string} "
            f"({home_form.points}/{home_form.max_points})"
        )
    else:
        parts.append(
            f"فورم أفضل للضيف {away_form.form_string} "
            f"({away_form.points}/{away_form.max_points})"
        )

    # H2H
    if not h2h.available:
        parts.append("لا توجد مواجهات مباشرة كافية في البيانات")
    elif abs(h2h_score) < 0.08:
        parts.append(f"المواجهات المباشرة متعادلة تقريبًا ({h2h.matches_used} مباريات)")
    elif h2h_score > 0:
        parts.append(
            f"تاريخ المواجهات يميل لـ {home_team} "
            f"({h2h.home_points}-{h2h.away_points} نقطة / {h2h.matches_used})"
        )
    else:
        parts.append(
            f"تاريخ المواجهات يميل لـ {away_team} "
            f"({h2h.away_points}-{h2h.home_points} نقطة / {h2h.matches_used})"
        )

    # جملة ختامية حسب النتيجة
    if result == config.RESULT_HOME_WIN:
        tail = f"لذلك الأرجحية لفوز {home_team}."
    elif result == config.RESULT_AWAY_WIN:
        tail = f"لذلك الأرجحية لفوز {away_team}."
    else:
        tail = "لذلك الأقرب هو التعادل."

    return "؛ ".join(parts) + ". " + tail


def predict_match(
    home_team: str,
    away_team: str,
    matches: pd.DataFrame | None = None,
    last_n: int | None = None,
    h2h_last_n: int | None = None,
    draw_margin: float | None = None,
    form_weight: float | None = None,
    h2h_weight: float | None = None,
) -> MatchPrediction:
    """توقع مباراة: هجوم/دفاع + فورم + مواجهات مباشرة + احتمالات."""
    if home_team == away_team:
        raise ValueError("لا يمكن توقع مباراة بين نفس الفريق.")

    if matches is None:
        matches = load_recent_matches()
    if matches.empty:
        raise RuntimeError("جدول matches فارغ. شغّل fetch_data.py أولًا.")

    # الفورم من النتائج الحديثة، وH2H من أوسع تاريخ متاح
    history = load_history_matches()

    home_form = compute_team_form(matches, home_team, last_n=last_n)
    away_form = compute_team_form(matches, away_team, last_n=last_n)
    h2h = compute_head_to_head(
        history, home_team, away_team, last_n=h2h_last_n
    )
    egh, ega = expected_goals(home_form, away_form)
    goal_score, form_score, raw_h2h, final_score = combine_scores(
        egh,
        ega,
        home_form,
        away_form,
        h2h,
        form_weight=form_weight,
        h2h_weight=h2h_weight,
    )

    # draw_margin اختياري: إن مُرّر نستخدمه كتحيّز تعادل إضافي بسيط
    draw_bias = 0.28
    if draw_margin is not None:
        draw_bias = max(0.15, float(draw_margin))

    prob_home, prob_draw, prob_away = probabilities_from_score(
        final_score, draw_bias=draw_bias
    )
    result, label, confidence = _decision_from_probabilities(
        prob_home, prob_draw, prob_away
    )
    reason = build_reason(
        home_team=home_team,
        away_team=away_team,
        home_form=home_form,
        away_form=away_form,
        h2h=h2h,
        egh=egh,
        ega=ega,
        goal_score=goal_score,
        form_score=form_score,
        h2h_score=raw_h2h,
        result=result,
    )

    return MatchPrediction(
        home_team=home_team,
        away_team=away_team,
        home_form=home_form,
        away_form=away_form,
        h2h=h2h,
        expected_home_goals=egh,
        expected_away_goals=ega,
        goal_score=goal_score,
        form_score=form_score,
        h2h_score=raw_h2h,
        final_score=final_score,
        result=result,
        result_label=label,
        confidence=confidence,
        prob_home=prob_home,
        prob_draw=prob_draw,
        prob_away=prob_away,
        reason=reason,
    )


def list_known_teams(matches: pd.DataFrame | None = None) -> list[str]:
    if matches is None:
        # نعرض اتحاد الفرق من الحديث + التاريخي
        frames = [load_recent_matches()]
        try:
            frames.append(load_history_matches())
        except Exception:
            pass
        matches = pd.concat(frames, ignore_index=True)
    teams = set(matches["home_team"]).union(set(matches["away_team"]))
    return sorted(teams)


def find_team(name: str, teams: list[str]) -> str:
    name_clean = name.strip()
    if name_clean in teams:
        return name_clean

    lowered = name_clean.lower()
    contains = [t for t in teams if lowered in t.lower() or t.lower() in lowered]
    if len(contains) == 1:
        return contains[0]
    if len(contains) > 1:
        options = ", ".join(contains[:8])
        raise ValueError(f"الاسم '{name}' غامض. اختر واحدًا من: {options}")
    raise ValueError(f"الفريق غير معروف: {name}")
