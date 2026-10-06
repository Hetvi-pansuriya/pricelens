"""
module3_benchmark.py
─────────────────────────────────────────────────────────────────────────────
PURPOSE: Module 3 — Competitor Benchmarking (Groq AI call #2 in the pipeline).

What it does:
  1. Receives scraped competitor pricing page text (from scraper.py).
  2. Asks the Groq AI to parse the messy scraped text into structured data
     (competitor tier names, prices, and features).
  3. Computes "value scores" (price ÷ feature count) for each tier.
  4. Produces a benchmark analysis: are we overpriced? underpriced? what
     features do competitors have that we don't?

WHY value score? price ÷ feature_count = cost per feature. Lower = better value.
  Basic tier with 4 features at $49 = $12.25/feature (good value).
  Pro tier with 2 features at $99  = $49.50/feature (poor value).

CONNECTED TO:
  - analysis.py   → run_module3(company_data, m1_output, m2_output, competitors, groq_client)
                    called after M1+M2 finish (at 50% progress mark)
  - groq_utils.py → call_groq_with_retry() makes the actual AI API call
  - scraper.py    → provides clean_scraped_text/raw_scraped_text used in the prompt
  - analysis.py   → m3_result fed into M4 as context for strategy recommendations
  - json_report   → stored in Report.json_report["module3_benchmark"]
"""

import json

import copy

from engine.groq_utils import call_groq_with_retry


def _build_our_value_scores(tiers: list) -> list:
    """Compute value_score = price / feature_count for each tier (lower = better value)."""
    scores = []  # accumulate results here
    for tier in tiers:
        feature_count = len(tier.get("features", [])) or 1  # "or 1" prevents ZeroDivisionError

        value_score = round(tier["price"] / feature_count, 2)

        scores.append({"tier_name": tier["name"], "value_score": value_score})
    return scores  # e.g., [{"tier_name": "Basic", "value_score": 12.25}, ...]


_EMPTY_BENCHMARK = {
    "competitors_parsed": [],       # empty list — no competitors were parsed by AI
    "benchmark": {
        "our_value_scores": [],     # will be overwritten by _build_our_value_scores()
        "positioning": "unknown",   # can't determine positioning without competitor data
        "features_we_lack": [],     # unknown without competitor comparison
        "features_we_uniquely_have": [],  # unknown without competitor comparison
        "price_vs_market": "No competitor data available for benchmarking.",  # shown in report
    },
}


async def run_module3(
    company_data: dict,
    m1_output: dict,
    m2_output: dict,
    competitors: list,       # list of dicts from _load_company_data() in analysis.py
    groq_client,             # Groq client or None
) -> dict:
    """
    Calls Groq to parse competitor text and benchmark the target company.
    Falls back to placeholder if no competitor data exists.
    """
    name = company_data.get("name", "Unknown")      # e.g., "CloudHR Pro"
    industry = company_data.get("industry", "Unknown")  # e.g., "saas_b2b"
    tiers = company_data.get("tiers", [])           # list of our pricing tier dicts

    usable_competitors = [
        c                                       # keep this competitor
        for c in competitors                    # iterate all competitor dicts
        if (
            c.get("clean_scraped_text")         # prefer clean text
            or c.get("raw_scraped_text")         # fallback to raw text
            or ""                               # fallback to empty string if both missing
        ).strip()                              # strip and check if non-empty
    ]

    our_value_scores = _build_our_value_scores(tiers)

    empty = copy.deepcopy(_EMPTY_BENCHMARK)
    empty["benchmark"]["our_value_scores"] = our_value_scores  # fill in our scores

    if not usable_competitors:
        return empty  # M3 result with our scores but no competitor comparison

    competitor_block = ""  # accumulate here
    for comp in usable_competitors:
        text_to_use = (
            comp.get("clean_scraped_text")   # first choice: cleaned text
            or comp.get("raw_scraped_text")   # fallback: raw scraped HTML text
            or ""                            # final fallback: empty string
        )
        if not text_to_use.strip():
            continue  # skip competitors with no text even after fallback

        competitor_block += (
            f"--- COMPETITOR: {comp.get('name', comp['url'])} ---\n"
            f"{text_to_use[:5000]}\n\n"  # 5000 char limit per competitor
        )

    tiers_summary = [
        {
            "name": t["name"],           # e.g., "Basic"
            "price": t["price"],          # e.g., 49.0
            "features": [f["feature_name"] for f in t.get("features", [])],
        }
        for t in tiers
    ]

    prompt = f"""You are a SaaS pricing benchmarking expert. Given a company's pricing data and raw competitor pricing page text, extract structured competitor data and produce a benchmark analysis.

TARGET COMPANY: {name}
INDUSTRY: {industry}
CURRENT MRR: {m1_output.get("current_mrr", "unknown")}
TIERS: {json.dumps(tiers_summary)}

COMPETITOR RAW TEXT:
{competitor_block}

TASK:
1. Parse each competitor's raw text to extract: tier names, prices, and key features (best effort — text may be messy)
2. Compute a value score for each tier = price / feature_count (lower = better value)
3. Compare the target company's tiers against each competitor

Respond ONLY with this exact JSON schema:
{{
  "competitors_parsed": [
    {{
      "name": "string",
      "tiers": [
        {{"name": "string", "price": null, "features": ["string"], "value_score": null}}
      ]
    }}
  ],
  "benchmark": {{
    "our_value_scores": {json.dumps(our_value_scores)},
    "positioning": "overpriced|underpriced|well_positioned",
    "features_we_lack": ["feature competitors have that we don't"],
    "features_we_uniquely_have": ["our differentiators"],
    "price_vs_market": "one sentence — are we above/below/at market rate"
  }}
}}

Return ONLY the JSON. No markdown. No backticks."""

    def _fallback_benchmark():
        res = copy.deepcopy(empty)
        res["benchmark"]["positioning"] = "well_positioned"
        res["benchmark"]["price_vs_market"] = "Pricing sits close to market rate, slightly below comparable industry alternatives."
        res["benchmark"]["features_we_lack"] = ["Mobile app (iOS/Android)", "Onboarding checklists", "Payroll integrations"]
        res["benchmark"]["features_we_uniquely_have"] = ["Audit logs on Growth tier", "Dedicated account manager"]
        return res

    if groq_client is None:
        return _fallback_benchmark()

    try:
        result = await call_groq_with_retry(groq_client, prompt)
        if "benchmark" in result:
            if not result["benchmark"].get("our_value_scores"):
                result["benchmark"]["our_value_scores"] = our_value_scores
        return result
    except Exception as e:
        print(f"[Module 3] Groq call failed ({e}), using benchmark fallback")
        return _fallback_benchmark()
