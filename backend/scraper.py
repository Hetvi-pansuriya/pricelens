"""
scraper.py
─────────────────────────────────────────────────────────────────────────────
PURPOSE: Five-layer asynchronous competitor pricing page scraper for PriceLens.

When a user adds a competitor URL, this module fetches and cleans the text
from their pricing page so the AI (module3) can benchmark against it.

TWO-LAYER STRATEGY:
  Layer 1: requests (simple HTTP) — fast, works for static sites like Stripe.
  Layer 2: Playwright (headless Chrome) — slower, handles JS-rendered sites.

WHY two layers? Many SaaS pricing pages require JavaScript to render
(React/Next.js apps). requests only gets the raw HTML. Playwright actually
runs the browser, waits for JS to execute, then extracts text.

BUILT-IN OPTIMIZATIONS:
  - In-memory cache (24h TTL) — same URL is only scraped once per server restart.
  - Noise filtering — removes navbars, footers, cookie banners, legal text.
  - Pricing-signal filtering — only keeps text containing pricing keywords.
  - Character limits — caps raw text at 12,000 chars, clean at 8,000.

CONNECTED TO:
  - competitors.py → calls scrape_competitor() in a background task after adding a URL
  - analysis.py   → calls scrape_competitors_concurrent() to retry failed scrapes
  - module3       → receives clean_scraped_text in the company_data["competitors"] list
─────────────────────────────────────────────────────────────────────────────
"""

import os
import asyncio

import hashlib

import re

import time

import requests
from bs4 import BeautifulSoup
from url_safety import safe_requests_get, validate_url, is_safe_url, SSRFValidationError


_CACHE: dict[str, dict] = {}

_CACHE_TTL_SECONDS = 86_400  # 86400 = 60 × 60 × 24 seconds in one day

_MAX_RAW_CHARS = 12_000

_MAX_CLEAN_CHARS = 8_000

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

_PRICING_KEYWORDS = (
    "plan", "price", "pricing", "per month", "per year", "/mo", "/yr",
    "free", "starter", "pro", "enterprise", "business", "team", "annual",
    "monthly", "billed", "usd", "$", "€", "£", "₹", "upgrade",
    "subscribe", "tier", "features included",
)

_NOISE_TAGS = (
    "script", "style", "nav", "footer", "noscript", "iframe", "header",
    "aside", "form", "button", "svg", "img", "video", "audio", "canvas",
    "figure", "picture",
)

_PRICING_SELECTORS = (
    "[class*='pric']", "[class*='plan']", "[class*='tier']",
    "[id*='pric']", "[id*='plan']", "[id*='tier']", "main", "article",
    "[role='main']",
)

_NOISE_PATTERNS = (
    "cookie", "privacy policy", "terms of service", "all rights reserved",
    "sign in", "sign up", "log in", "log out", "get started", "contact us",
    "follow us", "© 20", "copyright", "javascript", "please enable",
    "browser not supported", "loading...", "skip to content",
)



def _cache_key(url: str) -> str:
    return hashlib.md5(url.encode("utf-8"), usedforsecurity=False).hexdigest()


def _get_cached(url: str) -> dict | None:
    key = _cache_key(url)          # compute the cache key for this URL
    entry = _CACHE.get(key)        # look up the key in the cache dict
    if not entry:
        return None                # cache miss — not found

    if time.time() - entry["cached_at"] > _CACHE_TTL_SECONDS:
        _CACHE.pop(key, None)  # remove the stale entry from cache
        return None            # treat as cache miss

    return entry  # cache hit — return the stored result


def _set_cache(url: str, result: dict) -> None:
    _CACHE[_cache_key(url)] = {**result, "cached_at": time.time()}



def _has_pricing_content(text: str) -> bool:
    """Require meaningful length and at least three distinct pricing signals."""
    if not text or len(text.strip()) < 200:
        return False

    lowered = text.casefold()

    return sum(keyword in lowered for keyword in _PRICING_KEYWORDS) >= 3


def _clean_pricing_content(raw_text: str) -> str:
    """Remove duplicated/legal/navigation noise and prioritize pricing lines."""
    pricing_lines: list[str] = []   # lines containing pricing keywords → shown first
    context_lines: list[str] = []   # other useful lines → shown after pricing lines
    seen: set[str] = set()          # track normalized lines to avoid duplicates

    for raw_line in raw_text.splitlines():  # split text into individual lines
        line = re.sub(r"\s+", " ", raw_line).strip()

        normalized = line.casefold()

        if len(line) < 3 or normalized in seen:
            continue

        if any(pattern in normalized for pattern in _NOISE_PATTERNS):
            continue

        if re.fullmatch(r"[\s\d\W]{1,5}", line):
            continue

        target = (
            pricing_lines
            if any(keyword in normalized for keyword in _PRICING_KEYWORDS)
            else context_lines
        )
        target.append(line)   # add the line to the appropriate list
        seen.add(normalized)  # mark this normalized line as seen (dedup)

    return "\n".join([*pricing_lines, *context_lines])[:_MAX_CLEAN_CHARS]


def _focused_bs4_text(soup: BeautifulSoup) -> str:
    """Try pricing-specific CSS selectors first, fall back to full page text."""
    for selector in _PRICING_SELECTORS:
        elements = soup.select(selector)  # find all matching elements
        if not elements:
            continue  # no elements found for this selector → try next

        text = "\n".join(
            element.get_text(separator="\n", strip=True)  # get inner text with newline separators
            for element in elements
        )

        if _has_pricing_content(text):
            return text  # this selector found a good pricing section

    return soup.get_text(separator="\n", strip=True)



def _layer1_sync(url: str) -> dict:
    response = safe_requests_get(
        url,
        timeout=12,
        headers=_HEADERS,
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup.find_all(_NOISE_TAGS):
        tag.decompose()  # e.g., removes all <script>, <style>, <nav>, <footer> tags

    raw_text = _focused_bs4_text(soup)

    if _has_pricing_content(raw_text):
        return {
            "text": raw_text[:_MAX_RAW_CHARS],         # raw text (capped at 12,000 chars)
            "clean_text": _clean_pricing_content(raw_text),  # noise-filtered version
            "status": "success_layer1",                 # tells the caller Layer 1 succeeded
        }

    return {
        "text": raw_text[:_MAX_RAW_CHARS],  # still return what we got
        "clean_text": "",                    # no clean text (not useful enough)
        "status": "too_short_or_no_pricing", # signals Layer 2 should be tried
    }



async def _layer2_playwright(url: str) -> dict:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {
            "text": "",
            "clean_text": "",
            "status": "playwright_not_installed",  # tells analysis.py to skip this
        }

    try:
        validate_url(url)
    except SSRFValidationError:
        return {
            "text": "",
            "clean_text": "",
            "status": "blocked_unsafe_url",
        }

    raw_text = ""  # accumulate extracted text here

    async with async_playwright() as playwright:
        browser = None  # track browser reference for cleanup in finally block
        try:
            browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )

            context = await browser.new_context(
                user_agent=_HEADERS["User-Agent"],
                viewport={"width": 1280, "height": 800},
                java_script_enabled=True,
            )

            page = await context.new_page()

            async def block_heavy_and_unsafe_resources(route):
                req_url = route.request.url
                if route.request.resource_type in {"image", "media", "font"}:
                    await route.abort()   # abort the request (don't download)
                    return

                if not is_safe_url(req_url):
                    await route.abort()
                    return

                await route.continue_()  # allow safe requests (JS, CSS, HTML)

            await page.route("**/*", block_heavy_and_unsafe_resources)

            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=35_000,
            )

            try:
                await page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass

            await page.wait_for_timeout(2_000)  # 2000ms = 2 seconds

            for selector in _PRICING_SELECTORS:
                try:
                    locator = page.locator(selector).first
                    text = await locator.inner_text(timeout=3_000)
                    if _has_pricing_content(text):
                        raw_text = text  # found a good pricing section
                        break           # stop trying other selectors
                except Exception:
                    continue  # selector failed (element not found) → try next

            if not raw_text:
                raw_text = await page.inner_text("body")

        except Exception as error:
            return {
                "text": "",
                "clean_text": "",
                "status": f"playwright_failed: {str(error)[:100]}",
            }
        finally:
            if browser:
                await browser.close()

    if _has_pricing_content(raw_text):
        return {
            "text": raw_text[:_MAX_RAW_CHARS],          # raw text capped at 12,000 chars
            "clean_text": _clean_pricing_content(raw_text),  # noise-filtered version
            "status": "success_layer2",                  # tells caller Layer 2 succeeded
        }
    return {
        "text": raw_text[:_MAX_RAW_CHARS],   # return what we got anyway
        "clean_text": "",                     # not useful enough
        "status": "no_pricing_content_after_render",  # even JS rendering didn't help
    }



async def scrape_competitor(url: str) -> dict:
    """Run static scrape, rendered scrape, cleaning, validation, then fallback."""
    try:
        validate_url(url)
    except SSRFValidationError:
        return {"text": "", "clean_text": "", "status": "blocked_unsafe_url"}

    cached = _get_cached(url)
    if cached:
        return {
            "text": cached["text"],
            "clean_text": cached["clean_text"],
            "status": f"{cached['status']}_cached",  # e.g., "success_layer1_cached"
        }

    try:
        result = await asyncio.to_thread(_layer1_sync, url)
        if result["status"] == "success_layer1":
            _set_cache(url, result)  # cache the successful result
            return result            # return immediately — Layer 1 was enough
        print(f"[Scraper] Layer 1 failed for {url}: {result['status']}")
    except Exception as error:
        print(f"[Scraper] Layer 1 exception for {url}: {error}")

    try:
        result = await _layer2_playwright(url)
        if result["status"] == "success_layer2":
            _set_cache(url, result)  # cache the Playwright result
            return result            # success on Layer 2
        print(f"[Scraper] Layer 2 failed for {url}: {result['status']}")
    except Exception as error:
        print(f"[Scraper] Layer 2 exception for {url}: {error}")

    return {"text": "", "clean_text": "", "status": "manual_required"}



async def scrape_competitors_concurrent(
    competitors: list[dict],  # list of dicts, each must have at least a "url" key
) -> list[dict]:
    """Scrape all supplied competitors concurrently while preserving order."""
    results = await asyncio.gather(
        *(scrape_competitor(comp["url"]) for comp in competitors),
        return_exceptions=True,  # exceptions are returned as values, not raised
    )

    output = []  # build the final result list here
    for competitor, result in zip(competitors, results):
        if isinstance(result, Exception):
            output.append(
                {
                    **competitor,   # spread original fields (id, url, name, etc.)
                    "text": "",
                    "clean_text": "",
                    "status": "failed",  # mark as failed
                }
            )
        else:
            output.append({**competitor, **result})  # result overrides matching keys

    return output  # list in same order as input competitors
