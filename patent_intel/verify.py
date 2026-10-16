#!/usr/bin/env python3
"""patent_intel.verify —— 把「清单声明值」与「Google Patents 实测值」逐条对照，按类输出不一致。

用法：
    python3 -m patent_intel.verify --ref list.csv --col number --lang ENGLISH --out mismatches.csv
退出码：0 = 全部一致；2 = 存在不一致（便于流水线门控）。
"""
import argparse, csv, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gp import resolve_numbers, stem

def norm_title(s):
    s = re.sub(r"<[^>]+>", "", (s or "")).lower()
    s = re.sub(r"[\s\-—–_·,，。.、;；:：()（）【】\[\]“”\"'`/]+", "", s)
    return s

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--col", default="number"); ap.add_argument("--name", default="title")
    ap.add_argument("--filing", default="filing_date"); ap.add_argument("--pub", default="publication_date")
    ap.add_argument("--lang", default="ENGLISH")
    a = ap.parse_args()
    rows = list(csv.DictReader(open(a.ref, encoding="utf-8-sig")))
    nums = [r[a.col].strip() for r in rows if r.get(a.col, "").strip()]
    meta = resolve_numbers(nums, lang=a.lang)
    rep, bad = [], 0
    for r in rows:
        n = r[a.col].strip()
        if not n: continue
        m = meta.get(n.upper().replace(" ", "")) or {}
        issues = []
        if m.get("src") in (None, "miss"):
            issues.append("号未取到")
        elif m.get("src") == "xhr(stem-only)":
            issues.append("仅同族命中，该号未确证：" + m.get("warn", ""))
        else:
            if m.get("pnum") and stem(m["pnum"]) != stem(n): issues.append(f"号码不符({m['pnum']})")
            if a.name in r and r[a.name].strip() and norm_title(r[a.name]) != norm_title(m.get("title", "")):
                issues.append("名称不符")
            f_ref = (r.get(a.filing, "") or "").strip(); f_got = m.get("filing", "")
            if f_ref and f_got and f_ref[:10] != f_got[:10]: issues.append(f"申请日不符({f_ref}/{f_got})")
            p_ref = (r.get(a.pub, "") or "").strip(); p_got = m.get("pub") or m.get("issue", "")
            if p_ref and p_got and p_ref[:10] != p_got[:10]: issues.append(f"公告日不符({p_ref}/{p_got})")
        if issues:
            bad += 1
            rep.append([n, "；".join(issues), r.get(a.name, ""), m.get("title", ""),
                        r.get(a.filing, ""), m.get("filing", ""), r.get(a.pub, ""), m.get("pub", "")])
    with open(a.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["号码", "问题", "清单·名称", "实测·名称", "清单·申请日", "实测·申请日", "清单·公告日", "实测·公告日"])
        w.writerows(rep)
    print(f"核对 {len(nums)} 条｜不一致 {bad} 条 → {a.out}")
    sys.exit(2 if bad else 0)

if __name__ == "__main__":
    main()
