"""Versioned data contracts, one YAML file per feed version."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

TYPES = {"string", "integer", "decimal", "date", "timestamp", "boolean"}


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class Field:
    name: str
    type: str
    required: bool = False
    allowed: tuple[str, ...] | None = None
    min: float | None = None
    max: float | None = None
    pattern: str | None = None
    references: tuple[str, str] | None = None
    label: str | None = None

    @property
    def display_name(self) -> str:
        return self.label or self.name.replace("_", " ")


@dataclass(frozen=True)
class Upgrade:
    rename: dict[str, str] = field(default_factory=dict)
    defaults: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Contract:
    feed: str
    version: int
    primary_key: tuple[str, ...]
    fields: dict[str, Field]
    upgrade_from: dict[int, Upgrade]
    description: str = ""

    @property
    def ref(self) -> str:
        return f"{self.feed}@{self.version}"

    @property
    def references(self) -> list[Field]:
        return [f for f in self.fields.values() if f.references]

    def key_of(self, record: dict) -> str | None:
        parts = [record.get(k) for k in self.primary_key]
        if any(p is None for p in parts):
            return None
        return "|".join(str(p) for p in parts)


def _parse_field(name: str, spec: dict) -> Field:
    if spec.get("type") not in TYPES:
        raise ContractError(f"{name}: unknown type {spec.get('type')!r}")
    references = None
    if "references" in spec:
        feed, _, ref_field = spec["references"].partition(".")
        references = (feed, ref_field)
    return Field(
        name=name,
        type=spec["type"],
        required=spec.get("required", False),
        allowed=tuple(spec["allowed"]) if "allowed" in spec else None,
        min=spec.get("min"),
        max=spec.get("max"),
        pattern=spec.get("pattern"),
        references=references,
        label=spec.get("label"),
    )


def load_contract(path: Path) -> Contract:
    raw = yaml.safe_load(path.read_text())
    fields = {name: _parse_field(name, spec) for name, spec in raw["fields"].items()}
    missing_pk = set(raw["primary_key"]) - fields.keys()
    if missing_pk:
        raise ContractError(f"{path}: primary key fields not defined: {sorted(missing_pk)}")
    upgrades = {
        int(v): Upgrade(rename=u.get("rename", {}), defaults=u.get("defaults", {}))
        for v, u in (raw.get("upgrade_from") or {}).items()
    }
    return Contract(
        feed=raw["feed"],
        version=int(raw["version"]),
        primary_key=tuple(raw["primary_key"]),
        fields=fields,
        upgrade_from=upgrades,
        description=raw.get("description", "").strip(),
    )


class ContractRegistry:
    def __init__(self, root: Path):
        self._contracts: dict[str, dict[int, Contract]] = {}
        for path in sorted(root.glob("*/v*.yml")):
            contract = load_contract(path)
            self._contracts.setdefault(contract.feed, {})[contract.version] = contract

    @property
    def feeds(self) -> list[str]:
        return sorted(self._contracts)

    def get(self, ref: str) -> Contract:
        feed, _, version = ref.partition("@")
        try:
            return self._contracts[feed][int(version)]
        except (KeyError, ValueError):
            raise ContractError(f"no contract {ref!r}") from None

    def latest(self, feed: str) -> Contract:
        versions = self._contracts[feed]
        return versions[max(versions)]

    def versions(self, feed: str) -> list[Contract]:
        return [self._contracts[feed][v] for v in sorted(self._contracts[feed])]

    def upgrade(self, record: dict, contract: Contract) -> dict:
        """Carry a record that passed `contract` forward to the latest version."""
        latest = self.latest(contract.feed)
        out = dict(record)
        for version in range(contract.version + 1, latest.version + 1):
            step = self._contracts[contract.feed][version].upgrade_from.get(version - 1)
            if step is None:
                raise ContractError(f"{contract.feed}@{version} has no upgrade from v{version - 1}")
            for old, new in step.rename.items():
                if old in out:
                    out[new] = out.pop(old)
            for name, value in step.defaults.items():
                if out.get(name) is None:
                    out[name] = value
        return {name: out.get(name) for name in latest.fields}
