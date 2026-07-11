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
    r = subprocess.run(['node', js_path], capture_output=True, timeout=10)
    _WENCAI_TOKEN = r.stdout.decode().strip()
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
    coms = content.get('components', [])
    if not coms: return pd.DataFrame()
    ds = coms[0].get('data', {}).get('datas', [])
    return pd.DataFrame(ds) if ds else pd.DataFrame()


import zzshare, time as _ttime
_ZZSHARE_TOKEN = os.environ.get("ZZSHARE_TOKEN", "37334f4dbf2dc4a3fe972e99b91fb9df7a7aed313a537b37586a2b7ce500c1e0")
_ZZ_API = zzshare.DataApi(_ZZSHARE_TOKEN)


def get_latest_trade_date():
    try: return _ZZ_API.trade_days()[-1]
    except:
        n = datetime.now()
        if n.weekday() == 5: return (n - timedelta(days=1)).strftime('%Y-%m-%d')
        if n.weekday() == 6: return (n - timedelta(days=2)).strftime('%Y-%m-%d')
        return n.strftime('%Y-%m-%d')


def get_kline_slope(stock_code, end_date, n_days=25):
    c = stock_code.replace('.SH', '').replace('.SZ', '')
    if c.startswith('6'): c = f"{c}.SH"
    elif c.startswith(('0', '3')): c = f"{c}.SZ"
    else: return 0, 0, 0, []
    try:
        _ttime.sleep(0.05)
        sd = (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=60)).strftime('%Y%m%d')
        k = _ZZ_API.daily(ts_code=c, start_date=sd, end_date=end_date.replace('-', ''))
        if k is None or k.empty: return 0, 0, 0, []
        p = k['close'].values[-n_days:]
        if len(p) < 10: return 0, 0, 0, []
        if p[0] <= 0: return 0, 0, 0, []
        rp = p / p[0]
        x = np.arange(len(rp)).reshape(-1, 1)
        lr = LinearRegression()
        lr.fit(x, rp)
        return lr.coef_[0], lr.score(x, rp), 10000 * lr.coef_[0] * lr.score(x, rp), p.tolist()
    except: return 0, 0, 0, []


def min_max_normalize(s):
    s = np.array(s, dtype=float)
    return (s - s.min()) / (s.max() - s.min()) if s.max() != s.min() else np.zeros_like(s)


THRESHOLDS = {
    "loose": {"label": "🔵 宽松", "slope": 0.003, "r2": 0.3},
    "medium": {"label": "🟡 中等", "slope": 0.005, "r2": 0.5},
    "strict": {"label": "🔴 严格", "slope": 0.008, "r2": 0.7},
}


def run_strong_stock_screen(date_str=None, top_n=10, n_days=25, positive_only=False, mode="medium"):
    t = THRESHOLDS.get(mode, THRESHOLDS["medium"])
    d = date_str or get_latest_trade_date()
    print(f"{'='*60}\n📊 强势股选股工具\n📅 交易日: {d}\n{'='*60}")

    # Step 1
    print("\n[步骤1/5] 获取(成交额/自由流通市值*100)TOP100...")
    dfv = _wencai_to_df(f"{d}(成交额/自由流通市值*100)前100", perpage=100)
    if dfv.empty: print("  ❌ 失败"); return pd.DataFrame()
    ratio_col = [c for c in dfv.columns if '100.0' in c and '{/}' in c][0]
    vol_col = [c for c in dfv.columns if c.startswith('成交额[')][0]
    mkt_col = [c for c in dfv.columns if c.startswith('自由流通市值[')][0]
    vol_rank = {code: i+1 for i, code in enumerate(dfv['股票代码'].tolist())}
    print(f"  ✅ {len(dfv)} 只")

    # Step 2
    print("[步骤2/5] 获取热度TOP100...")
    dfh = _wencai_to_df(f"{d}个股热度前100", perpage=100)
    if dfh.empty: print("  ❌ 失败"); return pd.DataFrame()
    hot_col = [c for c in dfh.columns if '个股热度[' in c][0]
    hot_rank_col = [c for c in dfh.columns if '个股热度排名' in c][0]
    print(f"  ✅ {len(dfh)} 只")

    # Step 3
    print("[步骤3/5] 取交集股票...")
    common = set(dfv['股票代码'].tolist()) & set(dfh['股票代码'].tolist())
    print(f"  ✅ 交集: {len(common)} 只")
    if len(common) < 3: print("  ❌ 交集太少"); return pd.DataFrame()

    rd = dfv.set_index('股票代码')[ratio_col].to_dict()
    vd = dfv.set_index('股票代码')[vol_col].to_dict()
    md = dfv.set_index('股票代码')[mkt_col].to_dict()
    hd = dfh.set_index('股票代码')[hot_col].to_dict()
    hr = dfh.set_index('股票代码')[hot_rank_col].to_dict()
    nd = dfv.set_index('股票代码')['股票简称'].to_dict()

    rows = []
    for code in common:
        rows.append({
            '代码': code, '名称': nd.get(code, ''),
            '比值': float(rd.get(code, 0) or 0),
            '成交额': float(vd.get(code, 0) or 0),
            '流通市值': float(md.get(code, 0) or 0),
            '比值排名': int('比值排名': int(vol_rank.get(code, 0)),
),
            '热度': float(hd.get(code, 0) or 0),
            '热度排名': str(hr.get(code, '')),
        })
    df = pd.DataFrame(rows)
    df['比值_norm'] = min_max_normalize(df['比值'].values)
    df['热度_norm'] = min_max_normalize(df['热度'].values)
    df['成交额_norm'] = df['比值_norm']
    df['综合评分'] = round((df['比值_norm'] + df['热度_norm']) / 2, 4)

    # Step 4
    print(f"[步骤4/5] 计算{n_days}日线性回归动量...")
    slopes, r2s, moms = [], [], []
    ok = 0
    for i, code in enumerate(df['代码']):
        s, r2, m, _ = get_kline_slope(code, d, n_days=n_days)
        slopes.append(s); r2s.append(r2); moms.append(m)
        if m != 0: ok += 1
        if (i+1) % 10 == 0: print(f"    进度: {i+1}/{len(df)} (成功{ok})")

    df['斜率'] = [round(x, 6) for x in slopes]
    df['R²'] = [round(x, 4) for x in r2s]
    df['动量评分'] = [round(x, 2) for x in moms]
    df['动量_norm'] = min_max_normalize(df['动量评分'].values)

      # Step 5
    print("[步骤5/5] 排序输出...")
    df['总分'] = round(df['成交额_norm'] + df['热度_norm'] + df['动量_norm'], 4)

    if positive_only:
        df = df[df['动量评分'] > 0].sort_values('动量评分', ascending=False).reset_index(drop=True)
        df_r = df.head(top_n).reset_index(drop=True)
        title = f"📈 上涨趋势股 TOP{min(top_n, len(df_r))}（斜率>0）"
        subtitle = f"   共 {len(df)} 只斜率正值，展示前{len(df_r)}"
    else:
        df_r = df.sort_values('总分', ascending=False).head(top_n).reset_index(drop=True)
        title = f"🏆 强势股 TOP{len(df_r)}"
        subtitle = f"   综合评分 = 比值_norm + 热度_norm + 动量_norm | 动量 = {n_days}日斜率×R²×10000"
        subtitle += f"\n   ⭐️标记标准: {t['label']} 斜率>{t['slope']} & R²>{t['r2']}"

    print(f"\n{'='*80}\n📊 {title}\n{subtitle}\n📅 交易日: {d}\n{'='*80}")
    print(f"{'排名':>4} {'代码':<14} {'名称':<10} {'动量评分':>8} {'斜率':>8} {'R²':>6} {'趋势':>6} {'比值排名':>10} {'热度排名':>8}")
    print("-" * 80)
    for i, (_, r) in enumerate(df_r.iterrows(), 1):
        vr = f"{int(r['比值排名'])}/5536" if r['比值排名'] else ''
        star = "⭐️" if (not positive_only and r['动量评分'] > 0) else (" ★" if positive_only and r['斜率'] > t['slope'] and r['R²'] > t['r2'] else "")
        print(f"{i:>4} {r['代码']:<14} {r['名称']:<10} {r['动量评分']:>8.2f} {r['斜率']:>8.4f} {r['R²']:>6.3f} {'📈' if r['动量评分']>0 else '📉'}{star:>2} {vr:>10} {str(r['热度排名']):>8}")

    output_file = f"{'上涨趋势_' if positive_only else ''}强势股_{d}.csv"
    df_save = df_r.copy()
    if '比值排名' in df_save.columns:
        df_save['比值排名'] = df_save['比值排名'].apply(lambda x: f"{int(x)}/5536")
    df_save.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"\n💾 已保存: {output_file}")
    return df_r


if __name__ == "__main__":
    da = None; tn = 10; nd = 25; po = False; mo = "medium"
    a = sys.argv[1:]; i = 0
    while i < len(a):
        if a[i] == "--date" and i+1 < len(a): da = a[i+1]; i += 1
        elif a[i] == "--top" and i+1 < len(a): tn = int(a[i+1]); i += 1
        elif a[i] == "--days" and i+1 < len(a): nd = int(a[i+1]); i += 1
        elif a[i] in ("--positive","--up","--up-only"): po = True
        elif a[i] == "--strict": mo = "strict"
        elif a[i] == "--loose": mo = "loose"
        i += 1
    run_strong_stock_screen(date_str=da, top_n=tn, n_days=nd, positive_only=po, mode=mo)
