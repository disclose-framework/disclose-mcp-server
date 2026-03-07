import httpx
import json
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Disclose Framework")


@mcp.tool()
async def get_merchant_disclosure(domain: str) -> str:
    """
    Fetch a merchant's Disclose Framework disclosure signals.

    Retrieves the disclosure document from the merchant's domain, checking
    /.well-known/disclose.json first (canonical path), then falling back to
    /disclose.json at the domain root for merchants on hosted platforms that
    do not support the /.well-known/ directory.

    Returns their published operational signals and permitted use terms.

    Args:
        domain: The merchant's domain (e.g. 'example.com' or 'https://example.com')

    Returns:
        The merchant's disclosure data as structured JSON, or an error message
        if no disclosure file is found.
    """
    domain = domain.strip()
    if domain.startswith("http://") or domain.startswith("https://"):
        base = domain.rstrip("/")
    else:
        base = f"https://{domain.rstrip('/')}"

    paths = [
        "/.well-known/disclose.json",
        "/disclose.json",
    ]

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for path in paths:
            url = f"{base}{path}"
            try:
                response = await client.get(url)

                if response.status_code == 200:
                    try:
                        data = response.json()
                        return json.dumps(data, indent=2)
                    except Exception:
                        return f"Found a file at {url} but it could not be parsed as valid JSON."

                elif response.status_code == 404:
                    continue  # Try next path

                else:
                    return f"Received HTTP {response.status_code} when trying to fetch {url}."

            except httpx.TimeoutException:
                return f"Request to {url} timed out."
            except httpx.ConnectError:
                return f"Could not connect to {domain}. Please check the domain is correct."
            except Exception as e:
                return f"Unexpected error fetching {url}: {str(e)}"

    return (
        f"No disclosure document found for {domain}. "
        f"Checked /.well-known/disclose.json and /disclose.json. "
        f"This merchant has not yet published a Disclose Framework disclosure file."
    )


if __name__ == "__main__":
    mcp.run(transport="sse")
