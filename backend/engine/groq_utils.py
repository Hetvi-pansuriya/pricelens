"""
groq_utils.py
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
PURPOSE: Shared helper that wraps the Groq AI API with retry logic,
         rate-limit handling, and JSON parsing.

HOW IT WORKS:
  1. Takes a prompt string and a Groq client object.
  2. Calls the Groq chat completion API (llama model) in a thread (non-blocking).
  3. Parses the JSON response from the model.
  4. If something goes wrong (rate limit, bad JSON), retries with corrections.

CONNECTED TO:
  - module2_features.py   â†’ calls call_groq_with_retry() for feature classification
  - module3_benchmark.py  â†’ calls call_groq_with_retry() for competitor benchmarking
  - module4_recommendations.py â†’ calls call_groq_with_retry() for strategy generation
  - analysis.py           â†’ passes the groq_client from app.state to these modules
  - main.py               â†’ creates the Groq client on startup (stored in app.state)
"""

import asyncio

import json

import re

import os

GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
if "openai" in GROQ_MODEL.lower():
    GROQ_MODEL = "openai/gpt-oss-120b"


async def call_groq_with_retry(client, prompt: str, max_retries: int = 3) -> dict:
    """
    Call the Groq chat completion API with retry logic.
    """
    if client is None:
        raise ValueError("GROQ client is not configured")

    last_error = None
    current_prompt = prompt

    for attempt in range(max_retries):
        try:
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=GROQ_MODEL,

                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a SaaS pricing expert. "             # establishes expertise
                            "Always respond with ONLY a valid JSON object. "  # format constraint
                            "No markdown fences, no backticks, no explanation outside the JSON."  # no decorators
                        ),
                    },
                    {
                        "role": "user",
                        "content": current_prompt,
                    },
                ],

                temperature=0.3,

                max_tokens=4096,

                response_format={"type": "json_object"},
            )

            text = response.choices[0].message.content.strip()

            if text.startswith("```"):
                text = re.sub(r"^```[a-z]*\n?", "", text)

                text = re.sub(r"\n?```$", "", text)

                text = text.strip()  # remove any remaining whitespace

            return json.loads(text)

        except json.JSONDecodeError as e:
            last_error = f"JSON parse error: {e}"

            if attempt < max_retries - 1:
                current_prompt = (
                    current_prompt
                    + "\n\nCRITICAL: Your previous response was not valid JSON. "
                    "Return ONLY a valid JSON object. No markdown, no backticks, no text outside the JSON braces."
                )
            continue

            if "rate_limit" in error_str.lower() or "429" in error_str:
                wait_seconds = 5
                print(f"Groq rate limit hit on attempt {attempt + 1}, waiting {wait_seconds}s...")
                await asyncio.sleep(wait_seconds)
                continue

            last_error = error_str
            break

    raise ValueError(f"Groq API call failed: {last_error}")

