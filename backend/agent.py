"""Search & ranking agent: Spitogatos search → shallow scrape → rank → deep scrape top 3.

Usage:
    from backend.agent import run_search_pipeline
    final_properties = run_search_pipeline("Apartment in Pangrati up to 600€, pet friendly")

Or from the CLI:  uv run python -m backend.agent "your request"

API keys are read from `.env` (GEMINI_API_KEY, FIRECRAWL_API_KEY); importing this module has
no side effects, so FastAPI can import it safely.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")


# ==========================================
# PYDANTIC SCHEMAS (Data structure)
# NOTE: no default values — the Gemini response_schema does not support them.
# ==========================================
class SearchURL(BaseModel):
    url: str = Field(description="The search URL for Spitogatos.")


class PropertyPreview(BaseModel):
    url: str = Field(description="The exact listing link")
    price: Optional[int] = Field(description="The price (number only)")
    sqm: Optional[int] = Field(description="The square meters")
    basic_info: str = Field(description="A short sentence with everything else mentioned in the summary")


class AllProperties(BaseModel):
    properties: List[PropertyPreview] = Field(description="The complete list of ALL properties on the page.")


class PropertyLink(BaseModel):
    url: str = Field(description="The exact listing link")


class PropertyList(BaseModel):
    links: List[PropertyLink] = Field(description="List of the top 3 listing links.")


class PropertyDetails(BaseModel):
    url: str
    price: Optional[int] = Field(description="The rental price in Euros (number only).")
    sqm: Optional[int] = Field(description="The square meters.")
    floor: Optional[str] = Field(description="The floor (e.g., 1st, Ground floor).")
    features: List[str] = Field(description="List of amenities/features (e.g., natural gas, pet friendly).")
    agent_name: Optional[str] = Field(
        description="Name of the landlord / real-estate agent or agency, if shown."
    )
    agent_phone: Optional[str] = Field(
        description="The phone number of the agent/owner exactly as shown, if available. "
        "Never the portal's own customer-support number."
    )
    agent_email: Optional[str] = Field(
        description="The e-mail address of the agent/owner, if available. "
        "Never the portal's own address (e.g. @spitogatos.gr)."
    )
    missing_info: List[str] = Field(
        description="Up to 4 short questions IN ENGLISH to ask the landlord about important details "
        "the user cares about that the listing does NOT state (e.g. 'Are pets allowed?')."
    )
    agentic_score: int = Field(description="Score 1-10 for how well it matches the requirements.")
    score_reason: str = Field(description="A short sentence explaining why it received this score.")


# ==========================================
# API CLIENTS (lazy, keys from .env)
# ==========================================
@lru_cache(maxsize=1)
def _gemini():
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY in .env")
    return genai.Client(api_key=api_key)


@lru_cache(maxsize=1)
def _firecrawl():
    from firecrawl import FirecrawlApp

    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        raise RuntimeError("Set FIRECRAWL_API_KEY in .env")
    return FirecrawlApp(api_key=api_key)


def _generate(prompt: str, schema: type[BaseModel]):
    from google.genai import types

    res = _gemini().models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema),
    )
    return res.parsed


def get_markdown(url: str) -> str:
    """Helper that works regardless of the firecrawl-py version"""
    firecrawl = _firecrawl()
    if hasattr(firecrawl, "scrape"):
        res = firecrawl.scrape(url, formats=["markdown"])
        return getattr(res, "markdown", "") or (res.get("markdown", "") if isinstance(res, dict) else "")
    res = firecrawl.scrape_url(url, params={"formats": ["markdown"]})
    return res.get("markdown", "") if isinstance(res, dict) else getattr(res, "markdown", "")


# ==========================================
# PIPELINE
# ==========================================
def run_search_pipeline(user_request: str, verbose: bool = True) -> List[PropertyDetails]:
    log = print if verbose else (lambda *a, **k: None)

    # STEP 1: URL Generation
    log("1. The Agent is thinking of the search URL...")
    prompt_url = f"""
    The user requests: '{user_request}'.
    Create a search URL for spitogatos.gr.
    Example structure: https://www.spitogatos.gr/enoikiaseis-katoikies/pagkrati?max_price=600
    """
    search_url = _generate(prompt_url, SearchURL).url
    log(f"-> Generated URL: {search_url}\n")

    # STEP 2: Shallow Scrape (Finding all Links)
    log("2. Firecrawl is scanning the initial results page...")
    search_page_markdown = get_markdown(search_url)
    prompt_extract_all = f"""
    Read the following markdown from the Spitogatos search results.
    Identify ALL property listings on the page.
    For each one, find its URL, price, square meters, and a brief description.
    Ignore ads or links that are not property listings.

    Markdown:
    {search_page_markdown[:25000]}
    """
    log("Gemini is extracting ALL URLs and their basic details...")
    all_houses = _generate(prompt_extract_all, AllProperties).properties
    log(f"Found {len(all_houses)} properties in total!\n")
    if not all_houses:
        return []

    # STEP 3A: Agentic Ranking on ALL properties
    log(f"3. The Agent is evaluating all {len(all_houses)} properties simultaneously...")
    houses_text = "".join(
        f"[{i}] Link: {h.url} | Price: {h.price} | Sq.m.: {h.sqm} | Info: {h.basic_info}\n"
        for i, h in enumerate(all_houses)
    )
    prompt_rank_all = f"""
    The user requests: '{user_request}'.
    Below is a list of {len(all_houses)} apartments.
    Acting as an expert real estate agent, evaluate each one and pick the top 3.
    Base your decision on the price, square meters, and description.

    List:
    {houses_text}
    """
    top_3_urls = [link.url for link in _generate(prompt_rank_all, PropertyList).links]
    log(f"-> The Agent selected the top 3: {top_3_urls}\n")

    # STEP 3B: Deep Scrape ONLY on the "Winners"
    log("4. The Agent is visiting the 3 best listings to find the contact details and give a final score...")
    final_properties: List[PropertyDetails] = []
    for url in top_3_urls:
        detail_markdown = get_markdown(url)
        prompt_details = f"""
        The user requests: '{user_request}'.
        Confirm if this listing matches (score it 1-10).
        Find the name, phone number and e-mail of the landlord / agent who posted it
        (NOT the website's own support contacts).
        List the important details the user cares about that the listing does not mention,
        phrased as short questions to the landlord. Always write the questions in English,
        even if the listing is in Greek.
        Extract the data into JSON.
        Listing Markdown:
        {detail_markdown[:15000]}
        """
        property_data = _generate(prompt_details, PropertyDetails)
        property_data.url = url
        final_properties.append(property_data)

    final_properties.sort(key=lambda x: x.agentic_score, reverse=True)
    return final_properties


if __name__ == "__main__":
    request = " ".join(sys.argv[1:]) or (
        "I am looking for an apartment in Pangrati, up to 600 euros, pet friendly. I want it to be bright."
    )
    results = run_search_pipeline(request)
    print("\n=== FINAL AGENT SELECTION ===")
    for prop in results:
        print(f"Property: {prop.url}")
        print(f"Price: {prop.price}€ | {prop.sqm} sq.m. | Floor: {prop.floor}")
        print(f"Score: {prop.agentic_score}/10")
        print(f"Reasoning: {prop.score_reason}")
        print(f"Contact: {prop.agent_name} | {prop.agent_phone} | {prop.agent_email}")
        print(f"Questions: {prop.missing_info}")
        print("-" * 30)
