"""Manual probe for the live patent search wired into
agent/tools.py:search_patents() — tries USPTO ODP, then Google Patents (via
Programmable Search), then the curated fixture. Reads backend/.env directly (this
script is run standalone, not through main.py's load_dotenv()). Run with
`python test_patents.py`; prints the parsed result so field-mapping mistakes are
obvious without needing to read raw JSON. The old api.patentsview.org this file
used to probe now redirects to a login page — that legacy API has been retired.
"""

import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

from agent.tools import search_patents


async def main():
    if os.environ.get("USPTO_ODP_API_KEY"):
        print("Trying live source: USPTO Open Data Portal.\n")
    elif os.environ.get("SERPAPI_API_KEY"):
        print("Trying live source: SerpAPI Google Patents.\n")
    elif os.environ.get("GOOGLE_SEARCH_API_KEY") and os.environ.get("GOOGLE_SEARCH_CX"):
        print("Trying live source: Google Patents (Programmable Search).\n")
    else:
        print("No patent API key set - using the fixture.\n")

    query = "solid state battery"
    results = await search_patents(query, limit=5)
    print(f"search_patents({query!r}) -> {len(results)} result(s)\n")
    for r in results:
        # Some Windows consoles are cp1252 and choke on characters a live source's
        # title/snippet can contain (e.g. a truncated "…") — fall back to an
        # ASCII-safe repr rather than crashing after the real work is done.
        try:
            print(r)
        except UnicodeEncodeError:
            print(repr(r).encode("ascii", "backslashreplace").decode("ascii"))


if __name__ == "__main__":
    asyncio.run(main())
