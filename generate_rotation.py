#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
板块强度轮动周期生成器
数据源: zzshare KPL板块强度(score) + 主力资金(plates_rank type=17) + 涨停梯队(plate)
功能:
  1. 拉取当日板块强度/主力资金/涨停数
  2. 计算轮动方向(较昨日排名变化) 与 周期阶段(启动/扩散/高潮/退潮/冰点)
  3. 追加历史数据 rotation_data.json (仓库即数据库, 每日累积)
用法: python3 generate_rotation.py [YYYY-MM-DD]
"""
import os, sys, json, re, time
from datetime import datetime
import requests as rq

ZZ_TOKEN = os.environ.get("ZZSHARE_TOKEN", "")
if not ZZ_TOKEN:
    ZZ_TOKEN = "37334f4dbf2dc4a3fe972e99b91fb9df7a7aed313a537b37586a2b7ce500c1e0"

DATA_FILE = "rotation_data.json"  # 历史累积库
LATEST_FILE = "rotation_latest.json"  # 最新日(供页面快速读取)
STOCKS_FILE = "rotation_stocks.json"  # 板块成分股/领涨股
TOP_N = 12  # 记录前N个板块
LEADER_N = 10  # 领涨股数
STOCK_SHOW = 20  # 成分股展示数


def fetch(date_str):
    """拉取板块强度(KPL score) + 主力资金 — plates_rank(17) 单源"""
    from zzshare import DataApi
    api = DataApi(ZZ_TOKEN)
    res = api.plates_rank(17, date_str.replace("-", ""))
    plates = []
    for b in (res or [])[:TOP_N]:
        nm = b.get("plate_name", "")
        if nm:
            plates.append({"name": nm, "code": b.get("plate_code", ""),
                           "score": b.get("score", 0),
                           "fund": round((b.get("money_leader", 0) or 0) / 1e8, 2),
                           "pct": b.get("rate", "")})
    return plates


def to_qq(code):
    c = str(code)
    if c.startswith(("6", "9")):
        return "sh" + c
    if c.startswith(("0", "3")):
        return "sz" + c
    if c.startswith(("4", "8")):
        return "bj" + c
    return "sh" + c


def fetch_stocks(plate_code):
    """板块成分股(zzshare) → 腾讯批量行情 → 返回领涨TOP + 成分股TOP + 总数"""
    if not plate_code:
        return None
    try:
        from zzshare import DataApi
        api = DataApi(ZZ_TOKEN)
        members = api.plates_stocks("17", plate_code) or []
        codes = [s.get("stock_code") for s in members if s.get("stock_code")]
        if not codes:
            return None
        # 腾讯分批查行情
        quotes = {}
        for i in range(0, len(codes), 50):
            batch = codes[i:i + 50]
            try:
                resp = rq.get("https://qt.gtimg.cn/q=" + ",".join(to_qq(c) for c in batch),
                              timeout=10)
                resp.encoding = "gbk"
                for m in re.finditer(r'v_\w+="([^"]+)"', resp.text):
                    p = m.group(1).split("~")
                    if len(p) > 32 and p[1] and p[3]:
                        try:
                            quotes[p[2]] = {"name": p[1], "code": p[2], "pct": float(p[32])}
                        except Exception:
                            pass
            except Exception:
                pass
            time.sleep(0.05)
        ranked = sorted(quotes.values(), key=lambda x: -x["pct"])
        return {
            "total": len(codes),
            "leaders": [[x["name"], x["code"], f"{x['pct']:+.2f}%"] for x in ranked[:LEADER_N]],
            "stocks": [[x["name"], x["code"], f"{x['pct']:+.2f}%"] for x in ranked[:STOCK_SHOW]],
        }
    except Exception:
        return None


def calc_phase(name, score, prev_rank, prev_score, rank):
    """轮动周期阶段判定(简化规则)"""
    delta = (score - prev_score) / prev_score if prev_score else 0
    up = rank < prev_rank if prev_rank else True  # 排名上升
    if prev_rank is None:
        return "启动"
    if up and delta > 0.05:
        return "扩散"
    if rank <= 3 and prev_rank <= 3:
        return "高潮"
    if (prev_rank is not None and rank > prev_rank + 3) or delta < -0.1:
        return "退潮"
    if rank >= 8:
        return "冰点"
    return "震荡"


def load_history():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
    hist = load_history()
    prev = hist.get(max(hist.keys())) if hist else None  # 前一日数据

    print(f"📅 板块强度轮动生成 {date_str}")
    plates = fetch(date_str)
    if not plates:
        print("❌ 数据获取失败")
        sys.exit(1)

    # 按强度排序
    plates.sort(key=lambda x: -x["score"])
    day = {}
    for i, p in enumerate(plates, 1):
        pv = (prev or {}).get(p["name"])
        prev_score = pv.get("score") if pv else None
        prev_rank = pv.get("rank") if pv else None
        day[p["name"]] = {
            "rank": i, "score": p["score"],
            "fund": p["fund"], "pct": p["pct"],
            "phase": calc_phase(p["name"], p["score"], prev_rank, prev_score, i),
        }
    hist[date_str] = day

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False)
    with open(LATEST_FILE, "w", encoding="utf-8") as f:
        json.dump({"date": date_str, "plates": day}, f, ensure_ascii=False)

    # 板块成分股/领涨股(仅最新日更新, 覆盖式)
    stocks_map = {}
    if os.path.exists(STOCKS_FILE):
        try:
            with open(STOCKS_FILE, encoding="utf-8") as f:
                stocks_map = json.load(f)
        except Exception:
            stocks_map = {}
    for p in plates:
        if p["name"] in stocks_map and stocks_map[p["name"]].get("date") == date_str:
            continue
        print(f"   📊 拉取 {p['name']} 成分股...")
        st = fetch_stocks(p["code"])
        if st:
            st["date"] = date_str
            st["rank"] = [i + 1 for i, pp in enumerate(plates) if pp["name"] == p["name"]][0]
            stocks_map[p["name"]] = st
    with open(STOCKS_FILE, "w", encoding="utf-8") as f:
        json.dump(stocks_map, f, ensure_ascii=False)

    print(f"✅ 已更新: {DATA_FILE} ({len(hist)}个交易日)")
    print("   今日板块强度TOP5:")
    for nm, info in list(day.items())[:5]:
        print(f"     {nm}: 强度{info['score']} 排名{info['rank']} 阶段[{info['phase']}]")
    print(f"   📈 成分股数据: {len(stocks_map)}个板块")


if __name__ == "__main__":
    main()
