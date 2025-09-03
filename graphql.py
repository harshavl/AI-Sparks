import os
import asyncio
import logging
import pynautobot
from typing import Dict, Any, List

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("nautobot-graphql")

# Load config from environment
NAUTOBOT_URL = os.getenv("NAUTOBOT_URL", "https://demo.nautobot.com")
NAUTOBOT_TOKEN = os.getenv("NAUTOBOT_TOKEN", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")

# Initialize pynautobot
nautobot = pynautobot.api(
    url=NAUTOBOT_URL,
    token=NAUTOBOT_TOKEN,
    threading=False,     # We control concurrency with asyncio
    verify=False         # Set True in production
)

# GraphQL query
GRAPHQL_QUERY = """
query ($device_names: [String!]) {
  devices(name__in: $device_names) {
    name
    primary_ip4 {
      address
    }
    platform {
      name
    }
    interfaces {
      name
      description
      connected_endpoint {
        __typename
        ... on InterfaceType {
          device {
            name
          }
          name
        }
      }
    }
  }
}
"""

async def run_graphql_query(device_names: List[str]) -> Dict[str, Any]:
    """Run GraphQL query with pynautobot in a background thread."""
    def _query():
        return nautobot.graphql.query(
            query=GRAPHQL_QUERY,
            variables={"device_names": device_names},
            timeout=15
        ).json

    return await asyncio.to_thread(_query)

async def fetch_devices_in_batches(all_devices: List[str], batch_size: int = 50) -> List[Dict[str, Any]]:
    """Fetch devices in parallel batches using GraphQL."""
    tasks = []
    for i in range(0, len(all_devices), batch_size):
        batch = all_devices[i:i+batch_size]
        tasks.append(run_graphql_query(batch))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Flatten & collect device data
    devices = []
    for res in results:
        if isinstance(res, Exception):
            logger.error(f"GraphQL batch failed: {res}")
        else:
            devices.extend(res.get("data", {}).get("devices", []))
    return devices

async def main():
    # Pull all active devices from Nautobot inventory
    all_devices = [dev.name for dev in nautobot.dcim.devices.filter(status="active")]

    logger.info(f"Found {len(all_devices)} active devices in Nautobot")

    # Fetch metadata via GraphQL
    devices = await fetch_devices_in_batches(all_devices, batch_size=50)

    for dev in devices:
        logger.info(f"✅ {dev['name']} | IP: {dev.get('primary_ip4', {}).get('address')} | Platform: {dev['platform']['name']}")

if __name__ == "__main__":
    asyncio.run(main())
