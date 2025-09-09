"""Nautobot Job to update interface descriptions with LLDP neighbor information."""

from nautobot.apps.jobs import Job, MultiObjectVar, register_jobs
from nautobot.dcim.models import Device, Interface
from nautobot.core.celery import register_jobs as celery_register_jobs
from nautobot.extras.models import Status
from napalm import get_network_driver
from nautobot.utilities.exceptions import JobException
from django.conf import settings

name = "LLDP Neighbor Updater"

class UpdateInterfaceDescriptionsWithLLDP(Job):
    """
    Nautobot Job to fetch LLDP neighbors from devices and update interface descriptions.
    """
    devices = MultiObjectVar(
        model=Device,
        query_params={"has_primary_ip": True},
        required=True,
        label="Devices",
        description="Select devices to update interface descriptions for."
    )

    class Meta:
        name = "Update Interface Descriptions with LLDP Neighbors"
        description = "Fetches LLDP neighbor information from selected devices using NAPALM and updates the interface descriptions in Nautobot."
        has_sensitive_variables = False

    def run(self, devices):
        active_status = Status.objects.get(name="Active")
        for device in devices:
            if not device.primary_ip:
                self.logger.warning(f"Device {device.name} has no primary IP. Skipping.")
                continue
            if not device.platform or not device.platform.napalm_driver:
                self.logger.warning(f"Device {device.name} has no NAPALM driver configured. Skipping.")
                continue

            driver = get_network_driver(device.platform.napalm_driver)
            napalm_device = driver(
                hostname=str(device.primary_ip.address.ip),
                username=settings.NAPALM_USERNAME,
                password=settings.NAPALM_PASSWORD,
                optional_args=settings.NAPALM_ARGS if hasattr(settings, 'NAPALM_ARGS') else {},
            )

            try:
                napalm_device.open()
                lldp_neighbors = napalm_device.get_lldp_neighbors()
                self.logger.info(f"Fetched LLDP neighbors for {device.name}: {len(lldp_neighbors)} interfaces with neighbors.")

                for local_intf, neighbors in lldp_neighbors.items():
                    # Find the interface in Nautobot
                    try:
                        iface = Interface.objects.get(device=device, name=local_intf)
                    except Interface.DoesNotExist:
                        self.logger.warning(f"Interface {local_intf} not found on device {device.name}. Skipping.")
                        continue

                    # Assuming one neighbor per interface; take the first one
                    if neighbors:
                        neighbor = neighbors[0]
                        description = f"Connected to {neighbor['hostname']} port {neighbor['port']}"
                        iface.description = description
                        iface.status = active_status  # Optional: set status to Active if needed
                        iface.validated_save()
                        self.logger.info(f"Updated description for {device.name} interface {local_intf}: {description}")
                    else:
                        self.logger.info(f"No neighbors for {device.name} interface {local_intf}. No update.")

            except Exception as e:
                self.logger.error(f"Error processing device {device.name}: {str(e)}")
                raise JobException(f"Failed to update for {device.name}: {str(e)}")
            finally:
                napalm_device.close()

# Register the job
register_jobs(UpdateInterfaceDescriptionsWithLLDP)
celery_register_jobs(UpdateInterfaceDescriptionsWithLLDP)
