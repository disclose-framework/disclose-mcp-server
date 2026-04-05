# Disclose Framework MCP Server

An MCP server for querying merchant disclosure signals published via the [Disclose Framework](https://discloseframework.dev).

## What it does

Merchants publish operational signals — return rates, fulfillment accuracy, chargeback ratios — along with permitted use terms. This MCP server lets any AI agent query that data directly.

The server checks three discovery paths in order:

1. `/.well-known/disclose.json` — canonical path
1. `/disclose.json` — fallback for hosted platforms like Shopify that do not support the `/.well-known/` directory
1. JSON-LD block in page `<head>` — for merchants using script-tag injection

Signals sourced from the Shopify API and computed by Sure Signal are returned with full provenance metadata: `source`, `reported_by`, `computed_by`, and `attestation`. Attestation is `null` until a third-party verifier (such as Loop Returns) cryptographically signs the signal.

## Available Tools

**`get_merchant_disclosure(domain)`**
Fetches a merchant’s published disclosure signals from their domain. Returns all signals the merchant has chosen to publish, with provenance metadata, or an error if no disclosure is found.

Example: `get_merchant_disclosure("example.com")`

**`check_signal_coverage(domain)`**
Returns a structured coverage report for the six Sure Signal V1 signals: which are present, which are missing, whether any carry attestation, and an overall coverage percentage. Useful for agents evaluating merchant data completeness before a purchase decision.

The six V1 signals:

- `product_return_rate`
- `on_time_shipment_rate`
- `refund_processing_time_median_days`
- `chargeback_rate` and `dispute_win_rate` (paired)
- `platform_seller_tenure_days`
- `order_accuracy_rate`

Example: `check_signal_coverage("example.com")`

## Setup

### Prerequisites

- Python 3.10 or higher
- [uv](https://astral.sh/uv) package manager

### Installation

1. Clone this repository:
   
   ```
   git clone https://github.com/disclose-framework/disclose-mcp-server
   cd disclose-mcp-server
   ```
1. Install uv if you don’t have it:
- macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Windows: `curl -LsSf https://astral.sh/uv/install.ps1 | powershell`
1. Install dependencies:
   
   ```
   uv venv
   source .venv/bin/activate
   uv add "mcp[cli]" httpx
   ```
1. Run the server:
   
   ```
   uv run server.py
   ```

## Connecting to Claude Desktop

1. Install [Claude Desktop](https://claude.ai/download)
1. Open or create the config file:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
1. Add this configuration:
   
   ```json
   {
     "mcpServers": {
       "disclose-framework": {
         "command": "/path/to/uv",
         "args": [
           "--directory",
           "/absolute/path/to/disclose-mcp-server",
           "run",
           "server.py"
         ]
       }
     }
   }
   ```
1. Restart Claude Desktop
1. Try asking: *“What are the disclosure signals for example.com?”* or *“Check signal coverage for example.com.”*

## About

Part of the [Disclose Framework](https://discloseframework.dev) — an open standard for machine-readable merchant performance signals for AI agents.

Contribute at [github.com/disclose-framework](https://github.com/disclose-framework)