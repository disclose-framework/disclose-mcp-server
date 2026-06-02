# Disclose MCP Server

An MCP server for querying merchant disclosure signals published via [Disclose](https://discloseprotocol.dev).

## What it does

Merchants publish operational signals — return rates, fulfillment accuracy, chargeback ratios — along with permitted use terms. This MCP server lets any AI agent query that data directly.

The server checks four discovery paths in order:

1. `/.well-known/disclose` — canonical path
2. `/.well-known/disclose.json` — canonical path with explicit extension
3. `/disclose.json` — fallback for hosted platforms like Shopify that do not support the `/.well-known/` directory
4. JSON-LD block in page `<head>` — for merchants using script-tag injection

Signals sourced from the Shopify API and computed by Sure Signal are returned with full provenance metadata: `source`, `reported_by`, `computed_by`, `attestation_level`, and `attestation`. Attestation is `null` until a third-party Signatory (such as Loop Returns) cryptographically signs the signal.

## Available Tools

**`get_merchant_disclosure(domain)`**

Fetches a merchant's published disclosure signals from their domain. Returns all signals the merchant has chosen to publish, with provenance metadata, or an error if no disclosure is found.

Example: `get_merchant_disclosure("example.com")`

**`check_signal_coverage(domain)`**

Returns a structured coverage report for the seven Sure Signal V1 signals: which are present, which are missing, whether any carry attestation, and an overall coverage percentage. Useful for agents evaluating merchant data completeness before a purchase decision.

The seven V1 signals:

- `product_return_rate`
- `on_time_shipment_rate`
- `refund_processing_time_median_days`
- `chargeback_rate`
- `dispute_win_rate`
- `platform_seller_tenure_days`
- `order_accuracy_rate`

Example: `check_signal_coverage("example.com")`

## Setup

### Prerequisites

- Python 3.10 or higher
- [uv](https://astral.sh/uv) package manager

### Installation

1. Clone this repository:
