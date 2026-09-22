"""Cancellation must retain admission capacity for real running thread work."""
import asyncio
import threading
import time

import pytest

from app.assistant import providers, service as service_module
from app.assistant.service import AssistantService


PLAN = {
    "title": "test", "periods": [{"id": "current", "label": "current", "start_date": "2026-09-20", "end_date": "2026-09-20"}],
    "ponds": [], "charts": [{"type": "bar", "title": "length", "metric": "length_mm", "secondary_metric": None, "group_by": "period"}],
}


class FakeProvider:
    def __init__(self):
        self.calls = 0

    async def generate(self, prompt, schema):
        self.calls += 1
        if self.calls == 1:
            return {"action": "analyze", "clarification": "", "plan": PLAN}
        return {"answer": "computed answer", "followups": []}


async def wait_started(event):
    deadline = time.monotonic() + 3
    while not event.is_set():
        if time.monotonic() > deadline:
            raise AssertionError("Background thread did not start")
        await asyncio.sleep(.005)


@pytest.mark.parametrize("stage", ["context", "analyze"])
@pytest.mark.parametrize("worker_error", [False, True])
def test_repeated_cancel_holds_capacity_until_real_thread_finishes(monkeypatch, stage, worker_error):
    monkeypatch.setenv("TIDE_AI_MAX_CONCURRENT", "1")
    provider = FakeProvider()
    monkeypatch.setattr(providers, "make_provider", lambda: provider)
    monkeypatch.setattr(service_module, "skill_instructions", lambda: "Trusted test instructions")
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    runner = AssistantService(None)
    states = []
    monkeypatch.setattr(runner, "_state", lambda message_id, status, **values: states.append((status, values)))
    context = {"catalog": {}, "demo": False, "history": [], "previous_query": None}
    board = {"charts": [], "sources": [], "total_jobs": 1}

    def slow_work(*args):
        started.set()
        try:
            assert release.wait(timeout=3), "Test never released the thread"
            if worker_error:
                raise RuntimeError("Synthetic error after cancellation")
            return context if stage == "context" else board
        finally:
            finished.set()

    monkeypatch.setattr(runner, "_context", slow_work if stage == "context" else lambda *args: context)
    monkeypatch.setattr(runner, "_analyze", slow_work if stage == "analyze" else lambda *args: board)

    async def scenario():
        errors = []
        asyncio.get_running_loop().set_exception_handler(lambda loop, information: errors.append(information))
        runner.start("request", "question")
        try:
            await wait_started(started)
            cancellation = asyncio.create_task(runner.cancel("request"))
            await asyncio.sleep(.01)
            second_cancellation = asyncio.create_task(runner.cancel("request"))
            await asyncio.sleep(.01)
            assert not finished.is_set()
            assert not runner.has_capacity(), "Cancellation released admission while SQL/thread work still ran"
            assert not cancellation.done() and not second_cancellation.done()
            assert not runner.tasks["request"].done()
            release.set()
            await asyncio.wait_for(asyncio.gather(cancellation, second_cancellation), timeout=3)
            await asyncio.sleep(0)
            assert finished.is_set() and runner.has_capacity()
            assert "request" not in runner.tasks
            assert all(status not in {"completed", "answering", "failed"} for status, values in states)
            assert states[-1][0] == "cancelled"
            assert provider.calls == (0 if stage == "context" else 1)
            assert not errors
        finally:
            release.set()
            await runner.close()

    asyncio.run(scenario())


def test_shutdown_waits_for_owned_thread_cleanup(monkeypatch):
    monkeypatch.setattr(providers, "make_provider", lambda: FakeProvider())
    monkeypatch.setattr(service_module, "skill_instructions", lambda: "test")
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    runner = AssistantService(None)
    monkeypatch.setattr(runner, "_state", lambda *args, **kwargs: None)

    def slow_context(*args):
        started.set()
        try:
            assert release.wait(timeout=3)
            return {}
        finally:
            finished.set()

    monkeypatch.setattr(runner, "_context", slow_context)

    async def scenario():
        runner.start("request", "question")
        try:
            await wait_started(started)
            closing = asyncio.create_task(runner.close())
            await asyncio.sleep(.01)
            assert not closing.done() and not finished.is_set()
            release.set()
            await asyncio.wait_for(closing, timeout=3)
            assert finished.is_set()
        finally:
            release.set()
            await runner.close()

    asyncio.run(scenario())
