import os
import asyncio
import logging
from typing import Dict, Any, List
from nornir import InitNornir
from nornir.core.task import Task, Result
from nornir_nautobot.plugins.inventory.nautobot import NautobotInventory
import pynautobot

# Configure logging with minimal output
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# GraphQL query for multiple devices
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

async def fetch_device_details(task: Task, nautobot: pynautobot.api, device_names: List[str]) -> Result:
    """Nornir task to fetch details for multiple devices using GraphQL."""
    try:
        # Execute GraphQL query for multiple devices
        gql_response = nautobot.graphql.query(
            query=GRAPHQL_QUERY,
            variables={"device_names": device_names},
            timeout=15
        )
        
        data = gql_response.json.get("data", {}).get("devices", [])
        if data:
            logger.info(f"Fetched data for {len(data)} devices")
            # Map results to host for Nornir compatibility
            host_result = {device["name"]: device for device in data if device["name"] == task.host.name}
            if host_result.get(task.host.name):
                return Result(host=task.host, result=host_result[task.host.name])
        
        logger.warning(f"No data for {task.host.name}")
        return Result(host=task.host, failed=True)
        
    except Exception as e:
        logger.error(f"Failed for {task.host.name}: {str(e)}")
        return Result(host=task.host, failed=True, exception=e)

async def main():
    """Main async function to run Nornir tasks for multiple devices."""
    try:
        # Load configuration from environment
        config = {
            "url": os.getenv("NAUTOBOT_URL", "https://demo.nautobot.com"),
            "token": os.getenv("NAUTOBOT_TOKEN", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
            "email": os.getenv("NAUTOBOT_EMAIL", "admin@example.com"),
            "password": os.getenv("NAUTOBOT_PASSWORD", ""),
            "ssl_verify": False,  # Set to True in production
            "workers": 5,  # Reduced for bulk query efficiency
            "timeout": 15,  # Increased timeout for bulk queries
            "batch_size": 50  # Number of devices per GraphQL query
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

        # Batch devices to avoid overwhelming GraphQL
        device_names = list(nr.inventory.hosts.keys())
        batches = [device_names[i:i + config["batch_size"]] for i in range(0, len(device_names), config["batch_size"])]

        # Process batches concurrently
        for batch in batches:
            tasks = [
                asyncio.get_event_loop().run_in_executor(
                    None, 
                    lambda host=host, names=batch: nr.run(
                        task=fetch_device_details, 
                        nautobot=nautobot, 
                        device_names=names
                    )[host.name]
                )
                for host in nr.inventory.hosts.values() if host.name in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for host_name, result in zip([h.name for h in nr.inventory.hosts.values() if h.name in batch], results):
                if isinstance(result, Exception) or result[0].failed:
                    logger.error(f"{host_name}: {result[0].exception or 'No data'}")
                else:
                    logger.info(f"{host_name}: {result[0].result}")

    except Exception as e:
        logger.error(f"Main execution failed: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main())