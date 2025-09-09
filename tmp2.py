"""Nautobot Job to copy interface descriptions from devices to Nautobot using LLDP neighbor information."""

from nautobot.apps.jobs import Job, MultiObjectVar, register_jobs
from nautobot.dcim.models import Device, Interface
from nautobot.core.celery import register_jobs as celery_register_jobs
from nautobot.extras.models import Status
from napalm import get_network_driver
from nautobot.utilities.exceptions import JobException
from django.conf import settings

name = "Interface Description Copier"

class CopyInterfaceDescriptions(Job):
    """
    Nautobot Job to fetch interface descriptions from devices using NAPALM and copy them to Nautobot.
    """
    devices = MultiObjectVar(
        model=Device,
        query_params={"has_primary_ip": True},
        required=True,
        label="Devices",
        description="Select devices to copy interface descriptions from."
    )

    class Meta:
        name = "Copy Interface Descriptions from Devices"
        description = "Fetches interface descriptions from devices using NAPALM and copies them to the interface descriptions in Nautobot."
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
                interfaces = napalm_device.get_interfaces()
                self.logger.info(f"Fetched interface details for {device.name}: {len(interfaces)} interfaces found.")

                for intf_name, intf_details in interfaces.items():
                    # Find the interface in Nautobot
                    try:
                        iface = Interface.objects.get(device=device, name=intf_name)
                    except Interface.DoesNotExist:
                        self.logger.warning(f"Interface {intf_name} not found on device {device.name}. Skipping.")
                        continue

                    # Copy the interface description from the device
                    description = intf_details.get('description', '')
                    iface.description = description
                    iface.status = active_status
                    iface.validated_save()
                    self.logger.info(f"Copied description for {device.name} interface {intf_name}: {description}")

            except Exception as e:
                self.logger.error(f"Error processing device {device.name}: {str(e)}")
                raise JobException(f"Failed to update for {device.name}: {str(e)}")
            finally:
                napalm_device.close()

# Register the job
register_jobs(CopyInterfaceDescriptions)
celery_register_jobs(CopyInterfaceDescriptions)
