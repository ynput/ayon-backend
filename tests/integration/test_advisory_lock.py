import asyncio

from ayon_server.lib.postgres import Postgres

KEY = "test:advisory-lock"


async def _hold(shared: bool, entered: asyncio.Event, release: asyncio.Event) -> None:
    async with Postgres.transaction():
        await Postgres.advisory_xact_lock(KEY, shared=shared)
        entered.set()
        await release.wait()


async def _blocks(first_shared: bool, second_shared: bool) -> bool:
    """Whether a second lock waits while the first one is held"""
    entered1, entered2, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    t1 = asyncio.create_task(_hold(first_shared, entered1, release))
    await entered1.wait()
    t2 = asyncio.create_task(_hold(second_shared, entered2, release))
    try:
        await asyncio.wait_for(entered2.wait(), 0.5)
        blocked = False
    except TimeoutError:
        blocked = True
    release.set()
    await asyncio.gather(t1, t2)
    return blocked


def test_shared_locks_only_conflict_with_exclusive(run) -> None:
    assert run(_blocks(True, True)) is False
    assert run(_blocks(True, False)) is True
    assert run(_blocks(False, True)) is True
