import random
from datetime import date, datetime, time, timedelta

from campcommand.synthetic.world import World

CATALOGS = {
    "en": [
        ("Freeze pop", "snack", 1.00),
        ("Granola bar", "snack", 1.50),
        ("Chips", "snack", 1.75),
        ("Candy bar", "snack", 2.00),
        ("Trail mix", "snack", 2.50),
        ("Ice cream sandwich", "snack", 2.75),
        ("Bottled water", "drink", 1.25),
        ("Lemonade", "drink", 1.75),
        ("Sports drink", "drink", 2.25),
        ("Camp T-shirt", "apparel", 18.00),
        ("Hoodie", "apparel", 38.00),
        ("Bucket hat", "apparel", 16.00),
        ("Sunscreen", "toiletries", 8.50),
        ("Bug spray", "toiletries", 7.50),
        ("Toothpaste", "toiletries", 3.50),
        ("Flashlight", "supplies", 9.00),
        ("Stationery set", "supplies", 4.50),
        ("Stamps (5)", "supplies", 3.40),
        ("Postcard", "souvenir", 1.00),
        ("Friendship bracelet kit", "souvenir", 6.00),
        ("Water bottle", "souvenir", 14.00),
    ],
    "fr": [
        ("Popsicle", "snack", 1.00),
        ("Barre tendre", "snack", 1.50),
        ("Croustilles", "snack", 1.75),
        ("Tablette de chocolat", "snack", 2.00),
        ("Mélange du randonneur", "snack", 2.50),
        ("Eau en bouteille", "drink", 1.25),
        ("Limonade", "drink", 1.75),
        ("Jus de pomme", "drink", 1.50),
        ("T-shirt du camp", "apparel", 20.00),
        ("Kangourou", "apparel", 42.00),
        ("Casquette", "apparel", 18.00),
        ("Crème solaire", "toiletries", 9.50),
        ("Chasse-moustiques", "toiletries", 8.00),
        ("Lampe de poche", "supplies", 10.00),
        ("Papier à lettres", "supplies", 4.50),
        ("Carte postale", "souvenir", 1.25),
        ("Gourde", "souvenir", 15.00),
    ],
}

PAYMENT_WEIGHTS = {"camper_account": 70, "cash": 14, "card": 16}


def generate_sales(world: World, season_start: date, season_end: date, seed: int) -> list[dict]:
    rng = random.Random(f"{world.tenant_id}-sales-{seed}")
    language = "fr" if world.tenant_id == "chene_rouge" else "en"
    catalog = [
        {
            "sku": f"{(700000 + i * 37) % 999999:06d}",
            "item_name": name,
            "item_category": cat,
            "unit_price": price,
        }
        for i, (name, cat, price) in enumerate(CATALOGS[language])
    ]
    store = world.buildings_of("store")[0]
    cashiers = world.staff_in("store") or world.staff_in("admin")
    methods, weights = list(PAYMENT_WEIGHTS), list(PAYMENT_WEIGHTS.values())

    lines = []
    seq = rng.randint(10000, 50000)
    day = season_start
    while day <= season_end:
        base = 55 if day.weekday() == 6 else 120
        for _ in range(int(base * rng.uniform(0.8, 1.2))):
            seq += 1
            sold_at = datetime.combine(day, time(9)) + timedelta(minutes=rng.randint(0, 11 * 60 + 30))
            txn = _transaction_id(world.tenant_id, seq, day)
            cashier = rng.choice(cashiers)
            method = rng.choices(methods, weights)[0]
            for line_number, item in enumerate(rng.sample(catalog, rng.choice([1, 1, 1, 2, 2, 3])), 1):
                lines.append(
                    {
                        "transaction_id": txn,
                        "line_number": line_number,
                        "sold_at": sold_at,
                        "store_building_code": store.code,
                        "cashier_staff_code": cashier.code,
                        "sku": item["sku"],
                        "item_name": item["item_name"],
                        "item_category": item["item_category"],
                        "quantity": rng.choices([1, 2, 3, 4], [80, 14, 4, 2])[0],
                        "unit_price": item["unit_price"],
                        "payment_method": method,
                    }
                )
        day += timedelta(days=1)
    return lines


def _transaction_id(tenant_id: str, seq: int, day: date) -> str:
    if tenant_id == "tall_pines":
        return f"R{seq:06d}"
    if tenant_id == "lakeview":
        return f"T-{day:%y%m%d}-{seq % 10000:04d}"
    return f"V{seq:07d}"
