"""A camp season of app events, delivered the way phones deliver them.

Maintenance and waterfront staff log work on shared iPads and phones that
spend a lot of time out of signal. Each device keeps an outbox and uploads
whatever it has when it gets a connection, so:

  * events arrive hours or days after they happened (late)
  * events from different devices interleave out of order
  * an upload that times out gets retried, and the server sees the same
    events twice (duplicates, same event_id)
  * one device has its clock set three hours fast for part of the season

The web app in the office is always online and uploads immediately.
"""

import json
import random
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from campcommand.synthetic.world import World

PRIORITIES = (["urgent", "high", "normal", "low"], [5, 20, 60, 15])


@dataclass
class Device:
    device_id: str
    offline: list[tuple[datetime, datetime]] = field(default_factory=list)
    clock_skew: tuple[datetime, datetime, timedelta] | None = None
    seq: int = 0
    outbox: list[dict] = field(default_factory=list)

    def is_offline(self, at: datetime) -> bool:
        return any(start <= at < end for start, end in self.offline)

    def device_clock(self, at: datetime) -> datetime:
        if self.clock_skew and self.clock_skew[0] <= at < self.clock_skew[1]:
            return at + self.clock_skew[2]
        return at


@dataclass
class Upload:
    upload_id: str
    tenant_id: str
    device_id: str
    received_at: datetime
    events: list[dict]

    def rows(self) -> list[dict]:
        return [
            {**e, "tenant_id": self.tenant_id, "upload_id": self.upload_id, "received_at": self.received_at}
            for e in self.events
        ]

    def __post_init__(self) -> None:
        self.events = [{k: v for k, v in e.items() if not k.startswith("_")} for e in self.events]

    def to_json(self) -> str:
        return json.dumps(
            {
                "upload_id": self.upload_id,
                "tenant_id": self.tenant_id,
                "device_id": self.device_id,
                "received_at": self.received_at.isoformat(),
                "events": [{**e, "occurred_at": e["occurred_at"].isoformat()} for e in self.events],
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, line: str) -> "Upload":
        raw = json.loads(line)
        return cls(
            upload_id=raw["upload_id"],
            tenant_id=raw["tenant_id"],
            device_id=raw["device_id"],
            received_at=datetime.fromisoformat(raw["received_at"]),
            events=[{**e, "occurred_at": datetime.fromisoformat(e["occurred_at"])} for e in raw["events"]],
        )


class SeasonSimulator:
    def __init__(self, world: World, timezone: str, season: tuple[date, date], seed: int):
        self.world = world
        self.tz = ZoneInfo(timezone)
        self.season = season
        self.rng = random.Random(f"{world.tenant_id}-events-{seed}")
        self.uuid_rng = random.Random(f"{world.tenant_id}-uuids-{seed}")
        start = self._utc(season[0], time(6))
        end = self._utc(season[1], time(22))

        self.web = Device("web")
        maintenance = [Device(f"ipad-maint-{i}") for i in (1, 2)]
        waterfront = [Device(f"iphone-waterfront-{i}") for i in (1, 2)]
        for device in maintenance + waterfront:
            device.offline = self._offline_windows(start, end)
        # The outpost site has no signal at all for a few days mid-season.
        outage_start = start + timedelta(days=self.rng.randint(20, 30))
        maintenance[1].offline.append((outage_start, outage_start + timedelta(days=4)))
        skew_start = start + timedelta(days=self.rng.randint(10, 40))
        maintenance[0].clock_skew = (skew_start, skew_start + timedelta(days=5), timedelta(hours=3))

        self.maintenance_devices = maintenance
        self.waterfront_devices = waterfront
        self.devices = [self.web, *maintenance, *waterfront]
        self.uploads: list[Upload] = []

    def _utc(self, day: date, at: time) -> datetime:
        return datetime.combine(day, at, tzinfo=self.tz).astimezone(UTC).replace(tzinfo=None)

    def _uuid(self) -> str:
        return str(uuid.UUID(int=self.uuid_rng.getrandbits(128), version=4))

    def _offline_windows(self, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
        windows = []
        for _ in range(self.rng.randint(6, 12)):
            begin = start + timedelta(seconds=self.rng.randint(0, int((end - start).total_seconds())))
            windows.append((begin, begin + timedelta(minutes=self.rng.randint(45, 36 * 60))))
        return windows

    def run(self) -> list[Upload]:
        timeline: list[tuple[datetime, Device, str, dict]] = []
        timeline += self._work_orders()
        timeline += self._waterfront_checks()
        timeline.sort(key=lambda item: item[0])

        for at, device, event_type, payload in timeline:
            device.seq += 1
            device.outbox.append(
                {
                    "event_id": self._uuid(),
                    "device_id": device.device_id,
                    "device_seq": device.seq,
                    "event_type": event_type,
                    "occurred_at": device.device_clock(at),
                    "payload": json.dumps(payload, ensure_ascii=False),
                    "_created_at": at,
                }
            )
            if device is self.web:
                self._upload(device, at + timedelta(seconds=self.rng.randint(0, 3)))

        self._flush_mobile_devices()
        return sorted(self.uploads, key=lambda u: u.received_at)

    def _upload(self, device: Device, received_at: datetime) -> None:
        if not device.outbox:
            return
        upload = Upload(self._uuid(), self.world.tenant_id, device.device_id, received_at, device.outbox)
        device.outbox = []
        self.uploads.append(upload)
        # The client never saw a response and sends the same events again.
        if self.rng.random() < 0.07:
            delay = (
                timedelta(days=self.rng.randint(1, 3))
                if self.rng.random() < 0.15
                else timedelta(minutes=self.rng.randint(1, 20))
            )
            self.uploads.append(
                Upload(
                    self._uuid(), upload.tenant_id, upload.device_id, received_at + delay, list(upload.events)
                )
            )

    def _flush_mobile_devices(self) -> None:
        # Walk the season in 10 minute steps; whenever a device is online and
        # has something queued, it syncs.
        start = self._utc(self.season[0], time(0))
        end = self._utc(self.season[1], time(23, 59)) + timedelta(days=6)
        step = timedelta(minutes=10)
        mobile = self.maintenance_devices + self.waterfront_devices
        queued: dict[str, list[dict]] = {d.device_id: [] for d in mobile}
        pending = {d.device_id: sorted(d.outbox, key=lambda e: e["device_seq"]) for d in mobile}
        for d in mobile:
            d.outbox = []

        now = start
        while (now <= end and any(pending.values())) or any(queued.values()):
            for d in mobile:
                while pending[d.device_id] and pending[d.device_id][0]["_created_at"] <= now:
                    queued[d.device_id].append(pending[d.device_id].pop(0))
                if queued[d.device_id] and not d.is_offline(now) and self.rng.random() < 0.6:
                    d.outbox = queued[d.device_id]
                    queued[d.device_id] = []
                    self._upload(d, now + timedelta(seconds=self.rng.randint(0, 590)))
            now += step

    def _work_orders(self):
        events = []
        maint_staff = self.world.staff_in("maintenance") or self.world.staff_in("admin")
        office_staff = self.world.staff_in("admin", "director")
        buildings = self.world.buildings
        assets_by_building: dict[str, list] = {}
        for a in self.world.assets:
            if a.status != "retired":
                assets_by_building.setdefault(a.building_code, []).append(a)

        day = self.season[0]
        while day <= self.season[1]:
            for _ in range(self.rng.randint(4, 10)):
                building = self.rng.choice(buildings)
                asset = self.rng.choice(assets_by_building.get(building.code, [None]))
                if self.rng.random() < 0.3:
                    asset = None
                wo_id = self._uuid()
                opened = self._utc(day, time(7)) + timedelta(minutes=self.rng.randint(0, 14 * 60))
                opener = self.web if self.rng.random() < 0.55 else self.rng.choice(self.maintenance_devices)
                reporter = self.rng.choice(office_staff if opener is self.web else maint_staff)
                events.append(
                    (
                        opened,
                        opener,
                        "work_order.opened",
                        {
                            "work_order_id": wo_id,
                            "building_code": building.code,
                            "asset_tag": asset.tag if asset else None,
                            "category": asset.category if asset else _category_for(building.type),
                            "priority": self.rng.choices(*PRIORITIES)[0],
                            "reported_by": reporter.code,
                        },
                    )
                )

                assignee = self.rng.choice(maint_staff)
                device = self.maintenance_devices[maint_staff.index(assignee) % len(self.maintenance_devices)]
                assigned = opened + timedelta(minutes=self.rng.randint(5, 240))
                events.append(
                    (
                        assigned,
                        self.web,
                        "work_order.assigned",
                        {
                            "work_order_id": wo_id,
                            "staff_code": assignee.code,
                        },
                    )
                )

                if self.rng.random() < 0.06:
                    continue  # still waiting on parts at the end of the season
                started = assigned + timedelta(minutes=self.rng.randint(10, 26 * 60))
                events.append(
                    (
                        started,
                        device,
                        "work_order.started",
                        {
                            "work_order_id": wo_id,
                            "staff_code": assignee.code,
                        },
                    )
                )
                labor = self.rng.randint(15, 8 * 60)
                completed = started + timedelta(minutes=labor + self.rng.randint(0, 90))
                events.append(
                    (
                        completed,
                        device,
                        "work_order.completed",
                        {
                            "work_order_id": wo_id,
                            "staff_code": assignee.code,
                            "labor_minutes": labor,
                            "parts_cost": round(self.rng.choice([0, 0, 0, self.rng.uniform(5, 400)]), 2),
                        },
                    )
                )
            day += timedelta(days=1)
        return events

    def _waterfront_checks(self):
        events = []
        lifeguards = self.world.staff_in("waterfront")
        sites = self.world.buildings_of("waterfront")
        day = self.season[0]
        while day <= self.season[1]:
            for site in sites:
                is_pool = any(word in site.name.lower() for word in ("pool", "piscine"))
                for slot in (time(8), time(12, 30), time(16, 30)):
                    at = self._utc(day, slot) + timedelta(minutes=self.rng.randint(-20, 20))
                    device = self.rng.choice(self.waterfront_devices)
                    events.append(
                        (
                            at,
                            device,
                            "waterfront.check_logged",
                            {
                                "check_id": self._uuid(),
                                "building_code": site.code,
                                "staff_code": self.rng.choice(lifeguards).code,
                                "chlorine_ppm": round(self.rng.gauss(2.2, 0.7), 1) if is_pool else None,
                                "ph": round(self.rng.gauss(7.5, 0.18), 2)
                                if is_pool
                                else round(self.rng.gauss(7.9, 0.3), 2),
                                "water_temp_f": round(self.rng.gauss(79 if is_pool else 72, 3), 1),
                            },
                        )
                    )
            day += timedelta(days=1)
        return events


def _category_for(building_type: str) -> str:
    return {"dining": "kitchen", "waterfront": "safety", "maintenance": "grounds"}.get(building_type, "other")
