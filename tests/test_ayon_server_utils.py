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

    def test_coalesces_class_methods_and_bound_methods(self):
        async def _run_test():
            coalescer = self._reset_coalescer()
            try:
                calls = 0
                started_event = asyncio.Event()
                release_event = asyncio.Event()

                class DummyClass:
                    @classmethod
                    async def class_method(cls, val):
                        nonlocal calls
                        calls += 1
                        if calls == 1:
                            started_event.set()
                        await release_event.wait()
                        return val

                    async def instance_method(self, val):
                        nonlocal calls
                        calls += 1
                        if calls == 1:
                            started_event.set()
                        await release_event.wait()
                        return val

                # Test classmethod coalescing
                t1 = asyncio.create_task(
                    coalescer(DummyClass.class_method, "class_val")
                )
                t2 = asyncio.create_task(
                    coalescer(DummyClass.class_method, "class_val")
                )

                await asyncio.wait_for(started_event.wait(), timeout=1)
                assert len(coalescer.current_futures) == 1
                assert len(coalescer.current_waiters) == 1

                release_event.set()
                res1, res2 = await asyncio.gather(t1, t2)
                assert res1 == "class_val"
                assert res2 == "class_val"
                assert calls == 1

                # Reset events and coalescer
                calls = 0
                started_event.clear()
                release_event.clear()
                self._reset_coalescer()

                # Test instancemethod coalescing
                dummy_inst = DummyClass()
                t1 = asyncio.create_task(
                    coalescer(dummy_inst.instance_method, "instance_val")
                )
                t2 = asyncio.create_task(
                    coalescer(dummy_inst.instance_method, "instance_val")
                )

                await asyncio.wait_for(started_event.wait(), timeout=1)
                assert len(coalescer.current_futures) == 1
                assert len(coalescer.current_waiters) == 1

                release_event.set()
                res1, res2 = await asyncio.gather(t1, t2)
                assert res1 == "instance_val"
                assert res2 == "instance_val"
                assert calls == 1
            finally:
                self._reset_coalescer()

        asyncio.run(_run_test())

    def test_overflow_waiters_are_batched(self):
        async def _run_test():
            coalescer = self._reset_coalescer()
            try:
                coalescer.max_waiters = 2
                started = 0
                started_event = asyncio.Event()
                release_event = asyncio.Event()

                async def work(val) -> int:
                    nonlocal started
                    started += 1
                    if started == 3:
                        started_event.set()
                    await release_event.wait()
                    return val

                # We will trigger 5 tasks.
                # max_waiters is 2, so they should batch as:
                # - Batch 1 (base_key): 2 waiters
                # - Batch 2 (base_key:uuid1): 2 waiters
                # - Batch 3 (base_key:uuid2): 1 waiter
                # Total distinct tasks should be exactly 3.
                tasks = [asyncio.create_task(coalescer(work, "val")) for _ in range(5)]

                await asyncio.wait_for(started_event.wait(), timeout=1)
                assert len(coalescer.current_futures) == 3
                assert len(coalescer.current_waiters) == 3
                assert started == 3

                release_event.set()
                results = await asyncio.gather(*tasks)
                assert all(res == "val" for res in results)
            finally:
                self._reset_coalescer()

        asyncio.run(_run_test())
