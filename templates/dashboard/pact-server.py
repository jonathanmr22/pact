#!/usr/bin/env python3
"""Tiny dashboard server.

Acts as a static-file server (like `python -m http.server`) for the
dashboard files PLUS exposes a single POST /open endpoint that runs
Windows `start "" <path>` to actually open a file in its default app.

The dashboard's PACT references panel POSTs here when you click a ref,
so links actually open instead of relying on Chrome's silent vscode://
protocol handling.

Usage:
    python serve.py [port]
Default port: 8800. Bind: 127.0.0.1.

Safety: the /open endpoint accepts ANY path and runs `start` on it.
That's fine because this server only listens on 127.0.0.1 and is meant
for the user's own dev machine. Don't expose to a network.
"""
from __future__ import annotations

import http.server
import socketserver
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse


SERVE_ROOT = Path(__file__).resolve().parent
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8800
HOST = "127.0.0.1"


class DashHandler(http.server.SimpleHTTPRequestHandler):
    # Force the file-server to serve from this script's directory regardless
    # of the cwd at launch time.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SERVE_ROOT), **kwargs)

    # Multi-project support: when the dashboard sends ?root=<absolute path>,
    # we re-root file lookups to that project's plans/dashboard/ for YAML
    # data fetches. The HTML/CSS/JS shell still comes from THIS serve.py's
    # SERVE_ROOT.
    SAFE_DATA_PATHS = ("_index.yaml", "trees/", "plans/dashboard/")

    def _resolve_project_root(self):
        """Return Path of the requested project root, or None for local."""
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        root_arg = qs.get("root", [None])[0]
        if not root_arg:
            return None
        try:
            p = Path(root_arg).resolve()
            # Sanity: must exist and be a directory
            if not p.exists() or not p.is_dir():
                return None
            return p
        except Exception:
            return None

    def _serve_yaml_from(self, abs_path: Path):
        if not abs_path.exists() or not abs_path.is_file():
            self.send_error(404, f"Not found: {abs_path}")
            return
        data = abs_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/yaml; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # Where the dashboard scaffold lives within a project root. Most projects
    # use plans/dashboard/ — that's the convention. PACT itself uses
    # templates/dashboard/ (the scaffold IS the deliverable). We probe in
    # priority order; first one with an _index.yaml wins. New layouts can
    # be added here without touching call sites.
    DASHBOARD_LAYOUTS = ("plans/dashboard", "templates/dashboard")

    def _resolve_dashboard_dir(self, project_root: Path) -> Path:
        """Pick the project's dashboard scaffold directory. Falls back to
        the first layout in DASHBOARD_LAYOUTS so a 404 path is still
        deterministic when no layout matches."""
        for layout in self.DASHBOARD_LAYOUTS:
            candidate = project_root / layout
            if (candidate / "_index.yaml").is_file():
                return candidate
        return project_root / self.DASHBOARD_LAYOUTS[0]

    def do_GET(self):
        parsed = urlparse(self.path)
        path_only = parsed.path
        project_root = self._resolve_project_root()

        # /dashboard-version → returns the SHELL's VERSION (PACT itself, not the
        # project being viewed). Powers the in-dashboard update notifier so it
        # can compare against the latest GitHub Release.
        if path_only == "/dashboard-version":
            return self._handle_dashboard_version()

        # When a project root is specified AND the request is for a YAML/dashboard
        # data file, re-root the read to the project's dashboard scaffold.
        # Strip query string from path_only for filesystem lookup.
        if project_root and (path_only.endswith(".yaml") or path_only.endswith(".yml")):
            rel = path_only.lstrip("/")
            target = self._resolve_dashboard_dir(project_root) / rel
            return self._serve_yaml_from(target)

        return super().do_GET()

    def _handle_dashboard_version(self):
        """Read the VERSION file colocated with the PACT install (the shell's
        own version, NOT the project being displayed via ?root=). The file
        sits two levels up from SERVE_ROOT (templates/dashboard/) → PACT root.
        Returns {version: "X.Y.Z"} or {version: null} if not found. Never 500s
        — the update notifier silently no-ops on missing version."""
        import json
        version_file = SERVE_ROOT.parent.parent / "VERSION"
        version = None
        if version_file.is_file():
            try:
                version = version_file.read_text(encoding="utf-8").strip() or None
            except Exception:
                version = None
        body = json.dumps({"version": version}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/open":
            self._handle_open()
        elif parsed.path == "/pythons":
            self._handle_pythons_list()
        elif parsed.path == "/kill":
            self._handle_kill()
        elif parsed.path == "/note":
            self._handle_note()
        elif parsed.path == "/notes":
            self._handle_notes_list()
        elif parsed.path == "/autoopen":
            self._handle_autoopen()
        elif parsed.path == "/yaml-edit":
            self._handle_yaml_edit()
        else:
            self.send_error(404, f"Unknown POST endpoint: {parsed.path}")

    # ── User notes on tasks ────────────────────────────────────────────────
    # Notes are appended to <project_root>/.claude/memory/dashboard_user_notes.yaml
    # PLUS a sentinel file <project_root>/.claude/memory/dashboard_notes_unread
    # is touched so the SessionStart hook can announce "you have N new notes
    # from the user since last session" without disrupting active work.
    def _project_root_for_notes(self):
        # Honor ?root= just like other endpoints; default to SERVE_ROOT.parent.parent
        proj = self._resolve_project_root()
        return proj if proj else SERVE_ROOT.parent.parent

    def _notes_file(self):
        d = self._project_root_for_notes() / ".claude" / "memory"
        d.mkdir(parents=True, exist_ok=True)
        return d / "dashboard_user_notes.yaml"

    def _notes_unread_sentinel(self):
        return self._project_root_for_notes() / ".claude" / "memory" / "dashboard_notes_unread"

    def _handle_note(self):
        import json, datetime
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
        except Exception as e:
            self._json({"ok": False, "error": "invalid json: " + str(e)}, status=400)
            return
        tree = payload.get("tree", "").strip()
        chain = payload.get("chain", [])  # list of node names from initiative down
        task_name = payload.get("task", "").strip()
        # level: "task" (default) or "initiative". For initiative-level notes,
        # the editor doesn't bind to a specific task — it lives on the modal
        # description area as "Your notes" alongside the YAML's `note:` field.
        level = (payload.get("level") or "task").strip()
        note = payload.get("note", "").strip()
        if not (tree and note):
            self._json({"ok": False, "error": "missing tree/note"}, status=400)
            return
        if level == "task" and not task_name:
            self._json({"ok": False, "error": "task-level note requires task name"}, status=400)
            return
        # For initiative notes, set task_name to the chain's last element so
        # downstream tooling has a stable identifier; mark level explicitly.
        if level == "initiative" and not task_name:
            task_name = chain[-1] if chain else "<initiative>"
        nf = self._notes_file()
        ts = datetime.datetime.now().isoformat(timespec="seconds")
        # Append-only YAML. Format: a top-level `notes:` list of records.
        # Read existing, append, write.
        existing_text = nf.read_text(encoding="utf-8") if nf.exists() else ""
        # Build a new YAML record block — keep it readable, don't roundtrip
        # via PyYAML (preserves any user hand-edits).
        if not existing_text.strip():
            existing_text = (
                "# Dashboard user notes — added by clicking a task name in the\n"
                "# PACT Dashboard. Claude reads this file at session start.\n"
                "# Format: append-only list of {when, tree, chain, task, note, status}.\n"
                "# Status starts as 'unread'; flip to 'read' once Claude has\n"
                "# acknowledged it.\n"
                "notes:\n"
            )
        new_block = (
            f"  - when: {ts}\n"
            f"    tree: {json.dumps(tree)}\n"
            f"    chain: {json.dumps(chain)}\n"
            f"    task: {json.dumps(task_name)}\n"
            f"    level: {json.dumps(level)}\n"
            f"    note: {json.dumps(note)}\n"
            f"    status: unread\n"
        )
        nf.write_text(existing_text + new_block, encoding="utf-8")
        # Touch the sentinel so the next session-start hook surfaces it
        sentinel = self._notes_unread_sentinel()
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text(ts, encoding="utf-8")
        self._json({"ok": True, "wrote_to": str(nf), "when": ts})

    def _handle_autoopen(self):
        """Read or write the dashboard auto-open flag.
        POST {action: 'get'} → {enabled: bool}
        POST {action: 'set', enabled: bool} → writes/removes the disable flag
        File: <project_root>/.claude/memory/dashboard_autoopen_disabled
        Presence of file = OFF; absence = ON (default).
        """
        import json
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            payload = json.loads(body) if body.strip() else {}
        except Exception:
            payload = {}
        action = payload.get("action", "get")
        flag_path = self._project_root_for_notes() / ".claude" / "memory" / "dashboard_autoopen_disabled"
        if action == "set":
            enabled = bool(payload.get("enabled", True))
            flag_path.parent.mkdir(parents=True, exist_ok=True)
            if enabled:
                if flag_path.exists(): flag_path.unlink()
            else:
                flag_path.write_text("disabled\n", encoding="utf-8")
            self._json({"ok": True, "enabled": enabled})
        else:
            self._json({"ok": True, "enabled": not flag_path.exists()})

    def _handle_yaml_edit(self):
        """Apply a scoped field edit to a tree YAML file.
        POST {
          stream_path: 'trees/governance/streams/dashboard_build.yaml',
          chain: ['initiative name', 'feature name', ...],   # path from root
          task_name: 'Some task' | null,                      # null = edit the chain's leaf node, not a task
          field: 'status' | 'name' | 'note' | 'last_touched',
          value: <new value>
        }
        Whitelist of editable fields: status, name, note, last_touched.
        Auto-bumps the parent initiative's `last_touched` to today's date.
        Writes via PyYAML (round-trip — comments NOT preserved).
        """
        import json, datetime, yaml as pyyaml
        ALLOWED_FIELDS = {'status', 'name', 'note', 'last_touched'}
        ALLOWED_TASK_STATUSES = {'todo', 'in_flight', 'done'}
        ALLOWED_NODE_STATUSES = {'not_started', 'in_flight', 'blocked_user', 'blocked_external', 'done'}

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
        except Exception as e:
            self._json({"ok": False, "error": "invalid json: " + str(e)}, status=400)
            return
        stream_path = (payload.get("stream_path") or "").strip()
        chain = payload.get("chain") or []
        task_name = payload.get("task_name")  # may be None
        field = (payload.get("field") or "").strip()
        new_value = payload.get("value")

        if field not in ALLOWED_FIELDS:
            self._json({"ok": False, "error": f"field '{field}' not editable; allowed: {sorted(ALLOWED_FIELDS)}"}, status=400)
            return
        if field == 'status':
            valid = ALLOWED_TASK_STATUSES if task_name else ALLOWED_NODE_STATUSES
            if new_value not in valid:
                self._json({"ok": False, "error": f"status '{new_value}' invalid; allowed: {sorted(valid)}"}, status=400)
                return

        # Resolve the stream file path (honor ?root= for cross-project).
        # Probe both standard layouts so PACT-style templates/dashboard/
        # projects work too.
        proj_root = self._resolve_project_root() or SERVE_ROOT.parent.parent
        target_file = self._resolve_dashboard_dir(proj_root) / stream_path
        if not target_file.exists():
            self._json({"ok": False, "error": f"file not found: {target_file}"}, status=404)
            return

        try:
            doc = pyyaml.safe_load(target_file.read_text(encoding="utf-8"))
        except Exception as e:
            self._json({"ok": False, "error": "yaml parse failed: " + str(e)}, status=500)
            return

        # Walk the chain to the target node
        node = doc.get('node') if isinstance(doc, dict) else None
        if node is None:
            self._json({"ok": False, "error": "stream missing top-level `node:` key"}, status=400)
            return
        # First chain element should match the initiative's name
        if chain and node.get('name') != chain[0]:
            self._json({"ok": False, "error": f"chain root '{chain[0]}' doesn't match initiative '{node.get('name')}'"}, status=400)
            return
        # Walk children for the rest of the chain
        for child_name in chain[1:]:
            kids = node.get('children') or []
            found = next((c for c in kids if c.get('name') == child_name), None)
            if not found:
                self._json({"ok": False, "error": f"chain segment '{child_name}' not found"}, status=404)
                return
            node = found

        # If task_name is set, find the task within the leaf node's `tasks:` list
        target = node
        if task_name:
            tasks = node.get('tasks') or []
            target = next((t for t in tasks if (t.get('name') == task_name)), None)
            if target is None:
                self._json({"ok": False, "error": f"task '{task_name}' not found in node"}, status=404)
                return

        # Apply the edit
        old_value = target.get(field)
        target[field] = new_value
        # Auto-bump the parent INITIATIVE's last_touched on any task/node status change
        today = datetime.date.today().isoformat()
        if field == 'status':
            init_node = doc.get('node')
            init_node['last_touched'] = today

        # Atomic write (write to .tmp, then rename)
        tmp_path = target_file.with_suffix(target_file.suffix + '.tmp')
        try:
            text = pyyaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=120)
            tmp_path.write_text(text, encoding='utf-8')
            tmp_path.replace(target_file)
        except Exception as e:
            self._json({"ok": False, "error": "write failed: " + str(e)}, status=500)
            return
        self._json({
            "ok": True, "field": field,
            "old_value": old_value, "new_value": new_value,
            "auto_bumped_last_touched": today if field == 'status' else None,
        })

    def _handle_notes_list(self):
        # Returns the parsed notes file (used by the dashboard to show counts)
        nf = self._notes_file()
        if not nf.exists():
            self._json({"ok": True, "notes": []})
            return
        try:
            import yaml
            data = yaml.safe_load(nf.read_text(encoding="utf-8")) or {}
            self._json({"ok": True, "notes": data.get("notes", [])})
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, status=500)

    def _handle_pythons_list(self):
        """Returns active python processes with PID, command, listening ports."""
        rows = []
        try:
            tasks = subprocess.check_output(
                ["wmic", "process", "where", "name='python.exe'",
                 "get", "ProcessId,CommandLine", "/format:csv"],
                text=True, timeout=8, stderr=subprocess.DEVNULL,
            )
            for line in tasks.splitlines():
                parts = line.strip().split(",")
                if len(parts) < 3 or parts[0] == "Node": continue
                cmdline = ",".join(parts[1:-1]).strip('"')
                pid_str = parts[-1].strip()
                if not pid_str.isdigit(): continue
                rows.append({"pid": int(pid_str), "cmd": cmdline})
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, status=500)
            return
        # Annotate with listening port if any
        try:
            ns = subprocess.check_output(["netstat", "-ano"], text=True, timeout=5)
            pid_to_ports = {}
            for line in ns.splitlines():
                if "LISTENING" not in line: continue
                parts = line.split()
                if len(parts) < 5: continue
                addr = parts[1]
                pid = parts[-1]
                if not pid.isdigit(): continue
                port = addr.rsplit(":", 1)[-1]
                pid_to_ports.setdefault(int(pid), set()).add(port)
            for r in rows:
                r["ports"] = sorted(pid_to_ports.get(r["pid"], []))
        except Exception:
            pass
        self._json({"ok": True, "processes": rows})

    def _handle_kill(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        pid = ""
        if body.lstrip().startswith("pid="):
            pid = parse_qs(body).get("pid", [""])[0]
        else:
            pid = body.strip()
        if not pid.isdigit():
            self._json({"ok": False, "error": "missing or invalid pid"}, status=400)
            return
        try:
            subprocess.run(["taskkill", "/F", "/PID", pid],
                           capture_output=True, timeout=5)
            self._json({"ok": True, "killed": int(pid)})
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, status=500)

    def _handle_open(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        # Accept either form-encoded (path=...) or raw text body
        path = ""
        if "=" in body and body.lstrip().startswith("path="):
            path = parse_qs(body).get("path", [""])[0]
        else:
            path = body.strip()
        if not path:
            self._json({"ok": False, "error": "missing path"}, status=400)
            return
        # For code-like files (.md, .yaml, .py, .ts, .dart, .sh, .json, .html, .css),
        # prefer VS Code via the `code` CLI — most users don't have a default
        # Windows handler registered for .md, which causes silent failure with
        # plain `start`. Fall back to `start` for everything else.
        code_exts = ('.md', '.yaml', '.yml', '.py', '.ts', '.tsx', '.js', '.jsx',
                     '.dart', '.sh', '.bat', '.ps1', '.json', '.html', '.css',
                     '.txt', '.toml', '.ini', '.env', '.sql')
        is_code_file = path.lower().endswith(code_exts)
        try:
            if sys.platform.startswith("win"):
                if is_code_file:
                    # `code` is a .cmd shim on Windows — invoke via cmd
                    try:
                        subprocess.Popen(["cmd", "/c", "code", path], shell=False)
                    except FileNotFoundError:
                        subprocess.Popen(["cmd", "/c", "start", "", path], shell=False)
                else:
                    subprocess.Popen(["cmd", "/c", "start", "", path], shell=False)
            elif sys.platform == "darwin":
                if is_code_file:
                    try: subprocess.Popen(["code", path])
                    except FileNotFoundError: subprocess.Popen(["open", path])
                else:
                    subprocess.Popen(["open", path])
            else:
                if is_code_file:
                    try: subprocess.Popen(["code", path])
                    except FileNotFoundError: subprocess.Popen(["xdg-open", path])
                else:
                    subprocess.Popen(["xdg-open", path])
            self._json({"ok": True, "opened": path, "via": "code" if is_code_file else "start"})
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, status=500)

    def _json(self, payload, status: int = 200):
        import json
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # CORS — dashboard is served from same origin (localhost:8800) so
        # no preflight needed, but be explicit anyway.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        # No-cache so dashboard.html edits show up on plain refresh too.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        super().end_headers()

    def log_message(self, fmt, *args):
        # Quieter logs — just the request line, no timestamp.
        sys.stderr.write("[serve] " + (fmt % args) + "\n")


def kill_existing_listeners(port: int):
    """Find any process currently listening on `port` and terminate it.

    Windows allows SO_REUSEADDR-style port sharing — multiple servers can
    bind the same port and the OS picks one randomly per request. That
    caused our dashboard to alternate between an old http.server and the
    new serve.py. Permanent fix: at startup, scan listeners with netstat
    + `taskkill /F /PID`, THEN bind.
    """
    if not sys.platform.startswith("win"):
        return                          # Only relevant on Windows
    try:
        out = subprocess.check_output(["netstat", "-ano"], text=True, timeout=5)
    except Exception:
        return
    pids = set()
    needle = f":{port} "
    for line in out.splitlines():
        if needle in line and "LISTENING" in line:
            parts = line.split()
            if parts and parts[-1].isdigit():
                pids.add(int(parts[-1]))
    my_pid = subprocess.os.getpid() if hasattr(subprocess, "os") else None
    for pid in pids:
        if pid == my_pid:
            continue
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, timeout=5)
            sys.stderr.write(f"[serve] killed stale listener PID {pid} on port {port}\n")
        except Exception as e:
            sys.stderr.write(f"[serve] could not kill PID {pid}: {e}\n")


def main():
    kill_existing_listeners(PORT)
    # Don't allow_reuse — we want a hard "already in use" failure if our
    # cleanup missed something, instead of silently sharing the port.
    socketserver.TCPServer.allow_reuse_address = False
    with socketserver.TCPServer((HOST, PORT), DashHandler) as httpd:
        sys.stderr.write(f"[serve] Dashboard server on http://{HOST}:{PORT}/dashboard.html\n")
        sys.stderr.write(f"[serve] Static root: {SERVE_ROOT}\n")
        sys.stderr.write(f"[serve] POST /open accepts a path body; runs `start \"\" <path>` to open it.\n")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
