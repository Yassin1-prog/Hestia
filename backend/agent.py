from google import genai
from google.genai import types
from firecrawl import FirecrawlApp
from pydantic import BaseModel, Field
from typing import List, Optional

# ==========================================
# PYDANTIC SCHEMAS (Data structure)
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
    agent_phone: Optional[str] = Field(description="The phone number of the agent/owner, if available.")
    agentic_score: int = Field(description="Score 1-10 for how well it matches the requirements.")
    score_reason: str = Field(description="A short sentence explaining why it received this score.")


# ==========================================
# API INITIALIZATION & HELPER
# ==========================================
client = genai.Client(api_key="***REMOVED***")
firecrawl = FirecrawlApp(api_key="fc-be37bf6164d945e282269be71a3ad856")

def get_markdown(url: str) -> str:
    """Helper that works regardless of the firecrawl-py version"""
    if hasattr(firecrawl, "scrape"):
        res = firecrawl.scrape(url, formats=["markdown"])
        return getattr(res, "markdown", "") or (res.get("markdown", "") if isinstance(res, dict) else "")
    res = firecrawl.scrape_url(url, params={"formats": ["markdown"]})
    return res.get("markdown", "") if isinstance(res, dict) else getattr(res, "markdown", "")

user_request = "I am looking for an apartment in Pangrati, up to 600 euros, pet friendly. I want it to be bright."


# ==========================================
# STEP 1: URL Generation
# ==========================================
print("1. The Agent is thinking of the search URL...")
prompt_url = f"""
The user requests: '{user_request}'. 
Create a search URL for spitogatos.gr. 
Example structure: https://www.spitogatos.gr/enoikiaseis-katoikies/pagkrati?max_price=600
"""

res_url = client.models.generate_content(
    model="gemini-3.8-flash",
    contents=prompt_url,
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=SearchURL,
    ),
)
search_url = res_url.parsed.url
print(f"-> Generated URL: {search_url}\n")


# ==========================================
# STEP 2: Shallow Scrape (Finding all Links)
# ==========================================
print("2. Firecrawl is scanning the initial results page...")
search_page_markdown = get_markdown(search_url)

prompt_extract_all = f"""
Read the following markdown from the Spitogatos search results.
Identify ALL property listings on the page.
For each one, find its URL, price, square meters, and a brief description.
Ignore ads or links that are not property listings.

Markdown: 
{search_page_markdown[:25000]}
"""

print("Gemini is extracting ALL URLs and their basic details...")
res_all = client.models.generate_content(
    model="gemini-3.8-flash",
    contents=prompt_extract_all,
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=AllProperties,
    ),
)

all_houses = res_all.parsed.properties
print(f"Found {len(all_houses)} properties in total!\n")


# ==========================================
# STEP 3A: Agentic Ranking on ALL properties
# ==========================================
print("3. The Agent is evaluating all", len(all_houses), "properties simultaneously...")

houses_text = ""
for i, h in enumerate(all_houses):
    houses_text += f"[{i}] Link: {h.url} | Price: {h.price} | Sq.m.: {h.sqm} | Info: {h.basic_info}\n"

prompt_rank_all = f"""
The user requests: '{user_request}'.
Below is a list of {len(all_houses)} apartments. 
Acting as an expert real estate agent, evaluate each one and pick the top 3.
Base your decision on the price, square meters, and description.

List:
{houses_text}
"""

res_ranking = client.models.generate_content(
    model="gemini-3.8-flash",
    contents=prompt_rank_all,
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=PropertyList,
    ),
)

top_3_urls = [link.url for link in res_ranking.parsed.links]
print(f"-> The Agent selected the top 3: {top_3_urls}\n")


# ==========================================
# STEP 3B: Deep Scrape ONLY on the "Winners"
# ==========================================
print("4. The Agent is visiting the 3 best listings to find the phone number and give a final score...")
final_properties = []

for url in top_3_urls:
    detail_markdown = get_markdown(url)
    
    prompt_details = f"""
    The user requests: '{user_request}'.
    Confirm if this listing matches (score it 1-10) and find the phone number of the agent/owner.
    Extract the data into JSON.
    Listing Markdown:
    {detail_markdown[:15000]}
    """
    
    res_details = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt_details,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=PropertyDetails,
        ),
    )
    
    property_data = res_details.parsed
    property_data.url = url
    final_properties.append(property_data)


# ==========================================
# THE FINAL RESULT
# ==========================================
print("\n=== FINAL AGENT SELECTION ===")
final_properties.sort(key=lambda x: x.agentic_score, reverse=True)

for prop in final_properties:
    print(f"Property: {prop.url}")
    print(f"Price: {prop.price}€ | {prop.sqm} sq.m. | Floor: {prop.floor}")
    print(f"Score: {prop.agentic_score}/10")
    print(f"Reasoning: {prop.score_reason}")
    print(f"Agent Phone: {prop.agent_phone}")
    print("-" * 30)


# Done! Connect your middleware (Teams) here
