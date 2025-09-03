import os
import asyncio
import logging
from typing import Dict, Any
from nornir import InitNornir
from nornir.core.task import Task, Result
from nornir_nautobot.plugins.inventory.nautobot import NautobotInventory
import pynautobot

# Configure logging with minimal output
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# GraphQL query for devices with specified fields
GRAPHQL_QUERY = """
query ($device_name: String!) {
  devices(name: $device_name) {
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

async def fetch_device_details(task: Task, nautobot: pynautobot.api) -> Result:
    """Nornir task to fetch device details using GraphQL."""
    device_name = task.host.name
    try:
        # Execute GraphQL query with timeout
        gql_response = nautobot.graphql.query(
            query=GRAPHQL_QUERY,
            variables={"device_name": device_name},
            timeout=10
        )
        
        data = gql_response.json.get("data", {}).get("devices")
        if data and isinstance(data, list) and data[0]:
            logger.info(f"Fetched data for {device_name}")
            return Result(host=task.host, result=data[0])
        
        logger.warning(f"No data for {device_name}")
        return Result(host=task.host, failed=True)
        
    except Exception as e:
        logger.error(f"Failed for {device_name}: {str(e)}")
        return Result(host=task.host, failed=True, exception=e)

async def main():
    """Main async function to run Nornir tasks."""
    try:
        # Load configuration from environment
        config = {
            "url": os.getenv("NAUTOBOT_URL", "https://demo.nautobot.com"),
            "token": os.getenv("NAUTOBOT_TOKEN", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
            "email": os.getenv("NAUTOBOT_EMAIL", "admin@example.com"),
            "password": os.getenv("NAUTOBOT_PASSWORD", ""),
            "ssl_verify": False,  # Set to True in production
            "workers": 10,  # Optimized for small to medium inventories
            "timeout": 10  # API request timeout in seconds
        }

        # Initialize pynautobot
        nautobot = pynautobot.api(
            url=config["url"],
            token=config["token"],
            threading=False,
            verify=config["ssl_verify"],
            timeout=config["timeout"]
        )

        # Initialize Nornir with NautobotInventory
        nr = InitNornir(
            runner={"plugin": "threaded", "options": {"num_workers": config["workers"]}},
            inventory={
                "plugin": "NautobotInventory",
                "options": {
                    "nautobot_url": config["url"],
                    "nautobot_token": config["token"],
                    "ssl_verify": config["ssl_verify"],
                    "filter_parameters": {"status": "active"},
                },
            },
            credentials={"defaults": {"username": config["email"], "password": config["password"]}}
        )

        # Run tasks with error handling
        results = await asyncio.get_event_loop().run_in_executor(
            None, lambda: nr.run(task=fetch_device_details, nautobot=nautobot)
        )

        # Process results efficiently
        for host, result in results.items():
            if result[0].failed:
                logger.error(f"{host}: {result[0].exception or 'No data'}")
            else:
                logger.info(f"{host}: {result[0].result}")

    except Exception as e:
        logger.error(f"Main execution failed: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main())