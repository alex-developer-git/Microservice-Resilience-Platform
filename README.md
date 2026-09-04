# Microservice Resilience Platform

FastAPI service for registering external services, checking health status, applying a circuit breaker, exposing Prometheus metrics, and streaming status updates over WebSocket.

## Runtime Requirements

- Python 3.11+
- PostgreSQL
- Redis for health check result caching
- Celery broker, for example Redis or RabbitMQ

## Setup

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Set the required environment variables:

```powershell
$env:DATABASE_URL="postgresql+asyncpg://user:password@localhost:5432/resilience"
$env:REDIS_URL="redis://localhost:6379/0"
$env:CELERY_BROKER_URL="redis://localhost:6379/1"
$env:CELERY_TASK_NAME="resilience_platform.process_event"
```

Apply database migrations:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Start the API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

API docs are available at:

```text
http://127.0.0.1:8000/docs
```

## Example Requests

Register a service:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/register-service" `
  -H "Content-Type: application/json" `
  -d "{\"name\":\"orders\",\"url\":\"https://orders.example.com\",\"health_check_path\":\"/health\",\"timeout_seconds\":3,\"failure_threshold\":3,\"recovery_timeout_seconds\":30,\"cache_ttl_seconds\":10,\"enabled\":true}"
```

Check service health:

```powershell
curl.exe "http://127.0.0.1:8000/health/{service_id}"
```

Manually trip the circuit breaker:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/circuit-breaker/{service_id}/trip"
```

Read Prometheus metrics:

```powershell
curl.exe "http://127.0.0.1:8000/metrics"
```

WebSocket status stream:

```text
ws://127.0.0.1:8000/ws/status
```

## Tests

Run unit and API tests:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Run PostgreSQL integration tests with a test database:

```powershell
$env:TEST_DATABASE_URL="postgresql+asyncpg://user:password@localhost:5432/resilience_test"
.\.venv\Scripts\python.exe -m pytest -m integration
```

## Docker

Build a local Alpine-based image:

```powershell
docker build -t resilience-platform:latest .
```

Build for both amd64 and arm64:

```powershell
docker buildx build --platform linux/amd64,linux/arm64 -t resilience-platform:latest .
```

Run with a non-root user and a read-only root filesystem:

```powershell
docker run --rm --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m `
  -p 8000:8000 `
  -e DATABASE_URL="postgresql+asyncpg://user:password@host.docker.internal:5432/resilience" `
  -e REDIS_URL="redis://host.docker.internal:6379/0" `
  -e CELERY_BROKER_URL="redis://host.docker.internal:6379/1" `
  resilience-platform:latest
```

Check the container health endpoint:

```powershell
curl.exe "http://127.0.0.1:8000/health"
```

Scan image vulnerabilities and inspect image layers:

```powershell
trivy image --severity HIGH,CRITICAL --exit-code 1 resilience-platform:latest
dive resilience-platform:latest
docker image inspect resilience-platform:latest --format='{{.Size}}'
```

## Docker Compose

Start the full local stack:

```powershell
docker compose up --build
```

Services:

- API: `http://127.0.0.1:8000`
- API docs: `http://127.0.0.1:8000/docs`
- Prometheus: `http://127.0.0.1:9090`
- Grafana: `http://127.0.0.1:3000` (`admin` / `admin`)
- Jaeger UI: `http://127.0.0.1:16686`
- RabbitMQ UI: `http://127.0.0.1:15672` (`resilience` / `resilience`)

OpenTelemetry tracing is enabled in Docker Compose with OTLP export to Jaeger.
After calling API endpoints, traces appear in Jaeger under:

- `resilience-platform-api`
- `resilience-platform-worker`

## Kubernetes Progressive Delivery

The standard Kubernetes manifests are in `k8s/`.
An optional Argo Rollouts canary overlay is available in `k8s/canary/`.

Prerequisite for canary deployments:

```powershell
kubectl apply -n argo-rollouts -f https://github.com/argoproj/argo-rollouts/releases/latest/download/install.yaml
```

Deploy the canary overlay:

```powershell
kubectl apply -k k8s/canary
```

The canary rollout shifts traffic in stages and runs `/health` and `/ready` checks through an Argo Rollouts
`AnalysisTemplate`. Failed analysis checks abort the rollout and keep the previous stable revision available for rollback.

## Telegram CI Notifications

GitHub Actions sends a Telegram notification after push workflows when these repository secrets are configured:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

If either secret is missing, the notification step is skipped without failing the pipeline.
