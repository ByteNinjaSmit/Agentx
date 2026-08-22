"""Manual probe for the live USPTO ODP patent search wired into
agent/tools.py:search_patents(). Requires USPTO_ODP_API_KEY in the environment (a
free key, but one that requires signing up for a USPTO.gov account with MFA — see
.env.example). Run with `python test_patents.py` after exporting the key; prints
the parsed result so field-mapping mistakes are obvious without needing to read raw
JSON. The old api.patentsview.org this file used to probe now redirects to a login
page — that legacy API has been retired.
"""

import asyncio
import os

from agent.tools import search_patents


async def main():
    if not os.environ.get("USPTO_ODP_API_KEY"):
        print("USPTO_ODP_API_KEY is not set - search_patents() will use the fixture, not the live API.")
        print("Set it and re-run to test the live USPTO Open Data Portal integration.\n")

    query = "solid state battery"
    results = await search_patents(query, limit=5)
    print(f"search_patents({query!r}) -> {len(results)} result(s)\n")
    for r in results:
        print(r)


if __name__ == "__main__":
    asyncio.run(main())
