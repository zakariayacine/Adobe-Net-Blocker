#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adobe & companions network toggle (Windows)
- Blocks/Unblocks internet for Adobe apps (Illustrator, Photoshop, CEPHtmlEngine, CCXProcess, AIMonitor)
- Optionally blocks WebView2 used by Photoshop (may affect other apps)
- Can also write/remove a hosts-file block section for Adobe domains

USAGE (run in an elevated PowerShell or CMD):
  python adobe_net_blocker.py block         # create firewall + hosts rules
  python adobe_net_blocker.py unblock       # remove firewall + hosts rules
  python adobe_net_blocker.py status        # show what will be targeted
  python adobe_net_blocker.py block --no-hosts      # firewall only
  python adobe_net_blocker.py block --include-webview   # include WebView2 exe
  python adobe_net_blocker.py unblock --keep-hosts  # remove firewall rules but keep hosts entries
"""

import argparse
import ctypes
import glob
import os
import re
import subprocess
import sys
from pathlib import Path

FIREWALL_RULE_PREFIX = "AdobeNetBlock"
HOSTS_BEGIN = "# BEGIN ADOBE_NET_BLOCK"
HOSTS_END = "# END ADOBE_NET_BLOCK"

# Default domains to block via hosts (customize by creating a domains.txt next to this script)
DEFAULT_DOMAINS = [
    "adobe.com",
    "adobelogin.com",
    "adobe.io",
    "adobecc.com",
    "behance.net",
    "adobesc.com",
    "cc-api-data.adobe.io",
    "cc-assets.adobe.com",
    "ccmdls.adobe.com",
    "lcs-cops.adobe.io",
    "ims-na1.adobelogin.com",
    "na1r.services.adobe.com",
    "prod-rel-ffc-ccm.oobesaas.adobe.com",
]

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run(cmd):
    completed = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()

def find_candidates(include_webview=False):
    # Expand likely install locations
    patterns = [
        r"C:\Program Files\Adobe\**\Illustrator.exe",
        r"C:\Program Files\Adobe\**\Photoshop.exe",
        r"C:\Program Files\Adobe\**\Support Files\Contents\Windows\CEPHtmlEngine\CEPHtmlEngine.exe",
        r"C:\Program Files\Adobe\**\AIMonitor.exe",
        r"C:\Program Files\Common Files\Adobe\**\CCXProcess.exe",
        r"C:\Users\*\AppData\Local\Programs\Common\**\CCXProcess.exe",
    ]
    if include_webview:
        patterns.append(r"C:\Program Files (x86)\Microsoft\EdgeWebView\Application\*\msedgewebview2.exe")

    found = []
    for pat in patterns:
        for p in glob.glob(pat, recursive=True):
            if os.path.isfile(p):
                try:
                    # normalize casing
                    found.append(str(Path(p)))
                except Exception:
                    found.append(p)
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for p in found:
        up = p.lower()
        if up not in seen:
            seen.add(up)
            unique.append(p)
    return unique

def rule_name_for(path, direction):
    base = Path(path).name
    return f"{FIREWALL_RULE_PREFIX} [{direction}] {base}"

def add_firewall_rules(paths):
    any_error = False
    for path in paths:
        for direction in ("out", "in"):
            name = rule_name_for(path, direction)
            cmd = f'netsh advfirewall firewall add rule name="{name}" dir={direction} action=block program="{path}" enable=yes profile=any'
            rc, out, err = run(cmd)
            if rc != 0:
                # If rule already exists, try to update it
                upd = f'netsh advfirewall firewall set rule name="{name}" new enable=yes'
                rc2, out2, err2 = run(upd)
                if rc2 != 0:
                    print(f"[!] Failed to add or update rule for {path} ({direction}): {err or err2}")
                    any_error = True
                else:
                    print(f"[=] Updated rule: {name}")
            else:
                print(f"[+] Added rule: {name}")
    return not any_error

def delete_firewall_rules():
    # Delete by prefix (twice to be safe for both directions)
    pattern = f"{FIREWALL_RULE_PREFIX}"
    rc, out, err = run(f'netsh advfirewall firewall show rule name=all | findstr /I "{pattern}"')
    # Attempt delete per known directions and generic wildcard
    deleted_any = False
    for direction in ("out", "in"):
        rc2, out2, err2 = run(f'netsh advfirewall firewall delete rule name=all dir={direction} program=any | findstr /I "{pattern}"')
        if out2 or err2:
            deleted_any = True
    # Also try deleting by explicit names that match our pattern
    # (Windows netsh doesn't support wildcards in delete by name; so we just try common exe bases)
    for base in ["Illustrator.exe", "Photoshop.exe", "CEPHtmlEngine.exe", "AIMonitor.exe", "CCXProcess.exe", "msedgewebview2.exe"]:
        for direction in ("out", "in"):
            name = f'{FIREWALL_RULE_PREFIX} [{direction}] {base}'
            run(f'netsh advfirewall firewall delete rule name="{name}"')
    print("[=] Requested deletion of firewall rules with prefix", FIREWALL_RULE_PREFIX)
    return True

def hosts_path():
    return r"C:\Windows\System32\drivers\etc\hosts"

def read_domains():
    local_txt = Path(__file__).with_name("domains.txt")
    if local_txt.exists():
        items = []
        for line in local_txt.read_text(encoding="utf-8", errors="ignore").splitlines():
            t = line.strip()
            if t and not t.startswith("#"):
                items.append(t)
        if items:
            return items
    return DEFAULT_DOMAINS

def ensure_hosts_block(add=True):
    hp = hosts_path()
    try:
        text = Path(hp).read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"[!] Unable to read hosts ({hp}): {e}")
        return False

    # Remove existing block
    new_text = re.sub(rf"\r?\n?{re.escape(HOSTS_BEGIN)}.*?{re.escape(HOSTS_END)}\r?\n?", "\n", text, flags=re.S|re.M)

    if add:
        lines = [HOSTS_BEGIN]
        for d in read_domains():
            lines.append(f"0.0.0.0 {d}")
            lines.append(f"::1 {d}")
        lines.append(HOSTS_END)
        block = "\n".join(lines) + "\n"
        if not new_text.endswith("\n"):
            new_text += "\n"
        new_text += block

    try:
        Path(hp).write_text(new_text, encoding="utf-8")
        print(f"[=] {'Added' if add else 'Removed'} hosts block section at {hp}")
        return True
    except Exception as e:
        print(f"[!] Unable to write hosts ({hp}): {e}")
        return False

def status(include_webview=False):
    print("== Candidate executables ==")
    for p in find_candidates(include_webview=include_webview):
        print(" -", p)
    print("\n== Hosts domains ==")
    for d in read_domains():
        print(" -", d)
    print("\nNote: run this script from an elevated shell (Administrator).")

def main():
    parser = argparse.ArgumentParser(description="Toggle network access for Adobe apps via Windows Firewall and hosts file.")
    parser.add_argument("action", choices=["block","unblock","status"])
    parser.add_argument("--no-hosts", action="store_true", help="Skip hosts-file modification")
    parser.add_argument("--keep-hosts", action="store_true", help="When unblocking, keep hosts-file block")
    parser.add_argument("--include-webview", action="store_true", help="Also block Edge WebView2 used by Photoshop (may affect other apps)")
    args = parser.parse_args()

    if not is_admin():
        print("[!] Please run this script as Administrator (elevated shell).")
        sys.exit(1)

    include_webview = args.include_webview

    if args.action == "status":
        status(include_webview=include_webview)
        return

    if args.action == "block":
        exe_paths = find_candidates(include_webview=include_webview)
        if not exe_paths:
            print("[!] No Adobe executables found in standard locations. You can still use hosts blocking or add paths manually.")
        ok_fw = add_firewall_rules(exe_paths) if exe_paths else True
        ok_hosts = True
        if not args.no_hosts:
            ok_hosts = ensure_hosts_block(add=True)
        if ok_fw and ok_hosts:
            print("[✓] Blocking applied.")
        else:
            print("[!] Some steps failed. See messages above.")
        return

    if args.action == "unblock":
        delete_firewall_rules()
        if not args.keep_hosts:
            ensure_hosts_block(add=False)
        print("[✓] Unblocking requested.")
        return

if __name__ == "__main__":
    main()
