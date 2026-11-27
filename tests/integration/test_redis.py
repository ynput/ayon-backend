"""Redis helpers and replica tracking against a real Redis (AYON_REDIS_URL).

Skipped when Redis is not available. See the `redis` fixture in conftest.py.
"""

from ayon_server.helpers.replicas import (
    REPLICA_INDEX,
    REPLICA_NS,
    ReplicaInfo,
    ServerReplicas,
)
from ayon_server.lib.redis import Redis


def test_keys_lists_each_key_once(run, redis) -> None:
    async def scenario() -> None:
        # More keys than one SCAN batch (count=1000), plus keys outside the namespace
        expected = {f"k{i}" for i in range(2500)}
        for key in expected:
            await Redis.set("scan", key, "1")
        await Redis.set("other", "k0", "1")

        keys = await Redis.keys("scan")
        assert len(keys) == len(expected)
        assert set(keys) == expected

        iterated = [key async for key, _ in Redis.iterate("scan")]
        assert sorted(iterated) == sorted(expected)

        assert await Redis.keys("missing") == []

    run(scenario())


def test_set_helpers(run, redis) -> None:
    async def scenario() -> None:
        assert await Redis.smembers("sets", "s") == []

        await Redis.sadd("sets", "s", "a", "b")
        await Redis.sadd("sets", "s", "a")
        assert sorted(await Redis.smembers("sets", "s")) == ["a", "b"]

        await Redis.srem("sets", "s", "a", "missing")
        assert await Redis.smembers("sets", "s") == ["b"]

    run(scenario())


def test_srem_if_missing(run, redis) -> None:
    async def scenario() -> None:
        await Redis.sadd("ns", "index", "alive", "dead")
        await Redis.set("ns", "alive", "1")

        await Redis.srem_if_missing("ns", "index", "alive")
        await Redis.srem_if_missing("ns", "index", "dead")
        await Redis.srem_if_missing("ns", "index", "not-a-member")

        assert await Redis.smembers("ns", "index") == ["alive"]

    run(scenario())


def make_replica(replica_id: str, **kwargs) -> ReplicaInfo:
    data = {
        "id": replica_id,
        "hostname": f"host-{replica_id}",
        "version": "1.0.0+202611271200",
        "boot_time": 0.0,
        "ready": True,
        "addons": {"core": ["1.0.0"]},
    }
    return ReplicaInfo(**(data | kwargs))


def test_replicas(run, redis) -> None:
    async def scenario() -> None:
        assert await ServerReplicas.count() == 0
        assert await ServerReplicas.out_of_sync() == 0

        a = make_replica("a")
        await ServerReplicas.save(a, ttl=30)
        await ServerReplicas.save(a, ttl=30)  # repeated heartbeat
        await ServerReplicas.save(make_replica("b"), ttl=30)
        await ServerReplicas.save(make_replica("c", version="2.0.0"), ttl=30)
        # starting replicas have no addons yet and don't count as out of sync
        await ServerReplicas.save(make_replica("d", ready=False, addons={}), ttl=30)

        replicas = {r.id: r async for r in ServerReplicas.iter()}
        assert sorted(replicas) == ["a", "b", "c", "d"]
        assert replicas["a"] == a
        assert await ServerReplicas.count() == 4
        assert await ServerReplicas.out_of_sync() == 1

        # Clean shutdown
        await ServerReplicas.delete("c")
        assert await ServerReplicas.count() == 3
        assert await ServerReplicas.out_of_sync() == 0

        # Died without a clean shutdown: the key expires, the reader prunes the id
        await Redis.delete(REPLICA_NS, "b")
        assert await ServerReplicas.count() == 2
        assert sorted(await Redis.smembers(REPLICA_NS, REPLICA_INDEX)) == ["a", "d"]

        # A late heartbeat brings it back
        await ServerReplicas.save(make_replica("b"), ttl=30)
        assert await ServerReplicas.count() == 3

    run(scenario())


def test_replicas_skip_invalid_payload(run, redis) -> None:
    async def scenario() -> None:
        await ServerReplicas.save(make_replica("a"), ttl=30)
        # e.g. written by a replica running a different version
        await Redis.set_json(REPLICA_NS, "old", {"id": "old"}, ttl=30)
        await Redis.sadd(REPLICA_NS, REPLICA_INDEX, "old")

        assert [r.id async for r in ServerReplicas.iter()] == ["a"]

    run(scenario())
