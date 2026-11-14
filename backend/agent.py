import os
from google import genai
from google.genai import types
from firecrawl import FirecrawlApp
from pydantic import BaseModel, Field
from typing import List, Optional

# ==========================================
# PYDANTIC SCHEMAS (Η δομή των δεδομένων)
# ==========================================
class SearchURL(BaseModel):
    url: str = Field(description="Το URL αναζήτησης για τον Σπιτόγατο.")

class PropertyPreview(BaseModel):
    url: str = Field(description="Το ακριβές link της αγγελίας")
    price: Optional[int] = Field(description="Η τιμή (μόνο αριθμός)")
    sqm: Optional[int] = Field(description="Τα τετραγωνικά")
    basic_info: str = Field(description="Μια σύντομη πρόταση με ό,τι άλλο γράφει η περίληψη")

class AllProperties(BaseModel):
    properties: List[PropertyPreview] = Field(description="Η πλήρης λίστα με ΟΛΑ τα σπίτια της σελίδας.")

class PropertyLink(BaseModel):
    url: str = Field(description="Το ακριβές link της αγγελίας")

class PropertyList(BaseModel):
    links: List[PropertyLink] = Field(description="Λίστα με τα top 3 links αγγελιών.")

class PropertyDetails(BaseModel):
    url: str
    price: Optional[int] = Field(description="Η τιμή ενοικίου σε Ευρώ (μόνο ο αριθμός).")
    sqm: Optional[int] = Field(description="Τα τετραγωνικά μέτρα.")
    floor: Optional[str] = Field(description="Ο όροφος (π.χ. 1ος, Ισόγειο).")
    features: List[str] = Field(description="Λίστα με παροχές (π.χ. φυσικό αέριο, pet friendly).")
    agent_phone: Optional[str] = Field(description="Το τηλέφωνο του μεσίτη/ιδιοκτήτη, αν υπάρχει.")
    agentic_score: int = Field(description="Βαθμολογία 1-10 για το πόσο ταιριάζει στις ανάγκες.")
    score_reason: str = Field(description="Μια σύντομη πρόταση που εξηγεί γιατί πήρε αυτόν τον βαθμό.")


# ==========================================
# ΑΡΧΙΚΟΠΟΙΗΣΗ API & HELPER
# ==========================================
client = genai.Client(api_key="***REMOVED***")
firecrawl = FirecrawlApp(api_key="fc-be37bf6164d945e282269be71a3ad856")

def get_markdown(url: str) -> str:
    """Helper που δουλεύει ανεξάρτητα από την έκδοση του firecrawl-py"""
    if hasattr(firecrawl, "scrape"):
        res = firecrawl.scrape(url, formats=["markdown"])
        return getattr(res, "markdown", "") or (res.get("markdown", "") if isinstance(res, dict) else "")
    res = firecrawl.scrape_url(url, params={"formats": ["markdown"]})
    return res.get("markdown", "") if isinstance(res, dict) else getattr(res, "markdown", "")

user_request = "Ψάχνω ένα διαμέρισμα στο Παγκράτι, μέχρι 600 ευρώ, pet friendly. Θέλω να είναι φωτεινό."


# ==========================================
# ΒΗΜΑ 1: URL Generation
# ==========================================
print("1. Ο Agent σκέφτεται το URL αναζήτησης...")
prompt_url = f"""
Ο χρήστης ζητάει: '{user_request}'. 
Φτιάξε ένα URL αναζήτησης για το spitogatos.gr. 
Παράδειγμα δομής: https://www.spitogatos.gr/enoikiaseis-katoikies/pagkrati?max_price=600
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
print(f"-> Δημιουργήθηκε το URL: {search_url}\n")


# ==========================================
# ΒΗΜΑ 2: Shallow Scrape (Εύρεση όλων των Links)
# ==========================================
print("2. Το Firecrawl σκανάρει την αρχική σελίδα αποτελεσμάτων...")
search_page_markdown = get_markdown(search_url)

prompt_extract_all = f"""
Διάβασε το παρακάτω markdown από τα αποτελέσματα αναζήτησης του Σπιτόγατου.
Εντόπισε ΟΛΕΣ τις αγγελίες σπιτιών που υπάρχουν στη σελίδα.
Για κάθε μία, βρες το URL της, την τιμή, τα τετραγωνικά και μια σύντομη περιγραφή.
Αγνόησε διαφημίσεις ή links που δεν είναι αγγελίες.

Markdown: 
{search_page_markdown[:25000]}
"""

print("Το Gemini εξάγει ΟΛΑ τα URLs και τα βασικά τους στοιχεία...")
res_all = client.models.generate_content(
    model="gemini-3.8-flash",
    contents=prompt_extract_all,
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=AllProperties,
    ),
)

all_houses = res_all.parsed.properties
print(f"Βρέθηκαν συνολικά {len(all_houses)} σπίτια!\n")


# ==========================================
# ΒΗΜΑ 3Α: Agentic Ranking σε ΟΛΑ τα σπίτια
# ==========================================
print("3. Ο Agent αξιολογεί και τα", len(all_houses), "σπίτια ταυτόχρονα...")

houses_text = ""
for i, h in enumerate(all_houses):
    houses_text += f"[{i}] Link: {h.url} | Τιμή: {h.price} | Τ.μ.: {h.sqm} | Info: {h.basic_info}\n"

prompt_rank_all = f"""
Ο χρήστης ζητάει: '{user_request}'.
Έχεις παρακάτω μια λίστα με {len(all_houses)} διαμερίσματα. 
Λειτουργώντας ως expert μεσίτης, αξιολόγησε το καθένα και διάλεξε τα 3 κορυφαία.
Βασίσου στην τιμή, τα τετραγωνικά και την περιγραφή.

Λίστα:
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
print(f"-> Ο Agent ξεχώρισε τα 3 κορυφαία: {top_3_urls}\n")


# ==========================================
# ΒΗΜΑ 3Β: Deep Scrape ΜΟΝΟ στους "Νικητές"
# ==========================================
print("4. Ο Agent μπαίνει στις 3 καλύτερες αγγελίες για να βρει το τηλέφωνο και να βαθμολογήσει τελικά...")
final_properties = []

for url in top_3_urls:
    detail_markdown = get_markdown(url)
    
    prompt_details = f"""
    Ο χρήστης ζητάει: '{user_request}'.
    Επιβεβαίωσε αν αυτή η αγγελία ταιριάζει (βαθμολόγησε την 1-10) και βρες το τηλέφωνο του μεσίτη/ιδιοκτήτη.
    Εξήγαγε τα δεδομένα σε JSON.
    Αγγελία Markdown:
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
# ΤΟ ΤΕΛΙΚΟ ΑΠΟΤΕΛΕΣΜΑ
# ==========================================
print("\n=== ΤΕΛΙΚΗ ΕΠΙΛΟΓΗ AGENT ===")
final_properties.sort(key=lambda x: x.agentic_score, reverse=True)

for prop in final_properties:
    print(f"Σπίτι: {prop.url}")
    print(f"Τιμή: {prop.price}€ | {prop.sqm} τ.μ. | Όροφος: {prop.floor}")
    print(f"Βαθμολογία: {prop.agentic_score}/10")
    print(f"Αιτιολόγηση: {prop.score_reason}")
    print(f"Τηλέφωνο Μεσίτη: {prop.agent_phone}")
    print("-" * 30)


# Τέλος! Εδώ συνδέετε το middleware σας (Teams)