import httpx
import json
import re
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(“Disclose Framework”)

V1_SIGNALS = [
“product_return_rate”,
“on_time_shipment_rate”,
“refund_processing_time_median_days”,
“chargeback_rate”,
“dispute_win_rate”,
“platform_seller_tenure_days”,
“order_accuracy_rate”,
]

def _normalize_base(domain: str) -> str:
domain = domain.strip()
if domain.startswith(“http://”) or domain.startswith(“https://”):
return domain.rstrip(”/”)
return f”https://{domain.rstrip(’/’)}”

def _extract_jsonld_from_html(html: str) -> dict | None:
“””
Extract a Disclose Framework signal block from a page’s <head>
by finding <script type="application/ld+json"> tags and looking
for a @type of DiscloseSignals (or a disclose_signals key).
“””
pattern = re.compile(
r’<script[^>]+type=[”']application/ld+json[”'][^>]*>(.*?)</script>’,
re.DOTALL | re.IGNORECASE,
)
for match in pattern.finditer(html):
try:
data = json.loads(match.group(1).strip())
# Accept if it looks like a Disclose payload
if isinstance(data, dict) and (
data.get(”@type”) == “DiscloseSignals”
or “disclose_signals” in data
or “merchant_domain” in data
):
return data
except Exception:
continue
return None

def _annotate_signals(data: dict) -> dict:
“””
Walk the disclosure payload and annotate any V1 signals that are
present but lack a source block with the platform-sourced default.
Signals with an existing source block are left untouched.
“””
signals = data.get(“disclose_signals”, data)
annotated = {}

```
for key, value in signals.items():
    if key in V1_SIGNALS:
        if isinstance(value, dict) and "source" in value:
            # Already has provenance — respect it
            annotated[key] = value
        else:
            # Bare value — wrap with V1 provenance block
            annotated[key] = {
                "value": value,
                "source": "shopify_api",
                "reported_by": "merchant",
                "computed_by": "sure_signal",
                "attestation": None,
            }
    else:
        annotated[key] = value

if "disclose_signals" in data:
    data["disclose_signals"] = annotated
    return data

return annotated
```

@mcp.tool()
async def get_merchant_disclosure(domain: str) -> str:
“””
Fetch a merchant’s Disclose Framework disclosure signals.

```
Checks three locations in order:
  1. /.well-known/disclose.json  (canonical path)
  2. /disclose.json              (fallback for hosted platforms like Shopify)
  3. JSON-LD block in <head>     (for merchants using script-tag injection)

Returns published operational signals with provenance metadata, or an
error message if no disclosure is found.

The six Sure Signal V1 signals — product_return_rate, on_time_shipment_rate,
refund_processing_time_median_days, chargeback_rate, dispute_win_rate,
platform_seller_tenure_days, order_accuracy_rate — are annotated as
platform-sourced and merchant-reported when no attestation is present.

Args:
    domain: The merchant's domain (e.g. 'example.com' or 'https://example.com')

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
                return f"Received HTTP {response.status_code} when trying to fetch {url}."
        except httpx.TimeoutException:
            return f"Request to {url} timed out."
        except httpx.ConnectError:
            return f"Could not connect to {domain}. Please check the domain is correct."
        except Exception as e:
            return f"Unexpected error fetching {url}: {str(e)}"

    # --- Path 3: JSON-LD in page <head> ---
    try:
        response = await client.get(base)
        if response.status_code == 200:
            data = _extract_jsonld_from_html(response.text)
            if data:
                data = _annotate_signals(data)
                return json.dumps(data, indent=2)
    except Exception:
        pass

return (
    f"No disclosure document found for {domain}. "
    f"Checked /.well-known/disclose.json, /disclose.json, and page <head>. "
    f"This merchant has not yet published a Disclose Framework disclosure."
)
```

@mcp.tool()
async def check_signal_coverage(domain: str) -> str:
“””
Check which of the six Sure Signal V1 signals a merchant has published.

```
Returns a coverage report showing which signals are present, which are
missing, and whether any carry attestation. Useful for agents evaluating
merchant data completeness before making a purchase decision.

Args:
    domain: The merchant's domain (e.g. 'example.com')

Returns:
    A structured coverage report for the six V1 signals.
"""
raw = await get_merchant_disclosure(domain)

# If it's an error string, return it directly
try:
    data = json.loads(raw)
except Exception:
    return raw

signals = data.get("disclose_signals", data)

report = {
    "domain": domain,
    "v1_signal_coverage": {},
    "summary": {},
}

present = []
missing = []
attested = []

for signal in V1_SIGNALS:
    if signal in signals:
        entry = signals[signal]
        present.append(signal)
        has_attestation = (
            isinstance(entry, dict)
            and entry.get("attestation") is not None
        )
        if has_attestation:
            attested.append(signal)
        report["v1_signal_coverage"][signal] = {
            "present": True,
            "attested": has_attestation,
            "value": entry.get("value") if isinstance(entry, dict) else entry,
        }
    else:
        missing.append(signal)
        report["v1_signal_coverage"][signal] = {
            "present": False,
            "attested": False,
            "value": None,
        }

report["summary"] = {
    "signals_present": len(present),
    "signals_missing": len(missing),
    "signals_attested": len(attested),
    "coverage_pct": round(len(present) / len(V1_SIGNALS) * 100),
    "missing": missing,
}

return json.dumps(report, indent=2)
```

if **name** == “**main**”:
mcp.run(transport=“sse”)