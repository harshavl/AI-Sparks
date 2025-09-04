# Nautobot Application and Dependent Services Restart Runbook (Docker)

## Purpose
This runbook provides step-by-step instructions to safely restart the Nautobot application and its dependent services (Nautobot application, Celery worker, PostgreSQL, and Redis) in a Docker environment using Docker Compose, ensuring minimal downtime and system stability.

## Scope
This runbook applies to Nautobot deployments running in a Docker environment with Docker Compose, as described in the Nautobot Docker Compose project. It assumes a multi-container setup with Nautobot, a Celery worker, PostgreSQL, and Redis, using the `networktocode/nautobot` Docker image and `docker-compose.yml` for orchestration.

## Prerequisites
- **Docker and Docker Compose**: Ensure Docker (version 1.10.0 or later) and Docker Compose are installed. Verify with:
  ```bash
  docker --version
  docker-compose --version
  ```
- **Access**: Root or sudo privileges, or a user account with permission to run Docker commands.
- **Nautobot Docker Compose Setup**: A working `docker-compose.yml` file in the Nautobot project directory (e.g., cloned from `https://github.com/nautobot/nautobot-docker-compose`).
- **Backup**: A recent backup of the PostgreSQL database (e.g., using `pg_dump`) and any custom configuration files (e.g., `nautobot_config.py`).
- **Network Connectivity**: Stable network access for container communication and pulling images if needed.
- **Environment Variables**: Access to the `creds.env` file or environment variables for configurations like `NAUTOBOT_CREATE_SUPERUSER`.

## Steps to Restart Nautobot and Dependent Services

### 1. Verify Current Container Status
Check the status of all Nautobot-related containers to ensure they are running.

```bash
docker-compose ps
```

**Expected Output**: Containers for `nautobot`, `nautobot-worker`, `postgres`, and `redis` should show `Up` with health status (if configured). Example:
```
       Name                     Command               State                 Ports
------------------------------------------------------------------------------------
nautobot_nautobot_1      /entrypoint.sh nautobot-se ...   Up (healthy)   0.0.0.0:8080->8080/tcp
nautobot_postgres_1      docker-entrypoint.sh postgres    Up (healthy)
nautobot_redis_1         redis-server                     Up (healthy)
nautobot_worker_1        /entrypoint.sh celery work ...   Up (healthy)
```

**Troubleshooting**: If any container is not running or unhealthy, check logs:
```bash
docker-compose logs <service-name>
```

### 2. Stop Nautobot Containers
Stop the Nautobot application and worker containers to prevent incomplete tasks or requests.

```bash
docker-compose stop nautobot nautobot-worker
```

**Note**: Stop the application and worker containers first to ensure graceful termination of web requests and background tasks. PostgreSQL and Redis can remain running unless they need to be restarted.

### 3. Verify Containers Have Stopped
Confirm that the Nautobot and worker containers have stopped.

```bash
docker-compose ps
```

**Expected Output**: The `nautobot` and `nautobot-worker` containers should show `Exit` or no status. PostgreSQL and Redis containers may still show `Up`.

**Troubleshooting**: If containers fail to stop, force stop them:
```bash
docker-compose kill nautobot nautobot-worker
```

### 4. Restart Dependent Services (PostgreSQL and Redis)
Restart the PostgreSQL and Redis containers to refresh their connections.

```bash
docker-compose restart postgres redis
```

**Verification**:
```bash
docker-compose ps
```

**Expected Output**: The `postgres` and `redis` containers should show `Up (healthy)`.

**Troubleshooting**:
- Check logs for errors:
  ```bash
  docker-compose logs postgres
  docker-compose logs redis
  ```
- Test Redis connectivity from a Nautobot container:
  ```bash
  docker-compose exec nautobot nautobot-server shell_plus
  import redis
  r = redis.Redis(host='redis', port=6379, db=0)
  r.ping()
  ```
  Expected output: `True`. If it fails, verify Redis configuration in `docker-compose.yml`.
- Test PostgreSQL connectivity:
  ```bash
  docker-compose exec postgres psql -U nautobot -d nautobot -c "SELECT 1;"
  ```
  Expected output: A table with `1`. If it fails, verify PostgreSQL credentials in `creds.env`.

### 5. Start Nautobot Containers
Start the Nautobot application and worker containers.

```bash
docker-compose start nautobot-worker
docker-compose start nautobot
```

**Note**: Start the worker before the application to ensure background tasks are ready when the web service starts. If using `invoke` (as per Nautobot’s Docker Compose project), you can use:
```bash
invoke start
```

### 6. Verify Containers Are Running
Confirm that all containers are running and healthy.

```bash
docker-compose ps
```

**Expected Output**: All containers (`nautobot`, `nautobot-worker`, `postgres`, `redis`) should show `Up (healthy)`.

**Troubleshooting**: If containers fail to start, check logs:
```bash
docker-compose logs nautobot
docker-compose logs nautobot-worker
```

### 7. Check Celery Worker Status (Optional)
For Nautobot 2.3.0 and later, verify Celery worker status via the web interface:
- Navigate to `http://localhost:8080/worker-status/` (or the configured port) in the Nautobot web UI (accessible from the "User" dropdown as a staff user).
- Ensure no performance issues are reported.

### 8. Test Nautobot Application
Verify that the Nautobot web application is accessible:
- Open a web browser and navigate to `http://localhost:8080` (or the configured port).
- Log in with valid credentials (e.g., superuser created via `NAUTOBOT_CREATE_SUPERUSER` environment variable).
- Confirm the dashboard loads correctly.
- Test a background task (e.g., run a Job or sync a Git repository) to verify Celery worker functionality.

### 9. Troubleshoot Common Issues
If containers fail to start or the application is inaccessible:
- Check container logs:
  ```bash
  docker-compose logs nautobot
  docker-compose logs nautobot-worker
  docker-compose logs postgres
  docker-compose logs redis
  ```
- Verify `nautobot_config.py` for configuration issues (e.g., database or Redis settings):
  ```bash
  docker-compose exec nautobot cat /opt/nautobot/nautobot_config.py
  ```
  Example fix for database connection issues:
  ```python
  DATABASES = {
      'default': {
          'NAME': 'nautobot',
          'USER': 'nautobot',
          'PASSWORD': '<password>',
          'HOST': 'postgres',
          'PORT': '5432',
          'ENGINE': 'django.db.backends.postgresql',
          'CONN_MAX_AGE': 0  # Avoid SSL errors
      }
  }
  ```
  Then restart Nautobot containers:
  ```bash
  docker-compose restart nautobot
  ```
- For plugin issues, ensure plugins are correctly installed in the Docker image (see `https://github.com/nautobot/nautobot-docker-compose/docs/plugins.md`).

### 10. Ensure Containers Restart on System Boot (Optional)
If the host system is rebooted, ensure containers restart automatically by adding `restart: always` to the `docker-compose.yml` services:
```yaml
services:
  nautobot:
    image: networktocode/nautobot
    restart: always
  nautobot-worker:
    image: networktocode/nautobot
    restart: always
  postgres:
    image: postgres
    restart: always
  redis:
    image: redis
    restart: always
```
Apply changes:
```bash
docker-compose up -d
```

## Post-Restart Validation
- Confirm the Nautobot web interface is accessible at `http://localhost:8080`.
- Verify background tasks (e.g., Jobs, Webhooks, Git sync) execute correctly.
- Monitor container logs for errors:
  ```bash
  docker-compose logs -f
  ```

## Rollback Plan
If the restart causes issues (e.g., containers fail to start, application is inaccessible, or data inconsistencies are detected), follow these detailed steps to revert to a stable state:

### 1. Identify the Issue
- Check container logs for errors:
  ```bash
  docker-compose logs nautobot
  docker-compose logs nautobot-worker
  docker-compose logs postgres
  docker-compose logs redis
  ```
- Note specific error messages (e.g., database connection failures, Celery task errors, or configuration issues).
- Verify if recent changes were made (e.g., updated `docker-compose.yml`, `nautobot_config.py`, or new plugins).

### 2. Stop All Nautobot Containers
Halt all Nautobot-related containers to prevent further issues:
```bash
docker-compose stop
```

**Verification**:
```bash
docker-compose ps
```
All containers should show `Exit`.

### 3. Revert Configuration Changes
If configuration changes were made prior to the restart:
- Restore the previous `docker-compose.yml` from a backup:
  ```bash
  cp docker-compose.yml.bak docker-compose.yml
  ```
- Restore the previous `nautobot_config.py` if customized (mounted via Docker volume):
  ```bash
  cp /local/path/to/nautobot_config.py.bak /local/path/to/nautobot_config.py
  ```
- If plugins were added, revert `pyproject.toml` and rebuild the custom image:
  ```bash
  cp pyproject.toml.bak pyproject.toml
  invoke build --no-cache
  ```

### 4. Restore Database (If Necessary)
If data corruption or inconsistencies are suspected:
- Stop the PostgreSQL container:
  ```bash
  docker-compose stop postgres
  ```
- Remove the existing PostgreSQL data volume (warning: this deletes current data):
  ```bash
  docker-compose rm -v postgres
  ```
- Restore the database from a backup:
  ```bash
  docker-compose up -d postgres
  docker-compose exec postgres psql -U nautobot -d postgres -c "DROP DATABASE nautobot;"
  docker-compose exec postgres psql -U nautobot -d postgres -c "CREATE DATABASE nautobot;"
  docker-compose exec postgres psql -U nautobot -d nautobot < /path/to/nautobot_db_backup.sql
  ```
- Verify database connectivity:
  ```bash
  docker-compose exec nautobot nautobot-server shell_plus
  from nautobot.dcim.models import Device
  Device.objects.all()
  ```
  Expected output: A list of devices or an empty queryset.

### 5. Clear Redis Cache (If Necessary)
If Redis-related issues (e.g., stale Celery tasks) are suspected:
- Flush the Redis database:
  ```bash
  docker-compose exec redis redis-cli FLUSHDB
  ```
- Restart the Redis container:
  ```bash
  docker-compose restart redis
  ```

### 6. Rebuild and Restart Containers
If the Docker image was updated or corrupted:
- Pull the latest stable Nautobot image:
  ```bash
  docker-compose pull
  ```
- Or rebuild the custom image if plugins are used:
  ```bash
  invoke build --no-cache
  ```
- Start all containers:
  ```bash
  docker-compose up -d
  ```
  Or using `invoke`:
  ```bash
  invoke start
  ```

### 7. Validate Rollback
- Verify container status:
  ```bash
  docker-compose ps
  ```
  All containers should show `Up (healthy)`.
- Test the Nautobot web interface at `http://localhost:8080`.
- Run a sample background task (e.g., a Job or Git sync) to confirm Celery functionality.
- If issues persist, check logs (`docker-compose logs`) or consult the Nautobot community on the `#nautobot` Slack channel.

### 8. Notify Stakeholders
- Inform the team of the rollback and any restored data.
- Document the root cause and resolution steps in the project’s documentation.

### 9. Prevent Future Issues
- Maintain backups of `docker-compose.yml`, `nautobot_config.py`, and `pyproject.toml`.
- Schedule regular database backups:
  ```bash
  docker-compose exec postgres pg_dump -U nautobot nautobot > /path/to/nautobot_db_backup_$(date +%F).sql
  ```
- Test configuration changes in a development environment before applying to production.

## References
- Nautobot Docker Compose: https://github.com/nautobot/nautobot-docker-compose[](https://github.com/nautobot/nautobot-docker-compose)
- Nautobot Docker Images: https://docs.nautobot.com/projects/core/en/stable/administration/docker/[](https://docs.nautobot.com/projects/core/en/stable/user-guide/administration/guides/docker/)
- PostgreSQL Documentation: Backup and Restore
- Redis Documentation: FLUSHDB Command