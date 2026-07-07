import asyncio
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))


from ayon_server.models.file_info import FileInfo
from ayon_server.utils import RequestCoalescer, dict_remove_path


class TestDictRemovePath:
    def test_remove_existing_path(self):
        data = {"a": {"b": {"c": 1}}}
        dict_remove_path(data, ["a", "b", "c"], remove_orphans=False)
        assert data == {"a": {"b": {}}}

        dict_remove_path(data, ["a", "b"], remove_orphans=False)
        assert data == {"a": {}}

    def test_remove_non_existent_path(self):
        data = {"a": {"b": {"c": 1}}}
        dict_remove_path(data, ["a", "x", "c"])
        assert data == {"a": {"b": {"c": 1}}}

    def test_remove_with_orphans(self):
        data = {"a": {"b": {"c": 1}}}
        dict_remove_path(data, ["a", "b", "c"], remove_orphans=True)
        assert data == {}

    def test_remove_without_orphans(self):
        data = {"a": {"b": {"c": 1}}}
        dict_remove_path(data, ["a", "b", "c"], remove_orphans=False)
        assert data == {"a": {"b": {}}}

    def test_remove_path_with_non_dict(self):
        data = {"a": {"b": "not a dict"}}
        dict_remove_path(data, ["a", "b", "c"])
        assert data == {"a": {"b": "not a dict"}}

    def test_remove_all(self):
        data = {"a": {"b": {"c": 1}}}
        dict_remove_path(data, ["a"])
        assert data == {}


class TestFileInfo:
    r = FileInfo(
        filename="example.txt",
        size=123,
    )

    assert r.filename == "example.txt"
    assert r.content_type == "text/plain"

    r = FileInfo(
        filename="example",
        size=123,
        content_type="image/png",
    )

    assert r.filename == "example"
    assert r.content_type == "image/png"


class TestRequestCoalescer:
    def _reset_coalescer(self) -> RequestCoalescer[object]:
        coalescer = RequestCoalescer()
        coalescer.current_futures.clear()
        coalescer.current_waiters.clear()
        coalescer.max_waiters = 20
        return coalescer

    def test_creates_distinct_keys_for_overflow_waiters(self):
        async def _run_test():
            coalescer = self._reset_coalescer()
            try:
                coalescer.max_waiters = 1
                started = 0
                started_event = asyncio.Event()
                release_event = asyncio.Event()

                async def work() -> int:
                    nonlocal started
                    started += 1
                    result = started
                    if started == 3:
                        started_event.set()
                    await release_event.wait()
                    return result

                tasks = [asyncio.create_task(coalescer(work)) for _ in range(3)]

                await asyncio.wait_for(started_event.wait(), timeout=1)
                assert len(coalescer.current_futures) == 3

                release_event.set()
                await asyncio.gather(*tasks)
            finally:
                self._reset_coalescer()

        asyncio.run(_run_test())
