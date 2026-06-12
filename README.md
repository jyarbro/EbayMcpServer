# Ebay MCP Server

Simple eBay server that lets you fetch auctions from eBay.com

Uses the official [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) to handle protocol communication and server interactions.

Forked from [CooKey-Monster/EbayMcpServer](https://github.com/CooKey-Monster/EbayMcpServer).

## Example

Lets you use prompts like, "Find me 10 auctions for batman comics"

## Components

### Tools

The server provides a single tool:

- `list-auction`: Scan eBay for auctions.
  - Required `query` argument — the search term
  - Required `ammount` argument — number of results to return
  - Returns results from eBay's Browse REST API

## Installation

### Prerequisites

Requires [uv](https://github.com/astral-sh/uv):

```bash
# macOS (Homebrew)
brew install uv

# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Clone and set up

```bash
git clone https://github.com/jyarbro/EbayMcpServer.git
cd EbayMcpServer
uv sync
```

### Configure Claude

Add the following to your Claude MCP config (e.g. `~/.claude.json`):

```json
{
  "mcpServers": {
    "ebay": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/EbayMcpServer", "python", "src/ebay-mcp/server.py"],
      "env": {
        "EBAY_CLIENT_ID": "your-client-id",
        "EBAY_CLIENT_SECRET": "your-client-secret",
        "EBAY_SANDBOX": "false"
      }
    }
  }
}
```

Replace `/path/to/EbayMcpServer` with the absolute path to where you cloned the repo.

### Environment Variables

Get your credentials from the [eBay Developer Portal](https://developer.ebay.com/develop).

| Variable | Required | Description |
|----------|----------|-------------|
| `EBAY_CLIENT_ID` | Yes | Your eBay App ID (Client ID) |
| `EBAY_CLIENT_SECRET` | Yes | Your eBay Client Secret |
| `EBAY_SANDBOX` | No | Set to `"true"` to use sandbox endpoints (default: `"false"`) |
