import asyncio
import aiohttp
import json
import os
import logging
from typing import List, Optional
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Nautobot connection details
NAUTOBOT_URL = os.environ.get("NAUTOBOT_URL", "https://demo.nautobot.com")
NAUTOBOT_TOKEN = os.environ.get("NAUTOBOT_TOKEN", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", 10))  # Number of devices per query

# GraphQL query
QUERY = """
query ($device_names: [String!]) {
  devices(name__in: $device_names) {
    name
    site {
      name
    }
    interfaces {
      name
      description
      ip_addresses {
        address
      }
    }
  }
}
"""

async def fetch_device_data(session: aiohttp.ClientSession, device_names: List[str], retries: int = 3) -> Optional[dict]:
    """
    Asynchronously fetch device data for a list of device names using GraphQL.
    """
    headers = {
        "Authorization": f"Token {NAUTOBOT_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "query": QUERY,
        "variables": {"device_names": device_names},
    }

    for attempt in range(1, retries + 1):
        try:
            start_time = time.time()
            async with session.post(f"{NAUTOBOT_URL}/graphql/", json=payload, headers=headers) as response:
                if response.status != 200:
                    logger.error(f"Query failed with status {response.status}: {await response.text()}")
                    return None

                data = await response.json()
                elapsed = time.time() - start_time
                logger.info(f"Query for {len(device_names)} devices took {elapsed:.2f} seconds")

                if data.get("data"):
                    return data["data"]["devices"]
                else:
                    logger.error(f"No data returned: {data.get('errors', 'Unknown error')}")
                    return None

        except aiohttp.ClientError as e:
            logger.warning(f"Attempt {attempt} failed: {str(e)}")
            if attempt < retries:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
            else:
                logger.error(f"Failed after {retries} attempts: {str(e)}")
                return None

async def fetch_all_devices(device_names: List[str]) -> List[dict]:
    """
    Fetch device data in parallel chunks.
    """
    # Split device names into chunks
    chunks = [device_names[i:i + CHUNK_SIZE] for i in range(0, len(device_names), CHUNK_SIZE)]
    logger.info(f"Split {len(device_names)} devices into {len(chunks)} chunks")

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_device_data(session, chunk) for chunk in chunks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Flatten results and filter out None values
    devices = []
    for result in results:
        if isinstance(result, list):
            devices.extend(result)
        elif result is None:
            logger.warning("One or more chunks failed to return data")

    return devices

async def main():
    # List of device names to query
    device_names = ["hq-access-01", "den-sw01", "ams-sw01"] * 10  # Example: 30 devices for testing

    start_time = time.time()
    devices = await fetch_all_devices(device_names)
    elapsed = time.time() - start_time
    logger.info(f"Total execution time: {elapsed:.2f} seconds")

    if devices:
        # Pretty print summary
        logger.info(f"Fetched {len(devices)} devices")
        for device in devices:
            logger.info(f"Device: {device['name']}")
            logger.info(f"Site: {device['site']['name']}")
            logger.info("Interfaces:")
            for interface in device['interfaces']:
                logger.info(f"  - {interface['name']}: {interface['description'] or 'No description'}")
                for ip in interface['ip_addresses']:
                    logger.info(f"    IP: {ip['address']}")

if __name__ == "__main__":
    asyncio.run(main())