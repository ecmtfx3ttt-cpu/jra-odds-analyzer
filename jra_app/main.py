import streamlit as st
import pandas as pd
import numpy as np  # 追加: 計算用
import re
import io

# ページ設定
st.set_page_config(layout="wide", page_title="JRAオッズ断層アナライザー")

# --- タイトル ---
st.title("🏇 JRAオッズ断層アナライザー")
st.markdown("JRA公式サイトのデータを貼り付けてください。単勝・複勝と馬単を同時に分析できます。")

# ==========================================
# 共通関数: レース情報抽出 & Excel出力
# ==========================================
def extract_race_info(text):
    match = re.search(r'(\d+回\s*\S+?\s*\d+日\s*\d+レース)', text)
    if match:
        return match.group(1)
    return None

def to_excel(df, selected_labels, sheet_name="オッズ分析"):
    output = io.BytesIO()
    df_excel = df.copy()
    
    # 「注目」列を追加
    if '選択用ラベル' in df_excel.columns:
        df_excel.insert(0, '注目', df_excel['選択用ラベル'].apply(lambda x: '〇' if x in selected_labels else ''))
        df_excel = df_excel.drop(columns=['選択用ラベル'])
    else:
        df_excel.insert(0, '注目', '')

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_excel.to_excel(writer, index=False, sheet_name=sheet_name)
    return output.getvalue()

# スタイリング関数（共通）
def style_red_bold(val):
    if pd.isna(val): return ''
    if isinstance(val, (int, float)) and val < 0:
        return 'color: red; font-weight: bold'
    return ''

# ==========================================
# 追加機能: カオス指数計算ロジック
# ==========================================
def calculate_chaos_stats(odds_series):
    """
    単勝オッズからカオス指数（エントロピー）とレベル判定を返す
    """
    # データ洗浄
    odds = pd.to_numeric(odds_series, errors='coerce').dropna()
    odds = odds[odds > 0]
    
    if len(odds) < 2:
        return 0.0, "判定不可"

    # 1. オッズを確率に変換（支持率）
    probs = 1 / odds
    # 2. 確率を正規化（合計を1にする）
    norm_probs = probs / probs.sum()
    # 3. エントロピー（カオス指数）算出
    entropy = -np.sum(norm_probs * np.log(norm_probs + 1e-9))
    
    # 4. レベル判定 (以前定義した閾値を使用)
    if entropy < 1.71:
        level = "Lv1 (鉄板)"
    elif entropy < 1.90:
        level = "Lv2 (堅め)"
    elif entropy < 2.05:
        level = "Lv3 (標準)"
    elif entropy < 2.19:
        level = "Lv4 (混戦)"
    else:
        level = "Lv5 (カオス🔥)"
        
    return entropy, level

# ==========================================
# ロジックA: 単勝・複勝処理
# ==========================================
def process_win_place_data(text):
    data = []
    # 順位、枠(文字OK)、馬番、馬名、単勝、複勝下限-上限
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
        return None, None, None, None  # 戻り値を増やしました

    df = pd.DataFrame(data)
    
    df['差'] = df['単勝'].diff()
    df['比'] = df['単勝'] / df['単勝'].shift(1)
    df['比差'] = df['比'].diff()
    
    df['累積'] = df['単勝'].cumsum()
    df['累積比'] = df['累積'] / df['累積'].shift(1)
    df['累積比差'] = df['累積比'].diff()
    
    df['下差'] = df['複勝下限'].diff()
    df['上差'] = df['複勝上限'].diff()

    avg_win_odds = df['単勝'].sum() / len(df)
    
    # ★追加: カオス指数の計算
    chaos_val, chaos_lvl = calculate_chaos_stats(df['単勝'])

    df['選択用ラベル'] = df['馬番'].astype(str) + ": " + df['馬名']

    cols = [
        '累積比差', '累積比', '累積', '比差', '比', '差', '単勝', 
        '馬番', '複勝下限', '複勝上限', '下差', '上差', '順', '馬名', '選択用ラベル'
    ]
    return df[cols], avg_win_odds, chaos_val, chaos_lvl

# ==========================================
# ロジックB: 馬単処理
# ==========================================
def process_umatan_data(text):
    data = []
    # パターン: 順位 + 組番(数字-数字) + オッズ
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
        return None, None

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

    avg_odds = df['表'].sum() / len(df)
    df['選択用ラベル'] = df['組番'] + " (" + df['表'].astype(str) + "倍)"

    cols = [
        '比差', '表比', '表差', '表', 
        '組番', 
        '裏', '裏差', '裏比', '裏比差', 
        '順', '選択用ラベル'
    ]
    return df[cols], avg_odds

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
    # レース情報の抽出と表示
    race_info_text = None
    if text_win:
        race_info_text = extract_race_info(text_win)
    elif text_umatan:
        race_info_text = extract_race_info(text_umatan)

    if race_info_text:
        st.info(f"📍 {race_info_text}")

    # --- 分析結果の表示エリア ---

    # 1. 単勝・複勝の処理
    if text_win:
        st.markdown("### 📊 単勝・複勝 分析結果")
        # 戻り値が増えています
        df_win, avg_win, chaos_val, chaos_lvl = process_win_place_data(text_win)
        
        if df_win is not None:
            # ★レイアウト変更: メトリクスを3つ並べる
            col_m1, col_m2, col_m3, col_select = st.columns([1, 1, 1, 3])
            
            col_m1.metric("平均単勝オッズ", f"{avg_win:.2f}")
            col_m2.metric("カオス指数", f"{chaos_val:.3f}")
            col_m3.metric("判定", chaos_lvl)
            
            selected_horses_win = col_select.multiselect(
                "注目馬を選択 (単勝)", df_win['選択用ラベル'].tolist(), key="sel_win"
            )

            def highlight_win(row):
                if row['選択用ラベル'] in selected_horses_win:
                    return ['background-color: #ffffcc'] * len(row)
                return [''] * len(row)

            st.dataframe(
                df_win.style
                .format("{:.2f}", subset=['累積比差', '累積比', '累積', '比差', '比', '差', '単勝', '複勝下限', '複勝上限', '下差', '上差'])
                .applymap(style_red_bold, subset=['累積比差', '比差', '下差', '上差'])
                .apply(highlight_win, axis=1)
                .highlight_null(color='transparent'),
                height=(len(df_win) + 1) * 35 + 3,
                column_order=[c for c in df_win.columns if c != '選択用ラベル']
            )
            
            excel_win = to_excel(df_win, selected_horses_win, "単勝複勝")
            st.download_button("📥 単勝・複勝Excelをダウンロード", excel_win, "odds_win_place.xlsx")
        else:
            st.error("単勝・複勝データを解析できませんでした。")

    if text_win and text_umatan:
        st.markdown("---")

    # 2. 馬単の処理
    if text_umatan:
        st.markdown("### 📊 馬単 分析結果 (表・裏比較)")
        df_uma, avg_uma = process_umatan_data(text_umatan)
        
        if df_uma is not None:
            col_metrics_u, col_select_u = st.columns([1, 3])
            col_metrics_u.metric("平均馬単オッズ", f"{avg_uma:.2f}")
            
            selected_horses_uma = col_select_u.multiselect(
                "注目買い目を選択 (馬単)", df_uma['選択用ラベル'].tolist(), key="sel_uma"
            )

            def highlight_uma(row):
                if row['選択用ラベル'] in selected_horses_uma:
                    return ['background-color: #ffffcc'] * len(row)
                return [''] * len(row)

            st.dataframe(
                df_uma.style
                .format("{:.2f}", subset=['比差', '表比', '表差', '表', '裏', '裏差', '裏比', '裏比差'])
                .applymap(style_red_bold, subset=['比差', '表差', '裏差', '裏比差'])
                .apply(highlight_uma, axis=1)
                .highlight_null(color='transparent'),
                height=(len(df_uma) + 1) * 35 + 3,
                column_order=[c for c in df_uma.columns if c != '選択用ラベル']
            )
            
            excel_uma = to_excel(df_uma, selected_horses_uma, "馬単")
            st.download_button("📥 馬単Excelをダウンロード", excel_uma, "odds_umatan.xlsx")
        else:
            st.error("馬単データを解析できませんでした。")
