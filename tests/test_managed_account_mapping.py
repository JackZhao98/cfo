from cfo.commands.portfolio import _rh_account_to_cfo


def test_managed_individual_maps_to_distinct_cfo_id():
    managed = _rh_account_to_cfo(
        {
            "account_number": "181785371244",
            "brokerage_account_type": "individual",
            "management_type": "managed",
            "portfolio_value": 1507.58,
            "cash": 7.65,
            "holdings": [],
        }
    )
    trading = _rh_account_to_cfo(
        {
            "account_number": "597357623",
            "brokerage_account_type": "individual",
            "management_type": "self_directed",
            "portfolio_value": 8043.00,
            "cash": 7450.38,
            "holdings": [],
        }
    )

    assert managed.id == "rh-managed-individual"
    assert trading.id == "rh-individual"
    assert managed.id != trading.id
