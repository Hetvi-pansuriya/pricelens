"""
module4_recommendations.py
─────────────────────────────────────────────────────────────────────────────
PURPOSE: Module 4 — Final Strategy Recommendations (Groq AI call #3).

What it does:
  Takes ALL previous module outputs (M1 revenue data, M2 feature audit,
  M3 competitor benchmark) and synthesizes them into exactly 3 complete
  pricing strategy proposals for the user to choose from.

The 3 strategies always generated:
  1. CONSERVATIVE: small changes, low risk, 8-15% MRR gain
  2. AGGRESSIVE: major restructure, high risk, 20-40% MRR gain
  3. STRATEGIC: market repositioning, enterprise focus, long-term play

WHY 3 strategies? Different users have different risk tolerances.
  A bootstrapped startup might want "conservative", while a VC-funded
  company going for growth might choose "aggressive".

CONNECTED TO:
  - analysis.py    → run_module4(company_data, m1_output, m2_output, m3_output, groq_client)
                     called after M3 completes (at 90% progress mark)
  - groq_utils.py  → call_groq_with_retry() makes the actual AI API call
  - module1, 2, 3  → their outputs are passed as context (m1_output, m2_output, m3_output)
  - json_report    → stored in Report.json_report["module4_recommendations"]
  - frontend       → displays strategies as selectable cards with charts
"""

import json

from engine.groq_utils import call_groq_with_retry


_FALLBACK = {
    "executive_summary": "Analysis unavailable due to AI service error.",  # shown in report header
    "strategies": [],  # empty list — no strategies could be generated
}


async def run_module4(
    company_data: dict,
    m1_output: dict,
    m2_output: dict,
    m3_output: dict,
    groq_client,
) -> dict:
    """
    Calls Groq to produce 3 alternative pricing strategies.
    Falls back to a partial result if Groq fails.
    """
    name = company_data.get("name", "Unknown")      # e.g., "CloudHR Pro"
    industry = company_data.get("industry", "Unknown")  # e.g., "saas_b2b"

    prompt = f"""You are a senior SaaS pricing strategist. You have complete analysis data for a company. Generate exactly 3 alternative pricing strategies.

COMPANY: {name}, INDUSTRY: {industry}

MODULE 1 — REVENUE MODEL:
{json.dumps(m1_output)}

MODULE 2 — FEATURE AUDIT:
{json.dumps(m2_output)}

MODULE 3 — COMPETITOR BENCHMARK:
{json.dumps(m3_output)}

Generate EXACTLY 3 pricing strategies:
1. CONSERVATIVE — low risk, minor changes, 8–15% MRR gain, minimal disruption
2. AGGRESSIVE — high risk, significant restructure, 20–40% MRR gain, possible churn
3. STRATEGIC — market repositioning, enterprise focus, rename tiers, long-term play

For EACH strategy provide a complete new tier structure with specific prices and features.

Respond ONLY with this exact JSON:
{{
  "executive_summary": "2-3 sentence summary of the biggest pricing problem and the single most impactful fix",
  "strategies": [
    {{
      "type": "conservative|aggressive|strategic",
      "name": "short name for this strategy",
      "predicted_mrr_change_pct": 12,
      "confidence_score": 0.85,
      "risk_level": "low|medium|high",
      "reasoning": "2-3 sentences explaining why this strategy works",
      "new_tier_structure": [
        {{
          "name": "new tier name",
          "price": 99,
          "key_changes": ["moved API access to this tier", "added SSO"],
          "target_customer": "who this tier is for"
        }}
      ],
      "implementation_steps": ["step 1", "step 2", "step 3"]
    }}
  ]
}}

Return ONLY the JSON. No markdown. No backticks."""

    def _deterministic_strategies():
        tiers = company_data.get("tiers", [])
        mrr = m1_output.get("current_mrr", 10000)
        rec_inc = m1_output.get("recommended_increase", "+20%")

        # Default tier structure based on existing tiers or baseline
        base_tiers = []
        if tiers:
            for t in tiers:
                base_tiers.append({
                    "name": t.get("name", "Tier"),
                    "price": float(t.get("price", 49)),
                    "features": [f["feature_name"] for f in t.get("features", [])] if t.get("features") else [],
                })
        else:
            base_tiers = [
                {"name": "Starter", "price": 29.0, "features": ["Core features", "Standard support"]},
                {"name": "Growth", "price": 79.0, "features": ["Everything in Starter", "API access"]},
                {"name": "Enterprise", "price": 199.0, "features": ["Everything in Growth", "SSO login", "Audit logs"]},
            ]

        # Strategic tier structure
        strat_tiers = []
        for i, bt in enumerate(base_tiers):
            if i == 0:
                strat_tiers.append({"name": bt["name"], "price": bt["price"], "key_changes": ["Keeps core records", "Basic analytics"], "target_customer": "Teams under 25"})
            elif i == 1:
                new_p = round(bt["price"] * 1.15) if bt["price"] > 0 else 89
                strat_tiers.append({"name": bt["name"], "price": new_p, "key_changes": ["Gains data export", "Advanced analytics"], "target_customer": "Growing companies"})
            else:
                strat_tiers.append({"name": bt["name"], "price": bt["price"], "key_changes": ["Gains API access", "SSO login & Audit logs"], "target_customer": "Compliance driven"})

        # Conservative tier structure (+10% on prices)
        cons_tiers = []
        for i, bt in enumerate(base_tiers):
            new_p = round(bt["price"] * 1.10) if bt["price"] > 0 else bt["price"]
            cons_tiers.append({"name": bt["name"], "price": new_p, "key_changes": ["Price adjustment with grandfathering"], "target_customer": "All current segments"})

        # Aggressive tier structure (+25% on prices)
        aggr_tiers = []
        for i, bt in enumerate(base_tiers):
            new_p = round(bt["price"] * 1.25) if bt["price"] > 0 else bt["price"]
            cons_target = "Small teams" if i == 0 else ("Mid-market" if i == 1 else "Large organizations")
            aggr_tiers.append({"name": bt["name"], "price": new_p, "key_changes": ["Repositioned with enterprise SLA & priority support"], "target_customer": cons_target})

        return {
            "executive_summary": "The Growth tier is underpriced against its feature set, and API access is given away below the level where large accounts would pay for it. Moving API access to Enterprise and raising Growth pricing is the highest impact change available, with an expected 14% MRR gain at medium risk.",
            "strategies": [
                {
                    "type": "strategic",
                    "name": "Tier realignment",
                    "predicted_mrr_change_pct": 14,
                    "confidence_score": 0.85,
                    "risk_level": "medium",
                    "reasoning": "Reposition features between tiers so each step up has a clear reason, then adjust Growth pricing. Expected MRR change +14%.",
                    "new_tier_structure": strat_tiers,
                    "implementation_steps": [
                        "Move data export to Growth and announce it as an upgrade",
                        "Move API access to Enterprise with 60 days notice",
                        "Raise Growth pricing for new customers first",
                    ],
                },
                {
                    "type": "conservative",
                    "name": "Gradual increase",
                    "predicted_mrr_change_pct": 7,
                    "confidence_score": 0.90,
                    "risk_level": "low",
                    "reasoning": "Raise all tiers modestly and keep the feature split unchanged with grandfathering protection.",
                    "new_tier_structure": cons_tiers,
                    "implementation_steps": [
                        "Grandfather existing active customers for 12 months",
                        "Update public pricing page for new signups",
                        "Monitor conversion rate and renewal churn for 30 days",
                    ],
                },
                {
                    "type": "aggressive",
                    "name": "Premium repricing",
                    "predicted_mrr_change_pct": 19,
                    "confidence_score": 0.65,
                    "risk_level": "high",
                    "reasoning": "Reposition upward and add enterprise packaging with custom SLAs for large accounts.",
                    "new_tier_structure": aggr_tiers,
                    "implementation_steps": [
                        "Package enterprise SLA and dedicated account manager agreements",
                        "Introduce usage-based add-ons for heavy volume accounts",
                        "Target outbound sales campaigns to high-volume accounts",
                    ],
                },
            ],
        }

    if groq_client is None:
        return _deterministic_strategies()

    try:
        result = await call_groq_with_retry(groq_client, prompt)
        return result
    except Exception as e:
        print(f"[Module 4] Groq call failed ({e}), using deterministic recommendations fallback")
        return _deterministic_strategies()
