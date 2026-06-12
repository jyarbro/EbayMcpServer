import os
import logging
from mcp.server.fastmcp import FastMCP
from ebayAPItool import get_access_token, make_ebay_api_request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-ebay-server")

mcp = FastMCP(
    "mcp-ebay-server",
    instructions="Search eBay for live auction listings. Use list-auction to find items currently up for bid.",
)


@mcp.tool()
def list_auction(query: str, amount: int = 10) -> str:
    """Search eBay for auction listings matching the query.

    Args:
        query: Item name to search for on eBay (e.g. 'vintage camera', 'lego set').
        amount: Number of auction results to return (default 10, max 100).
    """
    client_id = os.environ["EBAY_CLIENT_ID"]
    client_secret = os.environ["EBAY_CLIENT_SECRET"]

    access_token = get_access_token(client_id, client_secret)
    results = make_ebay_api_request(access_token, query, amount)

    if isinstance(results, str):
        return results

    lines = []
    for title, price, currency, end_date, url in results:
        price_str = f"{currency} {price}" if price else "No bids yet"
        lines.append(f"- {title}\n  Bid: {price_str} | Ends: {end_date}\n  {url}")

    return "\n\n".join(lines) if lines else "No auctions found."


if __name__ == "__main__":
    os.environ.setdefault("HOST", "0.0.0.0")
    os.environ.setdefault("PORT", "8000")
    mcp.run(transport="streamable-http")
