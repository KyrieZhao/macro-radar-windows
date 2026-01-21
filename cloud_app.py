import streamlit as st
import pandas as pd
import pandas_datareader.data as web
import yfinance as yf # <--- 改用 Yahoo，全球通用
import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ==========================================
# 🔧 网页配置
# ==========================================
st.set_page_config(
    page_title="Macro Radar (Cloud)",
    page_icon="📡",
    layout="wide"
)

# 注意：云端版本删除了所有 VPN/Proxy 设置，因为云服务器自带国际互联网

# ==========================================
# 📥 数据获取函数
# ==========================================
@st.cache_data(ttl=3600)
def get_market_data():
    # 1. 获取美联储数据 (FRED)
    # 云端服务器可以直接访问 FRED，不需要代理
    start_date = (datetime.datetime.now() - datetime.timedelta(days=1095)).strftime('%Y-%m-%d')
    end_date = datetime.datetime.now().strftime('%Y-%m-%d')
    
    try:
        fred_data = web.DataReader(['WALCL', 'WTREGEN', 'RRPONTSYD'], 'fred', start_date, end_date)
        fred_data = fred_data.ffill().dropna()
        fred_data['Net_Liquidity'] = (fred_data['WALCL'] - fred_data['WTREGEN'] - fred_data['RRPONTSYD']) / 1000
    except Exception as e:
        st.error(f"FRED 数据连接失败: {e}")
        return None
    
    # 2. 获取比特币数据 (Yahoo Finance)
    # yfinance 在云端服务器运行非常稳定，不需要 API Key
    try:
        btc_data = yf.download('BTC-USD', start=start_date, end=end_date, progress=False)
        # 格式清洗
        btc_data.index = btc_data.index.tz_localize(None)
        btc_df = btc_data[['Close']].copy()
    except Exception as e:
        st.error(f"Yahoo 财经数据连接失败: {e}")
        return None
    
    # 3. 合并数据
    df = pd.merge(fred_data[['Net_Liquidity']], btc_df, left_index=True, right_index=True, how='inner')
    df.rename(columns={'Close': 'BTC_Price'}, inplace=True)
    
    return df

# ==========================================
# 🧮 信号计算逻辑 (保持不变)
# ==========================================
def calculate_signal(df):
    df['Liq_SMA_20'] = df['Net_Liquidity'].rolling(window=20).mean()
    df['BTC_SMA_20'] = df['BTC_Price'].rolling(window=20).mean()
    df['Correlation'] = df['Net_Liquidity'].rolling(window=30).corr(df['BTC_Price'])

    def get_status(row):
        liq_trend_up = row['Net_Liquidity'] > row['Liq_SMA_20']
        btc_trend_up = row['BTC_Price'] > row['BTC_SMA_20']
        high_corr = row['Correlation'] > 0.5
        
        if liq_trend_up and btc_trend_up and high_corr:
            return "🟢 STRONG LONG"
        elif not liq_trend_up and btc_trend_up:
            return "🔴 DIVERGENCE (Risk)"
        elif liq_trend_up and not btc_trend_up:
             return "🟡 BUY OPPORTUNITY"
        else:
            return "⚪ NEUTRAL"

    df['Signal'] = df.apply(get_status, axis=1)
    return df

# ==========================================
# 🖥️ 网页主界面
# ==========================================
st.title("📡 Macro Radar (Online)")
st.markdown("Global Net Liquidity vs Bitcoin | Real-time Dashboard")

with st.spinner('Fetching data from global servers...'):
    raw_df = get_market_data()
    if raw_df is not None:
        df = calculate_signal(raw_df)
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 指标卡
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("BTC Price", f"${latest['BTC_Price']:,.0f}", f"{latest['BTC_Price'] - prev['BTC_Price']:.2f}")
        with col2:
            st.metric("Fed Net Liquidity", f"${latest['Net_Liquidity']:,.2f} B", f"{latest['Net_Liquidity'] - prev['Net_Liquidity']:.2f} B")
        with col3:
            st.metric("Correlation", f"{latest['Correlation']:.2f}")
        with col4:
            st.info(f"Signal: {latest['Signal']}")

        # 图表
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Scatter(x=df.index, y=df['Net_Liquidity'], name="Liquidity", fill='tozeroy', line=dict(color='rgba(0, 180, 255, 0.5)')), secondary_y=False)
        fig.add_trace(go.Scatter(x=df.index, y=df['BTC_Price'], name="BTC Price", line=dict(color='#F7931A')), secondary_y=True)
        fig.update_layout(template="plotly_dark", height=600, hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)