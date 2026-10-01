"""A provider input refusal preserves the rejected comment and the other sweep rows."""

import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from comment_tool.cli.sweep import QUESTIONS, sweep_unit
from comment_tool.core.comment_review import question_set
from comment_tool.journal.journaled_client import journaled_judge


class DecisionEndpoint(BaseHTTPRequestHandler):
    """Speak the actual System-One wire contract with an independent body-size boundary."""

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        request = json.loads(body)
        refused = len(body) > 25_000
        self.server.requests.append((request, refused))
        if refused:
            response = {"detail": {"error_type": "max_tokens_exceeded"}}
        else:
            answers = {}
            for name, question in request["questions"].items():
                kind = question["type"]
                if kind == "noul":
                    answers[name] = {"type": kind, "noul": 0.1}
                elif kind == "choice":
                    labels = list(question["criteria"])
                    answers[name] = {"type": kind, "choice": labels[0], "confidence": 1.0,
                                     "probabilities": {label: float(i == 0) for i, label in enumerate(labels)}}
                else:
                    answers[name] = {"type": kind, "score": 0.0, "confidence": 1.0,
                                     "legend": question["criteria"],
                                     "probabilities": {str(i): float(i == 0) for i in range(len(question["criteria"]))}}
            response = {"model": request["model"], "answers": answers}
        encoded = json.dumps(response).encode()
        self.send_response(400 if refused else 200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args):
        """Keep the independent endpoint silent; its actual exchanges are journaled by the client."""


def test_sweep_keeps_every_comment_after_real_sdk_input_refusal(tmp_path, monkeypatch):
    repository = tmp_path / "heedvane"
    repository.mkdir()
    source = "# Adds a marker for each stage.\ndef large(value):\n"
    source += "    value += 'marker-for-the-current-stage'\n" * 650
    source += "    return value\n\n# Normalizes a label.\ndef small(value):\n    return value.upper()\n"
    (repository / "sample.py").write_text(source)
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repository), "-c", "user.name=Test", "-c", "user.email=test@example.test",
                    "commit", "-qm", "comment evidence"], check=True)
    commit = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
    endpoint = ThreadingHTTPServer(("127.0.0.1", 0), DecisionEndpoint)
    endpoint.requests = []
    thread = threading.Thread(target=endpoint.serve_forever)
    thread.start()
    monkeypatch.setenv("TYPESAFE_BASE_URL", f"http://127.0.0.1:{endpoint.server_port}")
    monkeypatch.setenv("TYPESAFE_API_KEY", "local-protocol-test")
    monkeypatch.setenv("TYPESAFE_DEFAULT_MODEL", "jev-latest")
    monkeypatch.setenv("SYSTEM_ONE_ROUTES", "")
    try:
        out = tmp_path / "journal"
        out.mkdir()
        rows = sweep_unit(repository, commit, ["sample.py"], journaled_judge(out, {"heedvane"}),
                          question_set(json.loads(QUESTIONS.read_text())))
        assert len(rows) == 2
        rejected = next(row for row in rows if "each stage" in row["comment"])
        assert rejected["action"] is None
        assert rejected["decided_by"] == "escalated"
        assert "max_tokens_exceeded" in rejected["judgment_error"]
        assert "probabilities" not in rejected
        answered = next(row for row in rows if "Normalizes" in row["comment"])
        assert answered["probabilities"]
        exchanges = [json.loads(line) for line in (out / "journal.jsonl").read_text().splitlines()]
        assert any(event.get("response_status") == 400 for event in exchanges)
        assert any(refused for _, refused in endpoint.requests)
        assert any(not refused for _, refused in endpoint.requests)
    finally:
        endpoint.shutdown()
        endpoint.server_close()
        thread.join()
