import streamlit as st
import pandas as pd
import pandas_datareader.data as web
import yfinance as yf
import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ==========================================
# 🔧 网页配置
# ==========================================
st.set_page_config(
    page_title="Macro Radar (Live)",
    page_icon="📡",
    layout="wide"
)

# ==========================================
# 📥 数据获取 (缓存缩短为 5 分钟 = 300秒)
# ==========================================
@st.cache_data(ttl=300) 
def get_market_data():
    # 时间范围：过去3年
    start_date = (datetime.datetime.now() - datetime.timedelta(days=1095)).strftime('%Y-%m-%d')
    end_date = datetime.datetime.now().strftime('%Y-%m-%d')

    # 1. 获取美联储数据 (宏观-慢速数据)
    try:
        fred_data = web.DataReader(['WALCL', 'WTREGEN', 'RRPONTSYD'], 'fred', start_date, end_date)
        fred_data = fred_data.ffill().dropna()
        fred_data['Net_Liquidity'] = (fred_data['WALCL'] - fred_data['WTREGEN'] - fred_data['RRPONTSYD']) / 1000
        
        # 清洗索引
        fred_data.index = pd.to_datetime(fred_data.index)
        if fred_data.index.tz is not None: fred_data.index = fred_data.index.tz_localize(None)
            
    except Exception as e:
        st.error(f"美联储数据获取失败: {e}")
        return None
    
    # 2. 获取比特币数据 (市场-快速数据)
    try:
        # 强制获取最新数据，虽然是日线，但包含当天的最新报价
        btc_data = yf.download('BTC-USD', start=start_date, end=end_date, progress=False)
        
        if isinstance(btc_data.columns, pd.MultiIndex): btc_df = btc_data['Close']
        else: btc_df = btc_data[['Close']]
            
        # 清洗索引
        btc_df.index = pd.to_datetime(btc_df.index)
        if btc_df.index.tz is not None: btc_df.index = btc_df.index.tz_localize(None)
        
        # 统一列名
        if isinstance(btc_df, pd.Series): btc_df = btc_df.to_frame(name='BTC_Price')
        else: 
            btc_df.rename(columns={'Close': 'BTC_Price'}, inplace=True)
            if 'BTC_Price' not in btc_df.columns: btc_df.columns = ['BTC_Price']

    except Exception as e:
        st.error(f"比特币数据获取失败: {e}")
        return None
    
    # 3. 合并数据
    try:
        df_liq = fred_data[['Net_Liquidity']]
        # 使用 outer join 保留最新的 BTC 数据，即使今天的美联储数据还没出
        # 这样能保证你看到最新的币价，而不用等美联储更新
        df = df_liq.join(btc_df, how='outer').ffill().dropna()
    except Exception as e:
        st.error(f"数据合并失败: {e}")
        return None
    
    return df

# ==========================================
# 🧮 信号计算
# ==========================================
def calculate_signal(df):
    df['Liq_SMA_20'] = df['Net_Liquidity'].rolling(window=20).mean()
    df['BTC_SMA_20'] = df['BTC_Price'].rolling(window=20).mean()
    df['Correlation'] = df['Net_Liquidity'].rolling(window=30).corr(df['BTC_Price'])

    def get_status(row):
        # 简单的信号逻辑
        liq_trend_up = row['Net_Liquidity'] > row['Liq_SMA_20']
        btc_trend_up = row['BTC_Price'] > row['BTC_SMA_20']
        
        if liq_trend_up and btc_trend_up: return "🟢 STRONG LONG"
        elif not liq_trend_up and btc_trend_up: return "🔴 DIVERGENCE (Risk)"
        elif liq_trend_up and not btc_trend_up: return "🟡 BUY OPPORTUNITY"
        else: return "⚪ NEUTRAL"

    df['Signal'] = df.apply(get_status, axis=1)
    return df

# ==========================================
# 🖥️ 界面渲染
# ==========================================
st.title("📡 Macro Radar (Cloud Live)")
st.markdown(f"最后更新时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (UTC)")

# --- 侧边栏控制区 ---
st.sidebar.header("控制台")
if st.sidebar.button("🔄 立即刷新数据"):
    st.cache_data.clear()
    st.rerun()
st.sidebar.info("提示：由于美联储数据是日更，图表保持日线级别。点击刷新可获取最新 BTC 实时价格。")

with st.spinner('正在同步全球数据...'):
    raw_df = get_market_data()
    
    if raw_df is not None and not raw_df.empty:
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
