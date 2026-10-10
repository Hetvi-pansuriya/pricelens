"""
module2_features.py
─────────────────────────────────────────────────────────────────────────────
PURPOSE: Module 2 — Feature Audit (Groq AI call #1 in the pipeline).

What it does:
  Sends all pricing tiers and their features to the Groq AI.
  The AI classifies each feature into one of 4 types:
    - gatekeeper:      premium feature on a cheap tier → move it UP
    - blocker:         basic feature on a pricey tier  → move it DOWN
    - right_placed:    correct tier                    → keep it
    - undifferentiated: doesn't drive upgrades         → rethink it

WHY this matters for pricing?
  If your "API Access" (premium feature) is available on the $29 Starter tier,
  nobody upgrades to the $79 Pro tier. That's a "gatekeeper" — it gates upgrading.
  Moving API Access to Pro tier drives more upgrade revenue.

CONNECTED TO:
  - analysis.py    → run_module2(company_data, groq_client) called in M1+M2 parallel gather
  - groq_utils.py  → call_groq_with_retry() makes the actual AI API call
  - main.py        → groq_client comes from app.state.groq_client
  - models.py      → Feature.feature_name and PricingTier.name are the inputs
  - analysis.py    → m2_result fed into M3 and M4 as context
  - json_report    → stored in Report.json_report["module2_features"]
"""

import json

from engine.groq_utils import call_groq_with_retry


async def run_module2(company_data: dict, groq_client) -> dict:
    """
    Calls Groq to audit feature placement across pricing tiers.
    Falls back to a partial result with an error key if Groq fails.
    """
    name = company_data.get("name", "Unknown")       # company name, e.g., "CloudHR Pro"
    industry = company_data.get("industry", "Unknown")  # e.g., "saas_b2b"
    tiers = company_data.get("tiers", [])            # list of tier dicts with features

    tiers_with_features = [
        {
            "tier_name": tier["name"],               # e.g., "Basic"
            "price": tier["price"],                   # e.g., 49.0
            "billing_cycle": tier["billing_cycle"],  # e.g., "monthly"
            "features": [f["feature_name"] for f in tier.get("features", [])],
        }
        for tier in tiers  # iterate each tier in the company's tiers list
    ]

    prompt = f"""You are a SaaS pricing strategist. Analyze the following pricing tiers and their features.
Classify each feature into exactly one of these 4 types:
- "gatekeeper": a premium/enterprise feature being given away on a free or cheap tier — it should be moved up
- "blocker": a basic/essential feature locked behind a high-tier paywall — it's causing churn, move it down
- "right_placed": correctly placed in the right tier — no action needed
- "undifferentiated": provides no upgrade incentive between tiers — needs rethinking

Company: {name}, Industry: {industry}
Tiers and features: {json.dumps(tiers_with_features)}

Respond ONLY with a JSON object matching this exact schema:
{{
  "feature_audit": [
    {{
      "feature_name": "string",
      "tier_name": "string",
      "classification": "gatekeeper|blocker|right_placed|undifferentiated",
      "reasoning": "one sentence explanation",
      "recommended_action": "move to X tier / keep / rethink positioning"
    }}
  ],
  "summary": {{
    "gatekeepers_found": 2,
    "blockers_found": 1,
    "right_placed": 5,
    "undifferentiated": 3,
    "biggest_issue": "one sentence"
  }}
}}

Return ONLY the JSON. No markdown. No backticks. No explanation outside the JSON.

Example output:
{{"feature_audit": [{{"feature_name": "API access", "tier_name": "Starter", "classification": "gatekeeper", "reasoning": "API access is a power-user feature being given away on the cheapest tier", "recommended_action": "move to Pro tier"}}], "summary": {{"gatekeepers_found": 1, "blockers_found": 0, "right_placed": 0, "undifferentiated": 0, "biggest_issue": "API access is underpriced"}}}}"""

    def _deterministic_audit():
        audit = []
        gatekeepers = 0
        blockers = 0
        right_placed = 0
        undifferentiated = 0
        biggest = None

        ENTERPRISE_KEYWORDS = {"sso", "saml", "audit", "compliance", "scim", "sla", "dedicated", "white label", "custom domain"}
        POWER_KEYWORDS = {"api", "webhook", "integration", "export", "advanced", "automated", "workflow"}
        BASIC_KEYWORDS = {"email", "basic", "profiles", "standard", "dashboard"}

        # Find max tier price
        prices = [t.get("price", 0) for t in tiers_with_features]
        max_price = max(prices) if prices else 100
        min_price = min(prices) if prices else 0

        for t in tiers_with_features:
            t_name = t.get("name", "Tier")
            t_price = t.get("price", 0)
            is_top = (t_price == max_price) and len(tiers_with_features) > 1
            is_bottom = (t_price == min_price)

            for feat in t.get("features", []):
                feat_lower = feat.lower()
                classification = "right_placed"
                reasoning = "Well placed for this tier's target audience."
                action = "Keep"

                if any(k in feat_lower for k in ENTERPRISE_KEYWORDS) and not is_top:
                    classification = "gatekeeper"
                    reasoning = "Enterprise capability offered below the top price tier."
                    action = "Move to Enterprise"
                    gatekeepers += 1
                    if not biggest:
                        biggest = f"{feat} is included in {t_name} but is an enterprise feature large accounts will pay for."
                elif ("export" in feat_lower or "backup" in feat_lower) and is_top:
                    classification = "blocker"
                    reasoning = "Basic data portability requirement locked behind top paywall."
                    action = "Move to Growth"
                    blockers += 1
                    if not biggest:
                        biggest = f"{feat} is locked behind {t_name}, creating unnecessary onboarding friction."
                elif any(k in feat_lower for k in BASIC_KEYWORDS) and not is_bottom:
                    classification = "undifferentiated"
                    reasoning = "Standard baseline capability with minimal upgrade incentive."
                    action = "Rethink positioning"
                    undifferentiated += 1
                else:
                    classification = "right_placed"
                    reasoning = "Feature value aligns with tier pricing."
                    action = "Keep"
                    right_placed += 1

                audit.append({
                    "feature_name": feat,
                    "tier_name": t_name,
                    "classification": classification,
                    "reasoning": reasoning,
                    "recommended_action": action,
                })

        return {
            "feature_audit": audit,
            "summary": {
                "gatekeepers_found": gatekeepers,
                "blockers_found": blockers,
                "right_placed": right_placed,
                "undifferentiated": undifferentiated,
                "biggest_issue": biggest or "Optimize feature positioning so each upgrade tier has clear gating.",
            },
        }

    if groq_client is None:
        return _deterministic_audit()

    try:
        result = await call_groq_with_retry(groq_client, prompt)
        if isinstance(result, list):
            if len(result) > 0 and isinstance(result[0], dict) and "feature_audit" in result[0]:
                result = result[0]
            else:
                result = {"feature_audit": result, "summary": {}}
        if not isinstance(result, dict) or "feature_audit" not in result:
            return _deterministic_audit()
        return result
    except Exception as e:
        print(f"[Module 2] Groq call failed ({e}), using deterministic feature audit fallback")
        return _deterministic_audit()
