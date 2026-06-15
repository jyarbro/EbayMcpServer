import os
import hashlib
import base64
import secrets
import logging
import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Route, Mount
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

logging.basicConfig(level=logging.INFO)

mcp = FastMCP(
    "mcp-ebay-server",
    instructions="Search eBay for live auction listings. Use list-auction to find items currently up for bid.",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8000")),
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
    for title, price, currency, end_date, url, item_id in results:
        price_str = f"{currency} {price}" if price else "No bids yet"
        lines.append(f"- {title}\n  Bid: {price_str} | Ends: {end_date}\n  Item ID: {item_id}\n  {url}")
    return "\n\n".join(lines) if lines else "No auctions found."


@mcp.tool()
def get_auction_detail(item_id: str) -> str:
    """Fetch full details for a single eBay listing by item ID.

    Args:
        item_id: The eBay item ID (found at the end of the listing URL, e.g. '387234567890').
    """
    client_id = os.environ["EBAY_CLIENT_ID"]
    client_secret = os.environ["EBAY_CLIENT_SECRET"]
    access_token = get_access_token(client_id, client_secret)
    data = get_item_detail(access_token, item_id)

    if "error" in data:
        return f"Error fetching item: {data['error']}"

    lines = []
    lines.append(f"Title: {data.get('title', 'N/A')}")
    lines.append(f"Condition: {data.get('condition', 'N/A')} {data.get('conditionDescription', '')}")

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
    feedback_score = seller.get("feedbackScore", "N/A")
    feedback_pct = seller.get("feedbackPercentage", "N/A")
    lines.append(f"Seller: {seller.get('username', 'N/A')} — feedback: {feedback_score} ({feedback_pct}% positive)")

    lines.append(f"Location: {data.get('itemLocation', {}).get('city', '')} {data.get('itemLocation', {}).get('country', '')}")

    shipping_options = data.get("shippingOptions", [])
    for s in shipping_options:
        cost = s.get("shippingCost", {})
        cost_str = f"{cost.get('currency', '')} {cost.get('value', '')}" if cost.get("value") else "Free"
        eta = s.get("maxEstimatedDeliveryDate", "")
        eta_str = f" | Est. delivery by {eta}" if eta else ""
        lines.append(f"Shipping: {s.get('shippingServiceCode', '')} — {cost_str}{eta_str}")

    returns = data.get("returnTerms", {})
    if returns:
        accepted = returns.get("returnsAccepted", False)
        if accepted:
            window = returns.get("returnPeriod", {}).get("value", "")
            unit = returns.get("returnPeriod", {}).get("unit", "")
            who_pays = returns.get("refundMethod", "")
            lines.append(f"Returns: accepted, {window} {unit}, {who_pays}")
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

    images = [data.get("image", {}).get("imageUrl", "")] + [
        img.get("imageUrl", "") for img in data.get("additionalImages", [])
    ]
    images = [i for i in images if i]
    if images:
        lines.append(f"\nImages ({len(images)}):")
        for img in images:
            lines.append(f"  {img}")

    lines.append(f"\nURL: {data.get('itemWebUrl', 'N/A')}")
    return "\n".join(lines)


@mcp.tool()
def search_ebay(query: str, amount: int = 10, buying_options: str = "", category_ids: str = "") -> str:
    """Search eBay listings across all formats (auctions, Buy It Now, etc.).

    Args:
        query: Item name or keywords to search for.
        amount: Number of results to return (default 10, max 100).
        buying_options: Filter by buying format. Options: AUCTION, FIXED_PRICE, BEST_OFFER. Leave blank for all.
        category_ids: Comma-separated eBay category IDs to restrict search (e.g. '9355' for Cell Phones). Leave blank for all.
    """
    client_id = os.environ["EBAY_CLIENT_ID"]
    client_secret = os.environ["EBAY_CLIENT_SECRET"]
    access_token = get_access_token(client_id, client_secret)
    results = search_listings(
        access_token,
        query,
        amount,
        buying_options=buying_options or None,
        category_ids=category_ids or None,
    )
    if isinstance(results, dict) and "error" in results:
        return f"Error: {results['error']}"
    if not results:
        return "No listings found."
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
        item_id = item.get("itemId", "")
        url = item.get("itemWebUrl", "")
        lines.append(f"- {title}\n  {price_str} | {options}{end_str}\n  Item ID: {item_id}\n  {url}")
    return "\n\n".join(lines)


@mcp.tool()
def get_items_by_ids(item_ids: str) -> str:
    """Fetch details for up to 20 eBay items in a single call.

    Args:
        item_ids: Comma-separated list of eBay item IDs (e.g. '387234567890,398234512345').
    """
    client_id = os.environ["EBAY_CLIENT_ID"]
    client_secret = os.environ["EBAY_CLIENT_SECRET"]
    access_token = get_access_token(client_id, client_secret)
    ids = [i.strip() for i in item_ids.split(",") if i.strip()]
    if not ids:
        return "No item IDs provided."
    data = get_items_batch(access_token, ids)
    if "error" in data:
        return f"Error: {data['error']}"
    items = data.get("items", [])
    if not items:
        return "No items returned."
    lines = []
    for item in items:
        title = item.get("title", "N/A")
        price = item.get("price", {})
        bid = item.get("currentBidPrice", {})
        price_str = ""
        if bid.get("value"):
            price_str = f"Bid: {bid.get('currency', '')} {bid.get('value', '')}"
        elif price.get("value"):
            price_str = f"Price: {price.get('currency', '')} {price.get('value', '')}"
        lines.append(f"- [{item.get('itemId', '')}] {title}\n  {price_str}\n  {item.get('itemWebUrl', '')}")
    return "\n\n".join(lines)


@mcp.tool()
def get_item_variants(item_group_id: str) -> str:
    """Get all variants (color, size, etc.) for an eBay item group.

    Args:
        item_group_id: The eBay item group ID (shown on listings with multiple variations).
    """
    client_id = os.environ["EBAY_CLIENT_ID"]
    client_secret = os.environ["EBAY_CLIENT_SECRET"]
    access_token = get_access_token(client_id, client_secret)
    data = get_item_group(access_token, item_group_id)
    if "error" in data:
        return f"Error: {data['error']}"
    items = data.get("items", [])
    if not items:
        return "No variants found."
    lines = [f"Item group: {item_group_id}", f"Variants ({len(items)}):"]
    for item in items:
        aspects = "; ".join(
            f"{a.get('localizedName')}: {', '.join(a.get('localizedValues', []))}"
            for a in item.get("variationAttributes", [])
        )
        price = item.get("price", {})
        price_str = f"{price.get('currency', '')} {price.get('value', '')}" if price.get("value") else ""
        lines.append(f"  - {item.get('title', 'N/A')} | {aspects} | {price_str}\n    {item.get('itemWebUrl', '')}")
    return "\n".join(lines)


@mcp.tool()
def get_item_by_legacy(legacy_item_id: str, legacy_variation_id: str = "") -> str:
    """Fetch an eBay item using a legacy (old-style numeric) item ID.

    Args:
        legacy_item_id: The numeric legacy eBay item ID (e.g. '387234567890').
        legacy_variation_id: Optional legacy variation ID for multi-variation listings.
    """
    client_id = os.environ["EBAY_CLIENT_ID"]
    client_secret = os.environ["EBAY_CLIENT_SECRET"]
    access_token = get_access_token(client_id, client_secret)
    data = get_item_by_legacy_id(access_token, legacy_item_id, legacy_variation_id or None)
    if "error" in data:
        return f"Error: {data['error']}"
    lines = [
        f"Title: {data.get('title', 'N/A')}",
        f"Item ID: {data.get('itemId', 'N/A')}",
        f"Condition: {data.get('condition', 'N/A')}",
    ]
    price = data.get("price", {})
    bid = data.get("currentBidPrice", {})
    price_range = data.get("priceRange", {})
    if bid.get("value"):
        lines.append(f"Current bid: {bid.get('currency', '')} {bid.get('value', '')}")
    elif price.get("value"):
        lines.append(f"Price: {price.get('currency', '')} {price.get('value', '')}")
    elif price_range.get("minimum", {}).get("value"):
        min_p = price_range["minimum"]
        max_p = price_range.get("maximum", {})
        if max_p.get("value") and max_p["value"] != min_p["value"]:
            lines.append(f"Price range: {min_p.get('currency', '')} {min_p.get('value', '')} – {max_p.get('value', '')}")
        else:
            lines.append(f"Price: {min_p.get('currency', '')} {min_p.get('value', '')}")
    else:
        lines.append("Price: Not available")
    lines.append(f"URL: {data.get('itemWebUrl', 'N/A')}")
    return "\n".join(lines)


@mcp.tool()
def get_ebay_deals(amount: int = 10, category_ids: str = "") -> str:
    """Get current eBay daily deal items.

    Args:
        amount: Number of deals to return (default 10).
        category_ids: Comma-separated eBay category IDs to filter deals (leave blank for all categories).
    """
    client_id = os.environ["EBAY_CLIENT_ID"]
    client_secret = os.environ["EBAY_CLIENT_SECRET"]
    access_token = get_access_token(client_id, client_secret)
    data = get_deal_items(access_token, category_ids=category_ids or None, limit=amount)
    if "error" in data:
        return f"Error: {data['error']}"
    items = data.get("dealItems", [])
    if not items:
        return "No deal items found."
    lines = []
    for item in items:
        title = item.get("title", "N/A")
        price = item.get("price", {})
        original = item.get("marketingPrice", {}).get("originalPrice", {})
        disc = item.get("marketingPrice", {}).get("discountPercentage", "")
        price_str = f"{price.get('currency', '')} {price.get('value', '')}"
        orig_str = f" (was {original.get('currency', '')} {original.get('value', '')}, {disc}% off)" if original.get("value") else ""
        lines.append(f"- {title}\n  {price_str}{orig_str}\n  {item.get('itemWebUrl', '')}")
    return "\n\n".join(lines)


@mcp.tool()
def get_ebay_sale_events(amount: int = 10) -> str:
    """Get active eBay sale events (sitewide and category sales).

    Args:
        amount: Number of events to return (default 10).
    """
    client_id = os.environ["EBAY_CLIENT_ID"]
    client_secret = os.environ["EBAY_CLIENT_SECRET"]
    access_token = get_access_token(client_id, client_secret)
    data = get_deal_events(access_token, limit=amount)
    if "error" in data:
        return f"Error: {data['error']}"
    events = data.get("events", [])
    if not events:
        return "No sale events found."
    lines = []
    for event in events:
        event_id = event.get("eventId", "N/A")
        title = event.get("title", "N/A")
        start = event.get("startDate", "")
        end = event.get("endDate", "")
        lines.append(f"- {title}\n  Event ID: {event_id} | {start} → {end}")
    return "\n\n".join(lines)


@mcp.tool()
def get_sale_event_items(event_id: str, amount: int = 10) -> str:
    """Get items in a specific eBay sale event.

    Args:
        event_id: The eBay sale event ID (from get_ebay_sale_events).
        amount: Number of items to return (default 10).
    """
    client_id = os.environ["EBAY_CLIENT_ID"]
    client_secret = os.environ["EBAY_CLIENT_SECRET"]
    access_token = get_access_token(client_id, client_secret)
    data = get_deal_event_items(access_token, event_id, limit=amount)
    if "error" in data:
        return f"Error: {data['error']}"
    items = data.get("eventItems", [])
    if not items:
        return "No items found for this event."
    lines = []
    for item in items:
        title = item.get("title", "N/A")
        price = item.get("price", {})
        original = item.get("marketingPrice", {}).get("originalPrice", {})
        disc = item.get("marketingPrice", {}).get("discountPercentage", "")
        price_str = f"{price.get('currency', '')} {price.get('value', '')}"
        orig_str = f" (was {original.get('currency', '')} {original.get('value', '')}, {disc}% off)" if original.get("value") else ""
        lines.append(f"- {title}\n  {price_str}{orig_str}\n  {item.get('itemWebUrl', '')}")
    return "\n\n".join(lines)


@mcp.tool()
def search_sold_listings(query: str, amount: int = 10) -> str:
    """Search eBay's historical sold listings to research what items actually sold for.

    Args:
        query: Item name or keywords to search completed sales for.
        amount: Number of results to return (default 10).
    """
    client_id = os.environ["EBAY_CLIENT_ID"]
    client_secret = os.environ["EBAY_CLIENT_SECRET"]
    access_token = get_access_token(client_id, client_secret)
    data = search_sold_items(access_token, query, limit=amount)
    if "error" in data:
        return f"Error: {data['error']}"
    items = data.get("itemSales", [])
    if not items:
        return "No sold listings found."
    lines = []
    for item in items:
        title = item.get("title", "N/A")
        sold_price = item.get("lastSoldPrice", {})
        sold_date = item.get("lastSoldDate", "")
        price_str = f"{sold_price.get('currency', '')} {sold_price.get('value', '')}" if sold_price.get("value") else "N/A"
        lines.append(f"- {title}\n  Sold for: {price_str} | Date: {sold_date}\n  {item.get('itemWebUrl', '')}")
    return "\n\n".join(lines)


# In-memory store for pending auth codes: {code: {code_challenge, redirect_uri, client_id}}
_auth_codes: dict = {}

UNPROTECTED_PATHS = {
    "/token",
    "/authorize",
    "/.well-known/oauth-authorization-server",
    "/.well-known/oauth-protected-resource",
    "/.well-known/oauth-protected-resource/mcp",
    "/favicon.ico",
}


class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in UNPROTECTED_PATHS:
            return await call_next(request)
        auth_token = os.environ.get("MCP_AUTH_TOKEN", "")
        if not auth_token:
            return await call_next(request)
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer ") or auth_header[7:] != auth_token:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)


def public_base_url(request: Request) -> str:
    domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
    if domain:
        return f"https://{domain}"
    # Fallback: honour X-Forwarded-Proto from reverse proxy
    proto = request.headers.get("x-forwarded-proto", "https")
    host = request.headers.get("x-forwarded-host", request.headers.get("host", "localhost"))
    return f"{proto}://{host}"


async def oauth_metadata(request: Request):
    base = public_base_url(request)
    return JSONResponse({
        "issuer": base,
        "authorization_endpoint": f"{base}/authorize",
        "token_endpoint": f"{base}/token",
        "grant_types_supported": ["authorization_code", "client_credentials"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "none"],
        "response_types_supported": ["code"],
    })


async def protected_resource_metadata(request: Request):
    base = public_base_url(request)
    return JSONResponse({
        "resource": base,
        "authorization_servers": [base],
        "bearer_methods_supported": ["header"],
    })


def _authorize_page(params: dict, error: str = ""):
    from starlette.responses import HTMLResponse
    import html as html_mod
    hidden = "\n".join(
        f'<input type="hidden" name="{html_mod.escape(k, quote=True)}" value="{html_mod.escape(v, quote=True)}">'
        for k, v in params.items()
    )
    error_html = f'<p class="err">{html_mod.escape(error)}</p>' if error else ""
    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>eBay MCP – Authorize</title>
<style>body{{font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#f5f5f5}}
.card{{background:#fff;padding:2rem 3rem;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,.1);text-align:center}}
h2{{margin-bottom:.5rem}}p{{color:#666;margin-bottom:1.5rem}}
.err{{color:#c00;font-weight:600}}
input[type=password]{{padding:.6rem;border:1px solid #ccc;border-radius:8px;width:100%;margin-bottom:1rem;box-sizing:border-box}}
button{{display:inline-block;background:#0070f3;color:#fff;padding:.75rem 2rem;border-radius:8px;border:none;font-weight:600;font-size:1rem;cursor:pointer}}
button:hover{{background:#0051cc}}</style></head>
<body><div class="card">
<h2>eBay Auction Search</h2>
<p>Enter the passphrase to allow Claude.ai access.</p>
{error_html}
<form method="post" action="/authorize">
{hidden}
<input type="password" name="passphrase" placeholder="Passphrase" autofocus>
<button type="submit">Allow Access</button>
</form>
</div></body></html>"""
    return HTMLResponse(html, status_code=401 if error else 200)


async def authorize_endpoint(request: Request):
    if request.method == "POST":
        form = await request.form()
        params = {k: str(v) for k, v in form.items()}
    else:
        params = dict(request.query_params)
    passphrase = params.pop("passphrase", "")

    client_id = params.get("client_id", "")
    redirect_uri = params.get("redirect_uri", "")
    state = params.get("state", "")
    code_challenge = params.get("code_challenge", "")
    code_challenge_method = params.get("code_challenge_method", "S256")

    expected_id = os.environ.get("MCP_CLIENT_ID", "ebay-mcp")
    if client_id != expected_id:
        return JSONResponse({"error": "invalid_client"}, status_code=400)

    expected_passphrase = os.environ.get("MCP_AUTH_PASSPHRASE", "")
    if expected_passphrase:
        if request.method == "GET":
            return _authorize_page(params)
        if not secrets.compare_digest(passphrase, expected_passphrase):
            return _authorize_page(params, error="Incorrect passphrase.")

    code = secrets.token_urlsafe(32)
    _auth_codes[code] = {
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
    }

    sep = "&" if "?" in redirect_uri else "?"
    callback_url = f"{redirect_uri}{sep}code={code}&state={state}"
    return RedirectResponse(callback_url, status_code=302)


async def token_endpoint(request: Request):
    if request.method == "GET":
        base = public_base_url(request)
        return JSONResponse({"token_endpoint": f"{base}/token", "grant_types_supported": ["authorization_code", "client_credentials"]})
    form = await request.form()
    grant_type = form.get("grant_type", "")
    auth_token = os.environ.get("MCP_AUTH_TOKEN", "")

    if not auth_token:
        return JSONResponse({"error": "server_not_configured"}, status_code=500)

    if grant_type == "authorization_code":
        code = form.get("code", "")
        code_verifier = form.get("code_verifier", "")

        logging.info(f"Token exchange: code={code[:8]}... verifier_len={len(code_verifier)} form_keys={list(form.keys())}")

        stored = _auth_codes.pop(code, None)
        if not stored:
            logging.error(f"Code not found. Known codes: {list(_auth_codes.keys())}")
            return JSONResponse({"error": "invalid_grant", "detail": "code_not_found"}, status_code=401)

        # Validate PKCE S256
        digest = hashlib.sha256(code_verifier.encode()).digest()
        computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        logging.info(f"PKCE: computed={computed[:16]}... stored={stored['code_challenge'][:16]}...")
        if computed != stored["code_challenge"]:
            return JSONResponse({"error": "invalid_grant", "detail": "pkce_mismatch"}, status_code=401)

        return JSONResponse({
            "access_token": auth_token,
            "token_type": "bearer",
            "expires_in": 3600,
        })

    if grant_type == "client_credentials":
        client_id = form.get("client_id", "")
        client_secret = form.get("client_secret", "")
        expected_id = os.environ.get("MCP_CLIENT_ID", "ebay-mcp")
        if client_id == expected_id and client_secret == auth_token:
            return JSONResponse({
                "access_token": auth_token,
                "token_type": "bearer",
                "expires_in": 3600,
            })
        return JSONResponse({"error": "invalid_client"}, status_code=401)

    return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)


if __name__ == "__main__":
    from contextlib import asynccontextmanager

    fastmcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app):
        async with fastmcp_app.router.lifespan_context(fastmcp_app):
            yield

    app = Starlette(
        routes=[
            Route("/.well-known/oauth-authorization-server", oauth_metadata),
            Route("/.well-known/oauth-protected-resource", protected_resource_metadata),
            Route("/.well-known/oauth-protected-resource/mcp", protected_resource_metadata),
            Route("/authorize", authorize_endpoint, methods=["GET", "POST"]),
            Route("/token", token_endpoint, methods=["GET", "POST"]),
            Mount("/", fastmcp_app),
        ],
        lifespan=lifespan,
    )
    app.add_middleware(BearerAuthMiddleware)

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
