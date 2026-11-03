import pytest

from ayon_server.lib.postgres import Postgres


async def _commit_and_rollback() -> list[str]:
    log: list[str] = []

    def hook(name: str):
        async def run() -> None:
            # Runs outside the transaction, so other connections see the data
            log.append(f"{name}:{await Postgres.is_in_transaction()}")

        return run

    async def fail() -> None:
        raise RuntimeError("hook failed")

    await Postgres.on_commit(hook("no-transaction"))

    async with Postgres.transaction():
        await Postgres.on_commit(hook("outer"))
        async with Postgres.transaction():  # joins the outer transaction
            await Postgres.on_commit(fail)
            await Postgres.on_commit(hook("nested"))
        log.append("before-commit")

    with pytest.raises(ZeroDivisionError):
        async with Postgres.transaction():
            await Postgres.on_commit(hook("rolled-back"))
            _ = 1 / 0

    return log


def test_hooks_run_after_outermost_commit_only(run) -> None:
    assert run(_commit_and_rollback()) == [
        "no-transaction:False",
        "before-commit",
        "outer:False",
        "nested:False",
    ]
