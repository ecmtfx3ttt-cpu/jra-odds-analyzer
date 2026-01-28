import streamlit as st
import pandas as pd
import numpy as np
import re
import io

# ページ設定
st.set_page_config(layout="wide", page_title="JRAオッズ断層アナライザー Ver.2.2")

# --- タイトル ---
st.title("🏇 JRAオッズ断層アナライザー Ver.2.2")
st.markdown("""
**使い方**: JRA公式サイトのオッズページからデータをコピーして貼り付けてください。
- **「分析実行」**を押すと解析結果が表示されます。
- **ハイフン埋め**: 1位の馬など計算できない箇所は「-」で表示されます。
""")

# ==========================================
# 共通関数
# ==========================================
def extract_race_info(text):
    match = re.search(r'(\d+回\s*\S+?\s*\d+日\s*\d+レース)', text)
    if match:
        return match.group(1)
    return None

def to_csv_text(df, selected_labels=None):
    df_copy = df.copy()
    cols_to_exclude = ['選択用ラベル', 'style_class']
    cols = [c for c in df_copy.columns if c not in cols_to_exclude]
    df_copy = df_copy[cols]

    if selected_labels is not None and '選択用ラベル' in df.columns:
        is_selected = df['選択用ラベル'].isin(selected_labels)
        df_copy.insert(0, '注目', is_selected.apply(lambda x: '〇' if x else ''))
    else:
        df_copy.insert(0, '注目', '')

    # ★修正点: NaN（計算不可）をハイフンに置換して、カンマ連続を防ぐ
    df_copy = df_copy.fillna('-')
    
    return df_copy.to_csv(sep=',', index=False)

def style_red_bold(val):
    if pd.isna(val): return ''
    if isinstance(val, (int, float)) and val < 0:
        return 'color: red; font-weight: bold'
    return ''

# ==========================================
# カオス指数
# ==========================================
def calculate_chaos_stats(odds_series):
    odds = pd.to_numeric(odds_series, errors='coerce').dropna()
    odds = odds[odds > 0]
    
    if len(odds) < 2:
        return 0.0, "判定不可"

    probs = 1 / odds
    norm_probs = probs / probs.sum()
    entropy = -np.sum(norm_probs * np.log(norm_probs + 1e-9))
    
    if entropy < 1.71: level = "Lv1(鉄板)"
    elif entropy < 1.90: level = "Lv2(堅め)"
    elif entropy < 2.05: level = "Lv3(標準)"
    elif entropy < 2.19: level = "Lv4(混戦)"
    else: level = "Lv5(カオス🔥)"
        
    return entropy, level

# ==========================================
# ロジックA: 単勝・複勝処理
# ==========================================
def process_win_place_data(text):
    data = []
    # 柔軟な正規表現
    pattern = r'(\d{1,2})\s+(\S+)\s+(\d{1,2})\s+([^\s]+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s*-\s*(\d+\.\d+)'
    matches = re.findall(pattern, text)

    for match in matches:
        try:
            data.append({
                "順": int(match[0]),
                "枠": match[1],
                "馬番": int(match[2]),
                "馬名": match[3],
                "単勝": float(match[4]),
                "複勝下限": float(match[5]),
                "複勝上限": float(match[6])
            })
        except ValueError:
            continue
            
    if not data:
        return None, 0, "", 0, ""

    df = pd.DataFrame(data)
    
    df['差'] = df['単勝'].diff()
    df['比'] = df['単勝'] / df['単勝'].shift(1)
    df['比差'] = df['比'].diff()
    
    df['累積'] = df['単勝'].cumsum()
    df['累積比'] = df['累積'] / df['累積'].shift(1)
    df['累積比差'] = df['累積比'].diff()
    
    df['下差'] = df['複勝下限'].diff()
    df['上差'] = df['複勝上限'].diff()

    chaos_val_win, chaos_lvl_win = calculate_chaos_stats(df['単勝'])
    chaos_val_place, chaos_lvl_place = calculate_chaos_stats(df['複勝下限'])

    df['選択用ラベル'] = df['馬番'].astype(str) + ": " + df['馬名']

    cols = [
        '累積比差', '累積比', '累積', '比差', '比', '差', '単勝', 
        '馬番', '複勝下限', '複勝上限', '下差', '上差', '順', '馬名', '選択用ラベル'
    ]
    existing_cols = [c for c in cols if c in df.columns]
    return df[existing_cols], chaos_val_win, chaos_lvl_win, chaos_val_place, chaos_lvl_place

# ==========================================
# ロジックB: 馬単処理
# ==========================================
def process_umatan_data(text):
    data = []
    pattern = r'(\d+)\s+(\d+)-(\d+)\s+(\d+\.\d+)'
    matches = re.findall(pattern, text)
    
    temp_list = []
    for match in matches:
        try:
            rank = int(match[0])
            h1 = int(match[1])
            h2 = int(match[2])
            odds = float(match[3])
            temp_list.append({"順": rank, "組1": h1, "組2": h2, "表": odds})
        except ValueError:
            continue
    
    if not temp_list:
        return None

    odds_map = {(item['組1'], item['組2']): item['表'] for item in temp_list}

    final_data = []
    for item in temp_list:
        reverse_key = (item['組2'], item['組1'])
        reverse_odds = odds_map.get(reverse_key, None)
        
        row = item.copy()
        row['裏'] = reverse_odds
        row['組番'] = f"{item['組1']} - {item['組2']}"
        final_data.append(row)

    df = pd.DataFrame(final_data)
    df = df.sort_values('順')
    
    df['表差'] = df['表'].diff()
    df['表比'] = df['表'] / df['表'].shift(1)
    df['比差'] = df['表比'].diff()

    df['裏差'] = df['裏'].diff()
    df['裏比'] = df['裏'] / df['裏'].shift(1)
    df['裏比差'] = df['裏比'].diff()
    
    df['選択用ラベル'] = df['組番'] + " (" + df['表'].astype(str) + "倍)"

    cols = [
        '組1', '組2', 
        '比差', '表比', '表差', '表', 
        '組番', 
        '裏', '裏差', '裏比', '裏比差', 
        '順', '選択用ラベル'
    ]
    existing_cols = [c for c in cols if c in df.columns]
    return df[existing_cols]

# ==========================================
# メイン画面レイアウト
# ==========================================

if 'data_processed' not in st.session_state:
    st.session_state.data_processed = False
    st.session_state.df_win = None
    st.session_state.df_uma = None
    st.session_state.race_info = ""
    st.session_state.c_win = 0
    st.session_state.l_win = ""
    st.session_state.c_plc = 0
    st.session_state.l_plc = ""

# 入力フォーム
with st.form(key='analysis_form'):
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("① 単勝・複勝")
        text_win_input = st.text_area("ページ全体を貼り付け", height=150, key="input_win")
    with col2:
        st.subheader("② 馬単")
        text_umatan_input = st.text_area("ページ全体を貼り付け", height=150, key="input_umatan")

    submit_button = st.form_submit_button(label='🚀 分析実行')

# データ処理
if submit_button:
    st.session_state.df_win = None
    st.session_state.df_uma = None
    st.session_state.race_info = ""

    info_text = None
    if text_win_input: info_text = extract_race_info(text_win_input)
    elif text_umatan_input: info_text = extract_race_info(text_umatan_input)
    st.session_state.race_info = info_text

    if text_win_input:
        df_w, c_w, l_w, c_p, l_p = process_win_place_data(text_win_input)
        if df_w is not None:
            st.session_state.df_win = df_w
            st.session_state.c_win = c_w
            st.session_state.l_win = l_w
            st.session_state.c_plc = c_p
            st.session_state.l_plc = l_p
        else:
            st.error("⚠️ 単勝・複勝データの読み取りに失敗しました。")

    if text_umatan_input:
        df_u = process_umatan_data(text_umatan_input)
        if df_u is not None:
            st.session_state.df_uma = df_u
        else:
            st.error("⚠️ 馬単データの読み取りに失敗しました。")

    st.session_state.data_processed = True

# --- 結果表示 ---
if st.session_state.data_processed:
    st.markdown("---")
    if st.session_state.race_info:
        st.info(f"📍 {st.session_state.race_info}")

    # 1. 単勝・複勝
    if st.session_state.df_win is not None:
        st.markdown("### 📊 単勝・複勝 分析結果")
        df_win = st.session_state.df_win

        c1, c2, c3, c4 = st.columns([1, 1, 1, 3])
        c1.metric("単勝カオス", f"{st.session_state.c_win:.3f}")
        c1.caption(st.session_state.l_win)
        c2.metric("複勝カオス", f"{st.session_state.c_plc:.3f}")
        c2.caption(st.session_state.l_plc)
        
        selected_horses_win = c4.multiselect(
            "注目馬を選択（ハイライト）", 
            df_win['選択用ラベル'].tolist(), 
            key="sel_win"
        )

        def highlight_win(row):
            if row['選択用ラベル'] in selected_horses_win:
                return ['background-color: #ffffcc; color: black; font-weight: bold'] * len(row)
            return [''] * len(row)

        display_cols = [c for c in df_win.columns if c not in ['選択用ラベル', 'style_class']]
        
        st.dataframe(
            df_win.style
            .format("{:.2f}", subset=['累積比差', '累積比', '累積', '比差', '比', '差', '単勝', '複勝下限', '複勝上限', '下差', '上差'], na_rep="-")
            .applymap(style_red_bold, subset=['累積比差', '比差', '下差', '上差'])
            .apply(highlight_win, axis=1),
            height=(len(df_win) + 1) * 35 + 3,
            column_order=display_cols
        )
        
        # 個別コピーボタン（st.codeを使用）
        with st.expander("📋 単勝・複勝 CSVデータ（コピー用）"):
            st.code(to_csv_text(df_win, selected_horses_win), language='csv')

    # 2. 馬単
    if st.session_state.df_uma is not None:
        st.markdown("---")
        st.markdown("### 📊 馬単 分析結果")
        df_uma = st.session_state.df_uma.copy()

        col_sort, col_sel = st.columns([1, 2])
        sort_mode = col_sort.radio("並び順", ["人気順 (断層チェック)", "馬番順 (裏オッズ確認)"], horizontal=True)

        if sort_mode == "馬番順 (裏オッズ確認)":
            df_uma = df_uma.sort_values(['組1', '組2'])
            display_order = ['組番', '表', '裏', '裏差', '順']
        else:
            df_uma = df_uma.sort_values('順')
            display_order = ['比差', '表比', '表差', '表', '組番', '裏', '裏差', '裏比', '裏比差', '順']

        selected_horses_uma = col_sel.multiselect(
            "注目買い目を選択", 
            df_uma['選択用ラベル'].tolist(), 
            key="sel_uma"
        )

        def highlight_uma(row):
            if row['選択用ラベル'] in selected_horses_uma:
                return ['background-color: #ffffcc; color: black; font-weight: bold'] * len(row)
            return [''] * len(row)

        st.dataframe(
            df_uma.style
            .format("{:.1f}", subset=['比差', '表比', '表差', '表', '裏', '裏差', '裏比', '裏比差'], na_rep="-")
            .applymap(style_red_bold, subset=['比差', '表差', '裏差', '裏比差'])
            .apply(highlight_uma, axis=1)
            .highlight_null(color='transparent'),
            height=500,
            column_order=display_order
        )

        with st.expander("📋 馬単 CSVデータ（コピー用）"):
            st.code(to_csv_text(df_uma, selected_horses_uma), language='csv')

    # 3. まとめてコピー
    if st.session_state.df_win is not None and st.session_state.df_uma is not None:
        st.markdown("---")
        st.subheader("📥 全データCSV")
        # ★修正点: st.codeを使うことで、右上にワンクリックコピーボタンが表示されます
        csv_all = "[単勝・複勝]\n" + to_csv_text(st.session_state.df_win, selected_horses_win) + "\n\n[馬単]\n" + to_csv_text(st.session_state.df_uma, selected_horses_uma)
        st.code(csv_all, language='csv')
