import httpx
import json
import re
from mcp.server.fastmcp import FastMCP

from mcp.server.transport_security import TransportSecuritySettings

mcp = FastMCP(
    "Disclose Framework",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    )
)

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
    pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.DOTALL | re.IGNORECASE,
    )
    for match in pattern.finditer(html):
        try:
            data = json.loads(match.group(1).strip())
            if isinstance(data, dict) and (
                data.get("@type") == "DiscloseSignals"
                or "signals" in data
                or "merchant_domain" in data
            ):
                return data
        except Exception:
            continue
    return None


def _get_attestation_label(signal: dict) -> str:
    if not isinstance(signal, dict):
        return "present (legacy format, no provenance)"

    attestation = signal.get("attestation")
    computed_by = signal.get("computed_by")
    reported_by = signal.get("reported_by", "merchant")

    if attestation is not None:
        return f"attested ({attestation})"
    elif computed_by:
        return f"computed by {computed_by}"
    elif reported_by:
        return f"merchant-reported (via {reported_by})"
    else:
        return "merchant-reported"


def _annotate_signals(data: dict) -> dict:
    signals = data.get("signals", {})
    if not signals:
        return data

    for key in V1_SIGNALS:
        if key not in signals:
            continue

        sig = signals[key]

        if not isinstance(sig, dict):
            signals[key] = {
                "value": sig,
                "reported_by": "merchant",
                "computed_by": None,
                "attestation": None,
            }
            continue

        sig.setdefault("reported_by", "merchant")
        sig.setdefault("computed_by", None)
        sig.setdefault("attestation", None)

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
      - Which present signals have null values
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

    signals = data.get("signals", {})

    present = []
    present_with_null_value = []
    missing = []
    attestation_status = {}

    for key in V1_SIGNALS:
        if key in signals:
            present.append(key)
            sig = signals[key]
            attestation_status[key] = _get_attestation_label(sig)

            value = sig.get("value") if isinstance(sig, dict) else sig
            if value is None:
                present_with_null_value.append(key)
        else:
            missing.append(key)

    coverage_pct = round(len(present) / len(V1_SIGNALS) * 100, 1)
    populated_pct = round(
        (len(present) - len(present_with_null_value)) / len(V1_SIGNALS) * 100, 1
    )

    report = {
        "domain": domain,
        "schema_version": data.get("schema_version"),
        "generated_at": data.get("generated_at"),
        "v1_signal_coverage": {
            "total_v1_signals": len(V1_SIGNALS),
            "present": len(present),
            "present_with_null_value": len(present_with_null_value),
            "missing": len(missing),
            "coverage_percent": coverage_pct,
            "populated_percent": populated_pct,
        },
        "present_signals": {k: attestation_status[k] for k in present},
        "present_but_null": present_with_null_value,
        "missing_signals": missing,
    }

    return json.dumps(report, indent=2)


if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    app = mcp.streamable_http_app()
    uvicorn.run(app, host="0.0.0.0", port=port, proxy_headers=True, forwarded_allow_ips="*")
