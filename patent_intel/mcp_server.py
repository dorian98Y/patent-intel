#!/usr/bin/env python3
"""patent_intel.mcp_server —— 专利取数 / 同族 / 核对 / 去重 的 MCP 服务器（stdio）。

启动：python3 -m patent_intel.mcp_server

客户端配置（MCP 通用形态）：
  mcpServers:
    patent-intel:
      command: python3
      args: [ "-m", "patent_intel.mcp_server" ]
      env: { PYTHONPATH: "/path/to/patent-intel", GP_EXITS: "9050,9052,9054,9056" }

依赖：curl + 若干 SOCKS5 出口（Tor 或任意代理）；GP_EXITS 指定端口，GP_CACHE 指定缓存目录，
GP_NEWNYM（可选）指定换出口脚本。
"""
from __future__ import annotations
import json, os, sys, time, re, subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from patent_intel import gp

try:                                            # mcp >= 2.x
    from mcp.server import MCPServer as _Server
    def _mk(name, **kw):
        return _Server(name, **kw)
except Exception:                               # mcp 1.x (FastMCP)
    from mcp.server.fastmcp import FastMCP as _Server
    def _mk(name, **kw):
        return _Server(name)

mcp = _mk("patent-intel",
          instructions=("Google Patents 批量取数/核对/去重。numbers 可传数组或逗号/换行分隔的字符串。"
                        "取数走 XHR 批量端点（100 号/请求），未命中自动回落单件页面；结果带本地缓存。"))
TOOL_KW = {} if _Server.__name__ == "MCPServer" else {"description": None}

def _nums(x) -> list[str]:
    if x is None: return []
    if isinstance(x, str): x = re.split(r"[,\n;\s]+", x)
    return [str(n).strip().upper() for n in x if str(n).strip()]

def _brief(rec) -> dict:
    if not rec: return {}
    return {"number": rec.get("num") or rec.get("pnum", ""), "publication": rec.get("pnum", ""),
            "title": rec.get("title", ""), "filing_date": rec.get("filing", ""),
            "publication_date": rec.get("pub") or rec.get("issue", ""),
            "assignee": rec.get("assignee", ""), "inventor": rec.get("inventor", ""),
            "source": rec.get("src", ""), "warning": rec.get("warn", "")}

@mcp.tool(name="patent_resolve",
          description="按专利号批量取元数据（名称/申请日/公布日/主体/发明人）。numbers 支持数组或逗号分隔；"
                      "重跑走本地缓存；返回 hit/misses 与耗时。")
def patent_resolve(numbers, lang: str = "CHINESE") -> dict:
    nums = _nums(numbers)
    t0 = time.time()
    meta = gp.resolve_numbers(nums, lang=lang, log=lambda *_: None)
    res, miss, warn = [], [], []
    for n in nums:
        r = meta.get(n) or {}
        b = _brief(r)
        if not b or b["source"] == "miss":
            miss.append(n)
        else:
            res.append(b)
            if b["source"] == "xhr(stem-only)": warn.append(n)
    return {"requested": len(nums), "hit": len(res), "miss": miss,
            "not_verified": warn, "elapsed_s": round(time.time() - t0, 2), "results": res}

@mcp.tool(name="patent_family", description="取某号所在专利族的其它公布本号（Also Published As）。")
def patent_family(number: str, lang: str = "CHINESE") -> dict:
    n = _nums(number)[0]
    fam = gp.family_cached(n, "zh" if lang.upper().startswith("CH") else "en")
    return {"number": n, "family": fam, "count": len(fam)}

@mcp.tool(name="patent_verify",
          description="把清单声明值（rows: [{number,title,filing_date,publication_date}]，字段名可省略）与实测值逐条对照，"
                      "返回不一致清单（号未取到/仅同族未确证/名称不符/日期不符）。")
def patent_verify(rows, lang: str = "CHINESE") -> dict:
    if isinstance(rows, str):
        rows = json.loads(rows)
    meta = gp.resolve_numbers([_nums(r.get("number") or r.get("numbers") or "")[0] for r in rows], lang=lang, log=lambda *_: None)
    def norm(t):
        return re.sub(r"[\s\-—–_·,，。.、;；:：()（）【】\[\]“”\"'`/]+", "", (t or "").lower())
    issues = []
    for r in rows:
        n = n0 = _nums(r.get("number") or r.get("numbers") or "")
        n = n[0] if n else ""
        m = meta.get(n) or {}
        why = []
        if not m or m.get("src") == "miss": why.append("号未取到")
        else:
            if m.get("pnum") and gp.stem(m["pnum"]) != gp.stem(n): why.append(f"号码不符({m['pnum']})")
            if m.get("src") == "xhr(stem-only)": why.append("仅同族命中，该号未确证")
            if r.get("title") and norm(r["title"]) != norm(m.get("title", "")): why.append("名称不符")
            fr = (r.get("filing_date") or "").strip(); fg = m.get("filing", "")
            if fr and fg and fr[:10] != fg[:10]: why.append(f"申请日不符({fr}/{fg})")
            pr = (r.get("publication_date") or "").strip(); pg = m.get("pub") or m.get("issue", "")
            if pr and pg and pr[:10] != pg[:10]: why.append(f"公布日不符({pr}/{pg})")
        if why:
            issues.append({"number": n, "issues": why, "declared_title": r.get("title", ""),
                           "actual_title": m.get("title", ""), "declared_filing": r.get("filing_date", ""),
                           "actual_filing": m.get("filing", ""), "declared_pub": r.get("publication_date", ""),
                           "actual_pub": m.get("pub") or m.get("issue", "")})
    return {"checked": len(rows), "mismatch": len(issues), "issues": issues}

@mcp.tool(name="patent_dedupe",
          description="清单去重：同号族（A/B 公布本）合并 + 完全重复；family=true 时再按族链跨 CN/US/WO 合并。"
                      "仅标题一致但族链未连的对子列为『疑似同发明待判』，不自动合并。")
def patent_dedupe(numbers, family: bool = False, lang: str = "CHINESE") -> dict:
    nums = _nums(numbers)
    order, groups = [], {}
    for n in nums:
        s = gp.stem(n)
        groups.setdefault(s, []).append(n)
        if s not in order: order.append(s)
    rank = {"B": 0, "I": 0, "U": 0, "S": 0, "A": 1, "A1": 1, "W": 1, "A8": 1}
    def kind(n):
        m = re.search(r"([A-Z][0-9]?)$", n); return m.group(1) if m else ""
    kept, log, seen = [], [], set()
    for s in order:
        mem = groups[s]
        best = sorted(mem, key=lambda x: (rank.get(kind(x), 2), mem.index(x)))[0]
        for m in mem:
            if m != best and m in seen: log.append({"dropped": m, "kept": best, "reason": "完全重复"})
            elif m != best: log.append({"dropped": m, "kept": best, "reason": "同号族合并(A/B 公布本)"})
        seen.update(mem); kept.append(best)
    fam_merged = []
    if family and len(kept) > 1:
        fams = {n: set(gp.family_cached(n, "zh" if lang.upper().startswith("CH") else "en") + [n]) for n in kept}
        parent = {n: n for n in kept}
        def find(x):
            while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
            return x
        for i, x in enumerate(kept):
            for y in kept[i + 1:]:
                if fams[x] & fams[y] and find(x) != find(y):
                    rx, ry = find(x), find(y)
                    keep, drop = (rx, ry) if kept.index(rx) <= kept.index(ry) else (ry, rx)
                    parent[drop] = keep
                    log.append({"dropped": drop, "kept": keep, "reason": "同族链合并"})
        kept = [n for n in kept if find(n) == n]
        meta = gp.resolve_numbers(kept, lang=lang, log=lambda *_: None)
        by_title = {}
        for n in kept:
            t = re.sub(r"[\s\-—–_·,，。.、;；:：()（）【】\[\]“”\"'`/]+", "", ((meta.get(n) or {}).get("title") or "").lower())
            if t: by_title.setdefault(t, []).append(n)
        for t, ns in by_title.items():
            if len(ns) > 1:
                for x in ns[1:]: fam_merged.append({"dropped": x, "kept": ns[0], "reason": "疑似同发明（标题一致但族链未连，需人工判定）"})
    return {"input": len(nums), "kept": kept, "kept_count": len(kept),
            "merges": [l for l in log if l["reason"] != "疑似同发明（标题一致但族链未连，需人工判定）"],
            "soft_flags": fam_merged}

@mcp.tool(name="patent_search",
          description="Google Patents 检索（召回/分面）：query 用官方语法（assignee=…、inventor=…、q=\"关键词\"、country=US 等），"
                      "中文关键词必须加引号。num 建议 ≤20（大 num 会被截断）。")
def patent_search(query: str, num: int = 20, page: int = 0, lang: str = "CHINESE") -> dict:
    res = gp.xhr(query, num=num, page=page, lang=lang)
    if res is None:
        return {"error": "查询失败（被封或超时）——出口被限流，稍后重试或增加出口", "query": query}
    out = [{"publication_number": p.get("publication_number"), "title": re.sub(r"<[^>]+>", "", p.get("title", "")),
            "filing_date": p.get("filing_date"), "publication_date": p.get("publication_date"),
            "assignee": p.get("assignee"), "inventor": p.get("inventor")} for p in res]
    return {"query": query, "page": page, "count": len(out), "results": out}

@mcp.tool(name="patent_status", description="健康检查：各 SOCKS 出口可达性 + 本地缓存规模。")
def patent_status() -> dict:
    exits = []
    for port in gp.EXITS:
        t0 = time.time()
        txt = gp._curl("https://patents.google.com/patent/US2668287A/en", port, max_time=12)
        exits.append({"port": port, "ok": len(txt) > 5000 and not gp._banned(txt),
                      "bytes": len(txt), "sec": round(time.time() - t0, 1), "banned": gp._banned(txt)})
    cache = gp.load_cache()
    return {"exits": exits, "ok_exits": sum(1 for e in exits if e["ok"]),
            "cache_entries": len(cache), "cache_file": gp.CACHE,
            "newnym_script": gp.NE_WY if os.path.exists(gp.NE_WY) else None}

if __name__ == "__main__":
    mcp.run("stdio")
