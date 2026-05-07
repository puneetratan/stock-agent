#!/usr/bin/env python3
"""
Pipeline Dashboard Server.

    cd stock_intelligence
    .venv/bin/python pipeline_server.py

Then open: http://localhost:8765
"""

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "current_run.json")
SCHED_LOG  = os.path.join(BASE_DIR, "scheduler_error.log")
HTML_FILE  = os.path.join(BASE_DIR, "pipeline_dashboard.html")

# (key, log_marker, display_name, step_label)
STEPS = [
    ("step1",  "[STEP 1] ",   "World Intelligence Scan",       "1"),
    ("step15", "[STEP 1.5]",  "Politician Trade Intelligence",  "1.5"),
    ("step2",  "[STEP 2] ",   "Sentiment Analysis",            "2"),
    ("step2b", "[STEP 2b]",   "Narrative Cycle Analysis",      "2b"),
    ("step3",  "[STEP 3]",    "Causal Reasoning",              "3"),
    ("step4",  "[STEP 4]",    "Stock Screener",                "4"),
    ("step5",  "[STEP 5]",    "Deep Analysis",                 "5"),
    ("step6",  "[STEP 6]",    "Ranking & Synthesis",           "6"),
    ("step7",  "[STEP 7]",    "Delivering Report",             "7"),
]


def _alive(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (ProcessLookupError, OSError, ValueError):
        return False


def parse_log(log_file, stage=None):
    last_step_idx   = -1
    tickers_done    = []
    current_ticker  = None
    themes_count    = candidates_count = signals_count = total_tickers = None
    complete        = False

    # finalize runs skip steps 1-5; pre-mark them
    if stage == "finalize":
        last_step_idx = 5  # index of step5

    try:
        with open(log_file) as f:
            for line in f:
                for i, (key, marker, *_) in enumerate(STEPS):
                    if marker in line:
                        if i > last_step_idx:
                            last_step_idx = i
                        break

                m = re.search(r'\[(\d+)/(\d+)\] Analysing (\S+?)\.\.\.', line)
                if m:
                    total_tickers = int(m.group(2))
                    ticker = m.group(3)
                    if current_ticker and current_ticker != ticker:
                        tickers_done.append({"ticker": current_ticker, "state": "done"})
                    current_ticker = ticker

                m = re.search(r'TIMEOUT.*?skipping (\S+)', line)
                if m and current_ticker == m.group(1):
                    tickers_done.append({"ticker": current_ticker, "state": "timeout"})
                    current_ticker = None

                m = re.search(r'Error analysing (\S+?):', line)
                if m and current_ticker == m.group(1):
                    tickers_done.append({"ticker": current_ticker, "state": "error"})
                    current_ticker = None

                m = re.search(r'→ (\d+) themes detected', line)
                if m:
                    themes_count = int(m.group(1))
                m = re.search(r'→ (\d+) candidates passed screening', line)
                if m:
                    candidates_count = int(m.group(1))
                m = re.search(r'→ (\d+) signals generated', line)
                if m:
                    signals_count = int(m.group(1))
                m = re.search(r'\[STEP 5\] Deep Analysis \((\d+)', line)
                if m:
                    total_tickers = int(m.group(1))

                if 'Run complete' in line or 'Done — Run ID:' in line:
                    complete = True
                    if current_ticker:
                        tickers_done.append({"ticker": current_ticker, "state": "done"})
                        current_ticker = None

    except (FileNotFoundError, IOError):
        pass

    return {
        "last_step_idx":    last_step_idx,
        "tickers_done":     tickers_done,
        "current_ticker":   current_ticker,
        "themes_count":     themes_count,
        "candidates_count": candidates_count,
        "signals_count":    signals_count,
        "total_tickers":    total_tickers,
        "complete":         complete,
    }


def build_step_states(parsed, process_alive):
    last_idx = parsed["last_step_idx"]
    complete = parsed["complete"]
    states = {}
    for i, (key, *_) in enumerate(STEPS):
        if complete:
            states[key] = "done"
        elif i < last_idx:
            states[key] = "done"
        elif i == last_idx and last_idx >= 0:
            states[key] = "running" if process_alive else "error"
        else:
            states[key] = "pending"
    return states


def get_pipeline():
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"active": False}

    pid      = state.get("pid")
    log_file = state.get("log_file", "")
    started  = state.get("started_at", "")
    stage    = state.get("stage")
    alive    = _alive(pid)
    parsed   = parse_log(log_file, stage)
    states   = build_step_states(parsed, alive)

    elapsed = None
    if started:
        try:
            t0 = datetime.fromisoformat(started)
            elapsed = int((datetime.now(timezone.utc) - t0).total_seconds())
        except Exception:
            pass

    return {
        "active":           True,
        "run_id":           state.get("run_id", "")[:8],
        "pid":              pid,
        "log_file":         os.path.basename(log_file),
        "started_at":       started,
        "elapsed_seconds":  elapsed,
        "process_alive":    alive,
        "complete":         parsed["complete"],
        "steps":            states,
        "current_ticker":   parsed["current_ticker"],
        "tickers_done":     parsed["tickers_done"],
        "total_tickers":    parsed["total_tickers"],
        "themes_count":     parsed["themes_count"],
        "candidates_count": parsed["candidates_count"],
        "signals_count":    parsed["signals_count"],
    }


def get_scheduler():
    try:
        r = subprocess.run(["pgrep", "-f", "run_schedule.py"],
                           capture_output=True, text=True)
        pids = [p for p in r.stdout.strip().split("\n") if p]
        running = bool(pids)
        pid = pids[0] if pids else None
    except Exception:
        running, pid = False, None

    recent = []
    try:
        with open(SCHED_LOG) as f:
            lines = f.readlines()
        recent = [l.strip() for l in lines[-8:] if l.strip()]
    except Exception:
        pass

    return {"running": running, "pid": pid, "recent_logs": recent}


def get_status():
    return {
        "scheduler":  get_scheduler(),
        "pipeline":   get_pipeline(),
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "steps_meta": [
            {"key": key, "label": label, "name": name}
            for key, _, name, label in STEPS
        ],
    }


def get_step_logs(step_key: str, max_lines: int = 150) -> list[str]:
    """Return log lines belonging to a specific pipeline step."""
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return ["[no active run state found]"]

    log_file = state.get("log_file", "")
    if not log_file:
        return ["[no log file in state]"]

    # Collect the marker for this step and all subsequent step markers
    step_marker = None
    next_markers = []
    found = False

    for key, marker, *_ in STEPS:
        if key == step_key:
            step_marker = marker
            found = True
        elif found:
            next_markers.append(marker)

    if step_marker is None:
        return [f"[unknown step: {step_key}]"]

    lines = []
    in_step = False

    try:
        with open(log_file) as f:
            for line in f:
                line = line.rstrip("\n")
                if step_marker in line:
                    in_step = True
                elif in_step and next_markers and any(m in line for m in next_markers):
                    break
                if in_step and line.strip():
                    lines.append(line)
    except FileNotFoundError:
        return [f"[log file not found: {os.path.basename(log_file)}]"]
    except IOError as e:
        return [f"[error reading log: {e}]"]

    if not lines:
        return ["[no log lines for this step yet — check back when the step is running]"]

    return lines[-max_lines:]


VENV_PYTHON  = os.path.join(BASE_DIR, ".venv", "bin", "python")
AGENT_SCRIPT = os.path.join(BASE_DIR, "run_agent.py")


def trigger_pipeline():
    """Spawn run_agent.py in the background; return (ok, message)."""
    # Refuse if a run is already active
    pipeline = get_pipeline()
    if pipeline.get("active") and pipeline.get("process_alive") and not pipeline.get("complete"):
        return False, "A pipeline run is already in progress."

    ts       = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(BASE_DIR, f"run_{ts}_manual.log")
    try:
        with open(log_file, "w") as out:
            proc = subprocess.Popen(
                [VENV_PYTHON, AGENT_SCRIPT, f"--log-file={log_file}"],
                stdout=out, stderr=out,
                cwd=BASE_DIR,
                start_new_session=True,
            )
        return True, f"Pipeline started — PID {proc.pid}, log: {os.path.basename(log_file)}"
    except Exception as e:
        return False, f"Failed to start pipeline: {e}"


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/status":
            self._json(200, get_status())

        elif self.path.startswith("/logs"):
            from urllib.parse import urlparse, parse_qs
            params = parse_qs(urlparse(self.path).query)
            step = params.get("step", [""])[0]
            self._json(200, {"lines": get_step_logs(step)})

        elif self.path in ("/", "/index.html"):
            try:
                with open(HTML_FILE, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)
            except FileNotFoundError:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"pipeline_dashboard.html not found")
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/trigger":
            ok, msg = trigger_pipeline()
            self._json(200 if ok else 409, {"ok": ok, "message": msg})
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    port = 8765
    print(f"Pipeline Dashboard → http://localhost:{port}")
    HTTPServer(("", port), Handler).serve_forever()
