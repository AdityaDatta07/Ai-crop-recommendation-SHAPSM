"""The money maths.

Worth testing hard: this is the only place in the system where money is
computed, and a wrong number here reaches the farmer looking exactly as
authoritative as a right one.
"""

from __future__ import annotations

import pytest

from apps.api.services import economics


class TestInputCost:
    def test_derives_per_hectare_from_per_quintal(self):
        # 1239 Rs/quintal at 3595 kg/ha = 35.95 q/ha -> 44,542 Rs/ha
        assert economics.input_cost_per_ha(1239, 3595) == 44542

    def test_returns_none_when_either_input_is_missing(self):
        assert economics.input_cost_per_ha(None, 3595) is None
        assert economics.input_cost_per_ha(1239, None) is None


class TestCompute:
    def test_full_calculation_reconciles(self):
        """Hand-checked: 4.2 t/ha x 1.5 ha x 10 q/t x Rs 2400/q = Rs 151,200."""
        result = economics.compute(
            expected_yield_t_ha=4.2,
            published_yield_kg_per_ha=3850,
            cost_a2fl_per_quintal=1000,
            price_per_quintal=2400,
            area_ha=1.5,
            price_source="test",
            price_as_of=None,
        )
        assert result.gross_revenue == 151200
        assert result.input_cost_per_ha == 38500          # 1000 x 38.5 q/ha
        assert result.net_margin == 151200 - round(38500 * 1.5)
        assert result.margin_per_ha == round(result.net_margin / 1.5)

    def test_margin_per_ha_is_consistent_with_net_margin(self):
        result = economics.compute(
            expected_yield_t_ha=3.0,
            published_yield_kg_per_ha=3000,
            cost_a2fl_per_quintal=1200,
            price_per_quintal=2000,
            area_ha=2.5,
            price_source="test",
            price_as_of=None,
        )
        assert result.margin_per_ha == pytest.approx(result.net_margin / 2.5, abs=1)

    def test_no_price_leaves_revenue_null_but_keeps_cost(self):
        """Degrade, never collapse: the cost figure is still useful on its own."""
        result = economics.compute(
            expected_yield_t_ha=25.0,
            published_yield_kg_per_ha=25000,
            cost_a2fl_per_quintal=None,
            price_per_quintal=None,
            area_ha=1.0,
            price_source=None,
            price_as_of=None,
        )
        assert result.gross_revenue is None
        assert result.net_margin is None
        assert result.margin_per_ha is None
        assert result.expected_yield_t_ha == 25.0

    def test_never_substitutes_zero_for_unknown(self):
        """A zero margin and an unknown margin are different claims."""
        result = economics.compute(
            expected_yield_t_ha=None,
            published_yield_kg_per_ha=None,
            cost_a2fl_per_quintal=None,
            price_per_quintal=None,
            area_ha=1.0,
            price_source=None,
            price_as_of=None,
        )
        for value in (
            result.gross_revenue,
            result.net_margin,
            result.margin_per_ha,
            result.input_cost_per_ha,
        ):
            assert value is None and value != 0

    def test_price_source_is_not_claimed_without_a_price(self):
        result = economics.compute(
            expected_yield_t_ha=2.0,
            published_yield_kg_per_ha=2000,
            cost_a2fl_per_quintal=1000,
            price_per_quintal=None,
            area_ha=1.0,
            price_source="Agmarknet",
            price_as_of=None,
        )
        assert result.price_source is None

    def test_scales_linearly_with_area(self):
        def net(area: float) -> int:
            return economics.compute(
                expected_yield_t_ha=4.0,
                published_yield_kg_per_ha=4000,
                cost_a2fl_per_quintal=1000,
                price_per_quintal=2000,
                area_ha=area,
                price_source="test",
                price_as_of=None,
            ).net_margin

        assert net(2.0) == pytest.approx(net(1.0) * 2, abs=1)
