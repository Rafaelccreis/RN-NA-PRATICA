import hmac
import html
import io
import os
import re
import sqlite3
import time as _time
import unicodedata
import zipfile
from contextlib import contextmanager
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

# ============================================================
# Diário do Recém-nascido
# ============================================================

APP_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("NEWBORN_DB_PATH", str(APP_DIR / "diario_recem_nascido.db")))
TZ = ZoneInfo("America/Sao_Paulo")

# Edite aqui os nomes dos bebês.
BABIES = ["Davi Lucca", "Leon"]

WEEKDAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
WEEKDAYS_FULL = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
                 "Sexta-feira", "Sábado", "Domingo"]
MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
          "agosto", "setembro", "outubro", "novembro", "dezembro"]
TABLES = {"events", "measures", "milestones", "appointments", "notes", "reminders"}
DATE_COLS = {"Data e horário", "Início"}
SCREENINGS = ["Teste do pezinho", "Teste da orelhinha", "Teste do olhinho",
              "Teste do coraçãozinho", "Teste da linguinha"]
VACCINES = ["BCG", "Hepatite B", "Pentavalente", "VIP (pólio)", "Pneumocócica", "Rotavírus", "Meningocócica C"]

st.set_page_config(
    page_title="Diário do Recém-nascido",
    page_icon="♡",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ------------------------------------------------------------
# Compatibilidade: versões novas do Streamlit trocaram
# use_container_width=True por width="stretch".
# ------------------------------------------------------------
def _st_version():
    out = []
    for part in st.__version__.split(".")[:2]:
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits or 0))
    return tuple(out)


FULL = {"width": "stretch"} if _st_version() >= (1, 50) else {"use_container_width": True}

# ------------------------------------------------------------
# Visual: azul bebê + branco sobre noite azulada
# ------------------------------------------------------------
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700&family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&display=swap');

:root {
  --night: #0A1220;
  --surface: #111C2F;
  --surface-2: #16253D;
  --line: rgba(156, 211, 245, .16);
  --baby: #9CD3F5;
  --baby-strong: #B9E3FA;
  --baby-soft: rgba(156, 211, 245, .10);
  --white: #F5FAFF;
  --muted: #9DB2C7;
  --display: 'Fraunces', Georgia, 'Times New Roman', serif;
  --body: 'Figtree', 'Segoe UI', system-ui, -apple-system, sans-serif;
}

.stApp {
  background:
    radial-gradient(900px 480px at 88% -8%, rgba(156,211,245,.10), transparent 60%),
    radial-gradient(700px 420px at -10% 108%, rgba(156,211,245,.06), transparent 60%),
    var(--night);
  color: var(--white);
  font-family: var(--body);
}
button, input, textarea, select { font-family: var(--body) !important; }
[data-testid="stHeader"] { background: transparent; }
.block-container { max-width: 1240px; padding-top: 2rem; padding-bottom: 3rem; }

h1, h2, h3, h4 {
  font-family: var(--display) !important;
  color: var(--white) !important;
  font-weight: 500 !important;
  letter-spacing: -.01em;
}
p, label, li { color: var(--white); }
[data-testid="stCaptionContainer"], .section-note { color: var(--muted) !important; }
a { color: var(--baby) !important; }

/* ---------- Hero ---------- */
.hero {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 28px;
  padding: 34px 38px 32px;
  margin: 0 0 26px 0;
  background:
    radial-gradient(520px 260px at 96% 0%, rgba(156,211,245,.22), transparent 65%),
    linear-gradient(135deg, #15253E 0%, #0F1A2D 70%);
  box-shadow: 0 20px 50px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.04);
}
.hero-date {
  display: inline-block;
  font-size: .86rem;
  font-weight: 600;
  color: var(--baby-strong);
  background: var(--baby-soft);
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 5px 14px;
  margin-bottom: 16px;
}
.hero h1 {
  margin: 0 !important;
  font-size: 2.7rem !important;
  line-height: 1.08;
  color: var(--white) !important;
}
.hero p {
  margin: 12px 0 0;
  max-width: 62ch;
  font-size: 1.04rem;
  line-height: 1.55;
  color: #C3D6E8 !important;
}
.hero-center { text-align: center; }
.hero-center p { margin-left: auto; margin-right: auto; }

/* ---------- Seções ---------- */
h3 { font-size: 1.45rem !important; margin-top: .4rem !important; }
.section-note { font-size: .95rem; margin: -6px 0 14px; }

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] {
  background: #0D1727;
  border-right: 1px solid var(--line);
}
.brand { font-family: var(--display); font-size: 1.45rem; color: var(--white); line-height: 1.15; }
.brand small { display: block; margin-top: 4px; font-family: var(--body); font-size: .85rem; color: var(--muted); }
.brand .heart { color: var(--baby); }

[data-testid="stSidebar"] [data-testid="stRadio"] > div[role="radiogroup"] { gap: 4px; }
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"] {
  width: 100%;
  padding: 10px 14px;
  border-radius: 12px;
  border: 1px solid transparent;
  transition: background .15s ease, border-color .15s ease;
  cursor: pointer;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child { display: none; }
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"]:hover { background: var(--baby-soft); }
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) {
  background: var(--baby-soft);
  border-color: var(--line);
  box-shadow: inset 3px 0 0 var(--baby);
}
[data-testid="stSidebar"] [data-testid="stRadio"] label p { font-weight: 500; }
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p { color: var(--baby-strong); font-weight: 650; }

/* ---------- Métricas ---------- */
div[data-testid="stMetric"] {
  background: linear-gradient(180deg, var(--surface-2), var(--surface));
  border: 1px solid var(--line);
  border-radius: 20px;
  padding: 18px 20px;
}
div[data-testid="stMetricLabel"] p { color: var(--muted) !important; font-weight: 500; }
div[data-testid="stMetricValue"] {
  font-family: var(--display);
  color: var(--baby-strong) !important;
  font-weight: 500;
}

/* ---------- Formulários e campos ---------- */
[data-testid="stForm"] {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 22px;
  padding: 24px 24px 18px;
}
div[data-baseweb="input"], div[data-baseweb="textarea"], div[data-baseweb="select"] > div {
  background: #0C1627 !important;
  border-color: var(--line) !important;
  border-radius: 12px !important;
}
div[data-baseweb="input"] input, div[data-baseweb="textarea"] textarea { color: var(--white) !important; }
div[data-baseweb="input"]:focus-within, div[data-baseweb="textarea"]:focus-within,
div[data-baseweb="select"] > div:focus-within {
  border-color: var(--baby) !important;
  box-shadow: 0 0 0 3px rgba(156,211,245,.20) !important;
}
label[data-testid="stWidgetLabel"] p { color: #D5E4F2 !important; font-weight: 500; }

/* ---------- Botões ---------- */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
  border-radius: 12px;
  font-weight: 650;
  min-height: 2.8rem;
  border: 1px solid var(--line);
  background: var(--surface-2);
  color: var(--white);
  transition: transform .12s ease, background .15s ease, border-color .15s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover {
  border-color: var(--baby);
  color: var(--baby-strong);
}
.stButton > button:focus-visible, .stDownloadButton > button:focus-visible,
.stFormSubmitButton > button:focus-visible {
  outline: 3px solid rgba(156,211,245,.45);
  outline-offset: 2px;
}
button[kind="primary"], button[kind="primaryFormSubmit"],
button[data-testid="stBaseButton-primary"], button[data-testid="stBaseButton-primaryFormSubmit"] {
  background: var(--baby) !important;
  border-color: var(--baby) !important;
  color: #0A1830 !important;
}
button[kind="primary"] p, button[kind="primaryFormSubmit"] p,
button[data-testid="stBaseButton-primary"] p, button[data-testid="stBaseButton-primaryFormSubmit"] p {
  color: #0A1830 !important;
}
button[kind="primary"]:hover, button[kind="primaryFormSubmit"]:hover,
button[data-testid="stBaseButton-primary"]:hover, button[data-testid="stBaseButton-primaryFormSubmit"]:hover {
  background: var(--baby-strong) !important;
  border-color: var(--baby-strong) !important;
  transform: translateY(-1px);
}

/* ---------- Tabelas, expanders, alertas ---------- */
[data-testid="stDataFrame"] {
  border: 1px solid var(--line);
  border-radius: 16px;
  overflow: hidden;
}
div[data-testid="stExpander"] {
  background: var(--surface);
  border: 1px solid var(--line) !important;
  border-radius: 16px;
}
div[data-testid="stAlert"] { border-radius: 14px; }
hr { border-color: var(--line) !important; }
[data-testid="stVerticalBlockBorderWrapper"] { border-color: var(--line) !important; border-radius: 18px !important; }

/* ---------- Componentes próprios ---------- */
.callout {
  margin: 18px 0 6px;
  padding: 15px 18px;
  border-radius: 16px;
  background: var(--baby-soft);
  border: 1px solid var(--line);
  border-left: 4px solid var(--baby);
  color: #D9E8F5;
  font-size: .95rem;
  line-height: 1.55;
}
.callout b { color: var(--white); }

.timer {
  text-align: center;
  padding: 30px 18px 26px;
  margin-bottom: 16px;
  border-radius: 24px;
  border: 1px solid var(--line);
  background:
    radial-gradient(340px 180px at 50% 0%, rgba(156,211,245,.20), transparent 70%),
    var(--surface);
}
.timer-num {
  display: block;
  font-family: var(--display);
  font-size: 4.2rem;
  line-height: 1;
  color: var(--baby-strong);
  font-variant-numeric: tabular-nums;
}
.timer-lbl { display: block; margin-top: 10px; color: var(--muted); font-size: .95rem; }

.rem {
  display: flex; align-items: center; gap: 14px;
  padding: 12px 16px; margin-bottom: 8px;
  border-radius: 14px;
  background: var(--surface);
  border: 1px solid var(--line);
}
.rem-time { font-family: var(--display); font-size: 1.2rem; color: var(--baby-strong); min-width: 3.6rem; }
.rem-title { flex: 1; color: var(--white); }
.pill {
  font-size: .78rem; font-weight: 600;
  padding: 3px 11px; border-radius: 999px;
  border: 1px solid var(--line); color: var(--muted);
}
.pill.now { background: var(--baby); color: #0A1830; border-color: var(--baby); }
.pill.soon { color: var(--baby-strong); background: var(--baby-soft); }

.note-meta { color: var(--muted); font-size: .85rem; margin-bottom: 6px; }
.note-title { font-family: var(--display); font-size: 1.2rem; color: var(--white); margin: 0 0 4px; }
.note-body { color: #D5E4F2; white-space: pre-wrap; line-height: 1.6; }

.small-footer { color: var(--muted) !important; font-size: .8rem; line-height: 1.5; }

@media (max-width: 700px) {
  .block-container { padding: 1rem .8rem 2.5rem; }
  .hero { padding: 24px 22px; border-radius: 22px; }
  .hero h1 { font-size: 2rem !important; }
  .timer-num { font-size: 3.2rem; }
}
@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; }
}

.baby-name { font-family: var(--display); font-size: 1.55rem; color: var(--baby-strong); margin: 0 0 12px; }
.pill-row { display: flex; flex-wrap: wrap; gap: 8px; }
.pill.done { background: var(--baby-soft); color: var(--baby-strong); border-color: var(--baby); }
[data-testid="stVerticalBlockBorderWrapper"] .timer-num { font-size: 3rem; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def now_local():
    return datetime.now(TZ).replace(tzinfo=None, microsecond=0)


def now_time():
    return now_local().time().replace(second=0)


def esc(value):
    return html.escape(str(value), quote=True)


def slug(text):
    norm = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", norm.lower()).strip("_")


def long_date(d):
    return f"{WEEKDAYS_FULL[d.weekday()]}, {d.day} de {MONTHS[d.month - 1]}"


def fmt_dt(value):
    try:
        return datetime.fromisoformat(str(value)).strftime("%d/%m/%Y às %H:%M")
    except Exception:
        return str(value)


def flash(message):
    st.session_state["_flash"] = message


def saved(message):
    flash(message)
    st.rerun()


@contextmanager
def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=20)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db():
    with db() as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            baby TEXT NOT NULL, category TEXT NOT NULL, started_at TEXT NOT NULL,
            ended_at TEXT, kind TEXT, detail TEXT, amount REAL, notes TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_events_cat ON events(category, started_at);
        CREATE TABLE IF NOT EXISTS measures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            baby TEXT NOT NULL, measured_on TEXT NOT NULL,
            weight_g REAL, length_cm REAL, head_cm REAL, notes TEXT
        );
        CREATE TABLE IF NOT EXISTS milestones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            baby TEXT NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL,
            done_on TEXT NOT NULL, notes TEXT
        );
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            baby TEXT NOT NULL, scheduled_at TEXT NOT NULL,
            doctor TEXT, reason TEXT NOT NULL, notes TEXT
        );
        CREATE TABLE IF NOT EXISTS app_state (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL, subject TEXT NOT NULL, content TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, reminder_time TEXT NOT NULL,
            days TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1
        );
        """)


def query_df(sql, params=()):
    with db() as con:
        return pd.read_sql_query(sql, con, params=params)


def execute(sql, params=()):
    with db() as con:
        return con.execute(sql, params).lastrowid


def get_state(key):
    with db() as con:
        row = con.execute("SELECT value FROM app_state WHERE key=?", (key,)).fetchone()
    return None if row is None else row["value"]


def set_state(key, value):
    execute(
        "INSERT INTO app_state(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def hero(title, subtitle, date_chip=True, center=False):
    chip = f'<div class="hero-date">{esc(long_date(now_local().date()))}</div>' if date_chip else ""
    cls = "hero hero-center" if center else "hero"
    st.markdown(
        f'<div class="{cls}">{chip}<h1>{esc(title)}</h1><p>{esc(subtitle)}</p></div>',
        unsafe_allow_html=True,
    )


def section(title, subtitle=None):
    st.subheader(title)
    if subtitle:
        st.markdown(f'<p class="section-note">{esc(subtitle)}</p>', unsafe_allow_html=True)


def callout(text, title=None):
    head = f"<b>{esc(title)}</b> " if title else ""
    st.markdown(f'<div class="callout">{head}{esc(text)}</div>', unsafe_allow_html=True)


def _row_label(row, cols, id_col):
    bits = []
    for c in cols[:2]:
        value = fmt_dt(row[c]) if c in DATE_COLS else str(row[c])
        bits.append(value if len(value) <= 40 else value[:37] + "…")
    return f"#{int(row[id_col])} · " + " · ".join(bits)


def _do_delete(table, select_key, confirm_key):
    if table in TABLES and select_key in st.session_state:
        execute(f"DELETE FROM {table} WHERE id=?", (int(st.session_state[select_key]),))
        flash("Registro excluído.")
    st.session_state[confirm_key] = False


def delete_box(df, table, label, id_col="id"):
    cols = [c for c in df.columns if c != id_col]
    labels = {int(r[id_col]): _row_label(r, cols, id_col) for _, r in df.iterrows()}
    scope = st.session_state.get("_page", table)
    select_key, confirm_key = f"delete_{table}_{scope}", f"confirm_{table}_{scope}"
    with st.expander(f"Excluir {label}"):
        st.selectbox("Registro", list(labels), format_func=labels.get, key=select_key)
        st.checkbox("Confirmo que quero excluir este registro", key=confirm_key)
        st.button(
            "Excluir registro",
            key=f"delete_btn_{table}_{scope}",
            disabled=not st.session_state.get(confirm_key, False),
            on_click=_do_delete,
            args=(table, select_key, confirm_key),
        )


def show_history(df, table, label="registro", id_col="id"):
    if df.empty:
        st.caption(f"Nenhum {label} cadastrado ainda. Use o formulário acima para criar o primeiro.")
        return
    display = df.drop(columns=[id_col], errors="ignore").copy()
    for col in display.columns:
        if col in DATE_COLS:
            display[col] = display[col].map(fmt_dt)
    st.dataframe(display, hide_index=True, **FULL)
    delete_box(df, table, label, id_col)


def trend_chart(df, x, series, y_title, height=280):
    long = df.melt(id_vars=[x], value_vars=series, var_name="Medida", value_name="Valor").dropna()
    palette = ["#9CD3F5", "#F5FAFF"]
    legend = alt.Legend(orient="top", title=None, labelColor="#D5E4F2") if len(series) > 1 else None
    chart = (
        alt.Chart(long)
        .mark_line(point=alt.OverlayMarkDef(filled=True, size=70), strokeWidth=2.5, interpolate="monotone")
        .encode(
            x=alt.X(f"{x}:T", title=None),
            y=alt.Y("Valor:Q", title=y_title, scale=alt.Scale(zero=False)),
            color=alt.Color("Medida:N", scale=alt.Scale(domain=series, range=palette[:len(series)]), legend=legend),
            tooltip=[
                alt.Tooltip(f"{x}:T", title="Data", format="%d/%m/%Y %H:%M"),
                alt.Tooltip("Medida:N", title="Medida"),
                alt.Tooltip("Valor:Q", title="Valor"),
            ],
        )
        .properties(height=height)
        .configure(background="transparent")
        .configure_view(strokeWidth=0)
        .configure_axis(
            labelColor="#9DB2C7", titleColor="#9DB2C7",
            gridColor="rgba(156,211,245,0.10)", domainColor="rgba(156,211,245,0.25)",
            tickColor="rgba(156,211,245,0.25)",
        )
    )
    st.altair_chart(chart, theme=None, **FULL)


def todays_reminders():
    now = now_local()
    day = WEEKDAYS[now.weekday()]
    df = query_df("SELECT title, reminder_time, days FROM reminders WHERE active=1 ORDER BY reminder_time")
    rows = [r for _, r in df.iterrows() if day in str(r["days"]).split(",")]
    return rows, now.strftime("%H:%M")


def render_reminders(rows, now_hm):
    for r in rows:
        t = str(r["reminder_time"])
        if t == now_hm:
            pill = '<span class="pill now">Agora</span>'
        elif t > now_hm:
            pill = '<span class="pill soon">Mais tarde</span>'
        else:
            pill = '<span class="pill">Já passou</span>'
        st.markdown(
            f'<div class="rem"><span class="rem-time">{esc(t)}</span>'
            f'<span class="rem-title">{esc(r["title"])}</span>{pill}</div>',
            unsafe_allow_html=True,
        )


# ------------------------------------------------------------
# Acesso
# ------------------------------------------------------------
def login_gate():
    configured = None
    try:
        configured = st.secrets.get("app_password") or st.secrets.get("APP_PASSWORD")
    except Exception:
        pass
    configured = configured or os.getenv("APP_PASSWORD")

    if not configured:
        hero("Diário do Recém-nascido", "Seu espaço de registros e acompanhamento.", date_chip=False)
        st.error("Defina uma senha antes de usar o diário.")
        st.code('app_password = "sua-senha-forte"', language="toml")
        st.caption("No Streamlit Cloud: Manage app → Settings → Secrets. Não publique a senha no código.")
        st.stop()

    if not st.session_state.get("authenticated", False):
        _, mid, _ = st.columns([1, 2.2, 1])
        with mid:
            hero("Diário do Recém-nascido",
                 "Um espaço calmo para acompanhar os primeiros dias dos bebês.",
                 date_chip=False, center=True)
            with st.form("login_form"):
                pwd = st.text_input("Senha de acesso", type="password")
                submit = st.form_submit_button("Entrar", type="primary", **FULL)
            if submit:
                if hmac.compare_digest(pwd.encode(), str(configured).encode()):
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    _time.sleep(1)
                    st.error("Senha incorreta. Confira e tente de novo.")
        st.stop()


def render_appointments(df):
    for _, r in df.iterrows():
        when_s = datetime.fromisoformat(str(r["scheduled_at"])).strftime("%d/%m %H:%M")
        st.markdown(
            f'<div class="rem"><span class="rem-time" style="min-width:8rem">{esc(when_s)}</span>'
            f'<span class="rem-title">{esc(r["baby"])}: {esc(r["reason"])}</span>'
            f'<span class="pill soon">{esc(since_future(r["scheduled_at"]))}</span></div>',
            unsafe_allow_html=True,
        )


def since_future(iso):
    delta = datetime.fromisoformat(str(iso)) - now_local()
    days = delta.days
    if days >= 1:
        return f"em {days} d"
    mins = max(0, int(delta.total_seconds() // 60))
    return f"em {mins // 60} h {mins % 60:02d} min" if mins >= 60 else f"em {mins} min"


init_db()
login_gate()

today = now_local().date()
today_s = today.isoformat()

PAGES = [
    "Visão geral", "Alimentação", "Fraldas", "Sono", "Crescimento", "Temperatura",
    "Medicações", "Cuidados e rotina", "Saúde e sinais", "Vacinas e triagens",
    "Consultas", "Anotações", "Lembretes", "Relatórios",
]
with st.sidebar:
    st.markdown(
        '<div class="brand"><span class="heart">♡</span> Diário do Recém-nascido'
        '<small>Acompanhamento dos bebês</small></div>',
        unsafe_allow_html=True,
    )
    st.divider()
    page = st.radio("Menu", PAGES, label_visibility="collapsed")
    st.divider()
    if st.button("Sair da conta", **FULL):
        st.session_state.authenticated = False
        st.rerun()
    st.markdown(
        '<p class="small-footer">Este diário organiza informações para consulta. '
        'Não substitui a avaliação ou a orientação do pediatra.</p>',
        unsafe_allow_html=True,
    )

st.session_state["_page"] = page
_msg = st.session_state.pop("_flash", None)
if _msg:
    st.toast(_msg)


# ------------------------------------------------------------
# Auxiliares dos registros
# ------------------------------------------------------------
def pick_baby(key, options=None):
    return st.selectbox("Bebê", options or BABIES, key=key)


def when(prefix, title=None):
    if title:
        st.markdown(f"**{title}**")
    c1, c2 = st.columns(2)
    d = c1.date_input("Data", value=today, format="DD/MM/YYYY", key=f"{prefix}_d")
    t = c2.time_input("Horário", value=now_time(), step=60, key=f"{prefix}_t")
    return datetime.combine(d, t)


def add_event(baby, cat, start, kind=None, detail=None, end=None, amount=None, notes=""):
    execute(
        "INSERT INTO events(baby,category,started_at,ended_at,kind,detail,amount,notes) VALUES(?,?,?,?,?,?,?,?)",
        (baby, cat, start.isoformat(sep=" "), end.isoformat(sep=" ") if end else None,
         kind, detail, amount, (notes or "").strip()),
    )


def since(iso):
    try:
        delta = now_local() - datetime.fromisoformat(str(iso))
    except Exception:
        return "—"
    mins = max(0, int(delta.total_seconds() // 60))
    if mins < 60:
        return f"há {mins} min"
    h, m = divmod(mins, 60)
    if h < 24:
        return f"há {h} h {m:02d} min"
    d, h = divmod(h, 24)
    return f"há {d} d {h} h"


def fmt_hm(minutes):
    h, m = divmod(int(minutes), 60)
    return f"{h} h {m:02d} min"


def filt(df):
    if df.empty:
        return df
    sel = st.selectbox("Filtrar por bebê", ["Todos"] + BABIES, key=f"flt_{page}")
    return df if sel == "Todos" else df[df["Bebê"] == sel]


def add_duration(df):
    if df.empty:
        return df.drop(columns=["ended_at"])
    mins = (pd.to_datetime(df["ended_at"]) - pd.to_datetime(df["Data e horário"])).dt.total_seconds() / 60
    df = df.copy()
    df.insert(df.columns.get_loc("ended_at"), "Duração (min)", mins.round().astype("Int64"))
    return df.drop(columns=["ended_at"])


def day_summary(df, **aggs):
    d = df.copy()
    d["_dia"] = pd.to_datetime(d["Data e horário"]).dt.date
    g = (d.groupby(["_dia", "Bebê"]).agg(**aggs).reset_index()
          .sort_values(["_dia", "Bebê"], ascending=[False, True]).head(14))
    g.insert(0, "Dia", g.pop("_dia").map(lambda x: x.strftime("%d/%m/%Y")))
    return g


def baby_trend(df, xcol, ycol, y_title):
    d = df.copy()
    d["Data"] = pd.to_datetime(d[xcol])
    wide = d.pivot_table(index="Data", columns="Bebê", values=ycol, aggfunc="mean").reset_index()
    wide.columns.name = None
    series = [b for b in BABIES if b in wide.columns]
    if series:
        trend_chart(wide, "Data", series, y_title)


def baby_title(name):
    st.markdown(f'<div class="baby-name">{esc(name)}</div>', unsafe_allow_html=True)


@st.fragment(run_every=1)
def live_clock(start_iso, label):
    start = datetime.fromisoformat(start_iso)
    s = max(0, int((now_local() - start).total_seconds()))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    clock = f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"
    st.markdown(
        f'<div class="timer"><span class="timer-num">{clock}</span>'
        f'<span class="timer-lbl">{esc(label)} {start.strftime("%H:%M")}</span></div>',
        unsafe_allow_html=True,
    )


def _field(spec, key):
    if spec.get("options"):
        return st.selectbox(spec["label"], spec["options"], key=key)
    return st.text_input(spec["label"], placeholder=spec.get("ph", ""), key=key)


def event_page(cat, title, subtitle, noun, done, kind, detail=None, amount=None,
               summary=None, after=None, note=None):
    """Página padrão: formulário + resumo por dia + histórico (tabela events)."""
    hero(title, subtitle)
    with st.form(f"{cat}_form", clear_on_submit=True):
        baby = pick_baby(f"{cat}_baby")
        start = when(cat)
        kind_v = _field(kind, f"{cat}_kind")
        detail_v = _field(detail, f"{cat}_detail") if detail else None
        amt = None
        if amount:
            amt = st.number_input(amount["label"], min_value=amount["min"], max_value=amount["max"],
                                  value=None, step=amount["step"], placeholder=amount.get("ph"),
                                  key=f"{cat}_amt")
        notes = st.text_area("Observações", key=f"{cat}_notes")
        if st.form_submit_button(f"Salvar {noun}", type="primary", **FULL):
            if not kind.get("options") and not (kind_v or "").strip():
                st.error(f"Preencha o campo “{kind['label']}”.")
            elif amount and amount.get("required") and amt is None:
                st.error(f"Preencha o campo “{amount['label']}”.")
            else:
                add_event(baby, cat, start, kind=(kind_v or "").strip(),
                          detail=(detail_v or "").strip() if detail else None,
                          amount=float(amt) if amt is not None else None, notes=notes)
                saved(done)
    if note:
        callout(note, title="Importante.")

    sql = f"id, started_at AS 'Data e horário', baby AS 'Bebê', kind AS '{kind['label']}'"
    if detail:
        sql += f", detail AS '{detail['label']}'"
    if amount:
        sql += f", amount AS '{amount['label']}'"
    sql += ", notes AS 'Observações'"
    df = filt(query_df(f"SELECT {sql} FROM events WHERE category=? ORDER BY started_at DESC", (cat,)))
    if summary and not df.empty:
        section("Resumo por dia")
        st.dataframe(summary(df), hide_index=True, **FULL)
    section("Histórico")
    show_history(df, "events", label=noun)
    if after and not df.empty:
        st.write("")
        after(df)


# ------------------------------------------------------------
# VISÃO GERAL
# ------------------------------------------------------------
if page == "Visão geral":
    hero("Os primeiros dias", "Veja como cada bebê está hoje: mamadas, fraldas, sono e as medidas mais recentes.")
    for col, baby in zip(st.columns(len(BABIES), gap="large"), BABIES):
        with col:
            baby_title(baby)
            ev = query_df("SELECT category, kind, started_at, ended_at, amount FROM events "
                          "WHERE baby=? AND substr(started_at,1,10)=?", (baby, today_s))

            def last(cat, baby=baby):
                return query_df("SELECT started_at, amount FROM events WHERE baby=? AND category=? "
                                "ORDER BY started_at DESC LIMIT 1", (baby, cat))

            lf, lt = last("feed"), last("temp")
            feeds = ev[ev["category"] == "feed"]
            dia = ev[ev["category"] == "diaper"]["kind"]
            sl = ev[(ev["category"] == "sleep") & ev["ended_at"].notna()]
            sleep_min = 0
            if not sl.empty:
                sleep_min = (pd.to_datetime(sl["ended_at"]) - pd.to_datetime(sl["started_at"])).dt.total_seconds().sum() / 60
            wt = query_df("SELECT weight_g FROM measures WHERE baby=? AND weight_g IS NOT NULL "
                          "ORDER BY measured_on DESC, id DESC LIMIT 1", (baby,))
            temp_ok = not lt.empty and pd.notna(lt.iloc[0]["amount"])

            a, b = st.columns(2)
            a.metric("Última mamada", since(lf.iloc[0]["started_at"]) if not lf.empty else "—")
            b.metric("Mamadas hoje", len(feeds))
            c, d = st.columns(2)
            c.metric("Xixis hoje", int(dia.isin(["Xixi", "Xixi e cocô"]).sum()))
            d.metric("Cocôs hoje", int(dia.isin(["Cocô", "Xixi e cocô"]).sum()))
            e, f = st.columns(2)
            e.metric("Sono hoje", fmt_hm(sleep_min) if sleep_min else "—")
            f.metric("Leite hoje (ml)", f"{feeds['amount'].sum():g}" if feeds["amount"].notna().any() else "—")
            g, h = st.columns(2)
            g.metric("Último peso", f"{int(wt.iloc[0]['weight_g'])} g" if not wt.empty else "—")
            h.metric("Última temperatura", f"{lt.iloc[0]['amount']:g} °C" if temp_ok else "—")
    callout("Os números aparecem exatamente como foram registrados. O aplicativo não interpreta medidas nem "
            "recomenda condutas.")

    rows, now_hm = todays_reminders()
    if rows:
        st.write("")
        section("Lembretes de hoje")
        render_reminders(rows, now_hm)
    ap = query_df("SELECT baby, scheduled_at, reason FROM appointments WHERE scheduled_at>=? "
                  "ORDER BY scheduled_at LIMIT 3", (now_local().isoformat(sep=" "),))
    if not ap.empty:
        st.write("")
        section("Próximas consultas")
        render_appointments(ap)

# ------------------------------------------------------------
# ALIMENTAÇÃO
# ------------------------------------------------------------
elif page == "Alimentação":
    hero("Alimentação", "Registre cada mamada: peito, mamadeira, duração e quantidade.")
    with st.form("feed_form", clear_on_submit=True):
        baby = pick_baby("feed_baby")
        start = when("feed")
        kind = st.selectbox("Tipo", ["Peito esquerdo", "Peito direito", "Ambos os peitos",
                                     "Mamadeira com leite materno", "Mamadeira com fórmula"], key="feed_kind")
        c1, c2 = st.columns(2)
        mins = c1.number_input("Duração (min, opcional)", min_value=0, max_value=240, value=None,
                               step=1, placeholder="Ex.: 15", key="feed_min")
        ml = c2.number_input("Quantidade (ml, opcional)", min_value=0, max_value=500, value=None,
                             step=5, placeholder="Ex.: 60", key="feed_ml")
        notes = st.text_area("Observações", placeholder="Ex.: mamou bem, regurgitou...", key="feed_notes")
        if st.form_submit_button("Salvar mamada", type="primary", **FULL):
            add_event(baby, "feed", start, kind=kind,
                      end=start + timedelta(minutes=int(mins)) if mins else None,
                      amount=float(ml) if ml else None, notes=notes)
            saved("Mamada salva.")

    df = query_df("SELECT id, started_at AS 'Data e horário', baby AS 'Bebê', kind AS 'Tipo', ended_at, "
                  "amount AS 'Quantidade (ml)', notes AS 'Observações' FROM events "
                  "WHERE category='feed' ORDER BY started_at DESC")
    df = filt(add_duration(df))
    if not df.empty:
        section("Resumo por dia")
        st.dataframe(day_summary(df, Mamadas=("id", "count"), **{"Total (ml)": ("Quantidade (ml)", "sum")}),
                     hide_index=True, **FULL)
    section("Histórico")
    show_history(df, "events", label="mamada")

# ------------------------------------------------------------
# FRALDAS
# ------------------------------------------------------------
elif page == "Fraldas":
    event_page(
        "diaper", "Fraldas", "Registre xixi e cocô para acompanhar a rotina de cada bebê.",
        "troca", "Troca de fralda salva.",
        kind={"label": "Tipo", "options": ["Xixi", "Cocô", "Xixi e cocô"]},
        detail={"label": "Aspecto do cocô (opcional)",
                "options": ["Não se aplica", "Preto-esverdeado", "Amarelo", "Mostarda", "Verde",
                            "Marrom", "Pastoso", "Líquido", "Outro"]},
        summary=lambda df: day_summary(
            df, Trocas=("id", "count"),
            Xixi=("Tipo", lambda s: int(s.isin(["Xixi", "Xixi e cocô"]).sum())),
            **{"Cocô": ("Tipo", lambda s: int(s.isin(["Cocô", "Xixi e cocô"]).sum()))}),
    )

# ------------------------------------------------------------
# SONO
# ------------------------------------------------------------
elif page == "Sono":
    hero("Sono", "Use o cronômetro de cada bebê ou registre um sono que já aconteceu.")
    for col, baby in zip(st.columns(len(BABIES), gap="large"), BABIES):
        key = f"sleep_start_{slug(baby)}"
        with col, st.container(border=True):
            baby_title(baby)
            running = get_state(key)
            if running:
                live_clock(running, "Dormindo desde")
                if st.button("Acordou: salvar sono", key=f"wake_{slug(baby)}", type="primary", **FULL):
                    add_event(baby, "sleep", datetime.fromisoformat(running), end=now_local())
                    set_state(key, "")
                    saved(f"Sono de {baby} salvo.")
                if st.button("Descartar", key=f"drop_{slug(baby)}", **FULL):
                    set_state(key, "")
                    saved("Cronômetro descartado.")
            else:
                st.caption("Toque quando o bebê começar a dormir.")
                if st.button("Começou a dormir", key=f"sleep_{slug(baby)}", type="primary", **FULL):
                    set_state(key, now_local().isoformat(sep=" "))
                    st.rerun()

    st.write("")
    section("Registrar um sono que já aconteceu")
    with st.form("sleep_form", clear_on_submit=True):
        baby = pick_baby("sl_baby")
        start = when("sl_a", "Quando dormiu")
        end = when("sl_b", "Quando acordou")
        notes = st.text_input("Observações (opcional)", key="sl_notes")
        if st.form_submit_button("Salvar sono", type="primary", **FULL):
            if end <= start:
                st.error("O horário em que acordou precisa ser depois do horário em que dormiu.")
            else:
                add_event(baby, "sleep", start, end=end, notes=notes)
                saved("Sono salvo.")

    df = query_df("SELECT id, started_at AS 'Data e horário', baby AS 'Bebê', ended_at, notes AS 'Observações' "
                  "FROM events WHERE category='sleep' ORDER BY started_at DESC")
    df = filt(add_duration(df))
    if not df.empty:
        section("Resumo por dia")
        st.dataframe(day_summary(df, Sonos=("id", "count"),
                                 **{"Total (h)": ("Duração (min)", lambda s: round(float(s.sum()) / 60, 1))}),
                     hide_index=True, **FULL)
    section("Histórico")
    show_history(df, "events", label="sono")

# ------------------------------------------------------------
# CRESCIMENTO
# ------------------------------------------------------------
elif page == "Crescimento":
    hero("Crescimento", "Peso, comprimento e perímetro cefálico ao longo do tempo.")
    with st.form("measure_form", clear_on_submit=True):
        baby = pick_baby("ms_baby")
        dt = st.date_input("Data da medição", value=today, format="DD/MM/YYYY", key="ms_date")
        c1, c2, c3 = st.columns(3)
        w = c1.number_input("Peso (g)", min_value=500, max_value=10000, value=None, step=10,
                            placeholder="Ex.: 3250", key="ms_w")
        ln = c2.number_input("Comprimento (cm)", min_value=20.0, max_value=80.0, value=None, step=0.1,
                             placeholder="Ex.: 49.5", key="ms_l")
        hd = c3.number_input("Perímetro cefálico (cm)", min_value=20.0, max_value=60.0, value=None, step=0.1,
                             placeholder="Ex.: 34.0", key="ms_h")
        notes = st.text_area("Observações", placeholder="Ex.: pesagem na consulta, balança da farmácia...",
                             key="ms_notes")
        if st.form_submit_button("Salvar medidas", type="primary", **FULL):
            if w is None and ln is None and hd is None:
                st.error("Informe pelo menos uma medida.")
            else:
                execute("INSERT INTO measures(baby,measured_on,weight_g,length_cm,head_cm,notes) VALUES(?,?,?,?,?,?)",
                        (baby, dt.isoformat(), float(w) if w is not None else None,
                         float(ln) if ln is not None else None, float(hd) if hd is not None else None,
                         notes.strip()))
                saved("Medidas salvas.")

    df = query_df("SELECT id, measured_on AS 'Data', baby AS 'Bebê', weight_g AS 'Peso (g)', "
                  "length_cm AS 'Comprimento (cm)', head_cm AS 'Perímetro cefálico (cm)', notes AS 'Observações' "
                  "FROM measures ORDER BY measured_on DESC, id DESC")
    df = filt(df)
    section("Histórico")
    if df.empty:
        st.caption("Nenhuma medida cadastrada ainda. Use o formulário acima para criar a primeira.")
    else:
        raw = df.copy()
        df = df.copy()
        df.insert(4, "Variação do peso (g)", df.sort_values("Data").groupby("Bebê")["Peso (g)"].diff())
        df["Data"] = pd.to_datetime(df["Data"]).dt.strftime("%d/%m/%Y")
        show_history(df, "measures", label="medida")
        if raw["Peso (g)"].notna().any():
            st.write("")
            section("Evolução do peso")
            baby_trend(raw, "Data", "Peso (g)", "gramas")

# ------------------------------------------------------------
# TEMPERATURA
# ------------------------------------------------------------
elif page == "Temperatura":
    event_page(
        "temp", "Temperatura", "Anote a temperatura e o local da medição.", "medição", "Temperatura salva.",
        kind={"label": "Local da medição", "options": ["Axilar", "Retal", "Timpânica", "Testa", "Outro"]},
        amount={"label": "Temperatura (°C)", "min": 30.0, "max": 45.0, "step": 0.1, "ph": "Ex.: 36.8", "required": True},
        note="Febre em recém-nascido exige contato imediato com o pediatra ou com um serviço de urgência. "
             "Não espere nem trate por conta própria.",
        after=lambda df: (section("Evolução"), baby_trend(df, "Data e horário", "Temperatura (°C)", "°C")),
    )

# ------------------------------------------------------------
# MEDICAÇÕES
# ------------------------------------------------------------
elif page == "Medicações":
    event_page(
        "med", "Medicações e vitaminas", "Registre o que foi dado, a dose e o horário.", "dose", "Dose registrada.",
        kind={"label": "Medicamento ou vitamina", "options": None, "ph": "Ex.: vitamina D"},
        detail={"label": "Dose", "options": None, "ph": "Ex.: 2 gotas, conforme a prescrição"},
        note="Registre apenas o que o pediatra prescreveu e siga a dose indicada por ele. Este registro serve para "
             "lembrar o que já foi dado, não para definir doses.",
    )

# ------------------------------------------------------------
# CUIDADOS E ROTINA
# ------------------------------------------------------------
elif page == "Cuidados e rotina":
    event_page(
        "care", "Cuidados e rotina", "Banho, coto umbilical, barriguinha para baixo, choro e outros cuidados.",
        "cuidado", "Cuidado registrado.",
        kind={"label": "Cuidado", "options": ["Banho", "Curativo do coto umbilical", "Barriguinha para baixo",
                                              "Banho de sol", "Choro ou cólica", "Massagem", "Outro"]},
        amount={"label": "Duração (min, opcional)", "min": 0, "max": 600, "step": 1, "ph": "Ex.: 10"},
    )

# ------------------------------------------------------------
# SAÚDE E SINAIS
# ------------------------------------------------------------
elif page == "Saúde e sinais":
    event_page(
        "health", "Saúde e sinais", "Anote o que observou na pele, na respiração, na digestão e no coto umbilical.",
        "observação", "Observação salva.",
        kind={"label": "O que observou", "options": [
            "Pele ou olhos amarelados", "Regurgitação", "Vômito", "Engasgo", "Cólica", "Assadura",
            "Congestão nasal", "Olhos com secreção", "Coto umbilical", "Outro"]},
        detail={"label": "Intensidade percebida", "options": ["Leve", "Moderado", "Intenso", "Não sei avaliar"]},
        note="Pele ou olhos amarelados, febre, recusa de mamar, muita sonolência, dificuldade para respirar, "
             "vômitos fortes ou qualquer sinal que preocupe exigem contato imediato com o pediatra ou com um "
             "serviço de urgência.",
    )

# ------------------------------------------------------------
# VACINAS E TRIAGENS
# ------------------------------------------------------------
elif page == "Vacinas e triagens":
    hero("Vacinas e triagens", "Acompanhe as triagens neonatais e as vacinas de cada bebê.")
    done_df = query_df("SELECT baby, name, done_on FROM milestones WHERE kind='Triagem'")
    section("Triagens neonatais")
    for col, baby in zip(st.columns(len(BABIES), gap="large"), BABIES):
        with col:
            baby_title(baby)
            pills = ""
            for s in SCREENINGS:
                r = done_df[(done_df["baby"] == baby) & (done_df["name"] == s)]
                if r.empty:
                    pills += f'<span class="pill">{esc(s)}: não registrado</span>'
                else:
                    d = pd.to_datetime(r.iloc[0]["done_on"]).strftime("%d/%m")
                    pills += f'<span class="pill done">{esc(s)} ✓ {d}</span>'
            st.markdown(f'<div class="pill-row">{pills}</div>', unsafe_allow_html=True)
    st.write("")
    section("Registrar vacina ou triagem")
    with st.form("mile_form", clear_on_submit=True):
        baby = pick_baby("ml_baby")
        name = st.selectbox("Qual?", SCREENINGS + VACCINES + ["Outro (digitar abaixo)"], key="ml_name")
        other = st.text_input("Nome, se escolheu “Outro”", key="ml_other")
        dt = st.date_input("Data", value=today, format="DD/MM/YYYY", key="ml_date")
        notes = st.text_area("Lote, local, resultado ou observações", key="ml_notes")
        if st.form_submit_button("Salvar registro", type="primary", **FULL):
            if name.startswith("Outro") and not other.strip():
                st.error("Digite o nome da vacina ou triagem.")
            else:
                final = other.strip() if name.startswith("Outro") else name
                kind = "Triagem" if name in SCREENINGS else ("Vacina" if name in VACCINES else "Outro")
                execute("INSERT INTO milestones(baby,kind,name,done_on,notes) VALUES(?,?,?,?,?)",
                        (baby, kind, final, dt.isoformat(), notes.strip()))
                saved("Registro salvo.")
    section("Histórico")
    df = filt(query_df("SELECT id, done_on AS 'Data', baby AS 'Bebê', kind AS 'Tipo', name AS 'Nome', "
                       "notes AS 'Observações' FROM milestones ORDER BY done_on DESC, id DESC"))
    if not df.empty:
        df["Data"] = pd.to_datetime(df["Data"]).dt.strftime("%d/%m/%Y")
    show_history(df, "milestones", label="registro")

# ------------------------------------------------------------
# CONSULTAS
# ------------------------------------------------------------
elif page == "Consultas":
    hero("Consultas", "Marque as consultas e exames e guarde o que foi orientado.")
    with st.form("appt_form", clear_on_submit=True):
        baby = pick_baby("ap_baby", BABIES + ["Os dois"])
        start = when("ap")
        c1, c2 = st.columns(2)
        doctor = c1.text_input("Profissional ou local", placeholder="Ex.: Dra. Ana, pediatra", key="ap_doc")
        reason = c2.text_input("Motivo", placeholder="Ex.: Consulta de rotina", key="ap_reason")
        notes = st.text_area("Orientações ou observações", key="ap_notes")
        if st.form_submit_button("Salvar consulta", type="primary", **FULL):
            if not reason.strip():
                st.error("Informe o motivo da consulta.")
            else:
                execute("INSERT INTO appointments(baby,scheduled_at,doctor,reason,notes) VALUES(?,?,?,?,?)",
                        (baby, start.isoformat(sep=" "), doctor.strip(), reason.strip(), notes.strip()))
                saved("Consulta salva.")
    up = query_df("SELECT baby, scheduled_at, reason FROM appointments WHERE scheduled_at>=? "
                  "ORDER BY scheduled_at", (now_local().isoformat(sep=" "),))
    if not up.empty:
        section("Próximas")
        render_appointments(up)
        st.write("")
    section("Histórico")
    df = query_df("SELECT id, scheduled_at AS 'Data e horário', baby AS 'Bebê', doctor AS 'Profissional ou local', "
                  "reason AS 'Motivo', notes AS 'Orientações' FROM appointments ORDER BY scheduled_at DESC")
    show_history(df, "appointments", label="consulta")

elif page == "Anotações":
    hero("Anotações", "Guarde dúvidas, orientações recebidas e informações para a próxima consulta.")
    with st.form("note_form", clear_on_submit=True):
        subject = st.text_input("Assunto", placeholder="Ex.: Dúvidas para a próxima consulta", key="note_subject")
        content = st.text_area("Anotação", height=150, key="note_content")
        if st.form_submit_button("Salvar anotação", type="primary", **FULL):
            if not subject.strip() or not content.strip():
                st.error("Preencha o assunto e a anotação.")
            else:
                execute("INSERT INTO notes(created_at,subject,content) VALUES(?,?,?)",
                        (now_local().isoformat(sep=" "), subject.strip(), content.strip()))
                saved("Anotação salva.")

    section("Anotações salvas")
    df = query_df("SELECT id, created_at AS 'Data e horário', subject AS 'Assunto', content AS 'Anotação' "
                  "FROM notes ORDER BY created_at DESC")
    if df.empty:
        st.caption("Nenhuma anotação salva ainda. Use o formulário acima para criar a primeira.")
    else:
        for _, row in df.iterrows():
            with st.container(border=True):
                st.markdown(
                    f'<div class="note-meta">{esc(fmt_dt(row["Data e horário"]))}</div>'
                    f'<div class="note-title">{esc(row["Assunto"])}</div>'
                    f'<div class="note-body">{esc(row["Anotação"])}</div>',
                    unsafe_allow_html=True,
                )
        delete_box(df, "notes", "anotação")

# ------------------------------------------------------------
# LEMBRETES
# ------------------------------------------------------------
elif page == "Lembretes":
    hero("Lembretes", "Organize lembretes que ficam visíveis dentro do aplicativo.")
    callout("Os lembretes aparecem quando você abre o aplicativo. Esta versão não envia notificações "
            "com o navegador fechado.")
    st.write("")
    with st.form("reminder_form", clear_on_submit=True):
        title = st.text_input("O que deseja lembrar?", placeholder="Ex.: Vitamina D (conforme a prescrição)",
                              key="rem_title")
        c1, c2 = st.columns(2)
        rtime = c1.time_input("Horário", value=time(8, 0), step=60, key="rem_time")
        days = c2.multiselect("Repetir nos dias", WEEKDAYS, default=WEEKDAYS, key="rem_days")
        if st.form_submit_button("Criar lembrete", type="primary", **FULL):
            if not title.strip() or not days:
                st.error("Informe o lembrete e selecione ao menos um dia.")
            else:
                ordered = [d for d in WEEKDAYS if d in days]
                execute("INSERT INTO reminders(title,reminder_time,days,active) VALUES(?,?,?,1)",
                        (title.strip(), rtime.strftime("%H:%M"), ",".join(ordered)))
                saved("Lembrete criado.")

    rows, now_hm = todays_reminders()
    if rows:
        section("Para hoje")
        render_reminders(rows, now_hm)
        st.write("")

    section("Todos os lembretes")
    df = query_df("SELECT id, title AS 'Lembrete', reminder_time AS 'Horário', days AS 'Dias', active "
                  "FROM reminders ORDER BY reminder_time")
    if df.empty:
        st.caption("Você ainda não criou lembretes.")
    else:
        view = df.copy()
        view["Status"] = view["active"].map({1: "Ativo", 0: "Pausado"})
        show_history(view[["id", "Lembrete", "Horário", "Dias", "Status"]], "reminders", label="lembrete")
        labels = {int(r["id"]): f'#{int(r["id"])} · {r["Lembrete"]} ({r["Horário"]})' for _, r in df.iterrows()}
        st.write("")
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        chosen = c1.selectbox("Lembrete para ativar ou pausar", list(labels),
                              format_func=labels.get, key="rem_toggle_sel")
        if c2.button("Ativar / pausar", **FULL):
            execute("UPDATE reminders SET active=CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id=?", (int(chosen),))
            saved("Status do lembrete atualizado.")

# ------------------------------------------------------------
# RELATÓRIOS
# ------------------------------------------------------------
elif page == "Relatórios":
    hero("Relatórios", "Consulte e baixe os registros para levar às consultas do pediatra.")

    def ev_sql(cat, cols):
        return f"SELECT {cols} FROM events WHERE category='{cat}' ORDER BY started_at"

    tables = {
        "Alimentação": ev_sql("feed", "started_at AS inicio, ended_at AS fim, baby AS bebe, kind AS tipo, amount AS ml, notes AS observacoes"),
        "Fraldas": ev_sql("diaper", "started_at AS data_hora, baby AS bebe, kind AS tipo, detail AS aspecto, notes AS observacoes"),
        "Sono": ev_sql("sleep", "started_at AS inicio, ended_at AS fim, baby AS bebe, notes AS observacoes"),
        "Crescimento": "SELECT measured_on AS data, baby AS bebe, weight_g AS peso_g, length_cm AS comprimento_cm, head_cm AS perimetro_cefalico_cm, notes AS observacoes FROM measures ORDER BY measured_on",
        "Temperatura": ev_sql("temp", "started_at AS data_hora, baby AS bebe, kind AS local, amount AS graus_c, notes AS observacoes"),
        "Medicações": ev_sql("med", "started_at AS data_hora, baby AS bebe, kind AS medicamento, detail AS dose, notes AS observacoes"),
        "Cuidados": ev_sql("care", "started_at AS data_hora, baby AS bebe, kind AS cuidado, amount AS minutos, notes AS observacoes"),
        "Saúde e sinais": ev_sql("health", "started_at AS data_hora, baby AS bebe, kind AS observacao, detail AS intensidade, notes AS detalhes"),
        "Vacinas e triagens": "SELECT done_on AS data, baby AS bebe, kind AS tipo, name AS nome, notes AS observacoes FROM milestones ORDER BY done_on",
        "Consultas": "SELECT scheduled_at AS data_hora, baby AS bebe, doctor AS profissional, reason AS motivo, notes AS orientacoes FROM appointments ORDER BY scheduled_at",
        "Anotações": "SELECT created_at AS data_hora, subject AS assunto, content AS anotacao FROM notes ORDER BY created_at",
        "Lembretes": "SELECT title AS lembrete, reminder_time AS horario, days AS dias, active AS ativo FROM reminders ORDER BY reminder_time",
    }
    all_data = {label: query_df(sql) for label, sql in tables.items()}

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for label, df in all_data.items():
            archive.writestr(f"{slug(label)}.csv", df.to_csv(index=False).encode("utf-8-sig"))
    st.download_button(
        "Baixar backup completo (ZIP)", data=buffer.getvalue(),
        file_name=f"backup_diario_recem_nascido_{today_s}.zip", mime="application/zip",
        type="primary", **FULL,
    )
    st.caption("O backup reúne todos os registros em arquivos CSV. Guarde-o em um local seguro.")
    st.write("")
    for label, df in all_data.items():
        with st.expander(f"{label} · {len(df)} registro(s)"):
            if df.empty:
                st.caption("Sem registros.")
            else:
                st.dataframe(df, hide_index=True, **FULL)
                st.download_button(f"Baixar {label} em CSV", df.to_csv(index=False).encode("utf-8-sig"),
                                   file_name=f"{slug(label)}.csv", mime="text/csv", key=f"csv_{slug(label)}")

st.divider()
st.markdown(
    '<p class="small-footer">Diário do Recém-nascido · Ferramenta de organização pessoal. Os registros não '
    'constituem diagnóstico nem orientação médica. Em caso de dúvida ou sinal de alerta, contate o pediatra.</p>',
    unsafe_allow_html=True,
)
