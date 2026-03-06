# Disclose Framework MCP Server

An MCP server for querying merchant disclosure signals published via the 
[Disclose Framework](https://discloseframework.dev).

## What it does

Merchants publish a `disclose.json` file at their domain root containing 
operational signals — return rates, fulfillment times, inventory accuracy — 
along with permitted use terms. This MCP server lets any AI agent query 
that data directly.

## Available Tools

**`get_merchant_disclosure(domain)`**
Fetches and returns a merchant's disclosed signals from their `disclose.json` file.

Example: `get_merchant_disclosure("example.com")`

## Setup

### Prerequisites
- Python 3.10 or higher
- [uv](https://github.com/astral-sh/uv) package manager

### Installation

1. Clone this repository:
   git clone https://github.com/disclose-framework/disclose-mcp-server
   cd disclose-mcp-server

2. Install uv if you don't have it:
   macOS/Linux: curl -LsSf https://astral.sh/uv/install.sh | sh
   Windows: curl -LsSf https://astral.sh/uv/install.ps1 | powershell

3. Install dependencies:
   uv venv
   source .venv/bin/activate
   uv add "mcp[cli]" httpx

4. Run the server:
   uv run server.py

## Connecting to Claude Desktop

1. Install [Claude Desktop](https://claude.ai/desktop)
2. Open or create the config file:
   macOS: ~/Library/Application Support/Claude/claude_desktop_config.json
   Windows: %APPDATA%\Claude\claude_desktop_config.json

3. Add this configuration:
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

4. Restart Claude Desktop
5. Try asking: "What are the disclosure signals for example.com?"

## About

Part of the [Disclose Framework](https://discloseframework.dev) — 
an open standard for machine-readable merchant disclosure signals for AI agents.

Contribute at [github.com/disclose-framework](https://github.com/disclose-framework)
