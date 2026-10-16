#!/usr/bin/env python3
"""Pre-publication checklist for this repository.

Fails (exit 1) if any file contains personal paths, e-mail addresses, credential-looking
strings, or any term from an optional external blocklist — the blocklist is deliberately NOT
part of the repository, so project-specific/retrieved data never gets committed.

Usage:
    python3 tools/sanitize_check.py                        # generic checks only
    BLOCKLIST=/path/to/blocklist.txt python3 tools/sanitize_check.py   # + your own terms (one per line)
"""
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "runs", "cache", "node_modules"}
GENERIC = [
    (r"/home/[A-Za-z0-9_.\-]+", "absolute user home path"),
    (r"/Users/[A-Za-z0-9_.\-]+", "absolute user home path"),
    (r"C:\\+Users\\+[A-Za-z0-9_.\-]+", "absolute user home path"),
    (r"/mnt/[a-z]/", "mounted host path"),
    (r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", "e-mail address"),
    (r"(?i)\b(api[_-]?key|secret|password|passwd|token)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{12,}", "credential-looking value"),
    (r"gh[pousr]_[A-Za-z0-9]{20,}", "GitHub token"),
    (r"sk-[A-Za-z0-9]{20,}", "API key"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key"),
    ("." + "he" + "rmes", "agent-specific config path"),   # split so this checker does not match itself
]

def load_blocklist():
    p = os.environ.get("BLOCKLIST")
    if not p or not os.path.exists(p):
        return []
    return [l.strip() for l in open(p, encoding="utf-8") if l.strip() and not l.startswith("#")]

def main():
    block = load_blocklist()
    findings, files = [], 0
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            path = os.path.join(dp, fn)
            rel = os.path.relpath(path, ROOT)
            try:
                text = open(path, encoding="utf-8", errors="ignore").read()
            except Exception as e:
                findings.append((rel, 0, f"unreadable: {e}")); continue
            files += 1
            for rx, label in GENERIC:
                for m in re.finditer(rx, text):
                    if m.group(0) == "Windows":        # browser user-agent string, not personal
                        continue
                    findings.append((rel, text[:m.start()].count("\n") + 1, f"{label}: {m.group(0)[:60]}"))
            for term in block:
                if term in text:
                    findings.append((rel, text.count("\n", 0, text.index(term)) + 1, f"blocklisted term: {term}"))
    print(f"scanned {files} files"
          + (f" (+{len(block)} blocklist terms)" if block else " (no external blocklist supplied)"))
    if not findings:
        print("PASS — no personal paths, credentials, or blocklisted terms found.")
        return 0
    print(f"FAIL — {len(findings)} finding(s):")
    for rel, ln, msg in findings[:200]:
        print(f"  {rel}:{ln}  {msg}")
    return 1

if __name__ == "__main__":
    sys.exit(main())
