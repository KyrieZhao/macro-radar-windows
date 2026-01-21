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
    page_title="Macro Radar (Real-Time Pro)",
    page_icon="📡",
    layout="wide"
)

# ==========================================
# 📥 数据获取核心
# ==========================================
@st.cache_data(ttl=60) # 缩短缓存到 60秒，保证价格新鲜
def get_market_data():
    # 设定时间窗口
    start_date = (datetime.datetime.now() - datetime.timedelta(days=1095)).strftime('%Y-%m-%d')
    # 🌟 关键修正：结束日期设为“明天”，确保包含“今天”的实时K线
    end_date = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')

    # --- 1. 获取美联储流动性 (FRED) ---
    try:
        # 注意：这里 end_date 用今天即可，因为美联储数据没那么快
        fred_end = datetime.datetime.now().strftime('%Y-%m-%d')
        fred_data = web.DataReader(['WALCL', 'WTREGEN', 'RRPONTSYD'], 'fred', start_date, fred_end)
        fred_data = fred_data.ffill().dropna()
        fred_data['Net_Liquidity'] = (fred_data['WALCL'] - fred_data['WTREGEN'] - fred_data['RRPONTSYD']) / 1000
        
        # 清洗时间索引
        fred_data.index = pd.to_datetime(fred_data.index)
        if fred_data.index.tz is not None: fred_data.index = fred_data.index.tz_localize(None)
    except Exception as e:
        st.error(f"美联储数据获取失败: {e}")
        return None, None
    
    # --- 2. 获取比特币日线数据 (用于画图) ---
    try:
        # 使用 period 替代 start/end 可以更智能地获取最新数据
        btc_data = yf.download('BTC-USD', start=start_date, end=end_date, interval="1d", progress=False)
        if isinstance(btc_data.columns, pd.MultiIndex): btc_df = btc_data['Close']
        else: btc_df = btc_data[['Close']]
        
        # 清洗
        btc_df.index = pd.to_datetime(btc_df.index)
        if btc_df.index.tz is not None: btc_df.index = btc_df.index.tz_localize(None)
        
        # 统一列名
        if isinstance(btc_df, pd.Series): btc_df = btc_df.to_frame(name='BTC_Price')
        else: btc_df.rename(columns={'Close': 'BTC_Price'}, inplace=True)
        if 'BTC_Price' not in btc_df.columns: btc_df.columns = ['BTC_Price']

    except Exception as e:
        st.error(f"比特币日线获取失败: {e}")
        return None, None

    # --- 3. 🌟 额外获取：当前最新实时价格 (用于顶部大数字) ---
    try:
        # 只抓过去1天的 1分钟 K线，取最后一根，这是最接近 TradingView 的价格
        live_data = yf.download('BTC-USD', period='1d', interval='1m', progress=False)
        if not live_data.empty:
            # 无论数据结构如何，取最后一行 Close
            if isinstance(live_data.columns, pd.MultiIndex): 
                current_price = float(live_data['Close'].iloc[-1].iloc[0]) if isinstance(live_data['Close'].iloc[-1], pd.Series) else float(live_data['Close'].iloc[-1])
            else:
                current_price = float(live_data['Close'].iloc[-1])
        else:
            # 如果抓不到分钟线，降级使用日线的最后一个价格
            current_price = float(btc_df['BTC_Price'].iloc[-1])
    except:
        current_price = float(btc_df['BTC_Price'].iloc[-1])

    # --- 4. 合并数据 (用于画图) ---
    try:
        df_liq = fred_data[['Net_Liquidity']]
        # 使用 outer join 确保即使美联储今天没更新，BTC数据也能显示
        df = df_liq.join(btc_df, how='outer').ffill().dropna()
    except Exception as e:
        st.error(f"数据合并失败: {e}")
        return None, None
    
    return df, current_price

# ==========================================
# 🧮 信号计算
# ==========================================
def calculate_signal(df):
    df['Liq_SMA_20'] = df['Net_Liquidity'].rolling(window=20).mean()
    df['BTC_SMA_20'] = df['BTC_Price'].rolling(window=20).mean()
    df['Correlation'] = df['Net_Liquidity'].rolling(window=30).corr(df['BTC_Price'])

    def get_status(row):
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
st.title("📡 Macro Radar (Real-Time)")
st.caption(f"Last Check: {datetime.datetime.now().strftime('%H:%M:%S')} | Source: Yahoo Finance (1m Live) + FRED")

# 侧边栏
st.sidebar.header("Control Panel")
if st.sidebar.button("🔄 Force Refresh"):
    st.cache_data.clear()
    st.rerun()

with st.spinner('Syncing with global markets...'):
    df, live_price = get_market_data()
    
    if df is not None and not df.empty:
        df = calculate_signal(df)
        latest_chart = df.iloc[-1]
        
        # 计算涨跌幅 (基于图表前一日收盘价)
        prev_close = df['BTC_Price'].iloc[-2]
        delta_val = live_price - prev_close
        
        # 指标卡
        c1, c2, c3, c4 = st.columns(4)
        
        # 🌟 这里的 live_price 是专门抓取的分钟级最新价
        c1.metric("BTC Price (Live)", f"${live_price:,.2f}", f"{delta_val:,.2f}")
        c2.metric("Net Liquidity", f"${latest_chart['Net_Liquidity']:,.2f} B")
        c3.metric("Correlation", f"{latest_chart['Correlation']:.2f}")
        c4.info(f"Signal: {latest_chart['Signal']}")

        # 图表
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Scatter(x=df.index, y=df['Net_Liquidity'], name="Liquidity", fill='tozeroy', line=dict(color='rgba(0, 180, 255, 0.5)')), secondary_y=False)
        fig.add_trace(go.Scatter(x=df.index, y=df['BTC_Price'], name="BTC (Daily Close)", line=dict(color='#F7931A')), secondary_y=True)
        fig.update_layout(template="plotly_dark", height=600, hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)
