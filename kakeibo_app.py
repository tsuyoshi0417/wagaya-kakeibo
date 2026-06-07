# -*- coding: utf-8 -*-
"""
わが家の家計簿アプリ（フェーズ1）
- 入力はGoogleフォーム/将来LINE。このアプリは「見る・管理する」担当。
- 妻モード = 1画面（あと使える を大きく）。俺モード(つよし) = タブで作り込み。
- 方式は封筒式：あと使える = 封筒 − 今月使った合計（収入は使わない）。
- 色＝黄色（アクセントのみ・文字は濃色・背景オフホワイト＝可読性死守）。

★ プライバシー設計（公開リポジトリでも家計が漏れないように）★
- 家計の実数（家賃・封筒額・記録）と フォームURL は、すべて
  非公開の Google スプレッドシート / Streamlit Secrets 側に置く。
  このコードには家計の実数を一切書かない（あるのは計算ロジックとデモ用の例だけ）。
- アプリ全体を「あいことば（KAKEIBO_PIN）」で保護＝URLを知っても中は見られない。

ローカル確認：
  "/Users/cotonoha/Desktop/cotonoha project/.venv/bin/streamlit" run kakeibo_app.py
"""
import os
import datetime as dt
import streamlit as st
import streamlit.components.v1 as components

# ===== 一般設定（家計の実数はここに書かない） ============================
ENVELOPE_DEFAULT = 50000                      # 接続前のデフォルト（実値は設定シートB2）
CATEGORIES = ["食費", "日用品", "外食", "その他"]
# デモ用の固定費（架空の例。実際の固定費は「固定費」シートから読む）
DEMO_FIXED = [("家賃", 50000), ("通信費", 5000), ("サブスク", 1500)]

JST = dt.timezone(dt.timedelta(hours=9))

INK, SOFT, WARN = "#2B2B2B", "#6B7280", "#C75B39"
# 背景からしっかり色を変えて、切り替えが「ぱっと見で分かる」ように差を大きく
PALETTES = {
    "honey": {"name": "はちみつ", "accent": "#C8881A", "soft": "#F3E2B0",
              "bg": "#FBEFCF", "border": "#E7D3A0"},
    "lemon": {"name": "レモン",   "accent": "#FFD21E", "soft": "#FFF59A",
              "bg": "#FFFCDB", "border": "#F2E89A"},
}


def _secret(key, default=""):
    try:
        return str(st.secrets.get(key, default))
    except Exception:
        return default


def _pin():
    """アプリ全体の あいことば（家族だけが開ける）。"""
    return _secret("KAKEIBO_PIN", "1234")


def _form_url():
    """入力フォームURL。Secretsに置く（公開コードに実URLを書かない）。"""
    return _secret("FORM_URL", "")


# ===== データ取得 =======================================================
def _to_int(v):
    try:
        return int(float(str(v).replace("¥", "").replace(",", "").strip()))
    except Exception:
        return 0


def _is_int(v):
    return str(v).replace("¥", "").replace(",", "").strip().lstrip("-").isdigit()


def _load_from_sheets():
    """Google Sheetsから記録・設定・固定費を読む。未設定/失敗なら None。"""
    try:
        import gspread
        sid = st.secrets["SHEET_ID"]
        gc = gspread.service_account_from_dict(dict(st.secrets["gcp_credentials"]))
        sh = gc.open_by_key(sid)

        rec = sh.worksheet("記録").get_all_values()  # A:日時 B:金額 C:カテゴリ D:メモ
        records = []
        for r in rec[1:]:
            if len(r) < 3 or not r[1]:
                continue
            records.append({"date": r[0], "amount": _to_int(r[1]),
                            "cat": r[2] if len(r) > 2 else "その他",
                            "memo": r[3] if len(r) > 3 else ""})

        envelope = ENVELOPE_DEFAULT
        try:
            envelope = _to_int(sh.worksheet("設定").acell("B2").value) or ENVELOPE_DEFAULT
        except Exception:
            pass

        fixed = []
        try:
            for r in sh.worksheet("固定費").get_all_values():
                if len(r) >= 2 and r[0] and r[0] != "合計" and _is_int(r[1]):
                    fixed.append((r[0], _to_int(r[1])))
        except Exception:
            fixed = []

        return records, envelope, fixed, True
    except Exception:
        return None


def _demo_data():
    """実データが無くても画面を確認できるデモ（今月の日付で作る・架空の数字）。"""
    today = dt.datetime.now(JST)
    y, m = today.year, today.month

    def d(day):
        return dt.datetime(y, m, min(day, 28), 12, 0, tzinfo=JST).strftime("%Y/%m/%d %H:%M:%S")

    records = [
        {"date": d(2),  "amount": 3200, "cat": "食費",   "memo": "スーパー"},
        {"date": d(4),  "amount": 1280, "cat": "日用品", "memo": "洗剤など"},
        {"date": d(6),  "amount": 4500, "cat": "外食",   "memo": "ランチ"},
        {"date": d(9),  "amount": 2780, "cat": "食費",   "memo": "スーパー"},
        {"date": d(12), "amount": 980,  "cat": "その他", "memo": ""},
        {"date": d(15), "amount": 3650, "cat": "食費",   "memo": "スーパー"},
        {"date": d(18), "amount": 1500, "cat": "日用品", "memo": ""},
    ]
    return records, ENVELOPE_DEFAULT, DEMO_FIXED, False


def get_data():
    res = _load_from_sheets()
    return res if res else _demo_data()


# ===== 集計 =============================================================
def _this_month(records):
    now = dt.datetime.now(JST)
    out = []
    for r in records:
        try:
            ds = str(r["date"]).replace("-", "/")
            d = dt.datetime.strptime(ds.split(" ")[0], "%Y/%m/%d")
            if d.year == now.year and d.month == now.month:
                out.append(r)
        except Exception:
            continue
    return out


def summarize(records, envelope):
    rows = _this_month(records)
    spent = sum(r["amount"] for r in rows)
    by_cat = {c: 0 for c in CATEGORIES}
    for r in rows:
        by_cat[r["cat"]] = by_cat.get(r["cat"], 0) + r["amount"]
    return {"spent": spent, "left": envelope - spent, "by_cat": by_cat,
            "rows": rows, "envelope": envelope}


# ===== 見た目（モバイルファースト・黄色アクセント） ======================
def inject_css(C):
    st.markdown(f"""
    <style>
      .stApp {{ background:{C['bg']}; }}
      .block-container {{ padding-top: 1.0rem; max-width: 720px; }}
      #MainMenu, footer {{ visibility: hidden; }}
      header[data-testid="stHeader"], [data-testid="stToolbar"] {{ display:none; }}
      .k-title {{ font-size: 1.05rem; color:{SOFT}; margin: 0 0 .2rem; }}
      .k-big {{ font-size: 3.2rem; font-weight: 800; color:{INK}; line-height:1.1; margin:.1rem 0; }}
      .k-big.warn {{ color:{WARN}; }}
      .k-cap {{ color:{SOFT}; font-size:.9rem; margin-bottom:.6rem; }}
      .k-msg {{ background:{C['soft']}; border-radius:14px; padding:.8rem 1rem; color:{INK};
               font-size:1rem; margin:.6rem 0 1rem; }}
      .k-card {{ background:#fff; border:1px solid {C['border']}; border-radius:14px;
                padding:1rem 1.1rem; margin:.5rem 0; }}
      .k-row {{ display:flex; justify-content:space-between; align-items:center;
               padding:.45rem 0; border-bottom:1px solid {C['border']}; }}
      .k-row:last-child {{ border-bottom:none; }}
      .k-row .lbl {{ color:{INK}; }}
      .k-row .amt {{ font-weight:700; color:{INK}; }}
      .k-bar {{ height:8px; border-radius:6px; background:{C['soft']}; overflow:hidden; margin-top:4px; }}
      .k-bar > span {{ display:block; height:100%; background:{C['accent']}; }}
      .k-link {{ display:block; text-align:center; background:{C['accent']}; color:{INK} !important;
                text-decoration:none; padding:.95rem; border-radius:12px; font-weight:800;
                font-size:1.05rem; margin:.8rem 0; box-shadow:0 1px 0 rgba(0,0,0,.05); }}
      .k-foot {{ color:{SOFT}; font-size:.8rem; text-align:center; margin-top:1rem; }}
      .stButton > button {{ border-radius:10px; border:1px solid {C['border']}; }}
    </style>
    """, unsafe_allow_html=True)


def yen(n):
    return f"¥{n:,.0f}"


def _gentle_message(left, envelope):
    if left >= envelope * 0.5:
        return "今月のペース、いい感じ"
    if left >= 0:
        return "ペースはだいじょうぶ。残りも上手に使おう"
    return "今月はちょっと使ったね。大丈夫、来月で調整しよう"


def render_overview(s, live):
    left, env, spent = s["left"], s["envelope"], s["spent"]
    warn = "warn" if left < 0 else ""
    st.markdown('<div class="k-title">今月、あと使えるお金</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="k-big {warn}">{yen(left)}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="k-cap">生活費の封筒 {yen(env)} から（食費・日用品・外食）</div>',
                unsafe_allow_html=True)
    st.markdown(f'<div class="k-msg">{_gentle_message(left, env)}</div>', unsafe_allow_html=True)

    rows_html = ""
    for c in CATEGORIES:
        amt = s["by_cat"].get(c, 0)
        pct = 0 if env <= 0 else min(100, round(amt / env * 100))
        rows_html += (f'<div class="k-row"><span class="lbl">{c}</span>'
                      f'<span class="amt">{yen(amt)}</span></div>'
                      f'<div class="k-bar"><span style="width:{pct}%"></span></div>')
    st.markdown(f'<div class="k-card"><div class="k-title" style="margin-bottom:.3rem">'
                f'何に使った？（今月）</div>{rows_html}'
                f'<div class="k-row" style="margin-top:.4rem"><span class="lbl">使った合計</span>'
                f'<span class="amt">{yen(spent)}</span></div></div>', unsafe_allow_html=True)

    form = _form_url()
    if form:
        st.markdown(f'<a class="k-link" href="{form}" target="_blank">＋ 記録する（レシートを見ながら）</a>',
                    unsafe_allow_html=True)
    if not live:
        st.markdown('<div class="k-foot">※ いまはデモ表示です（実データに接続すると本物の数字になります）</div>',
                    unsafe_allow_html=True)


# ===== 俺モード（管理・作り込みはここ） ==================================
def render_admin(records, s, fixed, live, palette):
    top = st.columns([1, 1])
    with top[0]:
        if st.button("← 妻モードに戻る", use_container_width=True):
            st.session_state.mode = "wife"
            st.rerun()
    with top[1]:
        names = list(PALETTES.keys())
        idx = names.index(palette) if palette in names else 0
        pick = st.radio("色（黄色2案）", names, index=idx, horizontal=True,
                        format_func=lambda k: PALETTES[k]["name"])
        if pick != palette:
            st.query_params["palette"] = pick
            st.rerun()

    st.markdown("### 管理ビュー（つよし用）")
    if not live:
        st.info("デモ表示中。実データ接続は secrets に SHEET_ID / gcp_credentials / FORM_URL を設定。")
    tabs = st.tabs(["ホーム", "内訳・推移", "固定費", "設定"])

    with tabs[0]:
        render_overview(s, live)

    with tabs[1]:
        import plotly.graph_objects as go
        acc = PALETTES[palette]["accent"]
        fig = go.Figure(go.Bar(x=[s["by_cat"].get(c, 0) for c in CATEGORIES],
                               y=CATEGORIES, orientation="h", marker_color=acc))
        fig.update_layout(title="カテゴリ別（今月）", height=260,
                          margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig, use_container_width=True)

        rows = sorted(s["rows"], key=lambda r: r["date"])
        cum, run, days = [], 0, []
        for r in rows:
            run += r["amount"]
            days.append(str(r["date"]).split(" ")[0][-5:])
            cum.append(run)
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=days, y=cum, mode="lines+markers",
                                  name="使った（累計）", line=dict(color=acc)))
        fig2.add_hline(y=s["envelope"], line_dash="dot", line_color=WARN,
                       annotation_text="封筒")
        fig2.update_layout(title="今月の使ったお金（累計）", height=300,
                           margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig2, use_container_width=True)

    with tabs[2]:
        if fixed:
            total = sum(a for _, a in fixed)
            html = ""
            for name, amt in fixed:
                html += (f'<div class="k-row"><span class="lbl">{name}</span>'
                         f'<span class="amt">{yen(amt)}</span></div>')
            html += (f'<div class="k-row"><span class="lbl"><b>合計</b></span>'
                     f'<span class="amt"><b>{yen(total)}</b></span></div>')
            st.markdown(f'<div class="k-card">{html}</div>', unsafe_allow_html=True)
            st.caption("※ 食費は封筒（生活費）で管理しているため、ここには入れていません。")
        else:
            st.caption("固定費は スプレッドシートの「固定費」シートに表示されます。")

    with tabs[3]:
        st.write("**封筒（今月使っていい上限）**")
        st.markdown(f'<div class="k-big">{yen(s["envelope"])}</div>', unsafe_allow_html=True)
        st.caption("スプレッドシートの「設定」シート B2 を変えると反映されます。")
        form = _form_url()
        st.write("**入力フォームURL**")
        st.code(form if form else "（Secretsに FORM_URL を設定してください）")


def palette_persist(palette):
    """選んだ色をその端末に記憶（localStorage）。URLに色指定が無ければ記憶を復元。"""
    components.html(f"""
    <script>
    try {{
      localStorage.setItem('kakeibo_palette', '{palette}');
      const u = new URL(window.parent.location);
      if (!u.searchParams.get('palette')) {{
        const saved = localStorage.getItem('kakeibo_palette');
        if (saved && saved !== '{palette}') {{
          u.searchParams.set('palette', saved); window.parent.location.replace(u);
        }}
      }}
    }} catch(e) {{}}
    </script>
    """, height=0)


def render_palette_switch(palette):
    """妻モード最下部の小さな色切替（私のアプリ感＝継続）。1画面を汚さないよう控えめに。"""
    st.caption("🎨 アプリのいろ（好きな方を選んでね）")
    cols = st.columns(2)
    for i, (k, info) in enumerate(PALETTES.items()):
        mark = "● " if k == palette else "○ "
        if cols[i].button(mark + info["name"], key=f"pal_{k}", use_container_width=True):
            st.query_params["palette"] = k
            st.rerun()


def load_yomimono():
    """運用チーム提供の「お金のよみもの_妻向け.md」を読み、記事(見出し,本文)に分解。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "お金のよみもの_妻向け.md")
    try:
        text = open(path, encoding="utf-8").read()
    except Exception:
        return []
    arts = []
    for chunk in text.split("\n## ")[1:]:
        head, _, body = chunk.partition("\n")
        arts.append((head.strip(), body.strip()))
    return arts


def render_yomimono():
    """妻向け読みもの。1画面を汚さないよう"読みたい時だけ"開く控えめなexpander。"""
    arts = load_yomimono()
    if not arts:
        return
    with st.expander("📖 お金のよみもの（よみたい時に）"):
        st.caption("むずかしい言葉・算数は出てきません。1本ずつ、気が向いたときに。")
        for title, body in arts:
            st.markdown(f"**{title}**")
            if body:
                st.markdown(body)
            st.markdown("---")


def render_switch():
    """妻モード最下部・つよし用への控えめな入口（あいことばで既に保護済みなのでトグルのみ）。"""
    with st.expander("つよし用（管理ビュー）"):
        if st.button("管理ビューをひらく", use_container_width=True):
            st.session_state.mode = "admin"
            st.rerun()


def gate():
    """アプリ全体を あいことば で保護。家族だけが開ける（URLを知られても中は見えない）。"""
    if st.session_state.get("authed"):
        return True
    if str(st.query_params.get("k", "")) == _pin():
        st.session_state.authed = True
        return True
    st.markdown("## 🪙 わが家の家計簿")
    st.text_input("あいことば（すうじ）", type="password", key="gate_pin")
    if st.button("ひらく", use_container_width=True):
        if str(st.session_state.get("gate_pin", "")) == _pin():
            st.session_state.authed = True
            st.query_params["k"] = _pin()
            st.rerun()
        else:
            st.error("あいことばが ちがうみたい")
    st.caption("家族だけが見られるように、あいことばで守っています。")
    return False


# ===== メイン ===========================================================
def main():
    st.set_page_config(page_title="わが家の家計簿", page_icon="🪙", layout="centered")
    palette = st.query_params.get("palette", "honey")
    if palette not in PALETTES:
        palette = "honey"
    inject_css(PALETTES[palette])
    palette_persist(palette)

    if not gate():
        return

    records, envelope, fixed, live = get_data()
    s = summarize(records, envelope)
    if "mode" not in st.session_state:
        st.session_state.mode = "wife"

    if st.session_state.mode == "admin":
        render_admin(records, s, fixed, live, palette)
    else:
        st.markdown("## 🪙 わが家の家計簿")
        render_overview(s, live)
        render_yomimono()
        render_palette_switch(palette)
        render_switch()


if __name__ == "__main__":
    main()
