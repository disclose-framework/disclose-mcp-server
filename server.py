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

# V1 signal keys with disclose: prefix for new spec structure
V1_SIGNAL_KEYS = [f"disclose:{s}" for s in V1_SIGNALS]


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


def _get_signal_value(signal):
    """
    Safely extract the scalar value from a signal object or flat value.
    Handles both new signal object structure and legacy flat values.
    """
    if isinstance(signal, dict):
        return signal.get("value")
    return signal


def _annotate_signals(data: dict) -> dict:
    """
    Walk the disclosure payload and annotate any V1 signals in the
    attributes object that are missing provenance fields.

    Handles three cases:
    - New signal object structure (has attestation_level) -- left untouched
    - Flat value (legacy) -- wrapped in a signal object with attestation_level: none
    - Signal object missing attestation_level -- annotated with defaults
    """
    attributes = data.get("attributes", {})
    if not attributes:
        return data

    for prefixed_key in V1_SIGNAL_KEYS:
        if prefixed_key not in attributes:
            continue

        sig = attributes[prefixed_key]

        # Already a fully-formed signal object -- leave untouched
        if isinstance(sig, dict) and "attestation_level" in sig:
            continue

        # Flat value (legacy format) -- wrap in signal object
        if not isinstance(sig, dict):
            attributes[prefixed_key] = {
                "value": sig,
                "reported_by": "merchant",
                "attestation_level": "none",
                "attestation": None,
            }
            continue

        # Signal object exists but missing attestation_level -- annotate
        # Infer tier from available fields
        if "computed_by" in sig and "source" in sig:
            level = "computed"
        else:
            level = "none"

        sig.setdefault("reported_by", "merchant")
        sig.setdefault("attestation_level", level)
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
      - Attestation level for present signals

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

    # Extract attributes from new spec structure
    attributes = data.get("attributes", {})

    present = []
    missing = []
    attestation_status = {}

    for sig_key in V1_SIGNAL_KEYS:
        bare_key = sig_key.replace("disclose:", "")

        if sig_key in attributes:
            present.append(bare_key)
            sig_val = attributes[sig_key]

            if isinstance(sig_val, dict):
                level = sig_val.get("attestation_level", "none")
                # Map attestation_level to human-readable label
                label = {
                    "signatory": "signatory-attested",
                    "computed": "computed (platform API)",
                    "none": "merchant-reported",
                }.get(level, level)
                attestation_status[bare_key] = label
            else:
                # Legacy flat value
                attestation_status[bare_key] = "present (legacy format, no provenance)"
        else:
            missing.append(bare_key)

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
mcp.run(transport="streamable-http")
