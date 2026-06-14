# eBay MCP Server — Claude.ai Connector

Search and research eBay listings via a hosted MCP server connected to Claude.ai.

Forked from [CooKey-Monster/EbayMcpServer](https://github.com/CooKey-Monster/EbayMcpServer).

## What it does

Adds ten tools to Claude.ai for browsing, researching, and comparing eBay listings:

> "Find me vintage cameras under $200 — auctions and Buy It Now"
> "What did that model actually sell for recently?"
> "Are there any eBay sale events on right now?"

## Deployment (Railway)

### 1. Prerequisites

- [Railway](https://railway.app) account
- [eBay Developer](https://developer.ebay.com/develop) app credentials (Client ID + Secret)

### 2. Deploy

1. Fork this repo and create a new Railway project from it
2. In Railway project settings, set **Build > Builder** to **Dockerfile** with path `Dockerfile.plugin`
3. Set the following environment variables in Railway:

| Variable | Required | Description |
|----------|----------|-------------|
| `EBAY_CLIENT_ID` | Yes | Your eBay App ID |
| `EBAY_CLIENT_SECRET` | Yes | Your eBay Client Secret |
| `MCP_AUTH_TOKEN` | Yes | Bearer token Claude.ai uses to authenticate every request. Use a strong random value (e.g. `openssl rand -hex 24`). |
| `MCP_CLIENT_ID` | Yes | Client identifier checked during OAuth. Can be any string (e.g. `ebay-mcp`). |
| `MCP_AUTH_PASSPHRASE` | Recommended | If set, the authorization page shows a password field. Only someone who knows this passphrase can connect a new Claude.ai session. Use ASCII characters only; avoid leading/trailing spaces. |

Railway automatically sets `PORT` and `RAILWAY_PUBLIC_DOMAIN`.

### 3. Connect to Claude.ai

1. Go to **Claude.ai → Settings → Connectors → Add custom connector**
2. Fill in:
   - **MCP Server URL**: `https://<your-railway-domain>/mcp`
   - **Client ID**: the value you set for `MCP_CLIENT_ID`
3. Click **Connect** — a browser page will open asking you to authorize access
4. If `MCP_AUTH_PASSPHRASE` is set, enter the passphrase and click **Allow Access**
5. You'll be redirected back to Claude.ai and the connector will activate

> The passphrase is only required when first connecting (or reconnecting). It is not needed for individual searches.

## Tools

### Browse & Search

| Tool | Arguments | Description |
|------|-----------|-------------|
| `list_auction` | `query` (string), `amount` (int, default 10) | Search eBay auction-only listings by keyword. Returns title, current bid, end time, item ID, and URL. |
| `search_ebay` | `query` (string), `amount` (int, default 10), `buying_options` (string, optional), `category_ids` (string, optional) | Search all eBay listing formats. `buying_options` can be `AUCTION`, `FIXED_PRICE`, or `BEST_OFFER` (leave blank for all). `category_ids` accepts a comma-separated list of eBay category IDs. |
| `get_auction_detail` | `item_id` (string) | Fetch full details for a single listing: title, condition, bid/price, bid count, seller feedback, return policy, shipping options with estimated delivery, item specifics, description, and photos. |
| `get_items_by_ids` | `item_ids` (string) | Batch-fetch details for up to 20 items in one call. Pass a comma-separated list of item IDs. |
| `get_item_variants` | `item_group_id` (string) | Get all variants (color, size, storage, etc.) for a multi-variation eBay listing. |
| `get_item_by_legacy` | `legacy_item_id` (string), `legacy_variation_id` (string, optional) | Look up an item using an old-style numeric eBay item ID. |

### Deals & Sale Events

| Tool | Arguments | Description |
|------|-----------|-------------|
| `get_ebay_deals` | `amount` (int, default 10), `category_ids` (string, optional) | Get current eBay daily deal items with prices and discount percentages. |
| `get_ebay_sale_events` | `amount` (int, default 10) | List active eBay sale events (sitewide and category sales). Returns event IDs, titles, and dates. |
| `get_sale_event_items` | `event_id` (string), `amount` (int, default 10) | Get items in a specific sale event. Use an event ID from `get_ebay_sale_events`. |

### Price Research

| Tool | Arguments | Description |
|------|-----------|-------------|
| `search_sold_listings` | `query` (string), `amount` (int, default 10) | Search historical sold listings to see what items actually sold for (Marketplace Insights API). |

> **Note:** Watcher count is not available — eBay restricts that to seller-authenticated APIs only.
