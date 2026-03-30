#!/usr/bin/env python3
"""
PACT Dashboard Server — serves the visualizer + event feed + task ratings.

Runs on localhost:7246 (one above TileHttpServer's 7245).
Endpoints:
  GET  /           — serves pact-dashboard.html
  GET  /events     — returns new events since ?after=N as JSON array
  GET  /ratings    — returns all task ratings as JSON array
  POST /rate       — submit a task rating (writes to ratings JSONL + regenerates scorecard)
  GET  /scorecard  — returns the current scorecard markdown

Start:  python .claude/hooks/pact-server.py &
Stop:   kill $(cat .claude/pact-server.pid)
"""

import http.server
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone

PORT = 7246
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CLAUDE_DIR = os.path.dirname(SCRIPT_DIR)
HOME_DIR = os.path.expanduser('~')

# Central user-level files (multi-project)
PACT_DIR = os.path.join(HOME_DIR, '.claude')
EVENTS_FILE = os.path.join(PACT_DIR, 'pact-events.jsonl')
CONFIG_FILE = os.path.join(PACT_DIR, 'pact-config.json')
RATINGS_FILE = os.path.join(CLAUDE_DIR, 'bugs', '_FEEDBACK.jsonl')
LEGACY_RATINGS_FILE = os.path.join(PACT_DIR, 'pact-ratings.jsonl')  # pre-0.7.0 location
SCORECARD_FILE = os.path.join(PACT_DIR, 'pact-scorecard.md')
# Fallback to project-local if central doesn't exist
LOCAL_EVENTS_FILE = os.path.join(CLAUDE_DIR, 'pact-events.jsonl')
DASHBOARD_FILE = os.path.join(CLAUDE_DIR, 'pact-dashboard.html')
PID_FILE = os.path.join(CLAUDE_DIR, 'pact-server.pid')

# Cache events in memory, reload from file periodically
events_cache = []
events_lock = threading.Lock()


def load_events():
    """Load all events from central JSONL (with local fallback)."""
    global events_cache
    source = EVENTS_FILE if os.path.exists(EVENTS_FILE) else LOCAL_EVENTS_FILE
    if not os.path.exists(source):
        return
    try:
        with open(source, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        new_events = []
        for line in lines:
            line = line.strip()
            if line:
                try:
                    new_events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        with events_lock:
            events_cache = new_events
    except Exception:
        pass


def load_ratings():
    """Load all ratings from the feedback file (checks new + legacy locations)."""
    source = RATINGS_FILE if os.path.exists(RATINGS_FILE) else LEGACY_RATINGS_FILE
    if not os.path.exists(source):
        return []
    ratings = []
    try:
        with open(source, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        ratings.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except Exception:
        pass
    return ratings


def regenerate_scorecard(ratings):
    """Regenerate the scorecard markdown that Claude reads at session start."""
    if not ratings:
        return

    recent = ratings[-10:]  # last 10
    scores = [r['score'] for r in recent if 'score' in r]
    avg = sum(scores) / len(scores) if scores else 0

    # Streak of 4+
    streak = 0
    for r in reversed(recent):
        if r.get('score', 0) >= 4:
            streak += 1
        else:
            break

    # Category failure frequency
    tag_counts = {}
    tag_examples = {}
    for r in recent:
        for tag in r.get('tags', []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
            if r.get('wrong'):
                tag_examples[tag] = r['wrong']

    # Category averages
    tag_scores = {}
    tag_score_counts = {}
    for r in recent:
        for tag in r.get('tags', []):
            tag_scores[tag] = tag_scores.get(tag, 0) + r.get('score', 3)
            tag_score_counts[tag] = tag_score_counts.get(tag, 0) + 1

    # What went right (from high-scoring tasks)
    went_right = [r.get('right', '') for r in recent if r.get('score', 0) >= 4 and r.get('right')]

    # Build scorecard
    score_words = {1: 'Failed', 2: 'Poor', 3: 'Adequate', 4: 'Good', 5: 'Nailed It'}
    lines = [
        '# PACT Task Scorecard',
        f'# Last updated: {datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}',
        f'# Read this at session start. This is direct user feedback on your work.',
        '',
        f'## Rolling Average: {avg:.1f}/5 (last {len(recent)} tasks)',
    ]

    if streak >= 2:
        lines.append(f'## Current Streak: {streak} consecutive 4+ ratings')
    lines.append('')

    # Weakest areas
    if tag_counts:
        lines.append('## Areas Needing Attention')
        sorted_tags = sorted(tag_counts.items(), key=lambda x: -x[1])
        for tag, count in sorted_tags:
            tag_avg = tag_scores.get(tag, 0) / tag_score_counts.get(tag, 1)
            example = f' — "{tag_examples[tag]}"' if tag in tag_examples else ''
            lines.append(f'- {tag}: {count}x in last {len(recent)} tasks (avg {tag_avg:.1f}/5){example}')
        lines.append('')

    # Recent ratings
    lines.append('## Recent Ratings')
    for i, r in enumerate(reversed(recent)):
        score = r.get('score', 3)
        word = score_words.get(score, '?')
        task = r.get('task', 'unnamed')
        tags = ', '.join(r.get('tags', []))
        wrong = r.get('wrong', '')
        right = r.get('right', '')
        line = f'{i+1}. [{score}/5 {word}] "{task}"'
        if tags:
            line += f' — Tags: {tags}'
        if wrong:
            line += f' — Wrong: "{wrong}"'
        if right:
            line += f' — Right: "{right}"'
        lines.append(line)
    lines.append('')

    # What's working
    if went_right:
        lines.append('## What\'s Working (keep doing this)')
        for wr in went_right[-5:]:
            lines.append(f'- "{wr}"')
        lines.append('')

    # Action items from low scores
    low_tasks = [r for r in recent if r.get('score', 5) <= 2]
    if low_tasks:
        lines.append('## Action Items From Low Scores')
        for r in low_tasks[-5:]:
            if r.get('wrong'):
                lines.append(f'- [{r.get("task","?")}] {r["wrong"]}')
        lines.append('')

    lines.append('# This scorecard is auto-generated by PACT. Do not edit manually.')

    try:
        with open(SCORECARD_FILE, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
    except Exception:
        pass


def event_watcher():
    """Background thread that reloads events every second."""
    while True:
        load_events()
        time.sleep(1)


class PACTHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Silence request logs

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self._serve_dashboard()
        elif self.path.startswith('/events'):
            self._serve_events()
        elif self.path == '/ratings':
            self._serve_ratings()
        elif self.path.startswith('/recall'):
            self._serve_recall()
        elif self.path == '/scorecard':
            self._serve_scorecard()
        elif self.path == '/pact-config':
            self._serve_config()
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/rate':
            self._handle_rate()
        elif self.path == '/pact-config':
            self._handle_config_update()
        else:
            self.send_error(404)

    def _serve_dashboard(self):
        try:
            with open(DASHBOARD_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(content.encode('utf-8'))
        except FileNotFoundError:
            self.send_error(404, 'Dashboard file not found')

    def _serve_events(self):
        after = 0
        if '?' in self.path:
            params = self.path.split('?')[1]
            for param in params.split('&'):
                if param.startswith('after='):
                    try:
                        after = int(param.split('=')[1])
                    except ValueError:
                        pass

        with events_lock:
            new_events = events_cache[after:]

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(new_events).encode('utf-8'))

    def _serve_ratings(self):
        ratings = load_ratings()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(json.dumps(ratings).encode('utf-8'))

    def _serve_scorecard(self):
        try:
            with open(SCORECARD_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(content.encode('utf-8'))
        except FileNotFoundError:
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'No ratings yet.')

    def _serve_recall(self):
        """Vector search across PACT knowledge. GET /recall?q=text&top=5&type=bug"""
        params = {}
        if '?' in self.path:
            for p in self.path.split('?')[1].split('&'):
                if '=' in p:
                    k, v = p.split('=', 1)
                    params[k] = v

        query_text = params.get('q', '').replace('+', ' ').replace('%20', ' ')
        if not query_text:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"error":"missing q parameter"}')
            return

        try:
            import subprocess
            memory_script = os.path.join(SCRIPT_DIR, '..', 'memory', 'pact-memory.py')
            if not os.path.exists(memory_script):
                memory_script = os.path.join(SCRIPT_DIR, 'pact-memory.py')

            cmd = [sys.executable, memory_script, 'query', query_text,
                   '--top', params.get('top', '5'), '--json']
            if params.get('type'):
                cmd.extend(['--type', params['type']])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(result.stdout.encode('utf-8'))
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))

    def _serve_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            else:
                config = {'dashboard': 'ask'}
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(config).encode('utf-8'))
        except Exception:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"dashboard":"ask"}')

    def _handle_config_update(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            updates = json.loads(body)
            # Read existing config
            config = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            config.update(updates)
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'ok': True}).encode('utf-8'))
        except Exception as e:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))

    def _handle_rate(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            rating = json.loads(body)

            # Add server timestamp
            rating['rated_at'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

            # Append to feedback JSONL (ensure directory exists)
            os.makedirs(os.path.dirname(RATINGS_FILE), exist_ok=True)
            with open(RATINGS_FILE, 'a', encoding='utf-8') as f:
                f.write(json.dumps(rating) + '\n')

            # Store in vector index (non-blocking, best-effort)
            try:
                memory_script = os.path.join(SCRIPT_DIR, '..', 'memory', 'pact-memory.py')
                if not os.path.exists(memory_script):
                    memory_script = os.path.join(SCRIPT_DIR, 'pact-memory.py')
                if os.path.exists(memory_script):
                    import subprocess
                    task = rating.get('task', '')
                    wrong = rating.get('wrong', '')
                    right = rating.get('right', '')
                    tags = ' '.join(rating.get('tags', []))
                    text = f"Task: {task}. Score: {rating.get('score',0)}/5. Wrong: {wrong}. Right: {right}. Tags: {tags}"
                    project = rating.get('project', '')
                    doc_id = f"feedback:{project}:{rating['rated_at']}"
                    subprocess.Popen(
                        [sys.executable, memory_script, 'store',
                         '--type', 'feedback', '--id', doc_id, '--text', text,
                         '--project', project],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
            except Exception:
                pass

            # Also emit as a PACT event so the dashboard + current session see it
            event = {
                'ts': rating['rated_at'],
                'type': 'task_rating',
                'sid': rating.get('sid', 'unknown'),
                'project': rating.get('project', ''),
                'score': rating.get('score', 0),
                'task': rating.get('task', ''),
                'tags': rating.get('tags', []),
            }
            event_file = EVENTS_FILE if os.path.exists(EVENTS_FILE) else LOCAL_EVENTS_FILE
            with open(event_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(event) + '\n')

            # Regenerate scorecard
            ratings = load_ratings()
            regenerate_scorecard(ratings)

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'ok': True, 'total_ratings': len(ratings)}).encode('utf-8'))

        except Exception as e:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))


def kill_existing():
    """Kill previous PACT server via PID file only. Safe — never kills by port scan."""
    import signal
    if os.path.exists(PID_FILE):
        try:
            old_pid = int(open(PID_FILE).read().strip())
            if old_pid != os.getpid():
                os.kill(old_pid, signal.SIGTERM)
                time.sleep(0.3)
        except (ValueError, OSError):
            pass


def main():
    # Kill any existing server first
    kill_existing()

    # Write PID file
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))

    # Ensure PACT dir exists
    os.makedirs(PACT_DIR, exist_ok=True)

    # Start event watcher thread
    watcher = threading.Thread(target=event_watcher, daemon=True)
    watcher.start()

    # Initial load
    load_events()

    # Generate initial scorecard if ratings exist
    ratings = load_ratings()
    if ratings:
        regenerate_scorecard(ratings)

    # Start server
    server = http.server.HTTPServer(('127.0.0.1', PORT), PACTHandler)
    print(f'PACT Dashboard: http://127.0.0.1:{PORT}')

    # Auto-open in VS Code Simple Browser
    try:
        import subprocess
        subprocess.Popen(
            ['code', '--reuse-window', f'--open-url=http://127.0.0.1:{PORT}'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)


if __name__ == '__main__':
    main()
