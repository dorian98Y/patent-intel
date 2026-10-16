#!/usr/bin/env python3
"""patent_intel.dedupe —— 清单级去重：先按「同号族」（去种类码）合并 A/B，再可选按族链（Also Published As）跨 CN/US/WO 合并。

用法：
    python3 -m patent_intel.dedupe --in list.csv --col number --out deduped.csv [--family] [--report merges.csv]
规则：
    * 同 stem 只留一件，代表号优先级 = 授权本(B/I/U/S) > 申请公布(A) > 其他；同优先级取输入顺序靠前者。
    * --family 时对保留件抓同族（缓存），用并查集合并跨号族重复（跨法域成员被分成两个号族的情形）。
"""
import argparse, csv, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gp import stem, page_meta, family_cached

KIND_RANK = {"B": 0, "I": 0, "U": 0, "S": 0, "A": 1, "A1": 1, "A8": 1, "A9": 1, "W": 1}
def kind(n):
    m = re.search(r"([A-Z][0-9]?)$", n.upper()); return m.group(1) if m else ""
def rank(n):
    return KIND_RANK.get(kind(n), 2)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--col", default="number"); ap.add_argument("--report", default="")
    ap.add_argument("--family", action="store_true")
    a = ap.parse_args()
    with open(a.inp, encoding="utf-8-sig") as fh:
        head = fh.readline()
        rest = fh.read()
    lines = [head] + rest.splitlines()
    if "," in head or "\t" in head:                      # CSV/TSV with a header row
        rows = list(csv.DictReader(lines))
    else:                                                # plain one-number-per-line list
        vals = [l.strip() for l in lines if l.strip()]
        if vals and vals[0].lower() in ("number", "numbers", "publication_number", "num",
                                        "\u53f7\u7801", "\u4e13\u5229\u53f7"):
            vals = vals[1:]                              # drop header
        rows = [{a.col: v} for v in vals]
    order, groups, seen_exact = [], {}, {}
    log = []
    for r in rows:
        n = (r.get(a.col) or "").strip().upper().replace(" ", "")
        if not n: continue
        if n in seen_exact:                      # 完全重复（同号出现多次）
            log.append([n, n, "完全重复（同号在输入中出现多次）"]); continue
        seen_exact[n] = True
        s = stem(n)
        groups.setdefault(s, []).append(n)
        if s not in order: order.append(s)
    kept = []
    for s in order:
        members = groups[s]
        best = sorted(members, key=lambda n: (rank(n), members.index(n)))[0]
        kept.append(best)
        for m in members:
            if m != best: log.append([m, best, "同号族合并（A/B 公布本）"])
    if a.family:
        from concurrent.futures import ThreadPoolExecutor
        import threading
        tls = threading.local()
        def _fam(n):
            return n, set(family_cached(n) + [n])
        with ThreadPoolExecutor(max_workers=4) as ex:      # 4 线程 = 4 个独立 Tor 出口
            fam = dict(ex.map(_fam, kept))
        parent = {n: n for n in kept}
        def find(x):
            while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
            return x
        for i, x in enumerate(kept):
            for y in kept[i + 1:]:
                if fam[x] & fam[y]:
                    rx, ry = find(x), find(y)
                    if rx != ry:
                        keep = rx if kept.index(rx) <= kept.index(ry) else ry
                        drop = ry if keep == rx else rx
                        parent[drop] = keep
                        log.append([drop, keep, "同族链合并（同族号重合）"])
        kept = [n for n in kept if find(n) == n]
    soft = []
    if a.family and len(kept) > 1:
        import difflib
        from gp import resolve_numbers
        meta = resolve_numbers(kept, lang="CHINESE")
        groups_by_title = {}
        for n in kept:
            t = (meta.get(n) or {}).get("title", "") or ""
            t = re.sub(r"[\s\-—–_·,，。.、;；:：()（）【】\[\]“”\"'`/]+", "", t.lower())
            if t:
                groups_by_title.setdefault(t, []).append(n)
        for t, ns in groups_by_title.items():
            if len(ns) > 1:
                for x in ns[1:]:
                    soft.append([x, ns[0], "疑似同发明（标题一致，Google 族链未连接 → 需人工判定）"])
    with open(a.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["index", "number"]); [w.writerow([i, n]) for i, n in enumerate(kept, 1)]
    if a.report:
        with open(a.report, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f); w.writerow(["被合并号", "保留号", "原因"]); w.writerows(log + soft)
    print(f"输入 {len(rows)} → 去重后 {len(kept)}｜合并 {len(log)} 条｜疑似同发明待判 {len(soft)} 条" + (f" → {a.report}" if a.report else ""))

if __name__ == "__main__":
    main()
