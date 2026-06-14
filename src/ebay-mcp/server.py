import asyncio
import os
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio
import logging

from ebayAPItool import (
    get_access_token,
    make_ebay_api_request,
    get_item_detail,
    search_listings,
    get_items_batch,
    get_item_group,
    get_item_by_legacy_id,
    get_deal_items,
    get_deal_events,
    get_deal_event_items,
    search_sold_items,
)

server = Server("mcp-ebay-server")
logger = logging.getLogger("mcp-ebay-server")
logger.setLevel(logging.INFO)


## Logging
@server.set_logging_level()
async def set_logging_level(level: types.LoggingLevel) -> types.EmptyResult:
    logger.setLevel(level.upper())
    await server.request_context.session.send_log_message(
        level="info", data=f"Log level set to {level}", logger="mcp-ebay-server"
    )
    return types.EmptyResult()


## Tools
@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="list-auction",
            description="Search eBay for auction-only listings matching a query.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Item name to search for."},
                    "ammount": {"type": "integer", "description": "Number of results to return."},
                },
                "required": ["query", "ammount"],
            },
        ),
        types.Tool(
            name="get-auction-detail",
            description="Fetch full details for a single eBay listing by item ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "string", "description": "The eBay item ID."},
                },
                "required": ["item_id"],
            },
        ),
        types.Tool(
            name="search-ebay",
            description="Search eBay listings across all buying formats (auctions, Buy It Now, etc.) with optional category filtering.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Item name or keywords to search for."},
                    "amount": {"type": "integer", "description": "Number of results (default 10, max 100)."},
                    "buying_options": {"type": "string", "description": "Filter by format: AUCTION, FIXED_PRICE, or BEST_OFFER. Leave blank for all."},
                    "category_ids": {"type": "string", "description": "Comma-separated eBay category IDs (e.g. '9355'). Leave blank for all."},
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="get-items-by-ids",
            description="Fetch details for up to 20 eBay items in a single call.",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_ids": {"type": "string", "description": "Comma-separated eBay item IDs."},
                },
                "required": ["item_ids"],
            },
        ),
        types.Tool(
            name="get-item-variants",
            description="Get all variants (color, size, etc.) for an eBay item group.",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_group_id": {"type": "string", "description": "The eBay item group ID."},
                },
                "required": ["item_group_id"],
            },
        ),
        types.Tool(
            name="get-item-by-legacy",
            description="Fetch an eBay item using a legacy (old-style numeric) item ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "legacy_item_id": {"type": "string", "description": "The numeric legacy eBay item ID."},
                    "legacy_variation_id": {"type": "string", "description": "Optional legacy variation ID."},
                },
                "required": ["legacy_item_id"],
            },
        ),
        types.Tool(
            name="get-ebay-deals",
            description="Get current eBay daily deal items.",
            inputSchema={
                "type": "object",
                "properties": {
                    "amount": {"type": "integer", "description": "Number of deals to return (default 10)."},
                    "category_ids": {"type": "string", "description": "Comma-separated category IDs to filter. Leave blank for all."},
                },
                "required": [],
            },
        ),
        types.Tool(
            name="get-ebay-sale-events",
            description="Get active eBay sale events (sitewide and category sales).",
            inputSchema={
                "type": "object",
                "properties": {
                    "amount": {"type": "integer", "description": "Number of events to return (default 10)."},
                },
                "required": [],
            },
        ),
        types.Tool(
            name="get-sale-event-items",
            description="Get items in a specific eBay sale event.",
            inputSchema={
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "The eBay sale event ID (from get-ebay-sale-events)."},
                    "amount": {"type": "integer", "description": "Number of items to return (default 10)."},
                },
                "required": ["event_id"],
            },
        ),
        types.Tool(
            name="search-sold-listings",
            description="Search eBay's historical sold listings to research what items actually sold for.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Item name or keywords to search completed sales for."},
                    "amount": {"type": "integer", "description": "Number of results to return (default 10)."},
                },
                "required": ["query"],
            },
        ),
    ]


def _get_token():
    client_id = os.environ["EBAY_CLIENT_ID"]
    client_secret = os.environ["EBAY_CLIENT_SECRET"]
    return get_access_token(client_id, client_secret)


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if not arguments:
        arguments = {}

    if name == "list-auction":
        query = arguments.get("query")
        amount = arguments.get("ammount", 1)
        if not query:
            raise ValueError("Missing query")
        token = _get_token()
        results = make_ebay_api_request(token, query, amount)
        if isinstance(results, str):
            text = results
        else:
            lines = []
            for title, price, currency, end_date, url, item_id in results:
                price_str = f"{currency} {price}" if price else "No bids yet"
                lines.append(f"- {title}\n  Bid: {price_str} | Ends: {end_date}\n  Item ID: {item_id}\n  {url}")
            text = "\n\n".join(lines) if lines else "No auctions found."

    elif name == "get-auction-detail":
        item_id = arguments.get("item_id")
        if not item_id:
            raise ValueError("Missing item_id")
        token = _get_token()
        data = get_item_detail(token, item_id)
        if "error" in data:
            text = f"Error fetching item: {data['error']}"
        else:
            lines = [
                f"Title: {data.get('title', 'N/A')}",
                f"Condition: {data.get('condition', 'N/A')} {data.get('conditionDescription', '')}",
            ]
            bid = data.get("currentBidPrice", {})
            if bid:
                lines.append(f"Current bid: {bid.get('currency', '')} {bid.get('value', 'N/A')}")
            bid_count = data.get("bidCount")
            if bid_count is not None:
                lines.append(f"Bid count: {bid_count}")
            buy_now = data.get("buyItNowPrice", {})
            if buy_now:
                lines.append(f"Buy It Now: {buy_now.get('currency', '')} {buy_now.get('value', '')}")
            lines.append(f"Ends: {data.get('itemEndDate', 'N/A')}")
            seller = data.get("seller", {})
            lines.append(f"Seller: {seller.get('username', 'N/A')} — feedback: {seller.get('feedbackScore', 'N/A')} ({seller.get('feedbackPercentage', 'N/A')}% positive)")
            lines.append(f"Location: {data.get('itemLocation', {}).get('city', '')} {data.get('itemLocation', {}).get('country', '')}")
            for s in data.get("shippingOptions", []):
                cost = s.get("shippingCost", {})
                cost_str = f"{cost.get('currency', '')} {cost.get('value', '')}" if cost.get("value") else "Free"
                eta = s.get("maxEstimatedDeliveryDate", "")
                lines.append(f"Shipping: {s.get('shippingServiceCode', '')} — {cost_str}" + (f" | Est. delivery by {eta}" if eta else ""))
            returns = data.get("returnTerms", {})
            if returns:
                if returns.get("returnsAccepted"):
                    window = returns.get("returnPeriod", {}).get("value", "")
                    unit = returns.get("returnPeriod", {}).get("unit", "")
                    lines.append(f"Returns: accepted, {window} {unit}, {returns.get('refundMethod', '')}")
                else:
                    lines.append("Returns: not accepted")
            specifics = data.get("localizedAspects", [])
            if specifics:
                lines.append("\nItem specifics:")
                for s in specifics:
                    lines.append(f"  {s.get('name')}: {s.get('value')}")
            desc = data.get("description", "")
            if desc:
                lines.append(f"\nDescription:\n{desc[:2000]}{'...' if len(desc) > 2000 else ''}")
            images = [data.get("image", {}).get("imageUrl", "")] + [img.get("imageUrl", "") for img in data.get("additionalImages", [])]
            images = [i for i in images if i]
            if images:
                lines.append(f"\nImages ({len(images)}):")
                for img in images:
                    lines.append(f"  {img}")
            lines.append(f"\nURL: {data.get('itemWebUrl', 'N/A')}")
            text = "\n".join(lines)

    elif name == "search-ebay":
        query = arguments.get("query")
        if not query:
            raise ValueError("Missing query")
        token = _get_token()
        results = search_listings(
            token,
            query,
            arguments.get("amount", 10),
            buying_options=arguments.get("buying_options") or None,
            category_ids=arguments.get("category_ids") or None,
        )
        if isinstance(results, dict) and "error" in results:
            text = f"Error: {results['error']}"
        elif not results:
            text = "No listings found."
        else:
            lines = []
            for item in results:
                title = item.get("title", "N/A")
                options = ", ".join(item.get("buyingOptions", []))
                price_obj = item.get("price", {})
                bid_obj = item.get("currentBidPrice", {})
                price_str = ""
                if bid_obj.get("value"):
                    price_str = f"Bid: {bid_obj.get('currency', '')} {bid_obj.get('value', '')}"
                elif price_obj.get("value"):
                    price_str = f"Price: {price_obj.get('currency', '')} {price_obj.get('value', '')}"
                end_date = item.get("itemEndDate", "")
                end_str = f" | Ends: {end_date}" if end_date else ""
                lines.append(f"- {title}\n  {price_str} | {options}{end_str}\n  Item ID: {item.get('itemId', '')}\n  {item.get('itemWebUrl', '')}")
            text = "\n\n".join(lines)

    elif name == "get-items-by-ids":
        item_ids_str = arguments.get("item_ids", "")
        ids = [i.strip() for i in item_ids_str.split(",") if i.strip()]
        if not ids:
            raise ValueError("No item IDs provided")
        token = _get_token()
        data = get_items_batch(token, ids)
        if "error" in data:
            text = f"Error: {data['error']}"
        else:
            items = data.get("items", [])
            lines = []
            for item in items:
                price = item.get("price", {})
                bid = item.get("currentBidPrice", {})
                price_str = ""
                if bid.get("value"):
                    price_str = f"Bid: {bid.get('currency', '')} {bid.get('value', '')}"
                elif price.get("value"):
                    price_str = f"Price: {price.get('currency', '')} {price.get('value', '')}"
                lines.append(f"- [{item.get('itemId', '')}] {item.get('title', 'N/A')}\n  {price_str}\n  {item.get('itemWebUrl', '')}")
            text = "\n\n".join(lines) if lines else "No items returned."

    elif name == "get-item-variants":
        item_group_id = arguments.get("item_group_id")
        if not item_group_id:
            raise ValueError("Missing item_group_id")
        token = _get_token()
        data = get_item_group(token, item_group_id)
        if "error" in data:
            text = f"Error: {data['error']}"
        else:
            items = data.get("items", [])
            lines = [f"Item group: {item_group_id}", f"Variants ({len(items)}):"]
            for item in items:
                aspects = "; ".join(
                    f"{a.get('localizedName')}: {', '.join(a.get('localizedValues', []))}"
                    for a in item.get("variationAttributes", [])
                )
                price = item.get("price", {})
                price_str = f"{price.get('currency', '')} {price.get('value', '')}" if price.get("value") else ""
                lines.append(f"  - {item.get('title', 'N/A')} | {aspects} | {price_str}\n    {item.get('itemWebUrl', '')}")
            text = "\n".join(lines) if items else "No variants found."

    elif name == "get-item-by-legacy":
        legacy_id = arguments.get("legacy_item_id")
        if not legacy_id:
            raise ValueError("Missing legacy_item_id")
        token = _get_token()
        data = get_item_by_legacy_id(token, legacy_id, arguments.get("legacy_variation_id") or None)
        if "error" in data:
            text = f"Error: {data['error']}"
        else:
            price = data.get("price", {})
            bid = data.get("currentBidPrice", {})
            price_str = ""
            if bid.get("value"):
                price_str = f"Bid: {bid.get('currency', '')} {bid.get('value', '')}"
            elif price.get("value"):
                price_str = f"Price: {price.get('currency', '')} {price.get('value', '')}"
            text = "\n".join([
                f"Title: {data.get('title', 'N/A')}",
                f"Item ID: {data.get('itemId', 'N/A')}",
                f"Condition: {data.get('condition', 'N/A')}",
                price_str,
                f"URL: {data.get('itemWebUrl', 'N/A')}",
            ])

    elif name == "get-ebay-deals":
        token = _get_token()
        data = get_deal_items(token, category_ids=arguments.get("category_ids") or None, limit=arguments.get("amount", 10))
        if "error" in data:
            text = f"Error: {data['error']}"
        else:
            items = data.get("dealItems", [])
            lines = []
            for item in items:
                price = item.get("price", {})
                original = item.get("marketingPrice", {}).get("originalPrice", {})
                disc = item.get("marketingPrice", {}).get("discountPercentage", "")
                price_str = f"{price.get('currency', '')} {price.get('value', '')}"
                orig_str = f" (was {original.get('currency', '')} {original.get('value', '')}, {disc}% off)" if original.get("value") else ""
                lines.append(f"- {item.get('title', 'N/A')}\n  {price_str}{orig_str}\n  {item.get('itemWebUrl', '')}")
            text = "\n\n".join(lines) if lines else "No deal items found."

    elif name == "get-ebay-sale-events":
        token = _get_token()
        data = get_deal_events(token, limit=arguments.get("amount", 10))
        if "error" in data:
            text = f"Error: {data['error']}"
        else:
            events = data.get("events", [])
            lines = []
            for event in events:
                lines.append(f"- {event.get('title', 'N/A')}\n  Event ID: {event.get('eventId', 'N/A')} | {event.get('startDate', '')} → {event.get('endDate', '')}")
            text = "\n\n".join(lines) if lines else "No sale events found."

    elif name == "get-sale-event-items":
        event_id = arguments.get("event_id")
        if not event_id:
            raise ValueError("Missing event_id")
        token = _get_token()
        data = get_deal_event_items(token, event_id, limit=arguments.get("amount", 10))
        if "error" in data:
            text = f"Error: {data['error']}"
        else:
            items = data.get("eventItems", [])
            lines = []
            for item in items:
                price = item.get("price", {})
                original = item.get("marketingPrice", {}).get("originalPrice", {})
                disc = item.get("marketingPrice", {}).get("discountPercentage", "")
                price_str = f"{price.get('currency', '')} {price.get('value', '')}"
                orig_str = f" (was {original.get('currency', '')} {original.get('value', '')}, {disc}% off)" if original.get("value") else ""
                lines.append(f"- {item.get('title', 'N/A')}\n  {price_str}{orig_str}\n  {item.get('itemWebUrl', '')}")
            text = "\n\n".join(lines) if lines else "No items found for this event."

    elif name == "search-sold-listings":
        query = arguments.get("query")
        if not query:
            raise ValueError("Missing query")
        token = _get_token()
        data = search_sold_items(token, query, limit=arguments.get("amount", 10))
        if "error" in data:
            text = f"Error: {data['error']}"
        else:
            items = data.get("itemSales", [])
            lines = []
            for item in items:
                sold_price = item.get("lastSoldPrice", {})
                price_str = f"{sold_price.get('currency', '')} {sold_price.get('value', '')}" if sold_price.get("value") else "N/A"
                lines.append(f"- {item.get('title', 'N/A')}\n  Sold for: {price_str} | Date: {item.get('lastSoldDate', '')}\n  {item.get('itemWebUrl', '')}")
            text = "\n\n".join(lines) if lines else "No sold listings found."

    else:
        raise ValueError(f"Unknown tool: {name}")

    return [types.TextContent(type="text", text=text)]


async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="mcp-ebay-server",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
