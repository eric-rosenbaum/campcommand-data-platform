from collections import Counter
from datetime import date

from campcommand.synthetic.events import SeasonSimulator
from campcommand.synthetic.world import build_world

SEASON = (date(2026, 6, 22), date(2026, 8, 21))


def simulate(seed=3):
    world = build_world("tall_pines", seed, SEASON[0])
    return SeasonSimulator(world, "America/New_York", SEASON, seed).run()


def test_is_deterministic():
    a, b = simulate(), simulate()
    assert [u.upload_id for u in a] == [u.upload_id for u in b]


def test_produces_the_delivery_problems_the_warehouse_has_to_handle():
    uploads = simulate()
    events = [e | {"received_at": u.received_at} for u in uploads for e in u.events]
    copies = Counter(e["event_id"] for e in events)

    assert any(n > 1 for n in copies.values()), "retried uploads"
    assert any((e["received_at"] - e["occurred_at"]).total_seconds() > 24 * 3600 for e in events), "late"
    assert any(e["occurred_at"] > e["received_at"] for e in events), "fast device clock"


def test_device_sequence_numbers_are_gapless_per_device():
    first_copies = {}
    for u in simulate():
        for e in u.events:
            first_copies.setdefault(e["event_id"], e)
    by_device = {}
    for e in first_copies.values():
        by_device.setdefault(e["device_id"], []).append(e["device_seq"])
    for seqs in by_device.values():
        assert sorted(seqs) == list(range(1, len(seqs) + 1))
