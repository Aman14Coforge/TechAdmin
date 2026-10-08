"""Visual theme for the TechAdmin Streamlit UI.

All styling lives here so app.py stays focused on behaviour. Streamlit widgets
are targeted through stable data-testid attributes and through the
``st-key-<key>`` class that Streamlit adds to every keyed container/widget.
"""
from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

_COFORGE_LOGO_PATH = Path(__file__).resolve().parent.parent / "Logo" / "Coforge_logo_Coral_White.svg"
_COFORGE_LOGO_DATA_URI = (
  "data:image/svg+xml;base64,"
  + base64.b64encode(_COFORGE_LOGO_PATH.read_bytes()).decode("ascii")
)
_OPERATIONS_ICON_PATH = Path(__file__).resolve().parent.parent / "Logo" / "icons8-operations-60.png"
_OPERATIONS_ICON_DATA_URI = (
    "data:image/png;base64,"
    + base64.b64encode(_OPERATIONS_ICON_PATH.read_bytes()).decode("ascii")
)

# ---------------------------------------------------------------------------
# Inline SVG icons (stroke icons, 24px grid). Used inside HTML fragments only;
# native Streamlit buttons use :material/...: icons instead.
# ---------------------------------------------------------------------------

def _svg(body: str, size: int = 18, stroke: str = "currentColor", width: float = 1.8) -> str:
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="{stroke}" stroke-width="{width}" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true">{body}</svg>'
    )


SPARKLE_PATH = (
    '<path d="M9.5 3.5 11 8l4.5 1.5L11 11l-1.5 4.5L8 11 3.5 9.5 8 8z"/>'
    '<path d="M17.5 13.5l.9 2.6 2.6.9-2.6.9-.9 2.6-.9-2.6-2.6-.9 2.6-.9z"/>'
)


def icon_sparkle(size: int = 18, stroke: str = "currentColor") -> str:
    return _svg(SPARKLE_PATH, size, stroke)


def icon_shield(size: int = 16, stroke: str = "currentColor") -> str:
    return _svg('<path d="M12 3l7 3v6c0 4.5-3 7.6-7 9-4-1.4-7-4.5-7-9V6z"/>', size, stroke)


def icon_shield_check(size: int = 16, stroke: str = "currentColor") -> str:
    return _svg(
        '<path d="M12 3l7 3v6c0 4.5-3 7.6-7 9-4-1.4-7-4.5-7-9V6z"/><path d="M9 12l2 2 4-4"/>',
        size, stroke,
    )


def icon_shield_alert(size: int = 16, stroke: str = "currentColor") -> str:
    return _svg(
        '<path d="M12 3l7 3v6c0 4.5-3 7.6-7 9-4-1.4-7-4.5-7-9V6z"/><path d="M12 8v4"/><path d="M12 15.5h.01"/>',
        size, stroke,
    )


def icon_users(size: int = 16, stroke: str = "currentColor") -> str:
    return _svg(
        '<circle cx="9" cy="8" r="3.2"/><path d="M3.5 19c.6-3 2.8-4.8 5.5-4.8s4.9 1.8 5.5 4.8"/>'
        '<path d="M16 5.2a3 3 0 0 1 0 5.6"/><path d="M17.5 14.4c1.6.6 2.7 2.2 3 4.6"/>',
        size, stroke,
    )


def icon_key(size: int = 16, stroke: str = "currentColor") -> str:
    return _svg(
        '<circle cx="8" cy="15" r="4"/><path d="M10.8 12.2 20 3"/><path d="M16 7l3 3"/><path d="M14 9l2 2"/>',
        size, stroke,
    )


def icon_alert(size: int = 16, stroke: str = "currentColor") -> str:
    return _svg(
        '<path d="M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>'
        '<path d="M12 9v4"/><path d="M12 17h.01"/>',
        size, stroke,
    )


def icon_check_circle(size: int = 16, stroke: str = "currentColor") -> str:
    return _svg('<circle cx="12" cy="12" r="9"/><path d="M8.5 12.5l2.3 2.3 4.7-5"/>', size, stroke)


def icon_x_circle(size: int = 16, stroke: str = "currentColor") -> str:
    return _svg('<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>', size, stroke)


def icon_help_circle(size: int = 16, stroke: str = "currentColor") -> str:
    return _svg(
        '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.3a2.6 2.6 0 0 1 5 .9c0 1.7-2.5 2.3-2.5 3.8"/>'
        '<path d="M12 17h.01"/>',
        size, stroke,
    )


def icon_search(size: int = 16, stroke: str = "currentColor") -> str:
    return _svg('<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>', size, stroke)


def coforge_wordmark(size_px: int = 40, light: bool = True) -> str:
  """Return the official Coforge SVG wordmark sized by its display height."""
  del light  # The supplied Coral/White logo is intended for the navy brand panels.
  return (
    f'<img class="ta-wordmark" src="{_COFORGE_LOGO_DATA_URI}" '
    f'alt="Coforge" style="display:block;width:auto;height:{size_px}px;max-width:100%">'
  )


def operations_icon(size_px: int = 60) -> str:
  """Return the supplied operations icon as an accessible embedded image."""
  return (
    f'<img class="ta-operations-icon" src="{_OPERATIONS_ICON_DATA_URI}" '
    f'alt="Operations" style="display:block;width:{size_px}px;height:{size_px}px;object-fit:contain">'
  )


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

BASE_CSS = r"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600;9..40,700&display=swap');

:root {
  --ta-navy: #0F1F33;
  --ta-navy-2: #132842;
  --ta-navy-3: #1C3757;
  --ta-navy-line: rgba(255,255,255,.08);
  --ta-orange: #EF5B3F;
  --ta-orange-2: #E14C30;
  --ta-orange-soft: #FDE7DF;
  --ta-orange-ink: #C2462B;
  --ta-ink: #1B2433;
  --ta-ink-2: #344054;
  --ta-muted: #667085;
  --ta-muted-2: #98A2B3;
  --ta-line: #E6E9EF;
  --ta-line-2: #EEF0F4;
  --ta-bg: #F7F8FA;
  --ta-card: #FFFFFF;
  --ta-ok: #1C7C45;
  --ta-ok-bg: #EBF7F0;
  --ta-ok-line: #CFEBDA;
  --ta-bad: #C53B3B;
  --ta-bad-bg: #FDEEEE;
  --ta-bad-line: #F6CFCF;
  --ta-warn: #A35A00;
  --ta-warn-bg: #FFF6E5;
  --ta-warn-line: #F5DDAE;
  --ta-unk: #667085;
  --ta-unk-bg: #F4F5F7;
  --ta-unk-line: #E3E6EB;
  --ta-radius: 14px;
  --ta-shadow: 0 1px 2px rgba(16,24,40,.04), 0 6px 20px rgba(16,24,40,.06);
}

html, body, [class*="st-"], .stMarkdown, button, input, textarea {
  font-family: 'DM Sans', system-ui, -apple-system, 'Segoe UI', sans-serif !important;
}
/* keep Material icon ligatures working */
[data-testid="stIconMaterial"], .material-symbols-rounded, span[translate="no"] {
  font-family: 'Material Symbols Rounded' !important;
}
.stApp { background: var(--ta-bg); color: var(--ta-ink); }
#MainMenu, footer, [data-testid="stStatusWidget"], [data-testid="stDecoration"] { display: none !important; }
[data-testid="stToolbar"] { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; height: 0; min-height: 0; }
[data-testid="stExpandSidebarButton"] { visibility: visible; }
.stMarkdown p { margin-bottom: 0; }
[data-testid="stElementContainer"]:has(style), [data-testid="stElementContainer"]:has(script),
.element-container:has(style), .element-container:has(script) { display: none !important; }
[data-testid="stBaseButton-primary"] p, .stFormSubmitButton button p { font-weight: 600; }
a { color: var(--ta-orange-2); }

/* Wordmark --------------------------------------------------------------- */
.ta-wordmark { font-weight: 700; letter-spacing: -.02em; line-height: 1; display:inline-flex; align-items:baseline; }
.ta-wm-c { color: var(--ta-orange); }
.ta-wm-o { position: relative; }

/* Generic bits ------------------------------------------------------------ */
.ta-kicker { color: var(--ta-orange-2); font-size: 11px; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; }
.ta-icon-tile { width: 40px; height: 40px; border-radius: 10px; background: var(--ta-orange);
  display:flex; align-items:center; justify-content:center; color:#fff; flex:none;
  box-shadow: 0 8px 22px rgba(239,91,63,.32); }
.ta-avatar { width: 36px; height: 36px; border-radius: 50%; background: var(--ta-orange-soft); color: var(--ta-orange-ink);
  display:flex; align-items:center; justify-content:center; font-weight:600; font-size: 13px; flex:none; }
.ta-avatar.lg { width: 46px; height: 46px; border-radius: 12px; font-size: 15px; }
.ta-avatar.dark { background: #2A4466; color: #DCE6F2; }
.ta-dot { width: 7px; height: 7px; border-radius: 50%; background: #22A35A; display:inline-block; }
.ta-badge { display:inline-flex; align-items:center; gap:4px; font-size: 11px; font-weight: 600; padding: 2px 8px;
  border-radius: 6px; background: var(--ta-unk-bg); color: var(--ta-ink-2); border: 1px solid var(--ta-unk-line); }
.ta-badge.ok { background: var(--ta-ok-bg); color: var(--ta-ok); border-color: var(--ta-ok-line); }
.ta-badge.bad { background: var(--ta-bad-bg); color: var(--ta-bad); border-color: var(--ta-bad-line); }
.ta-badge.warn { background: var(--ta-warn-bg); color: var(--ta-warn); border-color: var(--ta-warn-line); }
.ta-badge.preview { background: rgba(239,91,63,.14); color: #FFB4A3; border-color: rgba(239,91,63,.35); }

/* Buttons (global) ---------------------------------------------------------- */
.stButton > button, .stDownloadButton > button, [data-testid="stPopoverButton"] {
  border-radius: 10px; font-weight: 500; transition: all .15s ease; }
[data-testid="stBaseButton-primary"], .stFormSubmitButton > button[kind="primaryFormSubmit"] {
  background: var(--ta-orange) !important; border-color: var(--ta-orange) !important; color: #fff !important;
  box-shadow: 0 8px 22px rgba(239,91,63,.28); }
[data-testid="stBaseButton-primary"]:disabled { opacity: .45; box-shadow: none; cursor: not-allowed; }
[data-testid="stBaseButton-primary"]:hover { background: var(--ta-orange-2) !important; border-color: var(--ta-orange-2) !important; }
[data-testid="stBaseButton-secondary"] { background:#fff; border-color: var(--ta-line); color: var(--ta-ink-2); }
[data-testid="stBaseButton-secondary"]:hover { border-color: #D0D5DD; color: var(--ta-ink); background:#fff; }

/* Text inputs */
[data-testid="stTextInput"] [data-baseweb="input"], [data-testid="stTextInputRootElement"] { border-radius: 10px; border: 1px solid var(--ta-line) !important; background:#fff !important; min-height: 48px; }
[data-testid="stTextInput"] [data-baseweb="input"] > div, [data-testid="stTextInputRootElement"] > *, [data-testid="stTextInput"] input { background: transparent !important; }
[data-testid="stTextInput"] [data-baseweb="input"]:focus-within, [data-testid="stTextInputRootElement"]:focus-within { border-color: var(--ta-orange); box-shadow: 0 0 0 3px rgba(239,91,63,.12); }
[data-testid="stTextInput"] input { font-size: 14px; }
[data-testid="stWidgetLabel"] p { font-size: 13px; font-weight: 600; color: var(--ta-ink); }

/* Expanders */
[data-testid="stExpander"] details { border-radius: 10px; border-color: var(--ta-line); background:#fff; }
[data-testid="stExpander"] summary p { font-size: 13px; color: var(--ta-muted); }

/* Dataframes inside cards */
[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }

/* Dialog */
div[role="dialog"] { border-radius: 16px; }
</style>
"""

LOGIN_CSS = r"""
<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"] { display:none !important; }
.stApp { background: #FAFBFC; }
.stMainBlockContainer, .block-container { padding: 0 !important; max-width: 100% !important; }
.st-key-login_shell > div[data-testid="stHorizontalBlock"] { gap: 0 !important; min-height: 100vh; align-items: stretch; }
.st-key-login_shell [data-testid="stColumn"]:first-child { padding: 0 !important; }
.st-key-login_shell [data-testid="stColumn"]:first-child > div { height: 100%; }

.ta-hero { position: relative; overflow: hidden; height: 100vh; min-height: 640px; background: var(--ta-navy);
  border-bottom-right-radius: 26px; padding: 44px 54px; box-sizing: border-box; display:flex; flex-direction:column; }
.ta-hero .ring { position:absolute; border-radius:50%; pointer-events:none; }
.ta-hero .ring.r1 { width: 860px; height: 860px; right: -420px; top: 4%; border: 80px solid rgba(255,255,255,.035); }
.ta-hero .ring.r2 { width: 520px; height: 520px; right: -250px; top: 18%; background: rgba(9,20,36,.55); }
.ta-hero .ring.r3 { width: 380px; height: 380px; right: -90px; bottom: -150px; background: rgba(239,91,63,.10); }
.ta-hero .content { position: relative; margin-top: auto; margin-bottom: auto; max-width: 520px; }
.ta-hero h1 { color:#fff; font-size: clamp(36px, 3.4vw, 56px); line-height: 1.06; font-weight: 400; letter-spacing: -.035em; margin: 14px 0 22px; padding:0; }
.ta-hero p.lead { color: #B9C3D1; font-size: 16px; line-height: 1.65; margin: 0; }
.ta-hero .foot { position: relative; color: #9AA8BA; font-size: 12.5px; display:flex; align-items:center; gap:8px; }
.ta-hero .ta-kicker { color: #F27A62; margin-top: 22px; }

.st-key-login_form { max-width: 450px; margin: 0 auto; padding-top: 12vh; }
.ta-login-head h2 { font-size: 32px; font-weight: 400; letter-spacing: -.02em; color: var(--ta-ink); margin: 10px 0 8px; padding: 0; }
.ta-login-head p { color: var(--ta-muted); font-size: 15px; margin: 0 0 22px; }
.ta-sso-card { display:flex; gap: 14px; align-items:center; border: 1px solid var(--ta-line); background:#fff;
  border-radius: 12px; padding: 16px 16px; margin: 6px 0 18px; }
.ta-sso-card strong { display:block; font-size: 14px; color: var(--ta-ink); font-weight: 600; }
.ta-sso-card span { font-size: 12.5px; color: var(--ta-muted); }
.ta-ms-logo { display:grid; grid-template-columns: 10px 10px; gap: 2px; flex:none; }
.ta-ms-logo i { width:10px; height:10px; display:block; }
.ta-login-note { text-align:center; color: var(--ta-muted); font-size: 12.5px; margin-top: 14px; }
.ta-login-legal { text-align:center; color: var(--ta-muted-2); font-size: 11.5px; margin-top: 40px; }
.ta-optional { color: var(--ta-muted-2); font-weight: 400; font-size: 11px; margin-left: 6px; }

/* segmented control look for the sign-in tabs */
.st-key-login_form [role="tablist"] { background: #F0F2F5; border-radius: 12px; padding: 4px; gap: 4px; }
.st-key-login_form [role="tab"] { flex: 1; justify-content:center; height: 42px; border-radius: 9px; padding: 0 12px; }
.st-key-login_form [role="tab"] p { font-size: 13.5px; font-weight: 500; color: var(--ta-muted); }
.st-key-login_form [role="tab"][aria-selected="true"] { background:#fff; box-shadow: 0 1px 3px rgba(16,24,40,.10); }
.st-key-login_form [role="tab"][aria-selected="true"] p { color: var(--ta-ink); }
.st-key-login_form [data-baseweb="tab-highlight"], .st-key-login_form [data-baseweb="tab-border"],
.st-key-login_form [role="tab"] > div:not([data-testid]) { display:none !important; }
.st-key-login_form [role="tablist"] { box-shadow: none !important; border: none !important; }
.st-key-login_form [data-testid="stTabs"] [role="tablist"]::before, .st-key-login_form [data-testid="stTabs"] [role="tablist"]::after,
.st-key-login_form [data-testid="stTabs"] > div::after, .st-key-login_form [data-testid="stTabs"] > div::before { display:none !important; }
.st-key-login_form [data-testid="stForm"] { border: none; padding: 0; }
.st-key-login_form .stButton > button, .st-key-login_form .stFormSubmitButton > button { height: 50px; font-size: 15px; font-weight: 600; }

.st-key-microsoft_sign_in button p::before { content:""; display:inline-block; width:16px; height:16px; margin-right:10px; vertical-align:-2px;
  background: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16'><rect width='7.5' height='7.5' fill='%23F25022'/><rect x='8.5' width='7.5' height='7.5' fill='%237FBA00'/><rect y='8.5' width='7.5' height='7.5' fill='%2300A4EF'/><rect x='8.5' y='8.5' width='7.5' height='7.5' fill='%23FFB900'/></svg>") no-repeat center; }

@media (max-width: 900px) {
  .st-key-login_shell [data-testid="stColumn"]:first-child { display:none; }
  .st-key-login_form { padding: 48px 16px; }
}
</style>
"""

APP_CSS = r"""
<style>
/* Sidebar ------------------------------------------------------------------ */
section[data-testid="stSidebar"] { background: var(--ta-navy); border-right: none; }
section[data-testid="stSidebar"][aria-expanded="true"] { width: 290px !important; min-width: 290px !important; }
section[data-testid="stSidebar"][aria-expanded="false"] { width: 0 !important; min-width: 0 !important; max-width: 0 !important; overflow: hidden !important; }
section[data-testid="stSidebar"] > div { background: var(--ta-navy); }
[data-testid="stSidebarContent"] { padding: 0 !important; }
[data-testid="stSidebarHeader"] { padding: 14px 16px 0; height: 44px; min-height: 0; }
[data-testid="stSidebarHeader"] [data-testid="stLogo"] { height: 40px; max-width: 100%; }
[data-testid="stSidebarCollapseButton"] button { color: #9AA8BA; }
[data-testid="stSidebarUserContent"] { padding: 0 16px 18px !important; }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: .35rem; }
[data-testid="stSidebar"] hr { border-color: var(--ta-navy-line); margin: 14px 0; }

.ta-side-brand { padding: 0 8px 14px; }
.ta-app-card { display:flex; gap: 12px; align-items:center; background: var(--ta-navy-2); border: 1px solid var(--ta-navy-line);
  border-radius: 12px; padding: 14px 14px; margin: 4px 0 14px; }
.ta-app-card strong { color:#fff; font-size: 14.5px; font-weight: 600; display:block; }
.ta-app-card span { color: #9AA8BA; font-size: 12.5px; }
.ta-app-card .ta-icon-tile { box-shadow: none; width: 38px; height: 38px; }

/* nav buttons */
[data-testid="stSidebar"] .stButton > button { justify-content: flex-start; background: transparent; border: none; color: #C8D1DD;
  height: 42px; padding: 0 14px; font-size: 14.5px; font-weight: 500; box-shadow: none; }
[data-testid="stSidebar"] .stButton > button:hover { background: rgba(255,255,255,.05); color: #fff; }
[data-testid="stSidebar"] .stButton > button [data-testid="stIconMaterial"] { color: #9AA8BA; font-size: 19px; margin-right: 6px; }
[data-testid="stSidebar"] .stButton > button > div, [data-testid="stSidebar"] .stButton > button > div > span { justify-content: flex-start !important; width: 100%; }
[data-testid="stSidebar"] .stButton > button div[data-testid="stMarkdownContainer"] { flex: 1; width: 100%; text-align:left; }
[data-testid="stSidebar"] .st-key-sign_out .stButton > button > div, [data-testid="stSidebar"] .st-key-sign_out .stButton > button > div > span { justify-content: center !important; }
[data-testid="stSidebar"] .st-key-sign_out .stButton > button div[data-testid="stMarkdownContainer"] { flex: 0 0 auto; width: auto; }
[data-testid="stSidebar"] .stButton > button div[data-testid="stMarkdownContainer"] p { width: 100%; display:flex; justify-content:space-between; align-items:center; }
[class*="st-key-nav_active_"] .stButton > button, .st-key-nav_active .stButton > button { background: var(--ta-navy-3) !important; color:#fff !important; }
[class*="st-key-nav_active_"] .stButton > button [data-testid="stIconMaterial"] { color: #fff; }

.ta-side-label { display:flex; justify-content: space-between; align-items:center; color: #8C9AAE; font-size: 11px; font-weight: 600;
  letter-spacing: .14em; text-transform: uppercase; padding: 0 8px; margin: 2px 0 6px; }
.ta-recent { display:block; padding: 10px 12px; border-radius: 10px; margin: 0 0 2px; border-left: 2px solid transparent; }
.ta-recent strong { display:block; color: #E6EBF2; font-weight: 500; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ta-recent span { display:block; color: #8C9AAE; font-size: 12px; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ta-recent.active { background: var(--ta-navy-2); border-left-color: var(--ta-orange); }
.ta-recent .st { font-size: 10.5px; padding: 1px 6px; border-radius: 5px; margin-left: 6px; background: rgba(255,255,255,.06); color:#AFC0D3; }
.ta-side-empty { color: #8C9AAE; font-size: 12.5px; padding: 4px 10px 8px; }

.st-key-side_search [data-testid="stPopoverButton"] { background: transparent; border: none; color: #8C9AAE; min-height: 26px; height: 26px; padding: 0 6px; }
.st-key-side_search [data-testid="stPopoverButton"]:hover { color:#fff; }
.st-key-side_search [data-testid="stPopoverButton"] > div > div:last-child, .st-key-side_search [data-testid="stPopoverButton"] svg { display:none; }
[data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] { min-height: calc(100vh - 64px); }
[data-testid="stLayoutWrapper"]:has(> .st-key-side_bottom) { margin-top: auto !important; }
.st-key-side_bottom { margin-top: auto !important; border-top: 1px solid var(--ta-navy-line); padding-top: 16px; }
.ta-me { display:flex; gap: 12px; align-items:center; padding: 4px 6px 10px; }
.ta-me strong { color:#fff; font-size: 14px; font-weight: 600; display:block; }
.ta-me span { color: #8C9AAE; font-size: 12.5px; }
.st-key-sign_out .stButton > button { justify-content:center !important; border: 1px solid rgba(255,255,255,.12) !important; background: rgba(255,255,255,.03) !important; color: #E6EBF2 !important; }
.st-key-sign_out .stButton > button:hover { background: rgba(255,255,255,.07) !important; }

/* Main area ------------------------------------------------------------------ */
.stMainBlockContainer, .block-container { max-width: 100% !important; padding: 0 0 2rem 0 !important; }
.st-key-topbar { background: #fff; border-bottom: 1px solid var(--ta-line); padding: 14px 32px 12px; position: sticky; top: 0; z-index: 50; }
.st-key-topbar [data-testid="stHorizontalBlock"] { align-items: center; }
.ta-topbar-title { font-size: 17px; color: var(--ta-ink); font-weight: 500; line-height: 1.2; }
.ta-topbar-status { display:flex; align-items:center; gap: 6px; color: var(--ta-muted); font-size: 12px; margin-top: 3px; }
.ta-topbar-status.warn .ta-dot { background: #E0A100; }
.st-key-topbar [data-testid="stPopoverButton"] { border: none; background: transparent; color: var(--ta-muted); min-height: 36px; height: 36px; width: 36px; padding: 0; border-radius: 50%; }
.st-key-topbar [data-testid="stPopoverButton"]:hover { background: var(--ta-bg); color: var(--ta-ink); }
.st-key-topbar [data-testid="stPopoverButton"] [data-testid="stIconMaterial"] { font-size: 20px; }
.st-key-topbar [data-testid="stPopoverButton"] > div > div:last-child, .st-key-topbar [data-testid="stPopoverButton"] svg { display:none; }
.st-key-topbar [data-testid="stPopoverButton"] [data-testid="stIconMaterial"] { display:inline-block; }
.ta-top-right { display:flex; justify-content:flex-end; }
.ta-pill-count { background: var(--ta-orange); color:#fff; font-size: 10px; border-radius: 8px; padding: 0 5px; margin-left: -10px; vertical-align: top; }

.st-key-content { max-width: 1000px; margin: 0 auto; padding: 36px 32px 0; }
.ta-greet h1 { font-size: 30px; font-weight: 400; letter-spacing: -.02em; color: var(--ta-ink); padding: 0; margin: 0 0 6px; }
.ta-greet p { color: var(--ta-muted); font-size: 14.5px; margin: 0; }
.st-key-greet_row [data-testid="stHorizontalBlock"] { align-items: center; }
.st-key-greet_row { border-bottom: 1px solid var(--ta-line); padding-bottom: 24px; margin-bottom: 18px; }
.st-key-new_conversation .stButton > button { background:#fff; border: 1px solid var(--ta-line); height: 40px; color: var(--ta-ink); font-weight: 500; }

/* Chat ---------------------------------------------------------------------- */
.ta-user-row { display:flex; justify-content:flex-end; gap: 12px; align-items:flex-start; margin: 14px 0 22px; }
.ta-user-bubble { background: var(--ta-navy); color: #fff; padding: 12px 18px 13px; border-radius: 14px 4px 14px 14px; max-width: 70%; }
.ta-user-bubble .meta { color: #9AA8BA; font-size: 11px; margin-bottom: 4px; }
.ta-user-bubble .txt { font-size: 15px; line-height: 1.45; white-space: pre-wrap; word-break: break-word; }
.ta-asst-head { display:flex; gap: 14px; align-items:flex-start; margin-top: 8px; }
.ta-asst-head .ta-icon-tile { box-shadow: none; width: 38px; height: 38px; }
.ta-asst-head .who { color: var(--ta-muted); font-size: 12px; font-weight: 500; margin: 1px 0 6px; }
.ta-asst-head .msg { color: var(--ta-ink-2); font-size: 15px; line-height: 1.55; }
[class*="st-key-amsg_"] { padding-left: 52px; margin-bottom: 22px; }
[class*="st-key-amsg_"] > div { gap: .75rem; }

/* Generic card */
[class*="st-key-card_"] { background: var(--ta-card); border: 1px solid var(--ta-line); border-radius: var(--ta-radius);
  box-shadow: var(--ta-shadow); padding: 22px 22px 0; overflow: hidden; }
[class*="st-key-card_"] [data-testid="stVerticalBlock"] { gap: .8rem; }
.ta-card-head { display:flex; gap: 14px; align-items:center; min-width: 0; }
.ta-card-head .ta-kicker { color: var(--ta-ok); display:flex; align-items:center; gap: 6px; font-size: 10.5px; }
.ta-card-head .ta-kicker.warn { color: var(--ta-warn); }
.ta-card-head .ta-kicker.bad { color: var(--ta-bad); }
.ta-card-head .ta-kicker .ta-dot { width: 6px; height: 6px; }
.ta-card-head .ta-kicker.warn .ta-dot { background: #E0A100; }
.ta-card-head .ta-kicker.bad .ta-dot { background: var(--ta-bad); }
.ta-card-head .name { font-size: 19px; color: var(--ta-ink); font-weight: 500; margin: 3px 0 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ta-card-head .sub { font-size: 13px; color: var(--ta-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
[class*="st-key-card_"] [data-testid="stHorizontalBlock"] { align-items: center; }
[class*="st-key-card_"] [data-testid="stPopoverButton"], [class*="st-key-card_"] .stButton > button, [class*="st-key-card_"] .stDownloadButton > button {
  height: 38px; min-height: 38px; font-size: 13px; }
[class*="st-key-card_"] [data-testid="stPopoverButton"] { background:#fff; border: 1px solid var(--ta-line); color: var(--ta-ink-2); }

.ta-tiles { display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 10px; margin: 4px 0 2px; }
.ta-tile { display:flex; gap: 10px; align-items:center; border-radius: 10px; padding: 12px 12px; border: 1px solid var(--ta-unk-line); background: var(--ta-unk-bg); min-width: 0; }
.ta-tile .ic { width: 30px; height: 30px; border-radius: 50%; background:#fff; display:flex; align-items:center; justify-content:center; flex:none; color: var(--ta-unk); }
.ta-tile .lb { font-size: 11px; color: var(--ta-muted); }
.ta-tile .vl { font-size: 14px; font-weight: 600; color: var(--ta-unk); margin-top: 1px; white-space: nowrap; overflow:hidden; text-overflow: ellipsis; }
.ta-tile.ok { background: var(--ta-ok-bg); border-color: var(--ta-ok-line); } .ta-tile.ok .vl, .ta-tile.ok .ic { color: var(--ta-ok); }
.ta-tile.bad { background: var(--ta-bad-bg); border-color: var(--ta-bad-line); } .ta-tile.bad .vl, .ta-tile.bad .ic { color: var(--ta-bad); }
.ta-tile.warn { background: var(--ta-warn-bg); border-color: var(--ta-warn-line); } .ta-tile.warn .vl, .ta-tile.warn .ic { color: var(--ta-warn); }

/* underline tabs inside cards */
[class*="st-key-card_"] [role="tablist"] { gap: 22px; border-bottom: 1px solid var(--ta-line); margin: 0 -22px; padding: 0 22px; }
[class*="st-key-card_"] [role="tab"] { height: 44px; padding: 0; background: transparent; }
[class*="st-key-card_"] [role="tab"] p { font-size: 13.5px; color: var(--ta-muted); font-weight: 500; }
[class*="st-key-card_"] [role="tab"][aria-selected="true"] p { color: var(--ta-ink); }
[class*="st-key-card_"] [data-baseweb="tab-highlight"], [class*="st-key-card_"] [role="tab"] > div:not([data-testid]) { background: var(--ta-orange) !important; height: 2px; }
[class*="st-key-card_"] [data-baseweb="tab-border"] { display:none; }
[class*="st-key-card_"] [role="tabpanel"] { padding-top: 4px; }

.ta-kv { display:grid; grid-template-columns: 1fr 1fr; column-gap: 36px; }
.ta-kv .row { display:flex; justify-content: space-between; gap: 16px; padding: 12px 8px; border-bottom: 1px solid var(--ta-line-2); font-size: 13.5px; min-width:0; }
.ta-kv .row .k { color: var(--ta-muted); flex:none; }
.ta-kv .row .v { color: var(--ta-ink); font-weight: 500; text-align: right; word-break: break-word; min-width: 0; }
.ta-kv.single { grid-template-columns: 1fr; }

.ta-stats { display:grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 10px; margin: 8px 0 10px; }
.ta-stat { background: var(--ta-bg); border-radius: 10px; padding: 11px 14px; }
.ta-stat .lb { font-size: 11px; color: var(--ta-muted); }
.ta-stat .vl { font-size: 15px; color: var(--ta-ink); font-weight: 600; margin-top: 3px; }
.ta-group { display:flex; align-items:center; gap: 12px; padding: 12px 8px; border-bottom: 1px solid var(--ta-line-2); }
.ta-group .ic { width: 30px; height: 30px; border-radius: 8px; background: var(--ta-bg); color: var(--ta-muted); display:flex; align-items:center; justify-content:center; flex:none; }
.ta-group .nm { font-size: 13.5px; font-weight: 600; color: var(--ta-ink); }
.ta-group .ds { font-size: 11.5px; color: var(--ta-muted); margin-top: 1px; }
.ta-group .ta-badge { margin-left: auto; }
.ta-empty { color: var(--ta-muted); font-size: 13.5px; padding: 14px 8px; }

[data-testid="stMarkdownContainer"]:has(.ta-card-foot) { margin-bottom: 0 !important; }
.ta-card-foot { display:flex; justify-content: space-between; align-items:center; gap: 12px; background: #FAFBFC; border-top: 1px solid var(--ta-line);
  margin: 4px -22px 0; padding: 12px 22px; color: var(--ta-muted); font-size: 12px; }
.ta-card-foot .l { display:flex; align-items:center; gap: 6px; }

.ta-note { border-radius: 10px; padding: 12px 14px; font-size: 13.5px; line-height: 1.5; color: var(--ta-ink-2); background: var(--ta-bg); border: 1px solid var(--ta-line); }
.ta-note.warn { background: var(--ta-warn-bg); border-color: var(--ta-warn-line); }
.ta-note.bad { background: var(--ta-bad-bg); border-color: var(--ta-bad-line); color: #7A2626; }
.ta-note.ok { background: var(--ta-ok-bg); border-color: var(--ta-ok-line); color: #14532D; }
.ta-note strong { color: var(--ta-ink); }
.ta-secret { font-family: ui-monospace, SFMono-Regular, Menlo, monospace !important; letter-spacing: .06em; }

/* Approval card accent */
[class*="st-key-card_approval"] { border-color: var(--ta-warn-line); box-shadow: 0 0 0 4px rgba(224,161,0,.08), var(--ta-shadow); }

/* Technical details expander inside messages */
[class*="st-key-amsg_"] [data-testid="stExpander"] details { border: none; background: transparent; }
[class*="st-key-amsg_"] [data-testid="stExpander"] summary { padding: 4px 0; }

/* Working indicator */
.ta-working { display:flex; align-items:center; gap: 10px; color: var(--ta-muted); font-size: 14px; }
.ta-working i { width: 6px; height: 6px; border-radius: 50%; background: var(--ta-orange); display:inline-block; animation: ta-b 1.2s infinite ease-in-out; }
.ta-working i:nth-child(2) { animation-delay: .15s; } .ta-working i:nth-child(3) { animation-delay: .3s; }
@keyframes ta-b { 0%, 80%, 100% { opacity: .25; transform: translateY(0); } 40% { opacity: 1; transform: translateY(-3px); } }

/* Empty state quick actions */
.ta-hello { text-align:left; padding: 6px 0 18px; }
.ta-hello h3 { font-size: 16px; font-weight: 600; color: var(--ta-ink); margin: 0 0 4px; padding: 0; }
.ta-hello p { color: var(--ta-muted); font-size: 14px; margin: 0; }
[class*="st-key-qa_"] .stButton > button { height: auto; min-height: 92px; padding: 16px 18px; background:#fff; border: 1px solid var(--ta-line);
  border-radius: 14px; box-shadow: var(--ta-shadow); display:flex; flex-direction: column; align-items:flex-start; justify-content:flex-start; text-align:left; }
[class*="st-key-qa_"] .stButton > button > div, [class*="st-key-qa_"] .stButton > button > div > span { flex-direction: column; align-items: flex-start !important; justify-content: flex-start !important; width: 100%; gap: 10px; }
[class*="st-key-qa_"] .stButton > button:hover { border-color: #F3B9AA; transform: translateY(-1px); }
[class*="st-key-qa_"] .stButton > button [data-testid="stIconMaterial"] { color: var(--ta-orange); font-size: 22px; margin-bottom: 8px; }
[class*="st-key-qa_"] .stButton > button p { font-size: 14px; font-weight: 600; color: var(--ta-ink); text-align:left; white-space: normal; }
[class*="st-key-qa_"] .stButton > button div[data-testid="stMarkdownContainer"] p small { display:block; font-size: 12.5px; color: var(--ta-muted); font-weight: 400; margin-top: 3px; }

/* Suggestion chips + composer ------------------------------------------------ */
.st-key-chips { position: sticky; bottom: 0; z-index: 20; padding: 18px 0 6px;
  background: linear-gradient(180deg, rgba(247,248,250,0) 0%, rgba(247,248,250,.92) 38%, var(--ta-bg) 100%); }
.st-key-chips [data-testid="stHorizontalBlock"] { flex-wrap: wrap; gap: 8px; }
.st-key-chips [data-testid="stColumn"] { width: auto !important; flex: 0 0 auto !important; min-width: 0 !important; }
.st-key-chips .stButton > button { height: 34px; min-height: 34px; padding: 0 12px; background:#fff; border: 1px solid var(--ta-line);
  border-radius: 8px; font-size: 12.5px; color: var(--ta-ink-2); box-shadow: 0 1px 2px rgba(16,24,40,.04); }
.st-key-chips .stButton > button p { font-size: 12.5px; }
.st-key-chips .stButton > button:hover { border-color: #F3B9AA; color: var(--ta-ink); }
.st-key-chips .stButton > button [data-testid="stIconMaterial"] { order: 2; font-size: 16px; margin: 0 0 0 4px; color: var(--ta-muted); }

[data-testid="stBottom"] > div { background: var(--ta-bg); }
[data-testid="stBottomBlockContainer"] { max-width: 1000px; padding: 6px 32px 10px; }
[data-testid="stChatInput"] { border-radius: 14px; border: 1px solid var(--ta-line); background: #fff; box-shadow: var(--ta-shadow); }
[data-testid="stChatInput"]:focus-within { border-color: #F3B9AA; box-shadow: 0 0 0 4px rgba(239,91,63,.08), var(--ta-shadow); }
[data-testid="stChatInput"] > div { background: transparent; border: none; }
[data-testid="stChatInputTextArea"] { font-size: 15px; padding: 15px 12px 15px 46px !important; line-height: 1.5;
  background: transparent url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='%23EF5B3F' stroke-width='1.9' stroke-linecap='round' stroke-linejoin='round'><path d='M9.5 3.5 11 8l4.5 1.5L11 11l-1.5 4.5L8 11 3.5 9.5 8 8z'/><path d='M17.5 13.5l.9 2.6 2.6.9-2.6.9-.9 2.6-.9-2.6-2.6-.9 2.6-.9z'/></svg>") no-repeat 16px center; }
[data-testid="stChatInputSubmitButton"] { background: var(--ta-bg); border-radius: 9px; color: var(--ta-muted); }
[data-testid="stChatInputSubmitButton"]:enabled { background: var(--ta-orange); color: #fff; }
[data-testid="stBottomBlockContainer"]::after { content: "Actions are audited and require confirmation before execution.";
  display:block; text-align:center; color: var(--ta-muted-2); font-size: 11.5px; margin-top: 8px; }
.ta-composer-note { text-align:center; color: var(--ta-muted-2); font-size: 11.5px; margin-top: 8px; display:flex; justify-content:center; gap: 6px; align-items:center; }

/* Pages (history / directory) */
.ta-page-head h1 { font-size: 26px; font-weight: 400; letter-spacing: -.02em; margin: 0 0 6px; padding: 0; color: var(--ta-ink); }
.ta-page-head p { color: var(--ta-muted); font-size: 14px; margin: 0 0 20px; }
.ta-hist { display:grid; grid-template-columns: 1.5fr 1fr .8fr .9fr; gap: 12px; align-items:center; padding: 13px 16px; border-bottom: 1px solid var(--ta-line-2); font-size: 13.5px; }
.ta-hist.h { color: var(--ta-muted); font-size: 11.5px; text-transform: uppercase; letter-spacing: .08em; font-weight: 600; background: #FAFBFC; border-bottom: 1px solid var(--ta-line); }
.ta-hist .q { color: var(--ta-ink); font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ta-hist .t { color: var(--ta-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.st-key-hist_card, .st-key-dir_card { background:#fff; border: 1px solid var(--ta-line); border-radius: var(--ta-radius); box-shadow: var(--ta-shadow); overflow:hidden; }
.st-key-dir_card { padding: 20px 22px; }

@media (max-width: 1100px) {
  .ta-tiles { grid-template-columns: repeat(2, minmax(0,1fr)); }
  .ta-kv { grid-template-columns: 1fr; }
}
@media (max-width: 700px) {
  .st-key-content { padding: 22px 16px 0; }
  .st-key-topbar { padding: 12px 16px; }
  [class*="st-key-amsg_"] { padding-left: 0; }
  .ta-user-bubble { max-width: 88%; }
  .ta-hist { grid-template-columns: 1fr 1fr; }
  [data-testid="stBottomBlockContainer"] { padding: 6px 16px 10px; }
}
</style>
"""


def inject_base_css() -> None:
    st.markdown(BASE_CSS, unsafe_allow_html=True)


def inject_login_css() -> None:
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)


def inject_app_css() -> None:
    st.markdown(APP_CSS, unsafe_allow_html=True)
