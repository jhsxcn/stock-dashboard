"""
强势股选股工具
数据源: 问财（成交额/自由流通市值*100 的TOP100 + 热度TOP100 交集）
动量计算: 25日线性回归斜率 × R²
综合评分: 比值_norm + 热度_norm + 动量_norm
阈值: --strict(🔴) / 默认(🟡) / --loose(🔵)
"""

import sys, warnings, os, numpy as np, pandas as pd
from datetime import datetime, timedelta
from sklearn.linear_model import LinearRegression

warnings.filterwarnings('ignore')
os.environ['NODE_NO_WARNINGS'] = '1'
os.environ['NODE_OPTIONS'] = '--no-warnings --no-deprecation'

import requests, json, subprocess, pydash as _

_WENCAI_TOKEN = None

def _get_wencai_token():
    global _WENCAI_TOKEN
    if _WENCAI_TOKEN: return _WENCAI_TOKEN
    import pywencai
    js_path = os.path.join(os.path.dirname(pywencai.__file__), 'hexin-v.bundle.js')
    for p in [js_path, '/root/.pyenv/versions/3.11.1/lib/python3.11/site-packages/pywencai/hexin-v.bundle.js']:
        if os.path.exists(p): js_path = p; break
    result = subprocess.run(['node', js_path], capture_output=True, timeout=10)
    _WENCAI_TOKEN = result.stdout.decode().strip()
    return _WENCAI_TOKEN

def _wencai_request(question, perpage=50):
    token = _get_wencai_token()
    payload = {
        "add_info": '{"urp":{"scene":1,"company":1,"business":1},"contentType":"json","searchInfo":true}',
        "perpage": str(perpage), "page": 1, "source": "Ths_iwencai_Xuangu",
        "version": "2.0", "secondary_intent": "stock", "question": question,
    }
    headers = {
        "hexin-v": token, "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json", "Referer": "https://www.iwencai.com/",
    }
    resp = requests.post("http://www.iwencai.com/customized/chart/get-robot-data", json=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()

def _wencai_to_df(question, perpage=50):
    result = _wencai_request(question, perpage=perpage)
    content = _.get(result, 'data.answer.0.txt.0.content')
    if content and isinstance(content, str): content = json.loads(content)
    if not content: return pd.DataFrame()
    components = content.get('components', [])
    if not components: return pd.DataFrame()
    comp_data = components[0].get('data', {})
    datas = comp_data.get('datas', [])
    if not datas: return pd.DataFrame()
    return pd.DataFrame(datas)

import zzshare, time as _ttime

_ZZSHARE_TOKEN = os.environ.get("ZZSHARE_TOKEN", "37334f4dbf2dc4a3fe972e99b91fb9df7a7aed313a537b37586a2b7ce500c1e0")
_ZZ_API = zzshare.DataApi(_ZZSHARE_TOKEN)

def get_latest_trade_date():
    try:
        return _ZZ_API.trade_days()[-1]
    except:
        now = datetime.now()
        if now.weekday() == 5: return (now - timedelta(days=1)).strftime('%Y-%m-%d')
        elif now.weekday() == 6: return (now - timedelta(days=2)).strftime('%Y-%m-%d')
        return now.strftime('%Y-%m-%d')

def get_kline_slope(stock_code, end_date, n_days=25):
    ts_code = stock_code.replace('.SH', '').replace('.SZ', '')
    if ts_code.startswith('6'): ts_code = f"{ts_code}.SH"
    elif ts_code.startswith(('0', '3')): ts_code = f"{ts_code}.SZ"
    else: return 0, 0, 0, []
    try:
        _ttime.sleep(0.05)
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        start_dt = end_dt - timedelta(days=60)
        kline = _ZZ_API.daily(ts_code=ts_code, start_date=start_dt.strftime('%Y%m%d'), end_date=end_date.replace('-', ''))
        if kline is None or kline.empty: return 0, 0, 0, []
        prices = kline['close'].values[-n_days:]
        if len(prices) < 10: return 0, 0, 0, []
        base_price = prices[0]
        if base_price <= 0: return 0, 0, 0, []
        relative_prices = prices / base_price
        x = np.arange(len(relative_prices)).reshape(-1, 1)
        lr = LinearRegression()
        lr.fit(x, relative_prices)
        slope = lr.coef_[0]
        r_squared = lr.score(x, relative_prices)
        momentum_score = 10000 * slope * r_squared
        return slope, r_squared, momentum_score, prices.tolist()
    except Exception:
        return 0, 0, 0, []

def min_max_normalize(series):
    s = np.array(series, dtype=float)
    min_v, max_v = s.min(), s.max()
    if max_v == min_v: return np.zeros_like(s)
    return (s - min_v) / (max_v - min_v)

THRESHOLDS = {
    "loose":  {"label": "🔵 宽松", "slope": 0.003, "r2": 0.3, "desc": "斜率>0.003 & R²>0.3"},
    "medium": {"label": "🟡 中等", "slope": 0.005, "r2": 0.5, "desc": "斜率>0.005 & R²>0.5"},
    "strict": {"label": "🔴 严格", "slope": 0.008, "r2": 0.7, "desc": "斜率>0.008 & R²>0.7"},
}

def run_strong_stock_screen(date_str=None, top_n=10, n_days=25, positive_only=False, mode="medium"):
    t = THRESHOLDS.get(mode, THRESHOLDS["medium"])
    d = date_str or get_latest_trade_date()
    print(f"{'='*60}\n📊 强势股选股工具\n📅 交易日: {d}\n{'='*60}")

    print("\n[步骤1/5] 获取(成交额/自由流通市值*100)TOP100...")
    df_vol = _wencai_to_df(f"{d}(成交额/自由流通市值*100)前100", perpage=100)
    if df_vol.empty: print("  ❌ 失败"); return pd.DataFrame()
    ratio_col = [c for c in df_vol.columns if '100.0' in c and '{/}' in c][0]
    vol_col = [c for c in df_vol.columns if c.startswith('成交额[')][0]
    mkt_col = [c for c in df_vol.columns if c.startswith('自由流通市值[')][0]
    vol_rank = {code: f"{i+1}/5536" for i, code in enumerate(df_vol['股票代码'].tolist())}
    print(f"  ✅ {len(df_vol)} 只")

    print("[步骤2/5] 获取热度TOP100...")
    df_hot = _wencai_to_df(f"{d}个股热度前100", perpage=100)
    if df_hot.empty: print("  ❌ 失败"); return pd.DataFrame()
    hot_col = [c for c in df_hot.columns if '个股热度[' in c][0]
    hot_rank_col = [c for c in df_hot.columns if '个股热度排名' in c][0]
    print(f"  ✅ {len(df_hot)} 只")

    print("[步骤3/5] 取交集股票...")
    vol_codes = set(df_vol['股票代码'].tolist())
    hot_codes = set(df_hot['股票代码'].tolist())
    common_codes = vol_codes & hot_codes
    print(f"  ✅ 交集: {len(common_codes)} 只")
    if len(common_codes) < 3: print("  ❌ 交集股票太少"); return pd.DataFrame()

    ratio_dict = df_vol.set_index('股票代码')[ratio_col].to_dict()
    vol_dict = df_vol.set_index('股票代码')[vol_col].to_dict()
    mkt_dict = df_vol.set_index('股票代码')[mkt_col].to_dict()
    hot_dict = df_hot.set_index('股票代码')[hot_col].to_dict()
    hot_rank_dict = df_hot.set_index('股票代码')[hot_rank_col].to_dict()
    name_dict = df_vol.set_index('股票代码')['股票简称'].to_dict()

    common_list = []
    for code in common_codes:
        common_list.append({
            '代码': code, '名称': name_dict.get(code, ''),
            '比值': float(ratio_dict.get(code, 0) or 0),
            '成交额': float(vol_dict.get(code, 0) or 0),
            '流通市值': float(mkt_dict.get(code, 0) or 0),
            '比值排名': vol_rank.get(code, ''),
            '热度': float(hot_dict.get(code, 0) or 0),
            '热度排名': str(hot_rank_dict.get(code, '')),
        })
    df_common = pd.DataFrame(common_list)
    df_common['比值_norm'] = min_max_normalize(df_common['比值'].values)
    df_common['热度_norm'] = min_max_normalize(df_common['热度'].values)
    df_common['成交额_norm'] = df_common['比值_norm']
    df_common['综合评分'] = round((df_common['比值_norm'] + df_common['热度_norm']) / 2, 4)

    print(f"[步骤4/5] 计算{n_days}日线性回归动量...")
    slopes, r2s, 
