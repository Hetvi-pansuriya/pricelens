"""
module1_revenue.py
─────────────────────────────────────────────────────────────────────────────
PURPOSE: Module 1 — Revenue Impact Analysis (pure Python math, NO AI required).

What it does:
  Calculates the company's current Monthly Recurring Revenue (MRR) from all
  pricing tiers. Then simulates 3 price-increase scenarios (+10%, +20%, +30%)
  and estimates how much revenue would increase AND how many users would leave
  (using industry-specific price elasticity data).

WHY no AI? This module only does math — addition, multiplication, percentages.
AI is not needed, and avoiding it makes M1 faster and more reliable.

CONNECTED TO:
  - analysis.py  → calls run_module1(company_data) wrapped in asyncio.to_thread()
                   (it's synchronous, so thread wrapping is needed)
  - analysis.py  → M1 output is passed as input to M3 (competitor benchmark)
                   and M4 (pricing recommendations) for context
  - models.py    → PricingTier.price and PricingTier.user_count are the inputs
  - schemas.py   → TierCreate validates price (ge=0) and user_count (ge=0)
  - json_report  → M1 output stored in Report.json_report["module1_revenue"]
"""

from typing import Any

ELASTICITY: dict[str, dict[str, float]] = {
    "saas_b2b": {"+10%": 0.03, "+20%": 0.08, "+30%": 0.18},  # low sensitivity (B2B)
    "saas_b2c": {"+10%": 0.08, "+20%": 0.18, "+30%": 0.32},  # high sensitivity (B2C)
    "default":  {"+10%": 0.05, "+20%": 0.12, "+30%": 0.25},  # middle ground (other)
}

SCENARIOS = ["+10%", "+20%", "+30%"]

MULTIPLIERS = {"+10%": 1.10, "+20%": 1.20, "+30%": 1.30}


def _resolve_elasticity(industry: str) -> dict[str, float]:
    industry_lower = industry.lower().replace(" ", "_")

    for key in ELASTICITY:
        if key in industry_lower:   # e.g., "saas_b2b" in "saas_b2b_enterprise" → True
            return ELASTICITY[key]  # return the matching elasticity dict

    return ELASTICITY["default"]


def run_module1(company_data: dict) -> dict:
    """
    Synchronous revenue simulation.
    Expected company_data keys: name, industry, tiers (list of tier dicts).
    """
    industry = company_data.get("industry", "")

    tiers = company_data.get("tiers", [])

    elasticity = _resolve_elasticity(industry)

    current_mrr = sum(t["price"] * t["user_count"] for t in tiers)

    scenario_totals: dict[str, float] = {s: 0.0 for s in SCENARIOS}

    scenario_user_loss: dict[str, float] = {s: 0.0 for s in SCENARIOS}

    total_users = max(sum(t["user_count"] for t in tiers), 1)

    per_tier_results = []

    for tier in tiers:
        price = tier["price"]       # e.g., 49.0 (dollars per month)
        users = tier["user_count"]  # e.g., 200 (current users on this tier)

        tier_current_mrr = price * users  # e.g., 49.0 × 200 = 9800.0

        tier_scenarios: dict[str, Any] = {}

        for scenario in SCENARIOS:
            loss_pct = elasticity[scenario]

            remaining_users = users * (1 - loss_pct)

            new_price = price * MULTIPLIERS[scenario]

            new_mrr = remaining_users * new_price

            tier_scenarios[scenario] = {
                "projected_mrr": round(new_mrr, 2),

                "user_loss_pct": round(loss_pct * 100, 2),

                "net_change_pct": round(
                    ((new_mrr - tier_current_mrr) / max(tier_current_mrr, 0.01)) * 100, 2
                ),
            }

            scenario_totals[scenario] += new_mrr

            scenario_user_loss[scenario] += users * loss_pct

        per_tier_results.append(
            {
                "tier_name": tier["name"],              # e.g., "Basic"
                "current_mrr": round(tier_current_mrr, 2),  # e.g., 9800.0
                "scenarios": tier_scenarios,             # the 3 scenario dicts above
            }
        )

    aggregate_scenarios: dict[str, Any] = {}
    for scenario in SCENARIOS:
        proj_mrr = round(scenario_totals[scenario], 2)

        net_change = round(
            ((proj_mrr - current_mrr) / max(current_mrr, 0.01)) * 100, 2
        )

        overall_loss_pct = round((scenario_user_loss[scenario] / total_users) * 100, 2)

        aggregate_scenarios[scenario] = {
            "projected_mrr": proj_mrr,          # total company MRR after change
            "user_loss_pct": overall_loss_pct,  # % of all users who leave
            "net_change_pct": net_change,        # % change in revenue vs current
        }

    best_scenario = max(SCENARIOS, key=lambda s: aggregate_scenarios[s]["projected_mrr"])

    currency = str(company_data.get("currency") or "USD").upper()
    curr_map = {
        "USD": "$", "EUR": "€", "GBP": "£", "INR": "₹",
        "CAD": "CA$", "AUD": "AU$", "JPY": "¥", "CHF": "CHF ",
        "SGD": "S$", "AED": "AED ", "BRL": "R$", "CNY": "¥"
    }
    curr_symbol = curr_map.get(currency, f"{currency} " if len(currency) == 3 else "$")

    reasoning = (
        f"{best_scenario} increase yields highest projected MRR of "
        f"{curr_symbol}{best_data['projected_mrr']:,.2f} "
        f"({best_data['net_change_pct']:+.1f}% change) "
        f"with an estimated {best_data['user_loss_pct']:.1f}% user loss — "
        f"best balance of revenue gain and acceptable churn."
    )

    return {
        "currency": currency,
        "currency_symbol": curr_symbol,
        "current_mrr": round(current_mrr, 2),          # total MRR right now (e.g., 31243.0)
        "scenarios": aggregate_scenarios,               # {"+10%": {...}, "+20%": {...}, "+30%": {...}}
        "per_tier": per_tier_results,                   # breakdown per tier
        "recommended_increase": best_scenario,          # e.g., "+20%"
        "reasoning": reasoning,                         # human-readable explanation string
    }
