"""Nautobot Job to copy interface descriptions from Cisco IOS-XE, Cisco NX-OS, and Juniper devices to Nautobot using Nornir."""

from nautobot.apps.jobs import Job, MultiObjectVar, register_jobs
from nautobot.dcim.models import Device, Interface
from nautobot.core.celery import register_jobs as celery_register_jobs
from nautobot.extras.models import Status
from nautobot.utilities.exceptions import JobException
from django.conf import settings
from nornir import InitNornir
from nornir_netmiko.tasks import netmiko_send_command
from nornir.core.exceptions import NornirExecutionError
from nornir.core.inventory import Host
import xmltodict
import json
import time

name = "Interface Description Copier"

class CopyInterfaceDescriptions(Job):
    """
    Nautobot Job to fetch interface descriptions from Cisco IOS-XE, Cisco NX-OS, and Juniper devices using Nornir and copy them to Nautobot.
    """
    devices = MultiObjectVar(
        model=Device,
        query_params={"has_primary_ip": True},
        required=True,
        label="Devices",
        description="Select devices (Cisco IOS-XE, Cisco NX-OS, or Juniper Junos) to copy interface descriptions from."
    )

    class Meta:
        name = "Copy Interface Descriptions from Devices"
        description = "Fetches interface descriptions from Cisco IOS-XE, Cisco NX-OS, and Juniper Junos devices using Nornir and copies them to Nautobot."
        has_sensitive_variables = False

    def normalize_interface_name(self, name, platform_slug):
        """Normalize interface names for consistency across Cisco IOS-XE, NX-OS, and Junos."""
        name = name.strip().lower()
        if platform_slug == 'ios':
            # Cisco IOS-XE: Ensure names like 'GigabitEthernet0/1' are properly formatted
            return name.replace('gigabitethernet', 'GigabitEthernet')
        elif platform_slug == 'nxos':
            # Cisco NX-OS: Ensure names like 'Ethernet1/1' are properly formatted
            return name.replace('ethernet', 'Ethernet')
        elif platform_slug == 'junos':
            # Juniper Junos: Names like 'ge-0/0/0' typically need no change
            return name
        return name

    def connect_with_retry(self, nr, host, retries=3, delay=5):
        """Attempt to connect to the device with retries."""
        for attempt in range(retries):
            try:
                nr.run(task=netmiko_send_command, command_string="show version")
                return True
            except NornirExecutionError as e:
                self.logger.warning(f"Connection attempt {attempt + 1} failed for {host}: {str(e)}")
                time.sleep(delay)
        return False

    def parse_ios_interfaces(self, output):
        """Parse Cisco IOS-XE interface descriptions from show interfaces output."""
        interfaces = {}
        current_intf = None
        for line in output.splitlines():
            if " interface " in line.lower():
                current_intf = line.split()[-1]
            elif current_intf and "Description:" in line:
                description = line.split("Description:")[-1].strip()
                interfaces[current_intf] = {'description': description}
        return interfaces

    def parse_nxos_interfaces(self, output):
        """Parse Cisco NX-OS interface descriptions from show interface | json."""
        try:
            data = json.loads(output)
            interfaces = {}
            for intf in data.get('TABLE_interface', {}).get('ROW_interface', []):
                intf_name = intf.get('interface')
                description = intf.get('desc', '')
                interfaces[intf_name] = {'description': description}
            return interfaces
        except json.JSONDecodeError:
            self.logger.error("Failed to parse NX-OS JSON output.")
            return {}

    def parse_junos_interfaces(self, output):
        """Parse Juniper Junos interface descriptions from show interfaces | display xml."""
        try:
            data = xmltodict.parse(output)
            interfaces = {}
            intf_list = data.get('interface-information', {}).get('physical-interface', [])
            if not isinstance(intf_list, list):
                intf_list = [intf_list]
            for intf in intf_list:
                intf_name = intf.get('name')
                description = intf.get('description', '')
                interfaces[intf_name] = {'description': description}
            return interfaces
        except xmltodict.ParsingInterrupted:
            self.logger.error("Failed to parse Junos XML output.")
            return {}

    def run(self, devices):
        active_status = Status.objects.get(name="Active")
        
        # Initialize Nornir inventory from Nautobot devices
        inventory = {
            "hosts": {},
            "groups": {},
            "defaults": {
                "username": settings.NAPALM_USERNAME,
                "password": settings.NAPALM_PASSWORD,
            }
        }
        
        for device in devices:
            if not device.primary_ip:
                self.logger.warning(f"Device {device.name} has no primary IP. Skipping.")
                continue
            if not device.platform or not device.platform.slug:
                self.logger.warning(f"Device {device.name} has no platform configured. Skipping.")
                continue

            platform_slug = device.platform.slug
            inventory["hosts"][device.name] = {
                "hostname": str(device.primary_ip.address.ip),
                "platform": platform_slug,
                "groups": [platform_slug],
            }
            inventory["groups"][platform_slug] = {
                "platform": platform_slug,
                "connection_options": {
                    "netmiko": {
                        "platform": platform_slug,
                        "extras": {"device_type": platform_slug},
                    }
                }
            }

        try:
            nr = InitNornir(config_data={"inventory": {"options": inventory}})
        except Exception as e:
            self.logger.error(f"Failed to initialize Nornir: {str(e)}")
            raise JobException(f"Nornir initialization failed: {str(e)}")

        for device in devices:
            if device.name not in nr.inventory.hosts:
                continue

            host = nr.inventory.hosts[device.name]
            platform_slug = device.platform.slug

            try:
                # Test connection with retries
                if not self.connect_with_retry(nr, device.name):
                    self.logger.error(f"Failed to connect to {device.name} after retries.")
                    continue

                # Fetch interface descriptions based on platform
                if platform_slug == 'ios':
                    command = "show interfaces"
                    result = nr.run(task=netmiko_send_command, command_string=command)
                    interfaces = self.parse_ios_interfaces(result[device.name][0].result)
                elif platform_slug == 'nxos':
                    command = "show interface | json"
                    result = nr.run(task=netmiko_send_command, command_string=command)
                    interfaces = self.parse_nxos_interfaces(result[device.name][0].result)
                elif platform_slug == 'junos':
                    command = "show interfaces | display xml"
                    result = nr.run(task=netmiko_send_command, command_string=command)
                    interfaces = self.parse_junos_interfaces(result[device.name][0].result)
                else:
                    self.logger.warning(f"Unsupported platform {platform_slug} for {device.name}. Skipping.")
                    continue

                self.logger.info(f"Fetched interface details for {device.name}: {len(interfaces)} interfaces found.")

                # Update Nautobot interfaces
                for intf_name, intf_details in interfaces.items():
                    normalized_intf_name = self.normalize_interface_name(intf_name, platform_slug)
                    try:
                        iface = Interface.objects.get(device=device, name=normalized_intf_name)
                    except Interface.DoesNotExist:
                        self.logger.warning(f"Interface {normalized_intf_name} not found on device {device.name}. Skipping.")
                        continue

                    description = intf_details.get('description', '')
                    iface.description = description
                    iface.status = active_status
                    iface.validated_save()
                    self.logger.info(f"Copied description for {device.name} interface {normalized_intf_name}: {description}")

            except Exception as e:
                self.logger.error(f"Error processing device {device.name}: {str(e)}")
                raise JobException(f"Failed to update for {device.name}: {str(e)}")
            finally:
                nr.close_connections()

# Register the job
register_jobs(CopyInterfaceDescriptions)
celery_register_jobs(CopyInterfaceDescriptions)
