"""
收盘选股报告生成器
数据源: 问财（(成交额/自由流通市值*100)TOP100 + 热度TOP100）
动量: 25日线性回归斜率 × R²
运行: python3 daily_report.py [--date YYYY-MM-DD]
"""
import sys, os, subprocess, json
from datetime import datetime

REPORT_DIR = "daily_reports"
os.makedirs(REPORT_DIR, exist_ok=True)


def run_strong_stock_screen(date_str=None):
    cmd = ["python3", "strong_stock.py", "--top", "58"]
    if date_str:
        cmd += ["--date", date_str]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    print(result.stdout)
    if result.stderr:
        print("[stderr]", result.stderr[:500])
    output = result.stdout
    d = date_str or datetime.now().strftime("%Y-%m-%d")
    csv_file = f"强势股_{d}.csv"
    csv_up = f"上涨趋势_强势股_{d}.csv"
    return output, csv_file, csv_up


def generate_report(date_str=None):
    d = date_str or datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*60}")
    print(f"📋 收盘选股报告生成器")
    print(f"⏰ {now}")
    print(f"{'='*60}\n")
    print("▶ 步骤1/3: 执行选股程序...\n")
    output, csv_all, csv_up = run_strong_stock_screen(date_str)
    print("\n▶ 步骤2/3: 生成报告...\n")
    import pandas as pd
    report_lines = [
        f"# 收盘选股报告", f"",
        f"> 生成时间: {now}", f"> 数据日期: {d}", f"",
    ]
    if os.path.exists(csv_all):
        df_all = pd.read_csv(csv_all)
        report_lines.append("## 一、强势股综合排名 TOP10")
        report_lines.append("")
        report_lines.append("| 排名 | 代码 | 名称 | 动量评分 | 斜率 | R² | 趋势 | 比值排名 | 热度排名 |")
        report_lines.append("|:---:|:----:|:----:|:--------:|:----:|:--:|:----:|:--------:|:--------:|")
        for i, (_, r) in enumerate(df_all.head(10).iterrows(), 1):
            mom = r['动量评分']
            trend = "📈" if mom > 0 else "📉"
            report_lines.append(
                f"| {i} | {r['代码']} | {r['名称']} | {mom:+.2f} | {r['斜率']:.4f} | {r['R²']:.3f} | {trend} | {r['比值排名']} | {r['热度排名']} |"
            )
        report_lines.append("")
    if os.path.exists(csv_up):
        df_up = pd.read_csv(csv_up)
        report_lines.append(f"## 二、上涨趋势股（斜率>0）共{len(df_up)}只")
        report_lines.append("")
        report_lines.append("| 排名 | 代码 | 名称 | 动量评分 | 斜率 | R² | 比值排名 | 热度排名 |")
        report_lines.append("|:---:|:----:|:----:|:--------:|:----:|:--:|:--------:|:--------:|")
        for i, (_, r) in enumerate(df_up.iterrows(), 1):
            report_lines.append(
                f"| {i} | {r['代码']} | {r['名称']} | {r['动量评分']:+.2f} | {r['斜率']:.4f} | {r['R²']:.3f} | {r['比值排名']} | {r['热度排名']} |"
            )
        report_lines.append("")
    if os.path.exists(csv_up):
        strong = df_up[(df_up['斜率'] > 0.005) & (df_up['R²'] > 0.5)].head(5)
        if not strong.empty:
            report_lines.append("## 三、重点关注（强趋势标的）")
            report_lines.append("")
            report_lines.append("> 筛选条件: 斜率>0.005 且 R²>0.5\n")
            for i, (_, r) in enumerate(strong.iterrows(), 1):
                report_lines.append(f"{i}. **{r['名称']}({r['代码']})** — 动量{ r['动量评分']:+.2f}，斜率{r['斜率']:.4f}，R²={r['R²']:.3f}")
            report_lines.append("")
    report_lines.append("---")
    report_lines.append(f"*报告由 strong_stock.py 自动生成*")
    report_text = "\n".join(report_lines)
    report_file = os.path.join(REPORT_DIR, f"收盘报告_{d}.md")
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report_text)
    print("\n▶ 步骤3/3: 报告完成\n")
    print(report_text)
    print(f"\n💾 报告已保存: {report_file}")
    return report_file


if __name__ == "__main__":
    date_arg = None
    if len(sys.argv) > 1 and sys.argv[1] == "--date" and len(sys.argv) > 2:
        date_arg = sys.argv[2]
    generate_report(date_str=date_arg)
