#!/usr/bin/env python3
"""patent_intel.gp —— Google Patents 批量取数与族链工具（纯标准库 + curl + Tor 多出口）。

核心提速事实（本机实测，2026-10）：
  * 单件抓页面：2.2–3.5 s/件（页面 ~1 MB）
  * XHR 检索端点按号批量（OR 连接）：100 号/请求 ≈ 3.4 s → 0.034 s/件（≈100×）
  * num 上限 100：一次请求最多返回 100 条，超过部分静默丢弃（须分片）
  * 未被该查询形式索引的号（如部分 HK）→ 回落到单件抓页面

用法（库）：
    from gp import resolve_numbers, family_of, CACHE
    meta = resolve_numbers(["US2668287A", ...])     # dict[num] = {...}
用法（CLI）：
    python3 -m patent_intel.gp resolve numbers.csv --col number -o out.csv
    python3 -m patent_intel.gp family US2668287A
"""
import json, os, re, subprocess, sys, time, urllib.parse, random

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
EXITS = [int(x) for x in (os.environ.get("GP_EXITS") or "9050").split(",")]
CACHE_DIR = os.path.expanduser(os.environ.get("GP_CACHE", "~/.cache/patent-intel"))
CACHE = os.path.join(CACHE_DIR, "cache.json")
NE_WY = os.path.expanduser(os.environ.get("GP_NEWNYM", ""))   # 可选：Tor 换线脚本（无则仅轮转出口）
BATCH = int(os.environ.get("GP_BATCH", "100"))          # 实测上限 100
BAN_MARK = ("automated queries", "unusual traffic", "captcha")

_cache = None
def load_cache():
    global _cache
    if _cache is None:
        os.makedirs(CACHE_DIR, exist_ok=True)
        _cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
    return _cache
def save_cache():
    if _cache is not None:
        tmp = CACHE + ".tmp"; json.dump(_cache, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
        os.replace(tmp, CACHE)

def stem(num):                                  # strip kind code: US2668287A -> US2668287
    return re.sub(r"[A-Z][0-9]?$", "", num.upper().replace(" ", ""))

def _curl(url, exit_port, max_time=40):
    r = subprocess.run(["curl", "-sS", "-A", UA, "--proxy", f"socks5h://127.0.0.1:{exit_port}",
                        "--max-time", str(max_time), url], capture_output=True)
    return (r.stdout or b"").decode("utf-8", "ignore")

_NEWNYM_WARNED = False
def _newnym():
    """向 Tor 控制口请求新身份；脚本不存在时静默跳过（只靠出口轮转）。"""
    global _NEWNYM_WARNED
    if NE_WY and os.path.exists(NE_WY):
        subprocess.run([sys.executable, NE_WY], capture_output=True)
    elif not _NEWNYM_WARNED:
        _NEWNYM_WARNED = True
        print("[gp] no NEWNYM script configured (GP_NEWNYM); rotating exits only", file=sys.stderr)

def _banned(text):
    low = text.lower()
    return any(m in low for m in BAN_MARK)

def xhr(query, num=100, page=0, lang="ENGLISH", tries=5):
    """XHR 检索端点。返回 list[dict]（每条含 publication_number/title/filing_date/publication_date/assignee/inventor），
    失败返回 None。遇封禁自动换出口 + NEWNYM。"""
    u = urllib.parse.quote(f"q={urllib.parse.quote(query)}&num={num}&page={page}&language={lang}")
    url = f"https://patents.google.com/xhr/query?url={u}&exp="
    for a in range(tries):
        port = EXITS[a % len(EXITS)]
        txt = _curl(url, port)
        if len(txt) > 1500 and not _banned(txt) and txt.lstrip().startswith("{"):
            try:
                d = json.loads(txt)
            except Exception:
                time.sleep(2); continue
            out = []
            for c in d.get("results", {}).get("cluster") or []:
                for it in c.get("result") or []:
                    out.append(it["patent"])
            return out
        if _banned(txt) or len(txt) < 1500:
            _newnym()
        time.sleep(2 + 2 * a)
    return None

def page_meta(num, lang="zh", tries=3):
    """抓单件页面元数据（DC.* 元标签 + 事件），返回 dict 或 None。"""
    for a in range(tries):
        port = EXITS[a % len(EXITS)]
        h = _curl(f"https://patents.google.com/patent/{num}/{lang}", port, max_time=30)
        if len(h) > 5000 and not _banned(h):
            g = lambda p: (re.search(p, h, re.S).group(1).strip() if re.search(p, h, re.S) else "")
            return {"pnum": g(r'itemprop="publicationNumber">\s*([A-Z0-9]+)'),
                    "title": g(r'<meta name="DC.title" content="([^"]+)"'),
                    "kind": g(r'itemprop="publicationDescription" content="([^"]+)"'),
                    "filing": g(r'itemprop="filingDate"[^>]*>([0-9-]{10})'),
                    "pub": g(r'itemprop="publicationDate"[^>]*>([0-9-]{10})'),
                    "issue": g(r'<meta name="DC.date" content="([0-9-]{10})" scheme="issue">'),
                    "appnum": g(r'<meta name="citation_patent_application_number" content="([^"]+)"'),
                    "assignee": re.findall(r'<meta name="DC.contributor" content="([^"]+)" scheme="assignee">', h),
                    "inventor": re.findall(r'<meta name="DC.contributor" content="([^"]+)" scheme="inventor">', h),
                    "also": family_in(h), "url": f"https://patents.google.com/patent/{num}/{lang}"}
        if _banned(h):
            _newnym()
        time.sleep(2 + 2 * a)
    return None

def family_in(html):
    """从页面 HTML 抽 Also Published As 同族号。"""
    j = html.find("Also Published As")
    if j < 0: return []
    seg = html[j:j + 20000]
    k = seg.find("Similar Documents")
    if k > 0: seg = seg[:k]
    return re.findall(r'itemprop="publicationNumber">\s*([A-Z0-9]+)\s*<', seg)

def family_of(num, lang="zh"):
    m = page_meta(num, lang)
    return (m or {}).get("also", [])

def family_cached(num, lang="zh"):
    """同族号（带缓存）。缓存键 page@<号>@{lang}。"""
    cache = load_cache(); k = f"page@{num.upper()}@{lang}"
    if k not in cache:
        m = page_meta(num, lang)
        cache[k] = (m or {}).get("also", [])
        save_cache()
    return cache[k]

def resolve_numbers(nums, lang="ENGLISH", batch=BATCH, use_cache=True, log=print):
    """按号批量解析元数据。返回 dict[num] = {...}（缓存命中直接返回；未命中的按批请求，回落单件页面）。"""
    cache = load_cache(); out = {}; todo = []
    for n in nums:
        n = n.upper().replace(" ", "")
        k = f"{n}@{lang}"
        if use_cache and k in cache:
            out[n] = cache[k]
        else:
            todo.append(n)
    log(f"待取 {len(todo)} 件（缓存命中 {len(nums) - len(todo)}）")
    t0 = time.time()
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        res = xhr(" OR ".join(chunk), num=len(chunk), lang=lang)
        got = {}
        if res:
            for p in res:
                got[stem(p["publication_number"])] = p
        miss = []
        for n in chunk:
            p = got.get(stem(n))
            if p and p["publication_number"].upper() != n:
                # 批量查询可能回同族的另一公布本（要 B 却回 A）→ 直查该号页面确认真实存在与真实种类
                pm = page_meta(n, "zh" if lang == "CHINESE" else "en", tries=3)
                if pm:
                    pm.update({"num": n, "src": "page(exact)"})
                    out[n] = pm; cache[f"{n}@{lang}"] = pm
                    continue
                rec = {"num": n, "pnum": p["publication_number"],
                       "title": re.sub(r"<[^>]+>", "", p.get("title", "")).strip(),
                       "filing": p.get("filing_date", ""), "pub": p.get("publication_date", ""),
                       "assignee": p.get("assignee", ""), "inventor": p.get("inventor", ""),
                       "src": "xhr(stem-only)", "warn": f"批量查询只回同族的 {p['publication_number']}，未确证 {n} 存在"}
                out[n] = rec; cache[f"{n}@{lang}"] = rec
                continue
            if p and stem(p["publication_number"]) == stem(n):
                rec = {"num": n, "pnum": p["publication_number"],
                       "title": re.sub(r"<[^>]+>", "", p.get("title", "")).strip(),
                       "filing": p.get("filing_date", ""), "pub": p.get("publication_date", ""),
                       "assignee": p.get("assignee", ""), "inventor": p.get("inventor", ""),
                       "src": "xhr"}
                out[n] = rec; cache[f"{n}@{lang}"] = rec
            else:
                miss.append(n)
        for n in miss:                                    # 回落：单件页面
            m = page_meta(n, "zh" if lang == "CHINESE" else "en")
            if m:
                m.update({"num": n, "src": "page"})
                out[n] = m; cache[f"{n}@{lang}"] = m
            else:
                out[n] = {"num": n, "src": "miss"}
        save_cache()
        log(f"  {min(i + batch, len(todo))}/{len(todo)} 完成，{time.time() - t0:.0f}s（累计 {len(out)}）")
    log(f"用时 {time.time() - t0:.0f}s / {len(todo)} 件 = {(time.time() - t0) / max(len(todo), 1):.3f}s 每件")
    return out

def _cli():
    import argparse, csv as _csv
    ap = argparse.ArgumentParser(description="Google Patents 批量取数")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("resolve"); p1.add_argument("infile"); p1.add_argument("-o", "--out", required=True)
    p1.add_argument("--lang", default="ENGLISH"); p1.add_argument("--col", default="number")
    p1.add_argument("--refresh", action="store_true")
    p2 = sub.add_parser("family"); p2.add_argument("num")
    a = ap.parse_args()
    if a.cmd == "family":
        print(json.dumps(family_of(a.num), ensure_ascii=False)); return
    raw = open(a.infile, encoding="utf-8-sig").read().splitlines()
    head = raw[0] if raw else ""
    is_table = ("," in head) or (head.strip().lower() in ("number", "numbers", "publication_number", "num",
                                                          a.col.lower(), "号码", "专利号"))
    if is_table:
        rd = _csv.DictReader(raw)
        col = a.col if a.col in (rd.fieldnames or []) else (rd.fieldnames or ["number"])[0]
        nums = [r[col].strip() for r in rd if (r.get(col) or "").strip()]
    else:
        vals = [l.strip() for l in raw if l.strip()]
        if vals and vals[0].lower() == a.col.lower():
            vals = vals[1:]                      # drop a bare header line
        nums = vals
    meta = resolve_numbers(nums, lang=a.lang, use_cache=not a.refresh)
    with open(a.out, "w", newline="", encoding="utf-8-sig") as f:
        w = _csv.writer(f); w.writerow(["number", "publication_number", "title", "filing_date", "publication_date", "assignee", "inventor", "source"])
        for n in nums:
            r = meta.get(n.upper().replace(" ", "")) or {}
            w.writerow([n, r.get("pnum", ""), r.get("title", ""), r.get("filing", ""),
                        r.get("pub") or r.get("issue", ""), r.get("assignee", ""), r.get("inventor", ""), r.get("src", "")])
    hit = sum(1 for n in nums if (meta.get(n.upper().replace(" ", "")) or {}).get("src", "").startswith(("xhr", "page")))
    warn = sum(1 for n in nums if (meta.get(n.upper().replace(" ", "")) or {}).get("src") == "xhr(stem-only)")
    print(f"写出 {a.out}｜命中 {hit}/{len(nums)}｜仅同族未确证 {warn}")

if __name__ == "__main__":
    _cli()
