import streamlit as st
import pandas as pd
import re
import io

# ページ設定
st.set_page_config(layout="wide", page_title="JRAオッズ断層アナライザー")

st.title("🏇 JRAオッズ断層アナライザー")
st.markdown("PC・スマホ両対応。データを貼り付けて「分析開始」を押してください。")

# ==========================================
# 関数定義
# ==========================================

@st.cache_data
def process_win_place_data(text):
    data = []
    # PC版: 順位, 枠, 馬番, 馬名, 単勝, 複勝
    regex_pc = r'(\d{1,2})\s+(\d{1,8})\s+(\d{1,2})\s+([^\s]+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s*-\s*(\d+\.\d+)'
    
    # スマホ版 (改良): 馬名にスペースが含まれてもOKなように [^\d]+ (数字以外) でマッチさせる
    regex_mobile = r'(\d{1,2})\s+(\d{1,2})\s+([^\d]+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s*-\s*(\d+\.\d+)'

    matches_pc = re.findall(regex_pc, text)
    matches_mobile = re.findall(regex_mobile, text)
    
    # マッチ数が多い方を採用
    if len(matches_pc) >= len(matches_mobile) and len(matches_pc) > 0:
        for match in matches_pc:
            try:
                data.append({
                    "順": int(match[0]),
                    "枠": match[1],
                    "馬番": int(match[2]),
                    "馬名": match[3].strip(),
                    "単勝": float(match[4]),
                    "複勝下限": float(match[5]),
                    "複勝上限": float(match[6])
                })
            except ValueError: continue
    elif len(matches_mobile) > 0:
        for match in matches_mobile:
            try:
                data.append({
                    "順": int(match[0]),
                    "枠": "-",
                    "馬番": int(match[1]),
                    "馬名": match[2].strip(), # 余計なスペースや改行を除去
                    "単勝": float(match[3]),
                    "複勝下限": float(match[4]),
                    "複勝上限": float(match[5])
                })
            except ValueError: continue
            
    if not data: return None, None

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
    df['選択用ラベル'] = df['馬番'].astype(str) + ": " + df['馬名']

    cols = [
        '累積比差', '累積比', '累積', '比差', '比', '差', '単勝', 
        '馬番', '複勝下限', '複勝上限', '下差', '上差', '順', '馬名', '選択用ラベル'
    ]
    return df[cols], avg_win_odds

@st.cache_data
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
        except ValueError: continue
    
    if not temp_list: return None, None

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

def extract_race_info(text):
    match = re.search(r'(\d+回\s*\S+?\s*\d+日\s*\d+(?:レース|R))', text)
    if match: return match.group(1)
    return None

def to_excel(df, selected_labels, sheet_name="オッズ分析"):
    output = io.BytesIO()
    df_excel = df.copy()
    if '選択用ラベル' in df_excel.columns:
        df_excel.insert(0, '注目', df_excel['選択用ラベル'].apply(lambda x: '〇' if x in selected_labels else ''))
        df_excel = df_excel.drop(columns=['選択用ラベル'])
    else:
        df_excel.insert(0, '注目', '')
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_excel.to_excel(writer, index=False, sheet_name=sheet_name)
    return output.getvalue()

def style_red_bold(val):
    if pd.isna(val): return ''
    if isinstance(val, (int, float)) and val < 0:
        return 'color: red; font-weight: bold'
    return ''

def filter_dataframe_with_context(df, mask, context=1):
    target_indices = df.index[mask].tolist()
    if not target_indices:
        return df.iloc[[]]
    indices_to_keep = set()
    for idx in target_indices:
        start = max(0, idx - context)
        end = min(len(df), idx + context + 1)
        for i in range(start, end):
            indices_to_keep.add(i)
    return df.iloc[sorted(list(indices_to_keep))]

# ==========================================
# メイン画面レイアウト
# ==========================================

with st.form(key='analysis_form'):
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("① 単勝・複勝")
        text_win = st.text_area("データ貼り付け", height=100, key="input_win")
    with col2:
        st.subheader("② 馬単")
        text_umatan = st.text_area("データ貼り付け", height=100, key="input_umatan")
    
    # 閾値スライダーをフォーム内に入れるか迷いますが、再計算トリガーになるのでフォームの外に出す手もありますが
    # ここでは「設定を決めてから分析開始」という流れにします
    st.markdown("---")
    st.markdown("⚙️ **感度設定** (何も出ないときは右へ、ノイズが多いときは左へ)")
    threshold_win = st.slider("単勝・複勝の断層基準 (デフォルト: -0.10)", -0.50, 0.00, -0.10, 0.01)
    
    submit_button = st.form_submit_button(label='🚀 分析開始 (決定)')

st.markdown("---")

if submit_button:
    race_info_text = None
    if text_win: race_info_text = extract_race_info(text_win)
    elif text_umatan: race_info_text = extract_race_info(text_umatan)
    if race_info_text: st.info(f"📍 {race_info_text}")

    # --- 1. 単勝・複勝 ---
    if text_win:
        st.markdown("### 📊 単勝・複勝")
        df_win, avg_win = process_win_place_data(text_win)
        
        if df_win is not None:
            # 読み取り頭数を確認（デバッグ用）
            st.caption(f"読み取り成功: {len(df_win)}頭")
            
            show_only_red_win = st.checkbox("🔥 断層のみ表示", value=True, key="filter_win")
            
            if show_only_red_win:
                mask = (df_win['累積比差'] <= threshold_win) | (df_win['比差'] <= threshold_win) | (df_win['下差'] <= threshold_win)
                df_display_win = filter_dataframe_with_context(df_win, mask, context=1)
                
                if len(df_display_win) == 0:
                    st.warning(f"⚠️ 基準値 ({threshold_win}) 以下の断層は見つかりませんでした。（全行表示します）")
                    df_display_win = df_win
            else:
                df_display_win = df_win

            st.metric("平均単勝オッズ", f"{avg_win:.2f}")
            
            selected_horses_win = st.multiselect(
                "注目馬を選択", df_win['選択用ラベル'].tolist(), key="sel_win"
            )

            def highlight_win(row):
                if row['選択用ラベル'] in selected_horses_win:
                    return ['background-color: #ffffcc'] * len(row)
                return [''] * len(row)
            
            row_count = len(df_display_win)
            final_height = min((row_count + 1) * 35 + 3, 500)

            st.dataframe(
                df_display_win.style
                .format("{:.2f}", subset=['累積比差', '累積比', '累積', '比差', '比', '差', '単勝', '複勝下限', '複勝上限', '下差', '上差'])
                .applymap(style_red_bold, subset=['累積比差', '比差', '下差', '上差'])
                .apply(highlight_win, axis=1)
                .highlight_null(color='transparent'),
                height=final_height,
                column_order=[c for c in df_win.columns if c != '選択用ラベル']
            )
            
            excel_win = to_excel(df_win, selected_horses_win, "単勝複勝")
            st.download_button("📥 Excel DL", excel_win, "odds_win_place.xlsx")
        else:
            st.error("❌ データを解析できませんでした。コピーした範囲が正しいか、または「馬名」の列が含まれているか確認してください。")

    if text_win and text_umatan: st.markdown("---")

    # --- 2. 馬単 ---
    if text_umatan:
        st.markdown("### 📊 馬単")
        df_uma, avg_uma = process_umatan_data(text_umatan)
        
        if df_uma is not None:
            show_only_red_uma = st.checkbox("🔥 断層のみ表示", value=True, key="filter_uma")
            
            if show_only_red_uma:
                # 馬単用の閾値は -1.0 固定（あるいは必要ならスライダー追加）
                mask = (df_uma['比差'] <= -0.1) | (df_uma['裏差'] <= -1.0)
                df_display_uma = filter_dataframe_with_context(df_uma, mask, context=1)
                if len(df_display_uma) == 0:
                     st.warning("⚠️ 大きな断層は見つかりませんでした（全行表示します）")
                     df_display_uma = df_uma
            else:
                df_display_uma = df_uma

            st.metric("平均馬単オッズ", f"{avg_uma:.2f}")
            
            selected_horses_uma = st.multiselect(
                "注目買い目を選択", df_uma['選択用ラベル'].tolist(), key="sel_uma"
            )

            def highlight_uma(row):
                if row['選択用ラベル'] in selected_horses_uma:
                    return ['background-color: #ffffcc'] * len(row)
                return [''] * len(row)

            row_count = len(df_display_uma)
            final_height = min((row_count + 1) * 35 + 3, 500)

            st.dataframe(
                df_display_uma.style
                .format("{:.2f}", subset=['比差', '表比', '表差', '表', '裏', '裏差', '裏比', '裏比差'])
                .applymap(style_red_bold, subset=['比差', '表差', '裏差', '裏比差'])
                .apply(highlight_uma, axis=1)
                .highlight_null(color='transparent'),
                height=final_height,
                column_order=[c for c in df_uma.columns if c != '選択用ラベル']
            )
            
            excel_uma = to_excel(df_uma, selected_horses_uma, "馬単")
            st.download_button("📥 Excel DL", excel_uma, "odds_umatan.xlsx")
else:
    st.info("👆 ボックスにデータを貼り付けて、「分析開始 (決定)」ボタンを押してください")
