"""Model providers (querygenie/providers) — no model, no network, no API keys."""
import json
import os
import sqlite3
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from querygenie import providers  # noqa: E402
from querygenie.providers import http_apis  # noqa: E402
from querygenie.providers.base import CandidateBackend, chat_prompt, extract_sql  # noqa: E402


def _db(tmp_path):
    p = str(tmp_path / "shop.sqlite")
    con = sqlite3.connect(p)
    con.executescript("CREATE TABLE item (id INTEGER PRIMARY KEY, name TEXT, price REAL);"
                      "INSERT INTO item VALUES (1,'pen',2.5),(2,'book',12.0),(3,'bag',30.0);")
    con.commit(); con.close()
    return p


def test_extract_sql_from_chat_replies():
    assert extract_sql("```sql\nSELECT 1;\n```") == "SELECT 1;"
    assert extract_sql("Here is the query:\nSELECT name FROM item") == "SELECT name FROM item"
    assert extract_sql("<think>maybe count?</think>SELECT count(*) FROM item") == "SELECT count(*) FROM item"
    assert extract_sql("WITH t AS (SELECT 1) SELECT * FROM t") == "WITH t AS (SELECT 1) SELECT * FROM t"


def test_chat_prompt_keeps_schema_and_question():
    p = chat_prompt("table item , columns = [ item.name ]\n\nHow many items?\n", "How many items?")
    assert p.startswith("table item") and p.endswith("Question: How many items?\nSQLite query:")


class Fake(CandidateBackend):
    def __init__(self, replies):
        super().__init__("fake")
        self.replies = replies

    def raw_candidates(self, prompt):
        assert "item" in prompt and "Question:" in prompt
        return self.replies


def test_candidates_go_through_the_evaluated_selection(tmp_path):
    db = _db(tmp_path)
    same = "```sql\nSELECT count(*) FROM item\n```"
    d = Fake([same, same, "SELECT count(*) FROM item WHERE price > 5", "not sql"]).decide(db, "How many items?")
    assert d.n_agree == 2 and d.candidates[d.selected].rows == [(3,)]
    assert not d.candidates[3].runs                       # prose that isn't SQL counts as "did not run"
    d = Fake([same] * 4).decide(db, "How many items?")
    assert d.agreement == 1.0 and not d.abstain


def test_fewer_replies_are_padded_as_failed(tmp_path):
    d = Fake(["SELECT name FROM item"]).decide(_db(tmp_path), "Item names?")
    assert len(d.candidates) == 4 and sum(c.runs for c in d.candidates) == 1


class _FakeOpenAI(BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        body = {"data": [{"id": "model-b"}, {"id": "model-a"}]}
        self._send(body)

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _FakeOpenAI.seen.append((self.headers.get("Authorization"), req))
        if req["model"] == "missing":
            self.send_response(404); self.end_headers()
            self.wfile.write(json.dumps({"error": {"message": "model not found"}}).encode()); return
        self._send({"choices": [{"message": {"content": "SELECT name FROM item WHERE price > 10"}}]})

    def _send(self, body):
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(body).encode())


@pytest.fixture
def fake_server():
    srv = HTTPServer(("127.0.0.1", 0), _FakeOpenAI)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/v1"
    srv.shutdown()


def test_openai_compatible_round_trip(tmp_path, fake_server):
    _FakeOpenAI.seen.clear()
    assert [m["id"] for m in http_apis.openai_models(fake_server)] == ["model-a", "model-b"]
    be = http_apis.OpenAICompatible("model-a", base_url=fake_server, api_key="test-key", cloud=False)
    d = be.decide(_db(tmp_path), "Which items cost more than 10?")
    assert d.n_agree == 4 and sorted(d.candidates[d.selected].rows) == [("bag",), ("book",)]
    assert len(_FakeOpenAI.seen) == 4 and all(a == "Bearer test-key" for a, _ in _FakeOpenAI.seen)
    assert _FakeOpenAI.seen[0][1]["messages"][0]["role"] == "system"


def test_provider_errors_are_readable(tmp_path, fake_server):
    be = http_apis.OpenAICompatible("missing", base_url=fake_server, cloud=False)
    with pytest.raises(providers.ProviderError, match="404.*model not found"):
        be.decide(_db(tmp_path), "Anything?")
    with pytest.raises(providers.ProviderError, match="Couldn't reach"):
        http_apis.ollama_models("http://127.0.0.1:9")          # nothing listens on port 9


def test_keys_never_leave_the_keychain_layer(monkeypatch):
    store = {}

    class KR:
        def set_password(self, s, u, p): store[(s, u)] = p
        def get_password(self, s, u): return store.get((s, u))
        def delete_password(self, s, u): store.pop((s, u))

    monkeypatch.setattr(providers, "_keyring", lambda: KR())
    assert not providers.key_saved("openai")
    with pytest.raises(providers.ProviderError, match="API key first"):
        providers.build({"kind": "openai", "model": "x"}, {})
    providers.key_set("openai", "  sk-test  ")
    assert store[("QueryGenie", "openai")] == "sk-test" and providers.key_saved("openai")
    assert providers.build({"kind": "openai", "model": "x"}, {}).cloud
    providers.key_set("openai", None)
    assert not providers.key_saved("openai")


def test_build_rejects_missing_local_files(monkeypatch):
    monkeypatch.setattr(providers, "key_get", lambda provider: None)      # never touch the real keychain
    with pytest.raises(providers.ProviderError, match="not found"):
        providers.build({"kind": "gguf", "model": "/nope/model.gguf"}, {})
    local = providers.build({"kind": "compat", "model": "m", "base_url": "http://localhost:1234/v1"}, {})
    assert not local.cloud


def test_effort_is_sent_only_when_chosen(tmp_path, fake_server):
    db = _db(tmp_path)
    _FakeOpenAI.seen.clear()
    http_apis.OpenAICompatible("model-a", base_url=fake_server, cloud=False).decide(db, "Items over 10?")
    assert all("reasoning_effort" not in body for _, body in _FakeOpenAI.seen)
    _FakeOpenAI.seen.clear()
    http_apis.OpenAICompatible("model-a", base_url=fake_server, cloud=False, effort="high").decide(db, "Items over 10?")
    assert {body["reasoning_effort"] for _, body in _FakeOpenAI.seen} == {"high"}


def test_effort_levels_per_provider(monkeypatch):
    monkeypatch.setattr(providers, "key_get", lambda provider: None)
    assert providers.effort_levels("anthropic")[-1] == "max" and providers.effort_levels("ollama") == ["off", "on"]
    assert providers.effort_levels("gemini") is None and providers.effort_levels("mlx") is None
    be = providers.build({"kind": "compat", "model": "m", "base_url": "http://localhost:1/v1", "effort": "turbo"}, {})
    assert be.effort is None                               # unknown levels are ignored, never sent
