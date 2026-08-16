import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
import gspread
from google.oauth2.service_account import Credentials

# 1. Googleスプレッドシートへの接続設定（Streamlit Cloud用）
@st.cache_resource
def get_gspread_client():
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes
    )
    return gspread.authorize(credentials)

try:
    gc = get_gspread_client()
    spreadsheet = gc.open('utility_app')
    
    sheet_variable = spreadsheet.worksheet('kakeibo')
    
    try:
        sheet_fixed = spreadsheet.worksheet('fixed_costs')
    except Exception:
        sheet_fixed = spreadsheet.add_worksheet(title='fixed_costs', rows=20, cols=2)
        sheet_fixed.append_row(["中分類", "金額"])
        default_fixed = [
            ["住宅ローン", 100000],
            ["光熱費", 30000],
            ["保険", 20000],
            ["通信費", 10000],
            ["学費（習い事含む）", 30000],
            ["サブスク", 5000]
        ]
        for row in default_fixed:
            sheet_fixed.append_row(row)

except Exception as e:
    st.error(f"スプレッドシート接続エラー: {e}")
    st.stop()

# 2. ページ基本設定
st.set_page_config(page_title="我が家の家計簿アプリ", layout="centered")
st.title("我が家の家計簿アプリ")

# 3. 支出カテゴリの定義
VARIABLE_CATEGORIES = ["外食費", "医療費", "娯楽", "その他（自炊、日用品、服、ガソリン代など）"]
FIXED_CATEGORIES = ["住宅ローン", "光熱費", "保険", "通信費", "学費（習い事含む）", "サブスク"]

# タブ切り替え
tab1, tab2 = st.tabs(["📝 日々の入力・集計", "⚙️ 固定費の設定・見直し"])

# ---------------------------------------------------------
# TAB 1: 日々の変動費入力 ＆ 月別自動集計
# ---------------------------------------------------------
with tab1:
    st.header("📝 変動費を入力")

    col1, col2 = st.columns(2)
    with col1:
        date_val = st.date_input("日付", datetime.date.today())
        minor_cat = st.selectbox("項目（中分類）", VARIABLE_CATEGORIES)

    with col2:
        amount = st.number_input("金額 (円)", min_value=0, step=100, value=1000)
        memo = st.text_input("メモ（店舗名など）", placeholder="例：ラーメン店、スーパー買い物など")

    if st.button("✨ スプレッドシートに保存", type="primary"):
        new_row = [str(date_val), "変動費", minor_cat, int(amount), memo]
        sheet_variable.append_row(new_row)
        st.success("✅ スプレッドシートに保存しました！")

    st.divider()

    st.header("📊 今月の変動費ダッシュボード")

    raw_var_data = sheet_variable.get_all_records()
    raw_fix_data = sheet_fixed.get_all_records()

    df_fix = pd.DataFrame(raw_fix_data) if raw_fix_data else pd.DataFrame(columns=['中分類', '金額'])
    df_fix['金額'] = pd.to_numeric(df_fix['金額'], errors='coerce').fillna(0)
    fixed_total_monthly = df_fix['金額'].sum()

    if raw_var_data:
        df_var = pd.DataFrame(raw_var_data)
        df_var['金額'] = pd.to_numeric(df_var['金額'], errors='coerce').fillna(0)
        df_var['日付'] = pd.to_datetime(df_var['日付'], errors='coerce')
        df_var['年月'] = df_var['日付'].dt.strftime('%Y-%m')

        available_months = sorted(df_var['年月'].dropna().unique(), reverse=True)
        
        current_ym = datetime.date.today().strftime('%Y-%m')
        if current_ym not in available_months:
            available_months.insert(0, current_ym)

        selected_month = st.selectbox("📅 表示する月を選択", available_months)

        filtered_var_df = df_var[df_var['年月'] == selected_month].copy()
        var_total = filtered_var_df['金額'].sum() if not filtered_var_df.empty else 0

        # 🍔 当月の外食回数と外食合計金額をカウント
        if not filtered_var_df.empty and '中分類' in filtered_var_df.columns:
            eat_out_df = filtered_var_df[filtered_var_df['中分類'] == '外食費']
            eat_out_count = len(eat_out_df)
            eat_out_total = eat_out_df['金額'].sum()
        else:
            eat_out_count = 0
            eat_out_total = 0

        grand_total = fixed_total_monthly + var_total

        # 💰 1. メインダッシュボード指標
        m_col1, m_col2, m_col3 = st.columns(3)
        m_col1.metric("🛒 今月の変動費", f"{var_total:,.0f} 円")
        m_col2.metric("🍔 外食回数", f"{eat_out_count} 回", delta=f"計 {eat_out_total:,.0f}円" if eat_out_count > 0 else None, delta_color="normal")
        m_col3.metric("💳 総支出", f"{grand_total:,.0f} 円")

        # 🎯 2. 【メイン画面】変動費だけの内訳円グラフ（%のみ表示）
        if not filtered_var_df.empty and var_total > 0:
            st.subheader(f"🎨 {selected_month} の変動費内訳")
            
            fig_var = px.pie(
                filtered_var_df, 
                values='金額', 
                names='中分類', 
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            # 📱 グラフの内側は「%（パーセント）」のみに設定
            fig_var.update_traces(
                textposition='inside', 
                textinfo='percent',
                hovertemplate='%{label}: %{value:,}円 (%{percent})'
            )
            fig_var.update_layout(
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=-0.25,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(t=20, b=50, l=10, r=10),
                height=350
            )
            st.plotly_chart(fig_var, use_container_width=True)
        else:
            st.info("選択された月の変動費データはまだありません。")

        # 📋 変動費の登録履歴一覧
        with st.expander("📋 今月の変動費 登録履歴一覧を見る"):
            if not filtered_var_df.empty:
                display_df = filtered_var_df.copy()
                display_df['日付'] = display_df['日付'].dt.strftime('%Y-%m-%d')
                st.dataframe(display_df.drop(columns=['年月']).sort_index(ascending=False), use_container_width=True)
            else:
                st.info("履歴はありません。")

        st.divider()

        # 🔻 3. 【サブ表示】固定費を含めた全体バランス（折りたたみ表示 ＆ スマホ最適化）
        with st.expander("🔍 【サブ】固定費を含めた全体支出バランスを見る"):
            st.caption(f"毎月の固定費設定額: {fixed_total_monthly:,.0f} 円")
            
            df_fix_chart = df_fix.copy()
            df_fix_chart['大分類'] = '固定費'

            df_var_chart = filtered_var_df[['中分類', '金額']].copy() if not filtered_var_df.empty else pd.DataFrame(columns=['中分類', '金額'])
            df_var_chart['大分類'] = '変動費'

            combined_df = pd.concat([df_fix_chart, df_var_chart], ignore_index=True)

            if not combined_df.empty and combined_df['金額'].sum() > 0:
                fig_sub = px.pie(
                    combined_df, 
                    values='金額', 
                    names='中分類', 
                    title=f'固定費 ＋ 変動費 全体割合（{selected_month}）',
                    hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                fig_sub.update_traces(
                    textposition='inside', 
                    textinfo='percent',
                    hovertemplate='%{label}: %{value:,}円 (%{percent})'
                )
                fig_sub.update_layout(
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=-0.3,
                        xanchor="center",
                        x=0.5
                    ),
                    margin=dict(t=40, b=60, l=10, r=10),
                    height=380
                )
                st.plotly_chart(fig_sub, use_container_width=True)

    else:
        st.info("まだ変動費データが登録されていません。上のフォームから入力してください！")

# ---------------------------------------------------------
# TAB 2: 固定費の設定・定期見直し
# ---------------------------------------------------------
with tab2:
    st.header("⚙️ 毎月の固定費設定")
    st.caption("ここで設定した金額は、毎月自動的に総支出および全体グラフへ計算・引き継ぎされます。")

    raw_fix_data = sheet_fixed.get_all_records()
    df_fix_current = pd.DataFrame(raw_fix_data) if raw_fix_data else pd.DataFrame(columns=['中分類', '金額'])

    updated_costs = {}
    with st.form("fixed_cost_form"):
        for cat in FIXED_CATEGORIES:
            current_val = 0
            if not df_fix_current.empty and cat in df_fix_current['中分類'].values:
                val = df_fix_current[df_fix_current['中分類'] == cat]['金額'].values[0]
                try:
                    current_val = int(val) if (pd.notnull(val) and str(val).strip() != "") else 0
                except (ValueError, TypeError):
                    current_val = 0

            updated_costs[cat] = st.number_input(f"【固定費】{cat} (円)", min_value=0, step=1000, value=current_val)

        if st.form_submit_button("🔄 固定費設定を更新する", type="primary"):
            sheet_fixed.clear()
            sheet_fixed.append_row(["中分類", "金額"])
            for cat, amt in updated_costs.items():
                sheet_fixed.append_row([cat, int(amt)])
            st.success("✅ 固定費の設定を更新しました！毎月の集計に自動適用されます。")
            st.rerun()
