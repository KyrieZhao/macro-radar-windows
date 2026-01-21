import streamlit as st
import pandas as pd
import pandas_datareader.data as web
import yfinance as yf # 👈 云端神器，免代理
import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ==========================================
# 🔧 网页配置 (云端版)
# ==========================================
st.set_page_config(
    page_title="Macro Radar (Global)",
    page_icon="📡",
    layout="wide"
)

# ⚠️ 严禁在这里写 os.environ 代理设置，否则会导致云端服务器死机

# ==========================================
# 📥 数据获取
# ==========================================
@st.cache_data(ttl=3600)
def get_market_data():
    # 1. 美联储数据 (FRED)
    # 云端服务器可以直接连接 FRED
    start_date = (datetime.datetime.now() - datetime.timedelta(days=1095)).strftime('%Y-%m-%d')
    end_date = datetime.datetime.now().strftime('%Y-%m-%d')
    
    try:
        fred_data = web.DataReader(['WALCL', 'WTREGEN', 'RRPONTSYD'], 'fred', start_date, end_date)
        fred_data = fred_data.ffill().dropna()
        fred_data['Net_Liquidity'] = (fred_data['WALCL'] - fred_data['WTREGEN'] - fred_data['RRPONTSYD']) / 1000
    except Exception as e:
        st.error(f"美联储数据获取失败: {e}")
        return None
    
    # 2. 比特币数据 (Yahoo Finance)
    # yfinance 在云端最稳定
    try:
        btc_data = yf.download('BTC-USD', start=start_date, end=end_date, progress=False)
        btc_data.index = btc_data.index.tz_localize(None)
        btc_df = btc_data[['Close']].copy()
    except Exception as e:
        st.error(f"比特币数据获取失败: {e}")
        return None
    
    # 3. 合并
    df = pd.merge(fred_data[['Net_Liquidity']], btc_df, left_index=True, right_index=True, how='inner')
    df.rename(columns={'Close': 'BTC_Price'}, inplace=True)
    
    return df

# ==========================================
# 🧮 信号计算 (保持原逻辑)
# ==========================================
def calculate_signal(df):
    df['Liq_SMA_20'] = df['Net_Liquidity'].rolling(window=20).mean()
    df['BTC_SMA_20'] = df['BTC_Price'].rolling(window=20).mean()
    df['Correlation'] = df['Net_Liquidity'].rolling(window=30).corr(df['BTC_Price'])

    def get_status(row):
        liq_trend_up = row['Net_Liquidity'] > row['Liq_SMA_20']
        btc_trend_up = row['BTC_Price'] > row['BTC_SMA_20']
        high_corr = row['Correlation'] > 0.5
        
        if liq_trend_up and btc_trend_up and high_corr: return "🟢 STRONG LONG"
        elif not liq_trend_up and btc_trend_up: return "🔴 DIVERGENCE (Risk)"
        elif liq_trend_up and not btc_trend_up: return "🟡 BUY OPPORTUNITY"
        else: return "⚪ NEUTRAL"

    df['Signal'] = df.apply(get_status, axis=1)
    return df

# ==========================================
# 🖥️ 界面渲染
# ==========================================
st.title("📡 Macro Radar (Cloud Edition)")
st.markdown("全球流动性雷达 | 实时云端部署版")

with st.spinner('正在连接全球服务器...'):
    raw_df = get_market_data()
    if raw_df is not None:
        df = calculate_signal(raw_df)
        latest = df.iloc[-1]
        
        # 指标卡
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("BTC Price", f"${latest['BTC_Price']:,.0f}")
        c2.metric("Net Liquidity", f"${latest['Net_Liquidity']:,.2f} B")
        c3.metric("Correlation", f"{latest['Correlation']:.2f}")
        c4.info(f"Signal: {latest['Signal']}")

        # 图表
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Scatter(x=df.index, y=df['Net_Liquidity'], name="Liquidity", fill='tozeroy', line=dict(color='rgba(0, 180, 255, 0.5)')), secondary_y=False)
        fig.add_trace(go.Scatter(x=df.index, y=df['BTC_Price'], name="BTC", line=dict(color='#F7931A')), secondary_y=True)
        fig.update_layout(template="plotly_dark", height=600, hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)