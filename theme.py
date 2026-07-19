"""
UI theme constants and small pure helpers used by app.py and football.kv.
Keeps visual tokens separate from screen logic.
"""

from __future__ import annotations

PLACEHOLDER_HOME = "— Select home team —"
PLACEHOLDER_AWAY = "— Select away team —"
EMPTY_TEAMS_MSG = "No teams — update data"

# Map Arabic engine labels → English UI (predictor/config unchanged)
RESULT_LABEL_EN = {
    "فوز صاحب الأرض": "Home Win",
    "تعادل": "Draw",
    "فوز الضيف": "Away Win",
}

_AVATAR_PALETTE = (
    (0.26, 0.52, 0.96, 1.0),
    (0.18, 0.70, 0.47, 1.0),
    (0.92, 0.32, 0.30, 1.0),
    (0.61, 0.35, 0.90, 1.0),
    (0.95, 0.55, 0.18, 1.0),
    (0.10, 0.68, 0.72, 1.0),
    (0.90, 0.30, 0.55, 1.0),
    (0.35, 0.55, 0.25, 1.0),
    (0.20, 0.45, 0.75, 1.0),
    (0.85, 0.65, 0.15, 1.0),
    (0.45, 0.35, 0.80, 1.0),
    (0.15, 0.60, 0.55, 1.0),
    (0.80, 0.25, 0.40, 1.0),
    (0.30, 0.70, 0.85, 1.0),
    (0.55, 0.45, 0.25, 1.0),
    (0.40, 0.75, 0.35, 1.0),
)
_AVATAR_SKIP_WORDS = {
    "FC", "CF", "AFC", "SC", "BK", "IF", "FK", "CD", "UD",
    "CLUB", "DE", "THE", "AND", "OF",
}

# Dark theme palette (navy charcoal + emerald)
C_BG = (0.039, 0.047, 0.071, 1)          # #0A0C12
C_BG_MID = (0.055, 0.070, 0.110, 1)      # #0E121C
C_BG_TOP = (0.070, 0.090, 0.140, 1)      # #121724
C_SURFACE = (0.078, 0.094, 0.133, 0.96)  # #141822
C_SURFACE_SOLID = (0.078, 0.094, 0.133, 1)
C_CARD = (0.110, 0.130, 0.180, 0.94)     # #1C2130
C_CARD_SOLID = (0.110, 0.130, 0.180, 1)
C_CARD_ALT = (0.140, 0.162, 0.220, 1)    # #242938
C_ELEVATED = (0.160, 0.185, 0.250, 1)
C_BORDER = (0.28, 0.33, 0.42, 0.55)
C_BORDER_SOFT = (0.30, 0.36, 0.48, 0.28)
C_ACCENT = (0.18, 0.86, 0.62, 1)         # #2EDB9E
C_ACCENT_DIM = (0.08, 0.40, 0.32, 1)
C_ACCENT_SOFT = (0.18, 0.86, 0.62, 0.12)
C_GLOW_TEAL = (0.10, 0.55, 0.48, 0.16)
C_GLOW_BLUE = (0.15, 0.28, 0.55, 0.18)
# Result colors: green win / yellow draw / red loss (home perspective)
C_WIN = (0.18, 0.82, 0.48, 1)
C_DRAW = (0.98, 0.78, 0.18, 1)
C_LOSS = (0.94, 0.32, 0.36, 1)
C_HOME = C_WIN
C_AWAY = C_LOSS
C_TEXT = (0.945, 0.955, 0.975, 1)
C_MUTED = (0.58, 0.63, 0.72, 1)
C_HINT = (0.42, 0.47, 0.56, 1)
C_DANGER = (0.95, 0.35, 0.38, 1)
C_OK = (0.30, 0.88, 0.58, 1)
C_SHADOW = (0.0, 0.0, 0.0, 0.42)


def is_team_placeholder(name: str) -> bool:
    v = (name or "").strip()
    return (
        not v
        or v in {PLACEHOLDER_HOME, PLACEHOLDER_AWAY, EMPTY_TEAMS_MSG}
        or v.startswith("—")
    )


def team_color(name: str) -> tuple[float, float, float, float]:
    """Stable color per team name (simple FNV-like hash)."""
    if is_team_placeholder(name):
        return C_HINT
    h = 2166136261
    for ch in name.strip().lower():
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return _AVATAR_PALETTE[h % len(_AVATAR_PALETTE)]


def team_initials(name: str) -> str:
    """Two-letter initials for avatar badges (Gmail/Slack style)."""
    if is_team_placeholder(name):
        return "?"
    cleaned = (name or "").strip().replace("-", " ").replace("_", " ")
    words = [w for w in cleaned.split() if w]
    meaningful = [
        w
        for w in words
        if w.upper().strip(".") not in _AVATAR_SKIP_WORDS and any(c.isalpha() for c in w)
    ]
    if not meaningful:
        meaningful = [w for w in words if any(c.isalpha() for c in w)]

    def _first_alpha(word: str) -> str:
        for ch in word:
            if ch.isalpha():
                return ch.upper()
        return ""

    def _word_alpha(word: str) -> str:
        return "".join(ch for ch in word if ch.isalpha())

    if len(meaningful) >= 2:
        a = _first_alpha(meaningful[0])
        b = _first_alpha(meaningful[1])
        if a and b:
            return a + b

    if meaningful:
        alpha = _word_alpha(meaningful[0])
        if len(alpha) >= 2:
            return alpha[:2].upper()
        if len(alpha) == 1:
            return (alpha * 2).upper()

    alpha = "".join(ch for ch in cleaned if ch.isalpha())
    if len(alpha) >= 2:
        return alpha[:2].upper()
    if alpha:
        return (alpha[0] * 2).upper()
    return "?"
