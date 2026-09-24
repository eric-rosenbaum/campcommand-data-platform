"""The 'true' reference data for each synthetic camp.

Exports (with whatever mess a given client adds) and app events are both
generated from this, so events refer to buildings, assets and staff that
really exist even when the client's spreadsheet gets them wrong.
"""

import random
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

from faker import Faker


@dataclass(frozen=True)
class Building:
    code: str
    name: str
    type: str
    capacity: int | None
    year_built: int | None


@dataclass(frozen=True)
class Asset:
    tag: str
    name: str
    category: str
    building_code: str
    purchased_on: date | None
    cost: float | None
    status: str


@dataclass(frozen=True)
class Staff:
    code: str
    first_name: str
    last_name: str
    role: str
    email: str
    start_date: date
    is_active: bool


@dataclass
class World:
    tenant_id: str
    buildings: list[Building]
    assets: list[Asset]
    staff: list[Staff]

    def buildings_of(self, *types: str) -> list[Building]:
        return [b for b in self.buildings if b.type in types]

    def staff_in(self, *roles: str) -> list[Staff]:
        return [s for s in self.staff if s.role in roles and s.is_active]


@dataclass(frozen=True)
class Style:
    """Per-camp naming conventions."""

    building_code: str
    asset_tag: str
    staff_code: str
    email_domain: str
    locale: str
    cabin_names: tuple[str, ...]
    named_buildings: dict[str, tuple[str, ...]]
    waterfronts: tuple[str, ...]


STYLES = {
    "tall_pines": Style(
        building_code="TP-{:03d}",
        asset_tag="TP-{:05d}",
        staff_code="E{:04d}",
        email_domain="tallpines.example.org",
        locale="en_US",
        cabin_names=(
            "Birch",
            "Hemlock",
            "Spruce",
            "Tamarack",
            "Cedar",
            "Balsam",
            "Aspen",
            "Juniper",
            "Larch",
            "Maple",
            "Alder",
            "Willow",
            "Hickory",
            "Chestnut",
            "Sycamore",
            "Poplar",
            "Beech",
            "Linden",
        ),
        named_buildings={
            "dining": ("Dining Hall",),
            "program": ("Arts & Crafts Barn", "Archery Range Shed", "Climbing Tower", "Nature Lodge"),
            "admin": ("Main Office",),
            "health": ("Health Center",),
            "maintenance": ("Maintenance Shop",),
            "store": ("Trading Post",),
            "other": ("Staff Lounge",),
        },
        waterfronts=("Lake Beach", "Boathouse"),
    ),
    "lakeview": Style(
        building_code="B{:03d}",
        asset_tag="LV{:05d}",
        staff_code="S-{:04d}",
        email_domain="lakeviewcamp.example.org",
        locale="en_US",
        cabin_names=(
            "Heron",
            "Loon",
            "Osprey",
            "Kingfisher",
            "Otter",
            "Beaver",
            "Mallard",
            "Pike",
            "Walleye",
            "Bluegill",
            "Sturgeon",
            "Muskie",
            "Trillium",
            "Dune",
        ),
        named_buildings={
            "dining": ("Mess Hall",),
            "program": ("Rec Hall", "Ropes Course Hut", "Music Shack"),
            "admin": ("Welcome Center",),
            "health": ("Infirmary",),
            "maintenance": ("Facilities Garage",),
            "store": ("Canteen",),
        },
        waterfronts=("Swim Dock", "Pool"),
    ),
    "chene_rouge": Style(
        building_code="CR-{:02d}",
        asset_tag="CR-EQ-{:04d}",
        staff_code="M{:03d}",
        email_domain="chenerouge.example.org",
        locale="fr_CA",
        cabin_names=(
            "des Érables",
            "des Bouleaux",
            "des Pins",
            "des Cèdres",
            "des Mélèzes",
            "des Sapins",
            "des Trembles",
            "des Chênes",
            "des Ormes",
            "des Frênes",
            "des Saules",
            "des Épinettes",
        ),
        named_buildings={
            "dining": ("Salle à manger",),
            "program": ("Atelier d'arts", "Pavillon nature", "Tir à l'arc"),
            "admin": ("Bureau principal",),
            "health": ("Infirmerie",),
            "maintenance": ("Atelier d'entretien",),
            "store": ("Magasin général",),
        },
        waterfronts=("Plage du lac", "Piscine"),
    ),
}

ASSET_CATALOG = {
    "cabin": [
        ("Wall heater", "hvac", 450),
        ("Ceiling fan", "electrical", 180),
        ("Water heater", "plumbing", 1200),
        ("Smoke detector", "safety", 40),
    ],
    "dining": [
        ("Walk-in cooler", "kitchen", 14000),
        ("Six-burner range", "kitchen", 5200),
        ("Commercial dishwasher", "kitchen", 9800),
        ("Rooftop HVAC unit", "hvac", 16500),
        ("Grease trap", "plumbing", 2400),
        ("Ice machine", "kitchen", 3900),
    ],
    "waterfront": [
        ("Aluminum canoe", "watercraft", 1400),
        ("Sit-on-top kayak", "watercraft", 650),
        ("Sunfish sailboat", "watercraft", 4200),
        ("Rescue boat outboard", "watercraft", 7800),
        ("AED", "safety", 1600),
        ("Pool pump", "plumbing", 2800),
        ("Chlorinator", "plumbing", 1900),
        ("Lifeguard chair", "safety", 900),
    ],
    "program": [
        ("Climbing wall auto-belay", "recreation", 3200),
        ("Archery target set", "recreation", 700),
        ("Pottery kiln", "electrical", 4500),
        ("PA system", "electrical", 1300),
    ],
    "admin": [("Office HVAC split unit", "hvac", 3800), ("Backup generator", "electrical", 9000)],
    "health": [
        ("Medical refrigerator", "kitchen", 2100),
        ("AED", "safety", 1600),
        ("Mini-split heat pump", "hvac", 4100),
    ],
    "maintenance": [
        ("Utility vehicle", "vehicle", 14500),
        ("Pickup truck", "vehicle", 38000),
        ("Riding mower", "grounds", 4200),
        ("Chainsaw", "grounds", 450),
        ("Pressure washer", "grounds", 650),
        ("Golf cart", "vehicle", 6500),
    ],
    "store": [("Beverage cooler", "kitchen", 2300), ("POS terminal", "electrical", 900)],
    "other": [("Window AC unit", "hvac", 380)],
}

ROLE_MIX = [
    ("counselor", 0.52),
    ("kitchen", 0.12),
    ("waterfront", 0.12),
    ("maintenance", 0.08),
    ("health", 0.04),
    ("store", 0.04),
    ("admin", 0.06),
    ("director", 0.02),
]


def build_world(tenant_id: str, seed: int, season_start: date) -> World:
    style = STYLES[tenant_id]
    rng = random.Random(f"{tenant_id}-{seed}")
    fake = Faker(style.locale)
    fake.seed_instance(rng.randint(0, 10**9))

    buildings = []
    n = 0

    def add(name: str, btype: str, capacity: int | None) -> None:
        nonlocal n
        n += 1
        year = rng.choice([None, *range(1948, 2024)]) if rng.random() < 0.9 else None
        buildings.append(Building(style.building_code.format(n), name, btype, capacity, year))

    for cabin in style.cabin_names:
        label = f"Chalet {cabin}" if style.locale == "fr_CA" else f"{cabin} Cabin"
        add(label, "cabin", rng.choice([8, 10, 12, 14]))
    for btype, names in style.named_buildings.items():
        for name in names:
            capacity = {"dining": 320, "health": 12}.get(btype)
            add(name, btype, capacity)
    for name in style.waterfronts:
        add(name, "waterfront", None)

    assets = []
    tag = rng.randint(100, 900)
    for b in buildings:
        catalog = ASSET_CATALOG[b.type]
        count = len(catalog) if b.type != "cabin" else rng.randint(2, 4)
        picks = catalog if b.type != "cabin" else rng.sample(catalog, count)
        for name, category, base_cost in picks:
            copies = rng.randint(2, 6) if category == "watercraft" else 1
            for _ in range(copies):
                tag += rng.randint(1, 7)
                purchased = date(
                    rng.randint(2008, season_start.year - 1), rng.randint(1, 12), rng.randint(1, 28)
                )
                status = rng.choices(
                    ["in_service", "needs_repair", "out_of_service", "retired"], [85, 9, 4, 2]
                )[0]
                assets.append(
                    Asset(
                        tag=style.asset_tag.format(tag),
                        name=name,
                        category=category,
                        building_code=b.code,
                        purchased_on=purchased if rng.random() < 0.92 else None,
                        cost=round(base_cost * rng.uniform(0.8, 1.25), 2) if rng.random() < 0.9 else None,
                        status=status,
                    )
                )

    staff = []
    headcount = rng.randint(80, 110)
    roles = [r for r, _ in ROLE_MIX]
    weights = [w for _, w in ROLE_MIX]
    code = rng.randint(100, 400)
    used_emails = set()
    for i in range(headcount):
        role = roles[i] if i < len(roles) else rng.choices(roles, weights)[0]
        first, last = fake.first_name(), fake.last_name()
        code += rng.randint(1, 9)
        email = _email(first, last, style.email_domain, used_emails)
        year_round = role in ("director", "maintenance", "admin")
        start = (
            date(rng.randint(2012, season_start.year - 1), rng.randint(1, 12), 1)
            if year_round
            else season_start - timedelta(days=rng.randint(7, 21))
        )
        staff.append(
            Staff(
                code=style.staff_code.format(code),
                first_name=first,
                last_name=last,
                role=role,
                email=email,
                start_date=start,
                is_active=rng.random() > 0.04,
            )
        )

    return World(tenant_id, buildings, assets, staff)


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower().replace(" ", "")


def _email(first: str, last: str, domain: str, used: set[str]) -> str:
    base = f"{_ascii(first)}.{_ascii(last)}"
    email, n = f"{base}@{domain}", 1
    while email in used:
        n += 1
        email = f"{base}{n}@{domain}"
    used.add(email)
    return email
