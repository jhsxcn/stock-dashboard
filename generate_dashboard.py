#!/usr/bin/env python3
"""
生成独立HTML选股看板 — 不依赖后台服务器，数据嵌入HTML
用法: python3 generate_dashboard.py
输出: dashboard_YYYY-MM-DD.html（双击打开即可）
"""
import os, sys, json
import pandas as pd
from datetime import datetime
from strong_stock import run_strong_stock_screen, THRESHOLDS

def run_all_modes(d=None):
    print("=" * 60)
    print("📊 正在运行四种选股模式...")
    print("=" * 60)
    modes = [
        ("all",       "全部强势股TOP10",     dict(top_n=10, mode="medium", positive_only=False)),
        ("up",        "上涨趋势股",          dict(top_n=50, mode="medium", positive_only=True)),
        ("strict",    "严格模式上涨趋势股",   dict(top_n=50, mode="strict",  positive_only=True)),
        ("loose",     "宽松模式上涨趋势股",   dict(top_n=50, mode="loose",   positive_only=True)),
    ]
    results = {}
    for key, label, params in modes:
        print(f"\n▶ [{key}] {label}")
        df = run_strong_stock_screen(date_str=d, **params)
        results[key] = {"label": label, "data": df.to_dict('records') if not df.empty else [], "count": len(df)}
    return results


def load_from_csv(d=None):
    d = d or datetime.now().strftime('%Y-%m-%d')
    label_map = {"all":"全部强势股TOP10","up":"上涨趋势股","strict":"严格模式","loose":"宽松模式"}
    main_csv = f"强势股_{d}.csv"
    if os.path.exists(main_csv):
        df_all = pd.read_csv(main_csv)
        if '斜率' in df_all.columns:
            tab_filters = {
                "all":    (None, 10),
                "up":     (df_all['动量评分'] > 0, 10),
                "strict": ((df_all['斜率'] > THRESHOLDS["strict"]["slope"]) & (df_all['R²'] > THRESHOLDS["strict"]["r2"]), 10),
                "loose":  ((df_all['斜率'] > THRESHOLDS["loose"]["slope"]) & (df_all['R²'] > THRESHOLDS["loose"]["r2"]), 10),
            }
            results = {}
            for key, (filt, limit) in tab_filters.items():
                sub = (df_all.head(limit) if filt is None else df_all[filt].head(limit))
                results[key] = {"label": label_map[key], "data": sub.to_dict('records') if not sub.empty else [], "count": len(sub)}
            return results
    old_up = f"上涨趋势_强势股_{d}.csv"
    if os.path.exists(old_up):
        df_up = pd.read_csv(old_up)
        results = {"all":{"label":"全部强势股TOP10","data":[],"count":0},"up":{"label":"上涨趋势股","data":df_up.head(10).to_dict('records'),"count":min(10,len(df_up))}}
        if '斜率' in df_up.columns:
            t = THRESHOLDS["strict"]
            sd = df_up[(df_up['斜率']>t['slope'])&(df_up['R²']>t['r2'])].head(10)
            results["strict"] = {"label":"严格模式","data":sd.to_dict('records'),"count":len(sd)}
            t = THRESHOLDS["loose"]
            ld = df_up[(df_up['斜率']>t['slope'])&(df_up['R²']>t['r2'])].head(10)
            results["loose"] = {"label":"宽松模式","data":ld.to_dict('records'),"count":len(ld)}
        return results
    return {k:{"label":label_map[k],"data":[],"count":0} for k in label_map}


def export_tdx_blocks(results, d):
    tdx_dir = f"tdx_blocks_{d}"
    os.makedirs(tdx_dir, exist_ok=True)
    file_map = {"all":"强势股TOP10","up":"上涨趋势股","strict":"严格模式","loose":"宽松模式"}
    created = []
    for key, label in file_map.items():
        data = results.get(key, {}).get("data", [])
        if not data: continue
        lines = []
        for r in data:
            code = r.get('代码', '')
            if not code: continue
            if code.endswith('.SH'): tdx_code = f"1.{code.replace('.SH','')}"
            elif code.endswith('.SZ'): tdx_code = f"0.{code.replace('.SZ','')}"
            elif code.endswith('.BJ'): tdx_code = f"2.{code.replace('.BJ','')}"
            else: continue
            lines.append(tdx_code)
        if lines:
            fpath = os.path.join(tdx_dir, f"{label}.txt")
            with open(fpath, 'w', encoding='gbk') as f: f.write('\n'.join(lines))
            created.append(fpath)
    if created:
        print(f"\n📂 通达信板块文件已生成 ({tdx_dir}/):")
        for f in created: print(f"   {f}")
        print(f"\n   通达信导入步骤:\n   1. 打开通达信 → 工具 → 自定义板块设置\n   2. 导入板块 → 选择上述 .txt 文件")
    return tdx_dir

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.5, user-scalable=yes">
<title>📊 强势股看板</title>
<style>
  :root { --bg:#f5f6fa; --card:#fff; --text:#2d3436; --border:#dfe6e9; --accent:#0984e3;
          --positive:#00b894; --negative:#d63031; --header-bg:#2d3436; --header-text:#fff; }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
         background:var(--bg); color:var(--text); padding:0 0 40px; }
  .header { background:var(--header-bg); color:var(--header-text); padding:16px 20px;
            position:sticky; top:0; z-index:100; box-shadow:0 2px 8px rgba(0,0,0,0.15); }
  .header-top { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; }
  .header h1 { font-size:20px; font-weight:600; }
  .header-controls { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
  .btn { display:inline-flex; align-items:center; gap:4px; padding:8px 16px; border:none; border-radius:8px;
         font-size:13px; font-weight:500; cursor:pointer; transition:all 0.2s; }
  .btn-outline { background:transparent; color:var(--header-text); border:1px solid rgba(255,255,255,0.3); }
  .toggle-wrap { display:flex; align-items:center; gap:8px; font-size:13px; }
  .toggle { position:relative; width:44px; height:24px; background:rgba(255,255,255,0.2); border-radius:12px;
            cursor:pointer; transition:0.3s; }
  .toggle.active { background:var(--accent); }
  .toggle::after { content:''; position:absolute; width:20px; height:20px; border-radius:50%;
                   background:#fff; top:2px; left:2px; transition:0.3s; }
  .toggle.active::after { left:22px; }
  .container { max-width:1000px; margin:0 auto; padding:16px; }
  .card { background:var(--card); border-radius:12px; box-shadow:0 1px 4px rgba(0,0,0,0.06); margin-bottom:16px; overflow:hidden; }
  .card-header { padding:14px 16px; font-size:15px; font-weight:600; border-bottom:1px solid var(--border);
                 display:flex; justify-content:space-between; align-items:center; }
  .card-header .badge { font-size:11px; padding:2px 10px; border-radius:10px; font-weight:500; }
  .badge-green { background:#00b89420; color:#00b894; }
  .table-wrap { overflow-x:auto; -webkit-overflow-scrolling:touch; }
  table { width:100%; border-collapse:collapse; font-size:13px; white-space:nowrap; }
  th { background:#f8f9fa; padding:10px 8px; text-align:left; font-weight:600; border-bottom:2px solid var(--border); }
  td { padding:10px 8px; border-bottom:1px solid var(--border); }
  .num { text-align:right; }
  .pos { color:var(--positive); }
  .neg { color:var(--negative); }
  .code { font-family:monospace; font-size:12px; color:#636e72; }
  .name { font-weight:500; }
  .rank-badge { display:inline-block; min-width:24px; height:24px; line-height:24px; text-align:center;
                border-radius:50%; font-size:12px; font-weight:600; }
  .rank-1 { background:#ffd70030; color:#b8860b; }
  .rank-2 { background:#c0c0c030; color:#708090; }
  .rank-3 { background:#cd7f3230; color:#8b4513; }
  .star { color:#ffd700; }
  .empty-state { padding:30px; text-align:center; color:#b2bec3; }
  .info-bar { display:flex; gap:12px; flex-wrap:wrap; margin-bottom:16px; }
  .info-item { background:var(--card); border-radius:10px; padding:12px 16px; flex:1; min-width:120px; text-align:center; }
  .info-item .val { font-size:22px; font-weight:700; }
  .info-item .lbl { font-size:11px; color:#636e72; }
  .tabs { display:flex; gap:4px; margin-bottom:16px; overflow-x:auto; }
  .tab { padding:10px 18px; border-radius:8px 8px 0 0; font-size:13px; font-weight:500; cursor:pointer;
         background:var(--card); border:1px solid var(--border); border-bottom:none; white-space:nowrap;
         transition:0.2s; opacity:0.6; }
  .tab.active { opacity:1; border-bottom:2px solid var(--accent); }
  .dark-mode { --bg:#1a1a2e; --card:#16213e; --text:#eaeaea; --border:#2a2a4a; --header-bg:#0f0f1a; }
  .dark-mode th { background:#1a1a2e; }
  @media (max-width:600px) {
    .header h1 { font-size:17px; }
    .btn { padding:6px 12px; font-size:12px; }
    table { font-size:12px; }
    th, td { padding:7px 5px; }
    .info-item { min-width:80px; padding:10px; }
    .info-item .val { font-size:18px; }
    .tab { padding:8px 12px; font-size:12px; }
  }
</style>
</head>
<body>
<div class="header">
  <div class="header-top">
    <div>
      <h1>📊 强势股看板</h1>
      <div class="sub" id="dateDisplay">交易日: --</div>
    </div>
    <div class="header-controls">
      <div class="toggle-wrap">
        <span>🌙</span>
        <div class="toggle" id="darkToggle" onclick="toggleDark()"></div>
      </div>
      <button class="btn btn-outline" onclick="location.reload()">🔄 刷新</button>
      <button class="btn btn-outline" id="viewToggle" onclick="toggleView()">📄 源码</button>
    </div>
  </div>
</div>

<div class="container">
  <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px;
              font-size:12px;color:#636e72;margin-bottom:8px;
              background:var(--card);border-radius:8px;padding:8px 14px;">
    <span>📅 数据日期: <strong id="dateDisplay">—</strong></span>
    <span>⏱ 生成时间: <span id="genTime">—</span></span>
    <span id="dataSourceWrap">📦 <span id="dataSource">嵌入数据</span></span>
  </div>
  <div class="info-bar" id="infoBar"></div>
  <div class="tabs" id="tabBar"></div>
  <div id="contentArea"></div>
</div>

<script>
var SCREEN_DATA_EMBED = __DATA_PLACEHOLDER__;
var SCREEN_DATA = SCREEN_DATA_EMBED;
var DATE_STR = '__DATE_PLACEHOLDER__';
var GEN_TIME = '__GEN_TIME_PLACEHOLDER__';
document.getElementById('dateDisplay').textContent = DATE_STR;
document.getElementById('genTime').textContent = GEN_TIME;

(function(){
  var xhr = new XMLHttpRequest();
  xhr.open('GET', './dashboard_data_' + DATE_STR + '.json?t=' + Date.now(), true);
  xhr.onload = function() {
    if (xhr.status === 200) {
      try {
        var fresh = JSON.parse(xhr.responseText);
        if (fresh && fresh.all) {
          SCREEN_DATA = fresh;
          document.getElementById('dataSource').textContent = '外部数据（最新）';
          renderInfoBar(); renderContent();
        }
      } catch(e) {}
    }
  };
  xhr.send();
})();

var TAB_KEYS = ['all', 'up', 'loose', 'strict'];
var TAB_ICONS = {'all':'🏆','up':'📈','loose':'🔵','strict':'🔴'};
var TAB_NAMES = {'all':'综合排名','up':'上涨趋势','loose':'宽松模式','strict':'严格模式'};
var activeTab = 'all';

function renderInfoBar() {
  var bar = document.getElementById('infoBar');
  bar.innerHTML = TAB_KEYS.map(function(k) {
    var d = SCREEN_DATA[k] || {count:0};
    return '<div class="info-item"><div class="val">'+d.count+'</div><div class="lbl">'+d.label+'</div></div>';
  }).join('');
}

function renderTabs() {
  document.getElementById('tabBar').innerHTML = TAB_KEYS.map(function(k) {
    return '<div class="tab'+(k===activeTab?' active':'')+'" onclick="switchTab(\''+k+'\')">'+TAB_ICONS[k]+' '+TAB_NAMES[k]+'</div>';
  }).join('');
}

function renderTable(data) {
  if (!data || !data.length) return '<div class="empty-state">📭 暂无数据</div>';
  var h = '<div class="table-wrap"><table><thead><tr><th>#</th><th>代码</th><th>名称</th>' +
    '<th class="num">动量评分</th><th class="num">斜率</th><th class="num">R²</th>' +
    '<th class="num">比值%</th><th class="num">比值排名</th><th class="num">热度排名</th></tr></thead><tbody>';
  data.forEach(function(r, i) {
    var mom = parseFloat(r.动量评分) || 0;
    var slope = parseFloat(r.斜率) || 0;
    var r2 = parseFloat(r['R²']) || 0;
    var ratio = r.比值 ? parseFloat(r.比值).toFixed(1) : '-';
    var rc = i===0?'rank-1':i===1?'rank-2':i===2?'rank-3':'';
    var star = mom>0?'<span class="star">⭐️</span>':'';
    h += '<tr><td><span class="rank-badge '+rc+'">'+(i+1)+'</span></td>'+
         '<td class="code">'+(r.代码||'')+'</td>'+
         '<td class="name">'+(r.名称||'')+star+'</td>'+
         '<td class="num '+(mom>0?'pos':'neg')+'">'+(mom>0?'+':'')+mom.toFixed(2)+'</td>'+
         '<td class="num">'+slope.toFixed(4)+'</td>'+
         '<td class="num">'+r2.toFixed(3)+'</td>'+
         '<td class="num">'+ratio+'</td>'+
         '<td class="num">'+(r.比值排名||r.成交额排名||'')+'</td>'+
         '<td class="num">'+(r.热度排名||'')+'</td></tr>';
  });
  return h + '</tbody></table></div>';
}

function renderContent() {
  var d = SCREEN_DATA[activeTab] || {data:[], label:''};
  var td = '';
  if (activeTab==='strict') td = '<div style="font-size:12px;color:#636e72;padding:0 16px 10px">斜率>0.008 且 R²>0.7</div>';
  else if (activeTab==='loose') td = '<div style="font-size:12px;color:#636e72;padding:0 16px 10px">斜率>0.003 且 R²>0.3</div>';
  else if (activeTab==='up') td = '<div style="font-size:12px;color:#636e72;padding:0 16px 10px">斜率>0 的上涨趋势股</div>';
  document.getElementById('contentArea').innerHTML =
    '<div class="card"><div class="card-header"><span>'+TAB_ICONS[activeTab]+' '+d.label+'</span>'+
    '<span class="badge badge-green">'+d.count+' 只</span></div>'+td+renderTable(d.data)+'</div>';
}

function switchTab(key) { activeTab=key; renderTabs(); renderContent(); }
function toggleDark() { document.body.classList.toggle('dark-mode'); document.getElementById('darkToggle').classList.toggle('active'); }

var _viewMode='render';
function toggleView() {
  var btn=document.getElementById('viewToggle'), area=document.getElementById('contentArea');
  var tabs=document.getElementById('tabBar'), info=document.getElementById('infoBar');
  if (_viewMode==='render') {
    _viewMode='source'; btn.textContent='🎨 渲染';
    tabs.style.display='none'; info.style.display='none';
    area.innerHTML='<div class="card"><div class="card-header">📄 原始数据</div><div style="padding:16px;overflow:auto;max-height:70vh;font-size:12px;font-family:monospace;white-space:pre">'+
      JSON.stringify(SCREEN_DATA,null,2).replace(/&/g,'&').replace(/</g,'<').replace(/>/g,'>')+'</div></div>';
  } else {
    _viewMode='render'; btn.textContent='📄 源码';
    tabs.style.display='flex'; info.style.display='flex';
    renderContent();
  }
}

renderInfoBar(); renderTabs(); renderContent();
</script>
</body>
</html>
"""


def generate_html(d=None):
    d = d or datetime.now().strftime('%Y-%m-%d')
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    results = load_from_csv(d)
    need_run = any(v['count'] == 0 for v in results.values())
    if need_run:
        print("\n⚠️ CSV数据不足，正在重新运行选股程序...\n")
        results = run_all_modes(d)
    data_json = json.dumps(results, ensure_ascii=False, default=str)
    html = HTML_TEMPLATE.replace('__DATA_PLACEHOLDER__', data_json)
    html = html.replace('__DATE_PLACEHOLDER__', d)
    html = html.replace('__GEN_TIME_PLACEHOLDER__', now_str)
    filename = f"dashboard_{d}.html"
    with open(filename, 'w', encoding='utf-8') as f: f.write(html)
    json_file = f"dashboard_data_{d}.json"
    with open(json_file, 'w', encoding='utf-8') as f: json.dump(results, f, ensure_ascii=False, default=str)
    export_tdx_blocks(results, d)
    print(f"\n{'='*60}\n✅ 看板已生成: {filename}\n   数据文件: {json_file}\n   双击打开 {filename} 即可查看\n{'='*60}")
    return filename


if __name__ == "__main__":
    d = None
    if len(sys.argv) > 2 and sys.argv[1] == "--date": d = sys.argv[2]
    elif len(sys.argv) > 1 and sys.argv[1] != "--date": d = sys.argv[1]
    generate_html(d)
