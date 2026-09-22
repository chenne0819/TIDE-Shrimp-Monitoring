import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.assistant import providers


SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}},
          "required": ["ok"], "additionalProperties": False}


def test_status_is_disabled_by_default_and_never_reads_login(monkeypatch):
    monkeypatch.delenv("TIDE_AI_PROVIDER", raising=False)
    assert providers.provider_status()["enabled"] is False
    with pytest.raises(providers.ProviderError, match="尚未啟用"):
        providers.make_provider()


@pytest.mark.parametrize("name,value", [("TIDE_AI_PROVIDER", "evil"), ("TIDE_AI_MODEL", "x\n--shell"),
                                        ("TIDE_AI_TIMEOUT_SECONDS", "nan"), ("TIDE_AI_TIMEOUT_SECONDS", "601")])
def test_invalid_environment_fails_closed(monkeypatch, name, value):
    monkeypatch.setenv("TIDE_AI_PROVIDER", "codex")
    monkeypatch.setenv(name, value)
    assert providers.provider_status()["enabled"] is False
    assert isinstance(providers.provider_status()["model"], str)


def test_openai_status_requires_server_key_without_disclosing_it(monkeypatch):
    monkeypatch.setenv("TIDE_AI_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert not providers.provider_status()["enabled"]
    monkeypatch.setenv("OPENAI_API_KEY", "test-private-value")
    assert providers.provider_status()["enabled"]
    assert "test-private-value" not in str(providers.provider_status())


def test_codex_environment_is_a_small_allowlist(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "database-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "key-secret")
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-secret")
    monkeypatch.setenv("HTTP_PROXY", "proxy-secret")
    monkeypatch.setenv("CODEX_HOME", "login-home")
    environment = providers._codex_environment()
    assert environment["CODEX_HOME"] == "login-home"
    assert not {"DATABASE_URL", "OPENAI_API_KEY", "CODEX_THREAD_ID", "HTTP_PROXY"} & environment.keys()


def test_codex_command_disables_tools_and_personal_configuration(tmp_path):
    args = providers._codex_command(Path("codex"), "gpt-5.6-terra", tmp_path / "schema",
                                    tmp_path / "answer", tmp_path / "instructions", tmp_path / "catalog")
    assert "--ignore-user-config" in args and "--ephemeral" in args and "--strict-config" in args
    assert args[args.index("--sandbox") + 1] == "read-only"
    assert args[args.index("--cd") + 1] == str(providers.AGENT_ROOT)
    assert "--dangerously-bypass-approvals-and-sandbox" not in args
    assert "web_search=\"disabled\"" in args
    assert "approval_policy=\"never\"" in args and "project_doc_max_bytes=0" in args
    disabled = {args[index + 1] for index, value in enumerate(args) if value == "--disable"}
    assert {"shell_tool", "unified_exec", "apps", "plugins", "hooks", "multi_agent", "code_mode_host", "view_image"} <= disabled


def test_catalog_removes_patch_and_other_model_tool_capabilities(monkeypatch, tmp_path):
    import threading
    captured = {}
    def offline(args, environment, data, cancelled, deadline, *, capture=False):
        captured.update(args=args, environment=environment, capture=capture)
        return json.dumps({"models": [{"slug": "selected", "apply_patch_tool_type": "freeform",
                                      "shell_type": "unified_exec", "experimental_supported_tools": ["test_sync_tool"],
                                      "input_modalities": ["text", "image"]}]}).encode()
    monkeypatch.setattr(providers, "_run_process", offline)
    path = providers._write_restricted_catalog(Path("binary"), "selected", tmp_path, threading.Event(), 100)
    selected = json.loads(path.read_text())["models"][0]
    assert selected["slug"] == "selected"
    assert selected["apply_patch_tool_type"] is None and selected["shell_type"] == "disabled"
    assert selected["experimental_supported_tools"] == [] and selected["input_modalities"] == ["text"]
    assert captured["args"] == ["binary", "debug", "models", "--bundled"]
    assert Path(captured["environment"]["CODEX_HOME"]) == tmp_path / "catalog-home"


def test_unlisted_codex_model_fails_before_inference(monkeypatch, tmp_path):
    import threading
    monkeypatch.setattr(providers, "_run_process", lambda *args, **kwargs: b'{"models":[]}')
    with pytest.raises(providers.ProviderError, match="尚未包含"):
        providers._write_restricted_catalog(Path("binary"), "unknown", tmp_path, threading.Event(), 100)


@pytest.mark.parametrize("raw", ['[]', '{"value":NaN}', 'not-json', None, 'x' * (providers.MAX_OUTPUT_BYTES + 1)],
                         ids=["array", "nonfinite", "malformed", "empty", "oversize"])
def test_output_must_be_a_bounded_json_object(raw):
    with pytest.raises(providers.ProviderError):
        providers._json_object(raw)


def test_input_limits_and_schema_copy():
    copied = providers._inputs("question", SCHEMA)
    copied["properties"]["extra"] = {"type": "string"}
    assert "extra" not in SCHEMA["properties"]
    with pytest.raises(providers.ProviderError):
        providers._inputs("x" * (providers.MAX_PROMPT_BYTES + 1), SCHEMA)


def fake_openai(monkeypatch, action):
    import openai
    state = {}
    class Client:
        def __init__(self, **kwargs):
            state["client"] = kwargs
            self.responses = self
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            state["closed"] = True
        async def create(self, **kwargs):
            state["request"] = kwargs
            return await action(state)
    monkeypatch.setattr(openai, "AsyncOpenAI", Client)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    return state


def test_responses_uses_sdk_schema_without_tools_or_retries(monkeypatch):
    async def response(state):
        return SimpleNamespace(status="completed", output_text='{"ok":true}')
    state = fake_openai(monkeypatch, response)
    result = asyncio.run(providers.OpenAIProvider("model-id", 5).generate("question", SCHEMA))
    assert result == {"ok": True}
    assert state["request"]["tools"] == [] and state["request"]["tool_choice"] == "none"
    assert state["request"]["store"] is False
    assert state["request"]["text"]["format"]["schema"] == SCHEMA
    assert state["client"]["max_retries"] == 0 and state["closed"]
    assert state["client"]["base_url"] == "https://api.openai.com/v1"


def test_responses_errors_do_not_expose_provider_payload(monkeypatch):
    async def failure(state):
        raise RuntimeError("secret-key internal-prompt private-url")
    fake_openai(monkeypatch, failure)
    with pytest.raises(providers.ProviderError) as error:
        asyncio.run(providers.OpenAIProvider("model-id", 5).generate("question", SCHEMA))
    assert "secret" not in str(error.value) and "prompt" not in str(error.value)


def test_responses_timeout_closes_client(monkeypatch):
    async def blocked(state):
        await asyncio.sleep(10)
    state = fake_openai(monkeypatch, blocked)
    with pytest.raises(providers.ProviderError, match="逾時"):
        asyncio.run(providers.OpenAIProvider("model-id", 0.01).generate("question", SCHEMA))
    assert state["closed"]


def test_responses_cancellation_closes_connection(monkeypatch):
    async def scenario():
        started = asyncio.Event()
        async def blocked(state):
            started.set()
            await asyncio.sleep(10)
        state = fake_openai(monkeypatch, blocked)
        task = asyncio.create_task(providers.OpenAIProvider("model-id", 5).generate("question", SCHEMA))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert state["closed"]
    asyncio.run(scenario())


def test_codex_cancellation_waits_for_worker_cleanup(monkeypatch):
    import threading
    started, reaped = threading.Event(), threading.Event()
    def blocked(self, prompt, schema, cancelled):
        started.set()
        assert cancelled.wait(timeout=2)
        reaped.set()
        raise providers.ProviderError("已取消")
    monkeypatch.setattr(providers.CodexProvider, "_generate_sync", blocked)
    async def scenario():
        task = asyncio.create_task(providers.CodexProvider("model-id", 5).generate("question", SCHEMA))
        await asyncio.to_thread(started.wait, 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert reaped.is_set()
    asyncio.run(scenario())


def test_repeated_cancel_cannot_release_before_worker_reaps(monkeypatch):
    import threading
    started, release, reaped = threading.Event(), threading.Event(), threading.Event()
    def blocked(self, prompt, schema, cancelled):
        started.set()
        assert cancelled.wait(timeout=2)
        assert release.wait(timeout=2)
        reaped.set()
        raise providers.ProviderError("已取消")
    monkeypatch.setattr(providers.CodexProvider, "_generate_sync", blocked)
    async def scenario():
        task = asyncio.create_task(providers.CodexProvider("model-id", 5).generate("question", SCHEMA))
        await asyncio.to_thread(started.wait, 1)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done() and not reaped.is_set()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert reaped.is_set()
    asyncio.run(scenario())


def test_large_stdin_timeout_reaps_nonreading_child(monkeypatch):
    import subprocess
    import sys
    import threading
    import time
    created = []
    real_popen = subprocess.Popen
    def start(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        created.append(process)
        return process
    monkeypatch.setattr(providers.subprocess, "Popen", start)
    began = time.monotonic()
    with pytest.raises(providers.ProviderError, match="逾時"):
        providers._run_process([sys.executable, "-c", "import time;time.sleep(4)"],
                               providers._codex_environment(), b"x" * providers.MAX_PROMPT_BYTES, threading.Event(),
                               time.monotonic() + 0.15)
    assert time.monotonic() - began < 1.5
    assert created and created[0].poll() is not None
    assert not any(thread.name == "tide-codex-io" for thread in threading.enumerate())


def test_large_stdin_cancellation_reaps_nonreading_child(monkeypatch):
    import subprocess
    import sys
    import threading
    import time
    io_started = threading.Event()
    created = []
    real_popen = subprocess.Popen
    class TrackedPopen(real_popen):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)
        def communicate(self, *args, **kwargs):
            io_started.set()
            return super().communicate(*args, **kwargs)
    monkeypatch.setattr(providers.subprocess, "Popen", TrackedPopen)
    def blocked(self, prompt, schema, cancelled):
        providers._run_process([sys.executable, "-c", "import time;time.sleep(4)"],
                               providers._codex_environment(), prompt.encode(), cancelled,
                               time.monotonic() + 10)
        raise AssertionError("The child should be cancelled")
    monkeypatch.setattr(providers.CodexProvider, "_generate_sync", blocked)
    async def scenario():
        task = asyncio.create_task(providers.CodexProvider("model-id", 10).generate(
            "x" * providers.MAX_PROMPT_BYTES, SCHEMA))
        assert await asyncio.to_thread(io_started.wait, 2)
        await asyncio.sleep(0.05)  # let the child's unread stdin pipe fill
        began = time.monotonic()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert time.monotonic() - began < 1.5
        assert created and created[0].poll() is not None
        assert not any(thread.name == "tide-codex-io" for thread in threading.enumerate())
    asyncio.run(scenario())


@pytest.mark.skipif(os.name != "nt", reason="Windows native process-tree cleanup")
def test_windows_job_closing_reaps_entire_process_tree():
    import ctypes
    from ctypes import wintypes
    import subprocess
    import sys
    script = ("import subprocess,sys,time; "
              "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],creationflags=0x08000000); "
              "print(child.pid,flush=True);time.sleep(30)")
    process = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE,
                               text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    child_handle = None
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.WaitForSingleObject.restype = wintypes.DWORD
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    try:
        job = providers._WindowsJob(process)
        child_pid = int(process.stdout.readline().strip())
        child_handle = api.OpenProcess(0x00100000, False, child_pid)
        assert child_handle
        job.close()
        process.wait(timeout=3)
        assert process.poll() is not None
        assert api.WaitForSingleObject(child_handle, 3000) == 0
        job.close()  # idempotent
    finally:
        if child_handle:
            api.CloseHandle(child_handle)
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        if process.stdout:
            process.stdout.close()
