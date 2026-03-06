import httpx
import json
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Disclose Framework")

@mcp.tool()
async def get_merchant_disclosure(domain: str) -> str:
    """
    Fetch a merchant's Disclose Framework disclosure signals.
    
    Retrieves the disclose.json file from the merchant's domain root
    and returns their published operational signals and permitted use terms.
    
    Args:
        domain: The merchant's domain (e.g. 'example.com' or 'https://example.com')
    
    Returns:
        The merchant's disclosure data as structured JSON, or an error message
        if no disclosure file is found.
    """
    # Clean up the domain input
    domain = domain.strip()
    if domain.startswith("http://") or domain.startswith("https://"):
        base = domain.rstrip("/")
    else:
        base = f"https://{domain.rstrip('/')}"

    url = f"{base}/disclose.json"

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url)

            if response.status_code == 200:
                try:
                    data = response.json()
                    return json.dumps(data, indent=2)
                except Exception:
                    return f"Found a file at {url} but it could not be parsed as valid JSON. The merchant may have a formatting error in their disclose.json."

            elif response.status_code == 404:
                return f"No disclose.json found at {url}. This merchant has not yet published a Disclose Framework disclosure file."

            else:
                return f"Received HTTP {response.status_code} when trying to fetch {url}. The file may be temporarily unavailable."

    except httpx.TimeoutException:
        return f"Request to {url} timed out. The merchant's server may be slow or unavailable."

    except httpx.ConnectError:
        return f"Could not connect to {domain}. Please check that the domain is correct and reachable."

    except Exception as e:
        return f"Unexpected error fetching {url}: {str(e)}"


if __name__ == "__main__":
    mcp.run()
