import streamlit as st
import pandas as pd
import numpy as np
import re

# ページ設定
st.set_page_config(layout="wide", page_title="JRAオッズ断層アナライザー")

# --- タイトル ---
st.title("🏇 JRAオッズ断層アナライザー")
st.markdown("JRA公式サイトのデータを貼り付けてください。単勝・複勝と馬単を同時に分析できます。")

# ==========================================
# 共通関数: レース情報抽出
# ==========================================
def extract_race_info(text):
    match = re.search(r'(\d+回\s*\S+?\s*\d+日\s*\d+レース)', text)
    if match:
        return match.group(1)
    return None

def to_copy_text(df, selected_labels=None):
    df_copy = df.copy()
    if selected_labels is not None and '選択用ラベル' in df_copy.columns:
        df_copy.insert(0, '注目', df_copy['選択用ラベル'].apply(lambda x: '〇' if x in selected_labels else ''))
    elif '選択用ラベル' in df_copy.columns:
        df_copy.insert(0, '注目', '')
        
    if '選択用ラベル' in df_copy.columns:
        df_copy = df_copy.drop(columns=['選択用ラベル'])
        
    return df_copy.to_csv(sep='\t', index=False)

def style_red_bold(val):
    if pd.isna(val): return ''
    if isinstance(val, (int, float)) and val < 0:
        return 'color: red; font-weight: bold'
    return ''

# ==========================================
# カオス指数計算ロジック
# ==========================================
def calculate_chaos_stats(odds_series):
    """
    オッズ列からカオス指数（エントロピー）とレベル判定を返す
    """
    odds = pd.to_numeric(odds_series, errors='coerce').dropna()
    odds = odds[odds > 0]
    
    if len(odds) < 2:
        return 0.0, "判定不可"

    # 支持率(確率)に変換して正規化
    probs = 1 / odds
    norm_probs = probs / probs.sum()
    # エントロピー算出
    entropy = -np.sum(norm_probs * np.log(norm_probs + 1e-9))
    
    if entropy < 1.71:
        level = "Lv1(鉄板)"
    elif entropy < 1.90:
        level = "Lv2(堅め)"
    elif entropy < 2.05:
        level = "Lv3(標準)"
    elif entropy < 2.19:
        level = "Lv4(混戦)"
    else:
        level = "Lv5(カオス🔥)"
        
    return entropy, level

# ==========================================
# ロジックA: 単勝・複勝処理
# ==========================================
def process_win_place_data(text):
    data = []
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
        return None, None, None, None, None

    df = pd.DataFrame(data)
    
    df['差'] = df['単勝'].diff()
    df['比'] = df['単勝'] / df['単勝'].shift(1)
    df['比差'] = df['比'].diff()
    
    df['累積'] = df['単勝'].cumsum()
    df['累積比'] = df['累積'] / df['累積'].shift(1)
    df['累積比差'] = df['累積比'].diff()
    
    df['下差'] = df['複勝下限'].diff()
    df['上差'] = df['複勝上限'].diff()

    # ★単勝カオス指数
    chaos_val_win, chaos_lvl_win = calculate_chaos_stats(df['単勝'])
    # ★複勝カオス指数（複勝下限を使用）
    chaos_val_place, chaos_lvl_place = calculate_chaos_stats(df['複勝下限'])

    df['選択用ラベル'] = df['馬番'].astype(str) + ": " + df['馬名']

    cols = [
        '累積比差', '累積比', '累積', '比差', '比', '差', '単勝', 
        '馬番', '複勝下限', '複勝上限', '下差', '上差', '順', '馬名', '選択用ラベル'
    ]
    return df[cols], chaos_val_win, chaos_lvl_win, chaos_val_place, chaos_lvl_place

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

    df['表差'] = df['表'].diff()
    df['表比'] = df['表'] / df['表'].shift(1)
    df['比差'] = df['表比'].diff()

    df['裏差'] = df['裏'].diff()
    df['裏比'] = df['裏'] / df['裏'].shift(1)
    df['裏比差'] = df['裏比'].diff()

    df['選択用ラベル'] = df['組番'] + " (" + df['表'].astype(str) + "倍)"

    cols = [
        '比差', '表比', '表差', '表', 
        '組番', 
        '裏', '裏差', '裏比', '裏比差', 
        '順', '選択用ラベル'
    ]
    return df[cols]

# ==========================================
# メイン画面レイアウト
# ==========================================

with st.form(key='analysis_form'):
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("① 単勝・複勝（人気順）")
        text_win = st.text_area("「単勝・複勝」のページ全体を貼り付け", height=150, key="input_win")

    with col2:
        st.subheader("② 馬単（人気順）")
        text_umatan = st.text_area("「馬単（人気順）」のページ全体を貼り付け", height=150, key="input_umatan")

    submit_button = st.form_submit_button(label='🚀 分析開始')

st.markdown("---")

if submit_button:
    race_info_text = None
    if text_win:
        race_info_text = extract_race_info(text_win)
    elif text_umatan:
        race_info_text = extract_race_info(text_umatan)

    if race_info_text:
        st.info(f"📍 {race_info_text}")

    df_win_res = None
    df_uma_res = None
    selected_horses_win = []
    selected_horses_uma = []

    # --- 1. 単勝・複勝の処理 ---
    if text_win:
        st.markdown("### 📊 単勝・複勝 分析結果")
        df_win_res, c_win, l_win, c_plc, l_plc = process_win_place_data(text_win)
        
        if df_win_res is not None:
            # カオス指数表示（単勝・複勝の両方）
            c1, c2, c3, c4, c_sel = st.columns([1, 1, 1, 1, 2])
            c1.metric("単勝カオス", f"{c_win:.3f}")
            c1.caption(l_win)
            
            c2.metric("複勝カオス", f"{c_plc:.3f}")
            c2.caption(l_plc)
            
            # ズレ判定
            if c_plc > c_win + 0.1:
                 c3.warning("⚠️複勝が混戦")
            elif c_win > c_plc + 0.1:
                 c3.error("🔥単勝が混戦")
            
            selected_horses_win = c_sel.multiselect(
                "注目馬を選択", df_win_res['選択用ラベル'].tolist(), key="sel_win"
            )

            def highlight_win(row):
                if row['選択用ラベル'] in selected_horses_win:
                    return ['background-color: #ffffcc'] * len(row)
                return [''] * len(row)

            st.dataframe(
                df_win_res.style
                .format("{:.2f}", subset=['累積比差', '累積比', '累積', '比差', '比', '差', '単勝', '複勝下限', '複勝上限', '下差', '上差'])
                .applymap(style_red_bold, subset=['累積比差', '比差', '下差', '上差'])
                .apply(highlight_win, axis=1)
                .highlight_null(color='transparent'),
                height=(len(df_win_res) + 1) * 35 + 3,
                column_order=[c for c in df_win_res.columns if c != '選択用ラベル']
            )
            
            with st.expander("📋 単勝・複勝のコピー用データを表示"):
                tsv_win = to_copy_text(df_win_res, selected_horses_win)
                st.code(tsv_win, language='csv')
        else:
            st.error("データ解析エラー")

    if text_win and text_umatan:
        st.markdown("---")

    # --- 2. 馬単の処理 ---
    if text_umatan:
        st.markdown("### 📊 馬単 分析結果 (表・裏比較)")
        df_uma_res = process_umatan_data(text_umatan)
        
        if df_uma_res is not None:
            col_spacer, col_select_u = st.columns([1, 3])
            
            selected_horses_uma = col_select_u.multiselect(
                "注目買い目を選択", df_uma_res['選択用ラベル'].tolist(), key="sel_uma"
            )

            def highlight_uma(row):
                if row['選択用ラベル'] in selected_horses_uma:
                    return ['background-color: #ffffcc'] * len(row)
                return [''] * len(row)

            st.dataframe(
                df_uma_res.style
                .format("{:.2f}", subset=['比差', '表比', '表差', '表', '裏', '裏差', '裏比', '裏比差'])
                .applymap(style_red_bold, subset=['比差', '表差', '裏差', '裏比差'])
                .apply(highlight_uma, axis=1)
                .highlight_null(color='transparent'),
                height=(len(df_uma_res) + 1) * 35 + 3,
                column_order=[c for c in df_uma_res.columns if c != '選択用ラベル']
            )
            
            with st.expander("📋 馬単のコピー用データを表示"):
                tsv_uma = to_copy_text(df_uma_res, selected_horses_uma)
                st.code(tsv_uma, language='csv')
        else:
            st.error("データ解析エラー")

    # --- 3. まとめてコピー ---
    if df_win_res is not None and df_uma_res is not None:
        st.markdown("---")
        st.subheader("📥 全データをまとめてコピー")
        with st.container():
            st.info("右上のコピーボタンで全データをコピーできます。")
            tsv_all = "[単勝・複勝]\n" + to_copy_text(df_win_res, selected_horses_win) + "\n\n[馬単]\n" + to_copy_text(df_uma_res, selected_horses_uma)
            st.code(tsv_all, language='csv')
