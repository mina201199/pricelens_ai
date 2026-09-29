from price_lens.ingestion.mapping import ProductMappingRegistry, normalize_alias


def test_cabbage_uses_explicit_source_codes() -> None:
    registry = ProductMappingRegistry.load_default()

    domestic = registry.resolve("LA1", "甘藍-初秋")
    imported = registry.resolve("LA91", "甘藍-進口 初秋")
    kohlrabi = registry.resolve("SW1", "球莖甘藍")

    assert domestic.family_name == "甘藍"
    assert domestic.analytics_included is True
    assert domestic.origin_type == "domestic"
    assert imported.family_name == "甘藍"
    assert imported.analytics_included is False
    assert imported.origin_type == "imported"
    assert kohlrabi.family_name == "球莖甘藍"
    assert kohlrabi.analytics_included is True


def test_name_mismatch_fails_closed() -> None:
    registry = ProductMappingRegistry.load_default()
    result = registry.resolve("LA1", "球莖甘藍")
    assert result.matched is False
    assert result.family_name is None
    assert result.analytics_included is False
    assert result.reason == "source_name_mismatch"


def test_substring_is_not_mapping_strategy() -> None:
    registry = ProductMappingRegistry.load_default()
    result = registry.resolve("UNLISTED", "甘藍-看似相同但無官方 mapping")
    assert result.family_name is None
    assert result.analytics_included is False


def test_alias_normalization() -> None:
    assert normalize_alias(" 高 麗 菜 ") == "高麗菜"
