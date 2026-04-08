import httpx
import json
import re
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Disclose Framework")

V1_SIGNALS = [
    "product_return_rate",
    "on_time_shipment_rate",
    "refund_processing_time_median_days",
    "chargeback_rate",
    "dispute_win_rate",
    "platform_seller_tenure_days",
    "order_accuracy_rate",
]

def _normalize_base(domain: str) -> str:
    domain = domain.strip()
    if domain.startswith("http://") or domain.startswith("https://"):
        return domain.rstrip("/")
    return f"https://{domain.rstrip('/')}"

def _extract_jsonld_from_html(html: str) -> dict | None:
    """
    Extract a Disclose Framework signal block from a page's <head>
    by finding <script type="application/ld+json"> tags and looking
    for a @type of DiscloseSignals (or a disclose_signals key).
    """
    pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.DOTALL | re.IGNORECASE,
    )
    for match in pattern.finditer(html):
        try:
            data = json.loads(match.group(1).strip())
            # Accept if it looks like a Disclose payload
            if isinstance(data, dict) and (
                data.get("@type") == "DiscloseSignals"
                or "disclose_signals" in data
                or "merchant_domain" in data
            ):
                return data
        except Exception:
            continue
    return None

def _annotate_signals(data: dict) -> dict:
    """
    Walk the disclosure payload and annotate any V1 signals that are
    present but lack a source block with the platform-sourced default.
    Signals with an existing source block are left untouched.
    """
    default_source = {
        "source": "shopify_api",
        "reported_by": "merchant",
        "computed_by": "sure_signal",
        "attestation": None,
    }

    def annotate_block(block: dict) -> dict:
        signals = block.get("signals", {})
        for key in V1_SIGNALS:
            if key in signals:
                sig = signals[key]
                if isinstance(sig, dict) and "source" not in sig:
                    sig["source"] = default_source.copy()
        return block

    # Merchant-level signals
    if "signals" in data:
        data = annotate_block(data)

    # Offer-level signals
    for offer in data.get("offers", []):
        if "signals" in offer:
            annotate_block(offer)

    # Item-level signals
    for item in data.get("items", []):
        if "signals" in item:
            annotate_block(item)

    return data

@mcp.tool()
async def get_merchant_disclosure(domain: str) -> str:
    """
    Retrieve a merchant's Disclose Framework disclosure file.

    Checks three discovery paths in order:
      1. /.well-known/disclose.json
      2. /disclose.json
      3. JSON-LD embedded in the page <head>

    Args:
        domain: The merchant domain to check (e.g. 'example.com'
                or 'https://example.com')

    Returns:
        The merchant's disclosure data as structured JSON with provenance,
        or an error message if no disclosure file is found.
    """
    base = _normalize_base(domain)

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:

        # --- Path 1 and 2: disclose.json files ---
        for path in ["/.well-known/disclose.json", "/disclose.json"]:
            url = f"{base}{path}"
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    try:
                        data = response.json()
                        data = _annotate_signals(data)
                        return json.dumps(data, indent=2)
                    except Exception:
                        return f"Found a file at {url} but it could not be parsed as valid JSON."
                elif response.status_code == 404:
                    continue
                else:
                    return f"Received HTTP {response.status_code} from {url}."
            except httpx.RequestError as e:
                return f"Network error reaching {url}: {e}"

        # --- Path 3: JSON-LD in page <head> ---
        try:
            page_url = base
            response = await client.get(page_url)
            if response.status_code == 200:
                data = _extract_jsonld_from_html(response.text)
                if data:
                    data = _annotate_signals(data)
                    return json.dumps(data, indent=2)
        except httpx.RequestError:
            pass

        return (
            f"No Disclose Framework disclosure found for {domain}. "
            f"Checked: {base}/.well-known/disclose.json, "
            f"{base}/disclose.json, and JSON-LD in page <head>."
        )

@mcp.tool()
async def check_signal_coverage(domain: str) -> str:
    """
    Check which V1 signals a merchant has published in their disclosure file.

    Returns a structured report showing:
      - Which V1 signals are present
      - Which V1 signals are missing
      - Overall coverage percentage
      - Attestation status for present signals

    Args:
        domain: The merchant domain to check (e.g. 'example.com'
                or 'https://example.com')

    Returns:
        A structured coverage report as JSON.
    """
    base = _normalize_base(domain)
    data = None

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:

        for path in ["/.well-known/disclose.json", "/disclose.json"]:
            url = f"{base}{path}"
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    try:
                        data = response.json()
                        break
                    except Exception:
                        return json.dumps({
                            "domain": domain,
                            "error": f"Found a file at {url} but it could not be parsed as valid JSON."
                        }, indent=2)
            except httpx.RequestError as e:
                return json.dumps({
                    "domain": domain,
                    "error": f"Network error reaching {url}: {e}"
                }, indent=2)

        if data is None:
            try:
                response = await client.get(base)
                if response.status_code == 200:
                    data = _extract_jsonld_from_html(response.text)
            except httpx.RequestError:
                pass

    if data is None:
        return json.dumps({
            "domain": domain,
            "error": "No disclosure file found.",
            "checked_paths": [
                f"{base}/.well-known/disclose.json",
                f"{base}/disclose.json",
                f"{base} (JSON-LD in <head>)",
            ]
        }, indent=2)

    # Extract merchant-level signals
    signals = data.get("signals", {})

    present = []
    missing = []
    attestation_status = {}

    for sig_key in V1_SIGNALS:
        if sig_key in signals:
            present.append(sig_key)
            sig_val = signals[sig_key]
            if isinstance(sig_val, dict):
                attestation = sig_val.get("source", {}).get("attestation")
                attestation_status[sig_key] = "attested" if attestation else "merchant-reported"
            else:
                attestation_status[sig_key] = "present (no provenance block)"
        else:
            missing.append(sig_key)

    coverage_pct = round(len(present) / len(V1_SIGNALS) * 100, 1)

    report = {
        "domain": domain,
        "v1_signal_coverage": {
            "total_v1_signals": len(V1_SIGNALS),
            "present": len(present),
            "missing": len(missing),
            "coverage_percent": coverage_pct,
        },
        "present_signals": {k: attestation_status[k] for k in present},
        "missing_signals": missing,
    }

    return json.dumps(report, indent=2)

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8080))
    mcp.run(transport="sse", port=port)
