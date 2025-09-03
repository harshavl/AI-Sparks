import os
import asyncio
import logging
from typing import Dict, Any
import pynautobot
from nornir import InitNornir
from nornir.core.task import Task, Result
from nornir.core.inventory import Host
from nornir_nautobot.plugins.inventory.nautobot import NautobotInventory

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# GraphQL query to fetch device details with interfaces
GRAPHQL_QUERY = """
query ($device_name: String!) {
  devices(name: $device_name) {
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

async def fetch_device_details(task: Task, nautobot: pynautobot.api) -> Result:
    """Nornir task to fetch device details using GraphQL query."""
    try:
        device_name = task.host.name
        variables = {"device_name": device_name}
        
        # Execute GraphQL query
        gql_response = nautobot.graphql.query(query=GRAPHQL_QUERY, variables=variables)
        
        if gql_response.json.get("data") and gql_response.json["data"].get("devices"):
            device_data = gql_response.json["data"]["devices"][0]
            logger.info(f"Successfully fetched data for {device_name}")
            return Result(host=task.host, result=device_data)
        else:
            logger.warning(f"No data found for {device_name}")
            return Result(host=task.host, result=None, failed=True)
            
    except Exception as e:
        logger.error(f"Error fetching data for {device_name}: {str(e)}")
        return Result(host=task.host, result=str(e), failed=True)

async def main():
    """Main async function to initialize Nornir and run GraphQL queries."""
    try:
        # Nautobot configuration
        nautobot_url = os.getenv("NAUTOBOT_URL", "https://demo.nautobot.com")
        nautobot_token = os.getenv("NAUTOBOT_TOKEN", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        username = os.getenv("NAUTOBOT_USERNAME", "admin")
        password = os.getenv("NAUTOBOT_PASSWORD", "admin")

        # Initialize pynautobot
        nautobot = pynautobot.api(
            url=nautobot_url,
            token=nautobot_token,
            threading=False,  # Disable threading for async compatibility
            verify=False  # Set to True in production with valid SSL certs
        )

        # Initialize Nornir with NautobotInventory
        nr = InitNornir(
            runner={
                "plugin": "threaded",
                "options": {
                    "num_workers": 20,  # Adjust based on system resources
                },
            },
            inventory={
                "plugin": "NautobotInventory",
                "options": {
                    "nautobot_url": nautobot_url,
                    "nautobot_token": nautobot_token,
                    "ssl_verify": False,  # Set to True in production
                    "filter_parameters": {"status": "active"},  # Optional filter
                },
            },
            # Set default credentials
            credentials={
                "defaults": {
                    "username": username,
                    "password": password,
                }
            }
        )

        # Add credentials to each host
        for host in nr.inventory.hosts.values():
            host.username = username
            host.password = password

        # Run the GraphQL query task for all devices
        results = nr.run(
            task=fetch_device_details,
            nautobot=nautobot
        )

        # Process results
        for host_name, result in results.items():
            if result[0].failed:
                logger.error(f"Failed for {host_name}: {result[0].result}")
            else:
                logger.info(f"Result for {host_name}: {result[0].result}")

    except Exception as e:
        logger.error(f"Main execution error: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main())