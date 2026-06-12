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


async def oauth_metadata(request: Request):
    base = str(request.base_url).rstrip("/")
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
    base = str(request.base_url).rstrip("/")
    return JSONResponse({
        "resource": base,
        "authorization_servers": [base],
        "bearer_methods_supported": ["header"],
    })


async def authorize_endpoint(request: Request):
    params = dict(request.query_params)
    client_id = params.get("client_id", "")
    redirect_uri = params.get("redirect_uri", "")
    state = params.get("state", "")
    code_challenge = params.get("code_challenge", "")
    code_challenge_method = params.get("code_challenge_method", "S256")

    expected_id = os.environ.get("MCP_CLIENT_ID", "ebay-mcp")
    if client_id != expected_id:
        return JSONResponse({"error": "invalid_client"}, status_code=400)

    code = secrets.token_urlsafe(32)
    _auth_codes[code] = {
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
    }

    sep = "&" if "?" in redirect_uri else "?"
    callback_url = f"{redirect_uri}{sep}code={code}&state={state}"
    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>eBay MCP – Authorize</title>
<style>body{{font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#f5f5f5}}
.card{{background:#fff;padding:2rem 3rem;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,.1);text-align:center}}
h2{{margin-bottom:.5rem}}p{{color:#666;margin-bottom:1.5rem}}
a{{display:inline-block;background:#0070f3;color:#fff;padding:.75rem 2rem;border-radius:8px;text-decoration:none;font-weight:600}}
a:hover{{background:#0051cc}}</style></head>
<body><div class="card">
<h2>eBay Auction Search</h2>
<p>Allow Claude.ai to access your eBay MCP server?</p>
<a href="{callback_url}">Allow Access</a>
</div></body></html>"""
    from starlette.responses import HTMLResponse
    return HTMLResponse(html)


async def token_endpoint(request: Request):
    if request.method == "GET":
        base = str(request.base_url).rstrip("/")
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
    fastmcp_app = mcp.streamable_http_app()

    app = Starlette(routes=[
        Route("/.well-known/oauth-authorization-server", oauth_metadata),
        Route("/.well-known/oauth-protected-resource", protected_resource_metadata),
        Route("/.well-known/oauth-protected-resource/mcp", protected_resource_metadata),
        Route("/authorize", authorize_endpoint),
        Route("/token", token_endpoint, methods=["GET", "POST"]),
        Mount("/", fastmcp_app),
    ])
    app.add_middleware(BearerAuthMiddleware)

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
