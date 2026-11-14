"""Minimal LoomSci Report app.

This is the app boundary, not the research pipeline yet. It accepts a question,
runs a persisted job in the background, and writes the result to Core as an item.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from loomsci_core.sdk import CoreClient

DATA = Path(os.environ["LOOMSCI_APP_DATA_DIR"])
JOBS = DATA / "jobs.json"
LOCK = threading.Lock()
JOBS_MEMORY: dict[str, dict] = {}


def load_jobs() -> None:
    if JOBS.is_file():
        try:
            JOBS_MEMORY.update(json.loads(JOBS.read_text(encoding="utf-8")))
        except ValueError:
            pass


def save_jobs() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = JOBS.with_suffix(".tmp")
    tmp.write_text(json.dumps(JOBS_MEMORY, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(JOBS)


def update(job_id: str, **fields) -> None:
    with LOCK:
        JOBS_MEMORY.setdefault(job_id, {}).update(fields)
        save_jobs()


def run_job(job_id: str, question: str) -> None:
    try:
        update(job_id, status="running", stage="planning", started_at=time.time())
        for stage, delay in (
            ("planning", 0.2),
            ("searching", 0.2),
            ("verifying", 0.2),
            ("writing", 0.2),
        ):
            time.sleep(delay)
            update(job_id, stage=stage)
        client = CoreClient(os.environ["LOOMSCI_CORE_URL"], os.environ["LOOMSCI_APP_TOKEN"])
        body = "# Research Report\n\n## Question\n\n" + question + "\n\n## Status\n\nReport app skeleton completed. The online research pipeline is the next implementation step.\n"
        item = client.create_item(app="report", type="report.report", title="", body=body, tags=["report"])
        update(job_id, status="done", stage="done", item_id=item["id"], finished_at=time.time())
    except Exception as exc:  # noqa: BLE001 - job boundary
        update(job_id, status="failed", stage="failed", error=str(exc), finished_at=time.time())


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str = "text/html; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json")

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(200, {"ok": True, "app": "report"})
            return
        if self.path.startswith("/api/jobs/"):
            job = JOBS_MEMORY.get(self.path.rsplit("/", 1)[-1])
            self._json(200 if job else 404, {"ok": bool(job), "job": job})
            return
        self._send(200, INDEX.encode("utf-8"))

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/jobs":
            self._json(404, {"ok": False, "error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
            question = str(payload.get("question") or "").strip()
            if not question:
                raise ValueError("question_required")
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"ok": False, "error": str(exc)})
            return
        job_id = "job-" + secrets.token_hex(6)
        with LOCK:
            JOBS_MEMORY[job_id] = {"id": job_id, "question": question, "status": "queued", "stage": "queued"}
            save_jobs()
        threading.Thread(target=run_job, args=(job_id, question), daemon=True).start()
        self._json(202, {"ok": True, "job": JOBS_MEMORY[job_id]})

    def log_message(self, fmt: str, *args) -> None:
        return


INDEX = r'''<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LoomSci Report</title>
<style>
body{font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;background:#f5f6f8;color:#17202a}
main{max-width:860px;margin:0 auto;padding:32px}
.panel{background:#fff;border:1px solid #d0d5dd;border-radius:10px;padding:20px}
textarea,input,button{font:inherit;padding:9px 10px;border:1px solid #d0d5dd;border-radius:7px}
textarea,input{width:100%;box-sizing:border-box;margin:8px 0}
button{background:#2557a7;color:#fff;border-color:#2557a7;cursor:pointer}
pre{white-space:pre-wrap;background:#f5f6f8;padding:12px;border-radius:7px}
</style></head>
<body><main>
<h1>LoomSci Report</h1>
<p>输入研究问题，后台运行。关闭页面后任务继续。</p>
<div class="panel">
<textarea id="question" rows="5" placeholder="研究问题"></textarea>
<button id="start">开始调研</button>
<p id="status"></p>
<pre id="result"></pre>
</div>
</main>
<script>
const $ = s => document.querySelector(s);
$("#start").onclick = async () => {
  const question = $("#question").value.trim();
  if (!question) return;
  $("#status").textContent = "starting";
  const response = await fetch("/api/jobs", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({question})});
  const data = await response.json();
  if (!response.ok) { $("#status").textContent = data.error || "failed"; return; }
  const id = data.job.id;
  const timer = setInterval(async () => {
    const r = await fetch("/api/jobs/" + id);
    const d = await r.json();
    const j = d.job;
    if (!j) return;
    $("#status").textContent = j.status + " · " + (j.stage || "");
    if (j.status === "done") {
      clearInterval(timer);
      $("#result").textContent = "Core item: " + j.item_id;
    }
    if (j.status === "failed") {
      clearInterval(timer);
      $("#result").textContent = j.error || "failed";
    }
  }, 1000);
};
</script></body></html>'''


def main() -> None:
    load_jobs()
    port = int(os.environ["LOOMSCI_APP_PORT"])
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
