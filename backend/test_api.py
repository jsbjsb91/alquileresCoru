"""
Unit tests for the A Coruña Rental Market Backend API and ML valuation system.
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import HTTPException
from backend.main import (
    health_check,
    list_neighborhoods,
    get_properties,
    get_property_by_id,
    get_neighborhood_stats,
    get_market_summary,
    predict_rental_price,
)
from backend.schemas import ValuationRequest
from backend.ml_model import predict_valuation, load_model


def test_model_loading_and_metrics():
    bundle = load_model()
    assert bundle is not None
    assert "metrics" in bundle
    metrics = bundle["metrics"]
    assert metrics["r2"] >= 0.90, f"R² score {metrics['r2']} should be >= 0.90"
    assert metrics["mae"] <= 120.0, f"MAE {metrics['mae']} should be <= 120.0"
    print(f" [PASS] ML Model Metrics: R² = {metrics['r2']}, MAE = {metrics['mae']} €/m, RMSE = {metrics['rmse']} €/m")


def test_health_endpoint():
    res = health_check()
    assert res.status == "ok"
    assert res.total_listings >= 850
    assert res.model_loaded is True
    assert res.model_metrics is not None
    assert res.model_metrics["r2"] >= 0.90
    print(" [PASS] Health Check Endpoint verified.")


def test_neighborhoods_endpoint():
    neighborhoods = list_neighborhoods()
    assert len(neighborhoods) >= 10
    slugs = {n["neighborhood_id"] for n in neighborhoods}
    assert "pescaderia_ensanche" in slugs
    assert "monte_alto" in slugs
    assert "riazor_ciudad_jardin" in slugs
    assert "ciudad_vieja" in slugs
    print(f" [PASS] Neighborhoods Endpoint: {len(neighborhoods)} neighborhoods loaded correctly.")


def test_get_properties_pagination():
    res = get_properties(page=1, page_size=15)
    assert res.total >= 850
    assert res.page == 1
    assert res.page_size == 15
    assert len(res.items) == 15
    assert res.total_pages >= 57
    print(" [PASS] Properties Pagination (page 1, size 15).")


def test_get_properties_filters():
    # Filter 1: Monte Alto with parking
    res_ma = get_properties(neighborhood_id="monte_alto", has_parking=True)
    assert res_ma.total > 0
    for p in res_ma.items:
        assert p.neighborhood_id == "monte_alto"
        assert p.has_parking is True

    # Filter 2: Price range [700, 1000] and rooms >= 2
    res_price = get_properties(min_price=700, max_price=1000, min_rooms=2)
    assert res_price.total > 0
    for p in res_price.items:
        assert 700 <= p.price_month <= 1000
        assert p.rooms >= 2

    # Filter 3: Sorting price descending
    res_sort = get_properties(sort_by="price_desc", page_size=5)
    prices = [p.price_month for p in res_sort.items]
    assert prices == sorted(prices, reverse=True)
    print(" [PASS] Property Filters and Sorting verified.")


def test_get_property_by_id():
    # Fetch first property ID
    first_prop = get_properties(page=1, page_size=1).items[0]
    prop_id = first_prop.id

    detail = get_property_by_id(prop_id)
    assert detail.id == prop_id
    assert detail.valuation is not None
    assert detail.valuation.predicted_price > 0
    assert detail.valuation.market_verdict in [
        "Oportunidad / Muy buen precio",
        "Precio de mercado",
        "Sobreprecio",
    ]
    assert detail.valuation.price_range_min < detail.valuation.predicted_price < detail.valuation.price_range_max

    # Test Not Found
    try:
        get_property_by_id("coruna-nonexistent-id-99999")
        assert False, "Should have raised HTTPException 404"
    except HTTPException as e:
        assert e.status_code == 404
        assert "no encontrado" in e.detail

    print(" [PASS] Property Detail with ML Valuation & 404 Handling.")


def test_neighborhood_stats():
    stats = get_neighborhood_stats()
    assert len(stats) >= 10
    total_listings = sum(s.count for s in stats)
    assert total_listings >= 850

    # Ensure all neighborhoods have positive stats
    for s in stats:
        assert s.avg_price > 0
        assert s.avg_price_sqm > 0
        assert s.std_price >= 0

    # Ensanche or Ciudad Vieja or Riazor should be among the highest €/m²
    top_neighborhood = stats[0]
    assert top_neighborhood.avg_price_sqm >= 13.0
    print(f" [PASS] Neighborhood Stats: Top neighborhood = {top_neighborhood.neighborhood} ({top_neighborhood.avg_price_sqm:.2f} €/m²).")


def test_market_summary():
    summary = get_market_summary()
    assert summary.total_properties >= 850
    assert summary.avg_price > 500
    assert summary.avg_price_sqm > 8.0
    assert len(summary.most_expensive_neighborhoods) == 3
    assert len(summary.cheapest_neighborhoods) == 3
    assert "piso" in summary.property_type_distribution
    assert "pct_elevator" in summary.amenities_pct
    assert summary.amenities_pct["pct_elevator"] > 50.0
    print(f" [PASS] Market Summary: City Avg Price = {summary.avg_price:.2f} €/m, Avg €/m² = {summary.avg_price_sqm:.2f}.")


def test_valuation_prediction_scenarios():
    # Scenario A: Bargain / Opportunity in Ensanche
    req_deal = ValuationRequest(
        neighborhood_id="pescaderia_ensanche",
        sqm=95.0,
        rooms=3,
        bathrooms=2,
        has_elevator=True,
        has_parking=True,
        furnished=True,
        is_exterior=True,
        property_type="piso",
        offered_price=850.0,  # Far below estimated ~1600+
    )
    val_deal = predict_rental_price(req_deal)
    assert val_deal.predicted_price > 1200
    assert val_deal.market_verdict == "Oportunidad / Muy buen precio"
    assert val_deal.deviation_pct is not None and val_deal.deviation_pct < -12.0

    # Scenario B: Overpriced in Los Mallos
    req_expensive = ValuationRequest(
        neighborhood_id="los_mallos",
        sqm=55.0,
        rooms=1,
        bathrooms=1,
        has_elevator=False,
        has_parking=False,
        furnished=False,
        is_exterior=False,
        property_type="piso",
        offered_price=1600.0,  # Far above estimated ~500
    )
    val_exp = predict_rental_price(req_expensive)
    assert val_exp.market_verdict == "Sobreprecio"
    assert val_exp.deviation_pct is not None and val_exp.deviation_pct > 12.0

    # Scenario C: Fair market price
    fair_price = val_deal.predicted_price
    req_fair = ValuationRequest(
        neighborhood_id="pescaderia_ensanche",
        sqm=95.0,
        rooms=3,
        bathrooms=2,
        has_elevator=True,
        has_parking=True,
        furnished=True,
        is_exterior=True,
        property_type="piso",
        offered_price=fair_price,
    )
    val_fair = predict_rental_price(req_fair)
    assert val_fair.market_verdict == "Precio de mercado"
    assert abs(val_fair.deviation_pct) < 1.0

    # Scenario D: Valuation without offered price
    req_neutral = ValuationRequest(
        neighborhood_id="monte_alto",
        sqm=70.0,
        rooms=2,
        bathrooms=1,
        has_elevator=True,
        has_parking=False,
        furnished=False,
        is_exterior=True,
        property_type="piso",
    )
    val_neutral = predict_rental_price(req_neutral)
    assert val_neutral.predicted_price > 0
    assert val_neutral.deviation_pct is None
    assert val_neutral.market_verdict == "Precio de mercado"

    print(" [PASS] ML Valuation Simulation (Opportunity, Overpriced, Fair, Neutral).")


if __name__ == "__main__":
    print("==================================================")
    print(" Running Backend & ML Valuation Test Suite")
    print("==================================================")
    test_model_loading_and_metrics()
    test_health_endpoint()
    test_neighborhoods_endpoint()
    test_get_properties_pagination()
    test_get_properties_filters()
    test_get_property_by_id()
    test_neighborhood_stats()
    test_market_summary()
    test_valuation_prediction_scenarios()
    print("==================================================")
    print(" ALL TESTS PASSED! API & ML SUITE FULLY OPERATIONAL")
    print("==================================================")
