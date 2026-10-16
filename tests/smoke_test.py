#!/usr/bin/env python3
"""End-to-end smoke test: starts the MCP server and exercises tools/list plus two tool calls.

Requirements
  * the `mcp` Python SDK installed for the interpreter running this file (the server imports it),
  * network access to the patent endpoint through the exits in GP_EXITS.

Usage
    python3 tests/smoke_test.py [publication_number ...]
    # e.g. GP_EXITS=9050 python3 tests/smoke_test.py US2668287A
"""
import json, os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUMS = sys.argv[1:] or ["US2668287A"]

env = {**os.environ, "PYTHONPATH": ROOT}
p = subprocess.Popen([sys.executable, "-m", "patent_intel.mcp_server"], cwd=ROOT, env=env,
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)

def send(obj):
    p.stdin.write(json.dumps(obj) + "\n"); p.stdin.flush()

def recv(timeout=180):
    end = time.time() + timeout
    while time.time() < end:
        line = p.stdout.readline()
        if not line:
            return None
        line = line.strip()
        if line.startswith("{"):
            try: return json.loads(line)
            except Exception: pass
    return None

ok = True
try:
    send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
          "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "smoke", "version": "1"}}})
    init = recv(60)
    print("initialize:", (init or {}).get("result", {}).get("serverInfo"))
    ok &= bool(init)
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = [t["name"] for t in ((recv(60) or {}).get("result", {}).get("tools") or [])]
    print("tools:", tools)
    ok &= "patent_resolve" in tools
    send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
          "params": {"name": "patent_resolve", "arguments": {"numbers": NUMS, "lang": "ENGLISH"}}})
    r = recv()
    try:
        pl = json.loads(r["result"]["content"][0]["text"])
        print(f"patent_resolve: hit {pl['hit']}/{pl['requested']} in {pl['elapsed_s']}s, miss={pl['miss']}")
        for it in pl["results"][:3]:
            print("   ", it["number"], "|", (it["title"] or "")[:50], "|", it["filing_date"], it["publication_date"], "|", it["source"])
        ok &= pl["hit"] > 0
    except Exception as e:
        print("resolve call failed:", str(r)[:300], e); ok = False
    send({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "patent_status", "arguments": {}}})
    try:
        st = json.loads(recv()["result"]["content"][0]["text"])
        print(f"patent_status: {st['ok_exits']}/{len(st['exits'])} exits reachable, cache {st['cache_entries']} entries")
        ok &= st["ok_exits"] > 0
    except Exception as e:
        print("status call failed:", e); ok = False
finally:
    p.kill()
print("SMOKE TEST:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
