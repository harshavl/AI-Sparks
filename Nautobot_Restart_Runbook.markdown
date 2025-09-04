# Nautobot Application and Dependent Services Restart Runbook

## Purpose
This runbook provides step-by-step instructions to safely restart the Nautobot application and its dependent services, including the WSGI service, Celery worker, Celery scheduler, PostgreSQL, and Redis, to ensure the system remains stable and operational.

## Scope
This runbook applies to Nautobot deployments running on a Linux system with systemd, using uWSGI as the WSGI server, Celery for background tasks, and PostgreSQL and Redis as dependencies.

## Prerequisites
- Root or sudo privileges are required to execute the commands.
- Ensure you have access to the Nautobot root directory (e.g., `/opt/nautobot`).
- Verify that the `nautobot`, `nautobot-worker`, `nautobot-scheduler`, `postgresql`, and `redis` services are configured and running.
- Backup critical data (e.g., database) before performing restarts to prevent data loss in case of issues.
- Ensure network connectivity is stable, as Nautobot services depend on network availability.

## Steps to Restart Nautobot and Dependent Services

### 1. Verify Current Service Status
Check the status of all relevant services to ensure they are running before attempting a restart.

```bash
sudo systemctl status nautobot.service
sudo systemctl status nautobot-worker.service
sudo systemctl status nautobot-scheduler.service
sudo systemctl status postgresql.service
sudo systemctl status redis.service
```

**Expected Output**: Each service should show `active (running)`. If any service is not running, note the errors in the status output and investigate (e.g., using `journalctl -eu <service-name>`).

### 2. Stop Nautobot Services
Stop the Nautobot WSGI service, Celery worker, and Celery scheduler in the following order to prevent task interruptions or incomplete web requests.

```bash
sudo systemctl stop nautobot.service
sudo systemctl stop nautobot-worker.service
sudo systemctl stop nautobot-scheduler.service
```

**Note**: Stopping services in this order ensures that the web service and background tasks are gracefully terminated.

### 3. Verify Services Have Stopped
Confirm that the Nautobot services have stopped.

```bash
sudo systemctl status nautobot.service
sudo systemctl status nautobot-worker.service
sudo systemctl status nautobot-scheduler.service
```

**Expected Output**: Each service should show `inactive (dead)` or similar. If a service fails to stop, use `journalctl -eu <service-name>` to diagnose the issue.

### 4. Restart Dependent Services
Restart PostgreSQL and Redis to ensure they are running with fresh connections.

```bash
sudo systemctl restart postgresql.service
sudo systemctl restart redis.service
```

**Verification**:
```bash
sudo systemctl status postgresql.service
sudo systemctl status redis.service
```

**Expected Output**: Both services should show `active (running)`.

**Troubleshooting**:
- If PostgreSQL fails to start, check logs with `journalctl -eu postgresql`.
- If Redis fails to start, check logs with `journalctl -eu redis`.
- For Redis connectivity issues, test from a Nautobot shell:
  ```python
  /opt/nautobot/bin/nautobot-server shell_plus
  import redis
  r = redis.Redis(host='localhost', port=6379, db=0)
  r.ping()
  ```
  Expected output: `True`. If exceptions occur, verify Redis configuration and network settings.

### 5. Start Nautobot Services
Start the Nautobot services in the reverse order to ensure dependencies are available.

```bash
sudo systemctl start nautobot-scheduler.service
sudo systemctl start nautobot-worker.service
sudo systemctl start nautobot.service
```

**Note**: Starting the scheduler and worker before the WSGI service ensures background tasks are ready when the web application starts.

### 6. Verify Services Are Running
Confirm that all services are running correctly.

```bash
sudo systemctl status nautobot-scheduler.service
sudo systemctl status nautobot-worker.service
sudo systemctl status nautobot.service
```

**Expected Output**: All services should show `active (running)`.

### 7. Check Celery Worker Status (Optional)
For Nautobot 2.3.0 and later, staff users can verify Celery worker status via the web interface:
- Navigate to `/worker-status/` in the Nautobot web UI (accessible from the "User" dropdown).
- Ensure no performance issues are reported, as this page runs a live query against Celery workers.

### 8. Test Nautobot Application
Verify that the Nautobot web application is accessible:
- Open a web browser and navigate to the Nautobot URL (e.g., `http://<server-ip>:8000` or the configured port).
- Log in with valid credentials and confirm that the dashboard loads correctly.
- Optionally, test a background task (e.g., run a Job or sync a Git repository) to ensure Celery workers are functioning.

### 9. Troubleshoot Common Issues
If any service fails to start or the application is inaccessible:
- Check logs for the specific service:
  ```bash
  journalctl -eu nautobot.service
  journalctl -eu nautobot-worker.service
  journalctl -eu nautobot-scheduler.service
  ```
- For uWSGI issues (e.g., SSL errors), verify `nautobot_config.py`:
  ```python
  DATABASES = {
      "default": {
          # Other settings...
          "CONN_MAX_AGE": 0  # Set to 0 to avoid SSL errors
      }
  }
  ```
  Then restart the Nautobot service:
  ```bash
  sudo systemctl restart nautobot.service
  ```
- For `.svg` rendering issues on RedHat/CentOS:
  - Copy `/etc/mime.types` from an Ubuntu/Debian system to `/opt/nautobot/mime.types`.
  - Add `mime-file = /opt/nautobot/mime.types` to `/opt/nautobot/uwsgi.ini`.
  - Restart Nautobot services:
    ```bash
    sudo systemctl restart nautobot.service
    ```

### 10. Enable Services on Boot (Optional)
Ensure all services start automatically on system boot if not already enabled.

```bash
sudo systemctl enable nautobot.service
sudo systemctl enable nautobot-worker.service
sudo systemctl enable nautobot-scheduler.service
sudo systemctl enable postgresql.service
sudo systemctl enable redis.service
```

## Post-Restart Validation
- Confirm the Nautobot web interface is accessible and functional.
- Verify background tasks (e.g., Jobs, Webhooks, Git sync) are executing correctly.
- Monitor system logs for any errors during the first few minutes after restart:
  ```bash
  journalctl -u nautobot.service -f
  journalctl -u nautobot-worker.service -f
  journalctl -u nautobot-scheduler.service -f
  ```

## Rollback Plan
If the restart causes issues (e.g., services fail to start or application is inaccessible):
1. Revert any recent configuration changes (e.g., `nautobot_config.py`, `uwsgi.ini`).
2. Restore from the database backup if data corruption is suspected.
3. Restart services in the same order as above.
4. Contact Nautobot support or refer to the [Nautobot Documentation](https://docs.nautobot.com) for further assistance.

## References
- Nautobot Documentation: Deploying Nautobot Services[](https://docs.nautobot.com/projects/core/en/stable/user-guide/administration/installation/services/)[](https://demo.nautobot.com/static/docs/user-guide/administration/installation/services.html)
- GitHub Issue: Error when restarting nautobot-worker service[](https://github.com/nautobot/nautobot/issues/653)