import os
import logging
import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount
from ebayAPItool import get_access_token, make_ebay_api_request

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
    for title, price, currency, end_date, url in results:
        price_str = f"{currency} {price}" if price else "No bids yet"
        lines.append(f"- {title}\n  Bid: {price_str} | Ends: {end_date}\n  {url}")

    return "\n\n".join(lines) if lines else "No auctions found."


class BearerAuthMiddleware(BaseHTTPMiddleware):
    UNPROTECTED = {"/token", "/.well-known/oauth-authorization-server"}

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.UNPROTECTED:
            return await call_next(request)
        auth_token = os.environ.get("MCP_AUTH_TOKEN", "")
        if not auth_token:
            return await call_next(request)
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer ") or auth_header[7:] != auth_token:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)


async def oauth_metadata(request: Request):
    base = str(request.base_url).rstrip("/")
    return JSONResponse({
        "issuer": base,
        "token_endpoint": f"{base}/token",
        "grant_types_supported": ["client_credentials"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
    })


async def token_endpoint(request: Request):
    form = await request.form()
    grant_type = form.get("grant_type")
    client_id = form.get("client_id", "")
    client_secret = form.get("client_secret", "")

    expected_id = os.environ.get("MCP_CLIENT_ID", "ebay-mcp")
    expected_secret = os.environ.get("MCP_AUTH_TOKEN", "")

    if not expected_secret:
        return JSONResponse({"error": "server_not_configured"}, status_code=500)

    if grant_type == "client_credentials" and client_id == expected_id and client_secret == expected_secret:
        return JSONResponse({
            "access_token": expected_secret,
            "token_type": "bearer",
            "expires_in": 3600,
        })
    return JSONResponse({"error": "invalid_client"}, status_code=401)


if __name__ == "__main__":
    fastmcp_app = mcp.streamable_http_app()

    app = Starlette(routes=[
        Route("/.well-known/oauth-authorization-server", oauth_metadata),
        Route("/token", token_endpoint, methods=["POST"]),
        Mount("/", fastmcp_app),
    ])
    app.add_middleware(BearerAuthMiddleware)

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
