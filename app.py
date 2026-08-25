"""משחק היכרות — אפליקציית Streamlit בעברית."""

from __future__ import annotations

import io
import os

import qrcode
import streamlit as st

import db

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_HOST_PASSWORD = "changeme"
HOST_PASSWORD = os.environ.get("HOST_PASSWORD", DEFAULT_HOST_PASSWORD)
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

st.set_page_config(
    page_title="משחק היכרות",
    page_icon="🎲",
    layout="centered",
    initial_sidebar_state="collapsed",
)

RTL_CSS = """
<style>
    .stApp { direction: rtl; text-align: right; }
    [data-testid="stMarkdownContainer"] { direction: rtl; text-align: right; }
    h1, h2, h3, p, label, .stTextInput label { direction: rtl; text-align: right; }
    div[data-testid="stButton"] > button { width: 100%; }
    .question-box {
        background: linear-gradient(145deg, #1a3a4a 0%, #0f2740 100%);
        color: #f5f0e8;
        border-radius: 1.25rem;
        padding: 1.75rem 1.5rem;
        margin: 1rem 0;
        font-size: 1.45rem;
        line-height: 1.6;
        text-align: center;
        border: 1px solid rgba(245, 240, 232, 0.15);
    }
    .turn-badge {
        display: inline-block;
        background: #e8a54b;
        color: #1a1a1a;
        font-weight: 700;
        padding: 0.4rem 1rem;
        border-radius: 999px;
        margin: 0.5rem 0 1rem;
        font-size: 1.05rem;
    }
    .room-code {
        font-size: 2.4rem;
        font-weight: 800;
        letter-spacing: 0.2em;
        text-align: center;
        color: #1a3a4a;
    }
    .muted { color: #667; font-size: 0.95rem; text-align: center; }
</style>
"""

st.markdown(RTL_CSS, unsafe_allow_html=True)


def init_session() -> None:
    defaults = {
        "role": None,  # "host" | "player"
        "room_code": None,
        "player_name": None,
        "host_authenticated": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def join_url(room_code: str) -> str:
    base = PUBLIC_BASE_URL
    if not base:
        # Best-effort: Streamlit may expose the browser URL in newer versions
        try:
            base = st.context.headers.get("Origin") or ""
        except Exception:
            base = ""
    if not base:
        base = "http://localhost:8501"
    return f"{base}/?room={room_code}"


def make_qr_image(url: str):
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1a3a4a", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def render_home() -> None:
    st.title("🎲 משחק היכרות")
    st.markdown(
        '<p class="muted">שאלות משעשעות על החברים — עונים בקול בחדר</p>',
        unsafe_allow_html=True,
    )

    params = st.query_params
    room_from_qr = (params.get("room") or "").strip().upper()

    tab_join, tab_host = st.tabs(["הצטרפות לשחקנים", "כניסת מנחה"])

    with tab_join:
        default_room = room_from_qr
        room_code = st.text_input(
            "קוד חדר",
            value=default_room,
            max_chars=8,
            key="join_room_code",
        ).strip().upper()
        name = st.text_input("השם שלך", max_chars=40, key="join_name").strip()
        if st.button("הצטרפות", type="primary", key="btn_join"):
            if not room_code:
                st.error("נא להזין קוד חדר")
            elif not name:
                st.error("נא להזין שם")
            elif not db.room_exists(room_code):
                st.error("החדר לא נמצא — בדקו את הקוד או סרקו שוב את ה־QR")
            else:
                ok, msg = db.add_player(room_code, name)
                if ok:
                    st.session_state.role = "player"
                    st.session_state.room_code = room_code
                    st.session_state.player_name = name
                    st.rerun()
                else:
                    st.error(msg)

    with tab_host:
        password = st.text_input("סיסמת מנחה", type="password", key="host_pw")
        if st.button("כניסה ויצירת חדר", type="primary", key="btn_host"):
            if password != HOST_PASSWORD:
                st.error("סיסמה שגויה")
            else:
                code = db.create_room()
                st.session_state.role = "host"
                st.session_state.host_authenticated = True
                st.session_state.room_code = code
                st.session_state.player_name = "מנחה"
                st.rerun()

        st.caption(
            "ברירת מחדל לסיסמה: changeme — מומלץ להגדיר משתנה סביבה HOST_PASSWORD"
        )


def render_players_list(players: list[str]) -> None:
    st.subheader("שחקנים")
    if not players:
        st.info("עדיין אין שחקנים — שישתפו את ה־QR")
    else:
        for p in players:
            st.markdown(f"• **{p}**")


def render_host_lobby(room: dict) -> None:
    code = room["code"]
    url = join_url(code)
    st.markdown(f'<div class="room-code">{code}</div>', unsafe_allow_html=True)
    st.markdown('<p class="muted">סירקו להצטרפות</p>', unsafe_allow_html=True)
    st.image(make_qr_image(url), width=260)
    st.code(url, language=None)

    players = db.list_players(code)
    render_players_list(players)

    if st.button("התחלת משחק", type="primary", key="start_game"):
        ok, msg = db.start_or_next_round(code)
        if ok:
            st.rerun()
        else:
            st.warning(msg)


def render_question(room: dict, my_name: str | None, is_host: bool) -> None:
    answerer = room.get("answerer") or ""
    question = room.get("question") or ""
    st.markdown(
        f'<div style="text-align:center"><span class="turn-badge">'
        f"תור של {answerer} לענות בקול"
        f"</span></div>",
        unsafe_allow_html=True,
    )
    if my_name and my_name == answerer:
        st.success("זה התור שלך — ענו בקול לחדר!")
    st.markdown(f'<div class="question-box">{question}</div>', unsafe_allow_html=True)

    if is_host:
        c1, c2 = st.columns(2)
        with c1:
            if st.button("סיבוב הבא", type="primary", key="next_round"):
                ok, msg = db.start_or_next_round(room["code"])
                if ok:
                    st.rerun()
                else:
                    st.warning(msg)
        with c2:
            if st.button("סיום משחק", key="end_game"):
                db.end_game(room["code"])
                st.rerun()


def render_ended(is_host: bool, code: str) -> None:
    st.header("המשחק הסתיים")
    st.markdown('<p class="muted">תודה ששיחקתם!</p>', unsafe_allow_html=True)
    if is_host:
        if st.button("חזרה ללובי והתחלה מחדש", type="primary"):
            db.back_to_lobby(code)
            st.rerun()
        if st.button("יציאה"):
            reset_session()
            st.rerun()


def reset_session() -> None:
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    init_session()
    st.query_params.clear()


@st.fragment(run_every=2)
def live_room(code: str, is_host: bool, player_name: str | None) -> None:
    room = db.get_room(code)
    if not room:
        st.error("החדר נעלם")
        return

    status = room["status"]
    st.caption(f"חדר {code} · מתעדכן אוטומטית")

    if status == "lobby":
        if is_host:
            render_host_lobby(room)
        else:
            st.info("ממתינים שהמנחה יתחיל…")
            render_players_list(db.list_players(code))
    elif status == "playing":
        if is_host:
            with st.expander("שחקנים ו־QR", expanded=False):
                url = join_url(code)
                st.image(make_qr_image(url), width=180)
                render_players_list(db.list_players(code))
        render_question(room, player_name, is_host)
    elif status == "ended":
        render_ended(is_host, code)
    else:
        st.write(status)


def main() -> None:
    db.init_db()
    init_session()

    role = st.session_state.role
    code = st.session_state.room_code

    if not role or not code:
        render_home()
        return

    is_host = role == "host"
    title = "מנחה" if is_host else st.session_state.player_name or "שחקן"
    st.title(f"🎲 {title}")

    top = st.columns([3, 1])
    with top[1]:
        if st.button("יציאה", key="leave"):
            reset_session()
            st.rerun()

    live_room(code, is_host, st.session_state.player_name)


main()
