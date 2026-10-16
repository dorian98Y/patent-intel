# patent-intel

**Reliable, fast bulk patent data retrieval, verification and de-duplication for Google Patents.**
面向「一份专利清单要逐条核对网址与元数据」的任务：批量取数、逐条核对、族级去重，全程可复现。

[中文](#中文) · [English](#english)

---

## 中文

### 它解决什么问题

手工/逐件抓取专利数据在百件级清单上要慢到不可用，且容易出四类错：**漏件**（只被英文索引、漏实用新型/外观设计）、**误判**（把同族另一公布本当成缺漏）、**抓取失败被当成功**（出口被限流后静默返回 0 条）、**口径混用**（号级/族级、含不含各类公布本）。本工具把这三件事固化：

1. **批量取数**：把多个号拼进同一条官方页面查询接口，一次最多 100 号；
2. **逐条核对**：把清单声明值（名称/申请日/公布日/号）与实测值对照，输出差异清单；
3. **族级去重**：同号族（A/B 公布本）合并 + 可选族链合并（跨 CN/US/WO），仅标题一致的软证据只标记不自动合并。

### 实测速度

| 取数路径 | 速度 | 说明 |
|---|---|---|
| 逐件抓页面 | 2.2–3.5 s/件 | 页面约 1 MB，限流重试链会把均摊时间拉到 10 s+ |
| 单号查询接口 | 2.6 s/件 | 一请求一结果 |
| **按号批量（本工具）** | **0.03–0.15 s/件** | 一次最多 100 号，超出的静默丢弃 → 自动分片并校验 |
| 缓存命中重跑 | ≈0 | 缓存在 `GP_CACHE`（默认 `~/.cache/patent-intel`） |

参考：冷缓存 100 件全流程（去重→取数→核对→汇总）约 15 s（4 个出口）。

### 安装与依赖

```bash
git clone <this-repo> && cd patent-intel
# 依赖：python3（标准库）+ curl + 若干 SOCKS5 出口（Tor 或多出口代理）
export GP_EXITS=9050,9052,9054,9056      # SOCKS5 端口列表（默认 19080,19082,19084,19086）
export GP_CACHE=~/.cache/patent-intel    # 缓存目录
export GP_NEWNYM=/path/to/tor_newnym.py  # 可选：换 Tor 出口脚本；没有则只做出口轮转
```

没有 Tor 也可以：把 `GP_EXITS` 指向任意 SOCKS5 代理；或直接对可访问 Google Patents 的网络运行（端口列表填一个即可）。

### 一条命令

```bash
./cli/run_workflow.sh 清单.csv 号码 CHINESE          # 去重 → 取数 → 核对 → 汇总
./cli/run_workflow.sh 清单.csv 号码 ENGLISH --family  # 追加族级去重
```

产出（`GP_OUT` 或 `./runs/<时间戳>/`）：`1_dedup.csv`（去重后）｜`1_merge_log.csv`（合并与疑似同发明）｜`2_meta.csv`（实测元数据）｜`3_mismatch.csv`（差异清单）｜`0_summary.txt`（汇总）。

### 分项使用

```bash
python3 -m patent_intel.gp resolve 清单.csv --col 号码 --lang CHINESE -o meta.csv
python3 -m patent_intel.gp family EP1000000A1
python3 -m patent_intel.verify --ref 清单.csv --lang CHINESE --out 差异.csv   # 退出码 2 = 有差异
python3 -m patent_intel.dedupe --in 清单.csv --out 去重.csv --report 日志.csv [--family]
```

### MCP 服务器（给 AI agent 用）

```bash
python3 -m patent_intel.mcp_server        # stdio 传输
```

工具：`patent_resolve`（批量取数）｜`patent_verify`（逐条核对）｜`patent_dedupe`（族级去重）｜`patent_family`（同族号）｜`patent_search`（召回/分面检索）｜`patent_status`（出口与缓存健康检查）。

任一支持 MCP 的客户端配置示例：

```yaml
mcp_servers:
  patent-intel:
    command: /path/to/python
    args: ["-m", "patent_intel.mcp_server"]
    env:
      PYTHONPATH: /path/to/patent-intel
      GP_EXITS: "9050,9052,9054,9056"
    timeout: 300
```

`mcp.example.json` 提供了 JSON 形态的同款配置。

### 设计与判据（为什么这样做）

- **按同号族比对**：同一件专利有 A（申请公布）/B（授权公告）等不同公布本，跨法域还有 CN/US/WO 各一套号；比对前先去掉种类码，跨法域再查族链。
- **授权本优先**：`B`/`I`（发明）、`U`（实用新型）、`S`（外观设计）本身就是授权公告本；代表号优先取授权本。
- **名称以授权公告本为准**：官方可能在授权阶段改题，A/B 标题会不同。
- **硬证据自动合并、软证据只标记**：族链重合才合并；仅标题一致的写入「疑似同发明待判」交人工。
- **命中判定带校验**：返回号与请求号同族才算命中；批量查询未索引的号（如部分 HK 号）回落单件页面；返回同族另一公布本时直查该号确证，无法确证则标记 `xhr(stem-only)` 并在核对报告里列为问题。
- **限流检测**：响应过短或含阻止页关键字即换出口重试，失败返回 `None`（区别于「真的 0 结果」）。

坑清单见 `docs/pitfalls.md`；同类开源方案实测对比见 `docs/github-survey.md`。

### 已知限制

- 该接口的一次查询最多返回 100 条；分面检索的大 `num` 响应会被截断（约 20 KB 处 JSON 非法），分面检索请用 `num<=20`。
- 同族判定依赖页面公开的家族段，与 INPADOC 等权威族链口径可能不同。
- 「查得到授权公告本」不等于「专利有效」（失效/终止/未缴年费属法律状态，需另查）。
- 未公开的申请（如美国临时申请）在公开源上取不到，工具会如实记为未命中。

### License

MIT（见 `LICENSE`）。

---

## English

**patent-intel** is a small, dependency-light toolkit for *list-level* patent work on Google Patents: bulk metadata retrieval, row-by-row verification of an existing list, and family-aware de-duplication.

**Why it exists.** Scraping one page per patent is 2–3.5 s/patent and quietly wrong in predictable ways: patents indexed only under an English applicant string are missed; the same patent's other publication (A vs B) is counted as a separate gap; a rate-limited exit returns zero results without an error; and counts get mixed up between publication-number level and family level.

**What it does**

1. **Bulk retrieval** — batches many numbers into one request to the public Google Patents query endpoint (up to 100 per request, auto-sharded and validated).
2. **Verification** — compares a list's declared values (title / filing date / publication date / number) against fetched values and emits a mismatch report.
3. **De-duplication** — merges same-stem publications (A/B) and, optionally, family-linked siblings across jurisdictions; title-only matches are flagged for human review instead of auto-merged.

**Measured speed** (4 SOCKS exits): 0.03–0.15 s/patent in batch mode, versus 2.2–3.5 s/patent fetching pages; a 100-row full workflow (dedupe → fetch → verify → summarize) runs in ~15 s cold, and re-runs are cache-hits (~0 s).

**Quick start**

```bash
export GP_EXITS=9050,9052,9054,9056
./cli/run_workflow.sh list.csv 号码 CHINESE
```

**MCP server** — `python3 -m patent_intel.mcp_server` exposes `patent_resolve`, `patent_verify`, `patent_dedupe`, `patent_family`, `patent_search`, `patent_status` over stdio. See `mcp.example.json`.

**Requirements** — Python 3 standard library, `curl`, and one or more SOCKS5 exits (Tor or any SOCKS proxy). No Python packages required for the CLI; the MCP server needs the official `mcp` Python SDK.

**Scope limits** — the public endpoint returns at most 100 results per query; facet queries must stay at `num<=20` (larger responses truncate); family links come from the page's published-family section and may differ from INPADOC; "a granted publication exists" is not the same as "the patent is in force".

MIT licensed.
