# eBay MCP Server — Claude.ai Connector

Search eBay for live auction listings via a hosted MCP server connected to Claude.ai.

Forked from [CooKey-Monster/EbayMcpServer](https://github.com/CooKey-Monster/EbayMcpServer).

## What it does

Adds two tools to Claude.ai for researching eBay auctions:

> "Find me 10 auctions for vintage cameras"
> "Get the details on that first listing"

## Deployment (Railway)

### 1. Prerequisites

- [Railway](https://railway.app) account
- [eBay Developer](https://developer.ebay.com/develop) app credentials (Client ID + Secret)

### 2. Deploy

1. Fork this repo and create a new Railway project from it
2. In Railway project settings, set **Build > Builder** to **Dockerfile** with path `Dockerfile.plugin`
3. Set the following environment variables in Railway:

| Variable | Description |
|----------|-------------|
| `EBAY_CLIENT_ID` | Your eBay App ID |
| `EBAY_CLIENT_SECRET` | Your eBay Client Secret |
| `MCP_AUTH_TOKEN` | A strong random secret (e.g. output of `openssl rand -hex 24`) |
| `MCP_CLIENT_ID` | A client identifier string (e.g. `ebay-mcp`) |
| `MCP_AUTH_PASSPHRASE` | Optional. If set, the authorization page requires this passphrase before granting access |

Railway automatically sets `PORT` and `RAILWAY_PUBLIC_DOMAIN`.

### 3. Connect to Claude.ai

1. Go to **Claude.ai → Settings → Connectors → Add custom connector**
2. Fill in:
   - **MCP Server URL**: `https://<your-railway-domain>/mcp`
   - **Client ID**: the value you set for `MCP_CLIENT_ID`
3. Click **Connect** and approve access on the authorization page that appears

## Tools

| Tool | Arguments | Description |
|------|-----------|-------------|
| `list_auction` | `query` (string), `amount` (int, default 10) | Search eBay auctions by keyword. Returns title, current bid, end time, item ID, and URL for each result. |
| `get_auction_detail` | `item_id` (string) | Fetch full details for a single listing using the item ID from `list_auction`. Returns title, condition, current bid, bid count, seller feedback score and positive %, return policy, all shipping options with estimated delivery, item specifics (model, storage, etc.), full description, and all listing photos. |

> **Note:** Watcher count is not available — eBay restricts that to seller-authenticated APIs only.
