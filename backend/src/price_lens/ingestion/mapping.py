import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def normalize_alias(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


@dataclass(frozen=True)
class MappingDecision:
    family_name: str | None
    origin_type: str
    variety: str | None
    analytics_included: bool
    mapping_version: str
    matched: bool
    reason: str


@dataclass(frozen=True)
class FamilyDefinition:
    canonical_name: str
    slug: str
    display_name: str
    category: str
    default_include_imported: bool
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class _CodeMapping:
    family_name: str
    expected_names: frozenset[str]
    origin_type: str
    variety: str | None
    analytics_included: bool


class ProductMappingRegistry:
    def __init__(self, document: dict[str, Any]) -> None:
        self.version = str(document["version"])
        self.source = str(document["source"])
        self.families: list[FamilyDefinition] = []
        self._by_code: dict[str, _CodeMapping] = {}

        for raw_family in document["families"]:
            family = FamilyDefinition(
                canonical_name=raw_family["canonical_name"],
                slug=raw_family["slug"],
                display_name=raw_family["display_name"],
                category=raw_family["category"],
                default_include_imported=raw_family["default_include_imported"],
                aliases=tuple(raw_family["aliases"]),
            )
            self.families.append(family)
            for group in raw_family["source_mappings"]:
                entry = _CodeMapping(
                    family_name=family.canonical_name,
                    expected_names=frozenset(name.strip() for name in group["expected_names"]),
                    origin_type=group["origin_type"],
                    variety=group["variety"],
                    analytics_included=group["analytics_included"],
                )
                for code in group["codes"]:
                    if code in self._by_code:
                        raise ValueError(f"Duplicate product code in mapping: {code}")
                    self._by_code[code] = entry

    @classmethod
    def load_default(cls) -> "ProductMappingRegistry":
        path = Path(__file__).parent / "mappings" / "product_mappings.v1.json"
        with path.open(encoding="utf-8") as file:
            return cls(json.load(file))

    @property
    def mapped_codes(self) -> frozenset[str]:
        return frozenset(self._by_code)

    def resolve(self, source_code: str, source_name: str) -> MappingDecision:
        mapping = self._by_code.get(source_code)
        detected_origin = "imported" if "進口" in source_name else "unknown"
        if mapping is None:
            return MappingDecision(
                family_name=None,
                origin_type=detected_origin,
                variety=_extract_variety(source_name),
                analytics_included=False,
                mapping_version=self.version,
                matched=False,
                reason="unmapped_source_code",
            )

        normalized_name = source_name.strip()
        if mapping.expected_names and normalized_name not in mapping.expected_names:
            return MappingDecision(
                family_name=None,
                origin_type=detected_origin,
                variety=_extract_variety(source_name),
                analytics_included=False,
                mapping_version=self.version,
                matched=False,
                reason="source_name_mismatch",
            )

        return MappingDecision(
            family_name=mapping.family_name,
            origin_type=mapping.origin_type,
            variety=mapping.variety,
            analytics_included=mapping.analytics_included,
            mapping_version=self.version,
            matched=True,
            reason="explicit_code_and_name_match",
        )


def _extract_variety(source_name: str) -> str | None:
    parts = source_name.split("-", maxsplit=1)
    return parts[1].strip() if len(parts) == 2 and parts[1].strip() else None
