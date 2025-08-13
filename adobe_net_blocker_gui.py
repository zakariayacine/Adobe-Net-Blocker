#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adobe Net Blocker - GUI (Full Auto, corrected)
- Scans ALL Adobe directories for every .exe and blocks them (in/out, all profiles) via Windows Firewall
- Includes Adobe-related components in common Adobe folders (Common Files) and user AppData (Local/Roaming)
- Optional: include non-Adobe helper used by Adobe (Edge WebView2 for Photoshop/UXP) — may affect other apps
- Hosts block for known Adobe domains (editable in-app)
- Aggressive mode: disable Adobe services and Adobe scheduled tasks
- Auto-block on startup (configurable)

Run as Administrator.
"""

import ctypes
import glob
import os
import re
import subprocess
import sys
from pathlib import Path
import csv
import io
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

APP_TITLE = "Adobe Net Blocker - Full Auto"
FIREWALL_RULE_PREFIX = "AdobeNetBlock"
HOSTS_BEGIN = "# BEGIN ADOBE_NET_BLOCK"
HOSTS_END = "# END ADOBE_NET_BLOCK"

ADOBE_SERVICES = [
    "AdobeUpdateService",
    "AGSService",
    "AdobeARMservice",
]

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

# ----- Utils -----

def script_dir():
    try:
        return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    except Exception:
        return Path(os.getcwd())

DOMAINS_FILE = script_dir() / "domains.txt"

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

def run(cmd):
    completed = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    # Robust against None stdout/stderr
    out = (completed.stdout or "").strip()
    err = (completed.stderr or "").strip()
    return completed.returncode, out, err

def hosts_path():
    return r"C:\Windows\System32\drivers\etc\hosts"

def read_domains():
    if DOMAINS_FILE.exists():
        try:
            lines = DOMAINS_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
            items = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
            if items:
                return items
        except Exception:
            pass
    return list(DEFAULT_DOMAINS)

def write_domains(domains_list):
    try:
        DOMAINS_FILE.write_text("\n".join(domains_list) + "\n", encoding="utf-8")
        return True, None
    except Exception as e:
        return False, str(e)

def ensure_hosts_block(add=True, edited_domains=None):
    hp = hosts_path()
    try:
        text = Path(hp).read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return False, f"Lecture hosts échouée: {e}"

    # strip previous block
    new_text = re.sub(rf"\r?\n?{re.escape(HOSTS_BEGIN)}.*?{re.escape(HOSTS_END)}\r?\n?", "\n", text, flags=re.S|re.M)

    if add:
        domains = edited_domains if edited_domains is not None else read_domains()
        lines = [HOSTS_BEGIN]
        for d in domains:
            lines.append(f"0.0.0.0 {d}")
            lines.append(f"::1 {d}")
        lines.append(HOSTS_END)
        block = "\n".join(lines) + "\n"
        if not new_text.endswith("\n"):
            new_text += "\n"
        new_text += block

    try:
        Path(hp).write_text(new_text, encoding="utf-8")
        return True, None
    except Exception as e:
        return False, f"Écriture hosts échouée: {e}"

# ----- Scanning Adobe trees -----

ADOBE_ROOT_PATTERNS = [
    r"C:\Program Files\Adobe\**\*.exe",
    r"C:\Program Files (x86)\Adobe\**\*.exe",
    r"C:\Program Files\Common Files\Adobe\**\*.exe",
    r"C:\Users\*\AppData\Local\Adobe\**\*.exe",
    r"C:\Users\*\AppData\Roaming\Adobe\**\*.exe",
    r"C:\Users\*\AppData\Local\Programs\Common\**\*.exe",
]

WEBVIEW2_PATTERN = r"C:\Program Files (x86)\Microsoft\EdgeWebView\Application\*\msedgewebview2.exe"

def find_all_adobe_executables(include_webview=False):
    found = []
    for pat in ADOBE_ROOT_PATTERNS:
        for p in glob.glob(pat, recursive=True):
            if os.path.isfile(p) and p.lower().endswith(".exe"):
                found.append(str(Path(p)))
    if include_webview:
        for p in glob.glob(WEBVIEW2_PATTERN, recursive=True):
            if os.path.isfile(p):
                found.append(str(Path(p)))
    # deduplicate
    seen = set()
    uniq = []
    for p in found:
        low = p.lower()
        if low not in seen:
            seen.add(low)
            uniq.append(p)
    return uniq

def base_name(path):
    return Path(path).name

def rule_name_for(path, direction):
    base = base_name(path)
    return f"{FIREWALL_RULE_PREFIX} [{direction}] {base}"

def add_firewall_rules(paths):
    any_error = False
    logs = []
    for path in paths:
        for direction in ("out", "in"):
            name = rule_name_for(path, direction)
            cmd = f'netsh advfirewall firewall add rule name="{name}" dir={direction} action=block program="{path}" enable=yes profile=any'
            rc, out, err = run(cmd)
            if rc != 0:
                upd = f'netsh advfirewall firewall set rule name="{name}" new enable=yes'
                rc2, out2, err2 = run(upd)
                if rc2 != 0:
                    any_error = True
                    logs.append(f"Échec règle {name}: {err or err2}")
                else:
                    logs.append(f"MAJ règle: {name}")
            else:
                logs.append(f"Créée: {name}")
    return not any_error, "\n".join(logs)

def delete_firewall_rules():
    logs = []
    # Enumerate current Adobe trees to reconstruct likely rule names
    candidates = find_all_adobe_executables(include_webview=True)
    bases = sorted(set(base_name(p) for p in candidates) | {"msedgewebview2.exe"})
    for base in bases:
        for direction in ("out", "in"):
            name = f'{FIREWALL_RULE_PREFIX} [{direction}] {base}'
            rc, out, err = run(f'netsh advfirewall firewall delete rule name="{name}"')
            if rc == 0:
                logs.append(f"Supprimée: {name}")
    return True, "\n".join(logs)

# ----- Aggressive: services + tasks -----

def service_stop_disable(svc_name):
    run(f'sc stop "{svc_name}"')
    rc, out, err = run(f'sc config "{svc_name}" start= disabled')
    return rc == 0, err or out

def service_enable_start(svc_name):
    run(f'sc config "{svc_name}" start= demand')
    run(f'sc start "{svc_name}"')

def list_adobe_tasks():
    rc, out, err = run('schtasks /Query /FO CSV /V')
    if rc != 0 or not out:
        return []
    try:
        # Normalize newlines to be robust
        data = out.replace('\r\n', '\n').replace('\r', '\n')
        reader = csv.DictReader(io.StringIO(data))
        if not reader.fieldnames:
            return []
        # Find the "task name" column across locales
        field = None
        for fn in reader.fieldnames:
            low = fn.lower()
            if ("task" in low and "name" in low) or ("tâche" in low and "nom" in low) or ("tarea" in low and "nombre" in low):
                field = fn
                break
        if field is None:
            # Fallback to 2nd column if available (common position of TaskName)
            field = reader.fieldnames[1] if len(reader.fieldnames) > 1 else reader.fieldnames[0]
        names = []
        for row in reader:
            tn = (row.get(field) or "").strip()
            if "Adobe" in tn:
                names.append(tn)
        return sorted(set(names))
    except Exception:
        return []

def aggressive_apply(log_cb):
    for svc in ADOBE_SERVICES:
        ok, msg = service_stop_disable(svc)
        log_cb(f"Service {svc}: {'désactivé' if ok else 'échec'} ({msg})")
    tasks = list_adobe_tasks()
    if tasks:
        for tn in tasks:
            rc, out, err = run(f'schtasks /Change /TN "{tn}" /Disable')
            if rc == 0:
                log_cb(f"Tâche planifiée désactivée: {tn}")
            else:
                log_cb(f"Échec désactivation tâche: {tn} ({err or out})")
    else:
        log_cb("Aucune tâche planifiée Adobe détectée.")

def aggressive_revert(log_cb):
    for svc in ADOBE_SERVICES:
        service_enable_start(svc)
        log_cb(f"Service {svc}: réactivé (manuel)")
    tasks = list_adobe_tasks()
    if tasks:
        for tn in tasks:
            rc, out, err = run(f'schtasks /Change /TN "{tn}" /Enable')
            if rc == 0:
                log_cb(f"Tâche planifiée réactivée: {tn}")
            else:
                log_cb(f"Échec réactivation tâche: {tn} ({err or out})")

# ----- GUI -----

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1020x660")
        self.minsize(900, 560)

        # State
        self.include_webview = tk.BooleanVar(value=True)   # include helper used by Adobe
        self.use_hosts = tk.BooleanVar(value=True)
        self.auto_block_on_start = tk.BooleanVar(value=True)
        self.aggressive = tk.BooleanVar(value=True)        # aggressive ON by default

        # Header
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="⚠ Lancer en Administrateur. Ce mode bloque TOUT .exe dans les dossiers Adobe.", foreground="#b35c00").pack(side="left")

        # Options
        opts = ttk.Labelframe(self, text="Options", padding=10)
        opts.pack(fill="x", padx=10, pady=(6,0))
        ttk.Checkbutton(opts, text="Inclure WebView2 (utilisé par Photoshop/UXP) — peut impacter d'autres apps", variable=self.include_webview).pack(side="left")
        ttk.Checkbutton(opts, text="Modifier le fichier hosts", variable=self.use_hosts).pack(side="left", padx=(12,0))
        ttk.Checkbutton(opts, text="Auto-blocage au démarrage", variable=self.auto_block_on_start).pack(side="left", padx=(12,0))
        ttk.Checkbutton(opts, text="Mode agressif (services Adobe + tâches planifiées)", variable=self.aggressive).pack(side="right")

        # Split
        split = ttk.PanedWindow(self, orient="horizontal")
        split.pack(fill="both", expand=True, padx=10, pady=10)

        # Left: executables list
        left = ttk.Frame(split, padding=10)
        split.add(left, weight=1)

        ttk.Label(left, text="Exécutables détectés (Adobe trees + liés)").pack(anchor="w")
        self.candidates = tk.Listbox(left, height=14, selectmode="extended")
        self.candidates.pack(fill="both", expand=True, pady=(6,6))

        btns_left = ttk.Frame(left)
        btns_left.pack(fill="x")
        ttk.Button(btns_left, text="Scanner tout Adobe", command=self.on_scan).pack(side="left")
        ttk.Button(btns_left, text="Ajouter exécutable…", command=self.on_add_path).pack(side="left", padx=6)
        ttk.Button(btns_left, text="Retirer sélection", command=self.on_remove_selected).pack(side="left")
        ttk.Button(btns_left, text="Tout sélectionner", command=self.on_select_all).pack(side="right")

        # Right: hosts editor
        right = ttk.Frame(split, padding=10)
        split.add(right, weight=1)

        ttk.Label(right, text="Domains (hosts) — un par ligne").pack(anchor="w")
        self.hosts_text = tk.Text(right, height=14, wrap="none")
        self.hosts_text.pack(fill="both", expand=True, pady=(6,6))

        btns_right = ttk.Frame(right)
        btns_right.pack(fill="x")
        ttk.Button(btns_right, text="Charger", command=self.load_hosts_to_editor).pack(side="left")
        ttk.Button(btns_right, text="Sauvegarder", command=self.save_hosts_from_editor).pack(side="left", padx=6)
        ttk.Button(btns_right, text="Importer…", command=self.import_hosts_file).pack(side="left")
        ttk.Button(btns_right, text="Exporter…", command=self.export_hosts_file).pack(side="left", padx=6)

        # Bottom actions + log
        actions = ttk.Frame(self, padding=(10,0))
        actions.pack(fill="x")
        ttk.Button(actions, text="Bloquer (tout Adobe)", command=self.on_block).pack(side="left")
        ttk.Button(actions, text="Débloquer (tout)", command=self.on_unblock).pack(side="left", padx=6)
        ttk.Button(actions, text="Status", command=self.on_status).pack(side="left")
        ttk.Button(actions, text="Services Adobe (stop & disable)", command=self.on_services_disable).pack(side="right", padx=(6,0))
        ttk.Button(actions, text="Services Adobe (réactiver)", command=self.on_services_enable).pack(side="right")

        self.log = tk.Text(self, height=10, wrap="word")
        self.log.pack(fill="both", expand=False, padx=10, pady=(10,10))

        # Init
        self.on_scan()
        self.load_hosts_to_editor()

        if not is_admin():
            messagebox.showwarning("Droits requis", "Ouvre ce programme en tant qu'Administrateur pour appliquer le pare-feu et modifier le hosts.")

        # Auto block on start, if requested
        if is_admin() and self.auto_block_on_start.get():
            self.log_write("Auto-blocage au démarrage…")
            self.on_block()

    # ---- helpers ----
    def log_write(self, text):
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def on_scan(self):
        self.candidates.delete(0, "end")
        items = find_all_adobe_executables(include_webview=self.include_webview.get())
        if not items:
            self.log_write("Aucun exécutable trouvé dans les arbres Adobe. Ajoute manuellement si besoin.")
        for it in items:
            self.candidates.insert("end", it)
        self.log_write(f"Scan terminé. {len(items)} exécutables listés.")

    def on_add_path(self):
        path = filedialog.askopenfilename(title="Choisir un exécutable", filetypes=[("Executable", "*.exe"), ("Tous fichiers", "*.*")])
        if path:
            existing = set(self.candidates.get(0, "end"))
            if path not in existing:
                self.candidates.insert("end", path)

    def on_remove_selected(self):
        sel = list(self.candidates.curselection())
        if not sel: return
        for i in reversed(sel):
            self.candidates.delete(i)

    def on_select_all(self):
        self.candidates.select_set(0, "end")

    def load_hosts_to_editor(self):
        self.hosts_text.delete("1.0", "end")
        for d in read_domains():
            self.hosts_text.insert("end", d + "\n")
        self.log_write("Domains chargés dans l'éditeur.")

    def save_hosts_from_editor(self):
        text = self.hosts_text.get("1.0", "end").splitlines()
        items = [ln.strip() for ln in text if ln.strip() and not ln.strip().startswith("#")]
        ok, err = write_domains(items if items else [])
        if ok:
            self.log_write(f"domains.txt sauvegardé ({DOMAINS_FILE}).")
        else:
            messagebox.showerror("Erreur", f"Impossible d'écrire domains.txt : {err}")

    def import_hosts_file(self):
        p = filedialog.askopenfilename(title="Importer domains.txt", filetypes=[("Texte", "*.txt"), ("Tous fichiers", "*.*")])
        if not p: return
        try:
            lines = Path(p).read_text(encoding="utf-8", errors="ignore").splitlines()
            self.hosts_text.delete("1.0", "end")
            for ln in lines:
                self.hosts_text.insert("end", ln.rstrip() + "\n")
            self.log_write(f"Importé depuis {p}")
        except Exception as e:
            messagebox.showerror("Erreur", f"Lecture échouée: {e}")

    def export_hosts_file(self):
        p = filedialog.asksaveasfilename(defaultextension=".txt", title="Exporter domains.txt", initialfile="domains.txt", filetypes=[("Texte", "*.txt")])
        if not p: return
        try:
            data = self.hosts_text.get("1.0", "end")
            Path(p).write_text(data, encoding="utf-8")
            self.log_write(f"Exporté vers {p}")
        except Exception as e:
            messagebox.showerror("Erreur", f"Écriture échouée: {e}")

    def collect_paths(self):
        return list(self.candidates.get(0, "end"))

    def on_status(self):
        paths = self.collect_paths()
        self.log_write("=== STATUS ===")
        self.log_write(f"WebView2 inclus: {self.include_webview.get()} | Hosts: {self.use_hosts.get()} | Agressif: {self.aggressive.get()}")
        self.log_write(f"{len(paths)} exécutables listés.")
        if len(paths) <= 20:
            for p in paths:
                self.log_write(" - " + p)

    def on_block(self):
        if not is_admin():
            messagebox.showwarning("Droits requis", "Relance en Administrateur pour appliquer les règles.")
            return
        paths = self.collect_paths()
        if not paths:
            self.log_write("Rien à bloquer (liste vide).")
            return
        ok_fw, log_fw = add_firewall_rules(paths)
        self.log_write(log_fw)
        if self.use_hosts.get():
            ok_hosts, err = ensure_hosts_block(add=True, edited_domains=[ln.strip() for ln in self.hosts_text.get('1.0','end').splitlines() if ln.strip() and not ln.strip().startswith('#')])
            if ok_hosts:
                self.log_write("Bloc hosts ajouté.")
            else:
                self.log_write("ERREUR hosts: " + str(err))
        if self.aggressive.get():
            self.log_write("Mode agressif: désactivation services Adobe + tâches planifiées…")
            aggressive_apply(self.log_write)
        self.log_write("Blocage terminé.")

    def on_unblock(self):
        if not is_admin():
            messagebox.showwarning("Droits requis", "Relance en Administrateur pour retirer les règles.")
            return
        ok_fw, log_fw = delete_firewall_rules()
        self.log_write(log_fw)
        if self.use_hosts.get():
            ok_hosts, err = ensure_hosts_block(add=False)
            if ok_hosts:
                self.log_write("Bloc hosts retiré.")
            else:
                self.log_write("ERREUR hosts: " + str(err))
        if self.aggressive.get():
            self.log_write("Réactivation services Adobe + tâches planifiées…")
            aggressive_revert(self.log_write)
        self.log_write("Déblocage demandé.")

    def on_services_disable(self):
        if not is_admin():
            messagebox.showwarning("Droits requis", "Relance en Administrateur pour opérer sur les services.")
            return
        self.log_write("Désactivation manuelle des services Adobe + tâches planifiées…")
        aggressive_apply(self.log_write)

    def on_services_enable(self):
        if not is_admin():
            messagebox.showwarning("Droits requis", "Relance en Administrateur pour opérer sur les services.")
            return
        self.log_write("Réactivation manuelle des services Adobe + tâches planifiées…")
        aggressive_revert(self.log_write)

if __name__ == "__main__":
    app = App()
    app.mainloop()
