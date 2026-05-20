from quantuum.db import models


def test_all_tables_registered():
    names = set(models.SQLModel.metadata.tables.keys())
    assert {
        "tenants",
        "accounts",
        "account_identities",
        "account_refresh_tokens",
        "natal_profiles",
        "blueprints",
        "requests",
        "account_balance",
    } <= names


def test_blueprint_defaults():
    bp = models.Blueprint(tenant_id=1, account_id=1, natal_profile_id=1)
    assert bp.status == "pending"
    assert bp.calc_md is None
