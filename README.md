# Microservice Resilience Platform

FastAPI service for registering external services, checking health status, applying a circuit breaker, exposing Prometheus metrics, and streaming status updates over WebSocket.

## Runtime Requirements

- Python 3.11+
- PostgreSQL
- Redis for health check result caching and distributed application rate limiting
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
$env:RATE_LIMIT_ENABLED="true"
$env:RATE_LIMIT_GLOBAL_REQUESTS="120"
$env:RATE_LIMIT_WINDOW_SECONDS="60"
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

Core Prometheus metrics:

- `http_requests_total`
- `http_request_duration_seconds`
- `rate_limit_decisions_total`
- `rate_limit_backend_errors_total`
- `registered_services_total`
- `monitored_services`
- `enabled_services`
- `health_checks_total`
- `health_check_probes_total`
- `health_check_latency_ms`
- `health_check_latency_seconds`
- `service_health_status`
- `health_check_cache_hits_total`
- `health_check_cache_misses_total`
- `circuit_breaker_state`
- `circuit_breaker_open_total`
- `circuit_breaker_transitions_total`
- `circuit_breaker_manual_trips_total`

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
- Alertmanager: `http://127.0.0.1:9093`
- Grafana: `http://127.0.0.1:3000` (`admin` / `admin`)
- Jaeger UI: `http://127.0.0.1:16686`
- RabbitMQ UI: `http://127.0.0.1:15672` (`resilience` / `resilience`)

Grafana automatically provisions the `Microservice Resilience Platform` dashboard with API latency, API error rate,
health check error rate, service inventory, cache activity, and circuit breaker state panels.

Prometheus loads circuit breaker alert rules from `monitoring/prometheus/rules/resilience-alerts.yml` and sends alerts
to Alertmanager. Alertmanager forwards firing and resolved circuit breaker notifications to the API webhook at
`/alerts/alertmanager`, where they are logged and broadcast to connected `ws://127.0.0.1:8000/ws/status` clients.
Configured alerts:

- `CircuitBreakerOpen`: fires when `circuit_breaker_state == 2` for 1 minute.
- `CircuitBreakerOpenedRecently`: fires when `circuit_breaker_open_total` increases within 5 minutes.

OpenTelemetry tracing is enabled in Docker Compose with OTLP export to Jaeger.
After calling API endpoints, traces appear in Jaeger under:

- `resilience-platform-api`
- `resilience-platform-worker`

## Logging

Application logs are emitted as JSON to stdout.
Each HTTP request gets an `X-Correlation-ID`; if the caller sends a valid value it is reused, otherwise the API generates
a UUID and returns it in the response header. JSON logs include `correlation_id`, and include OpenTelemetry `trace_id`
and `span_id` when a span is active.

Start local Loki log collection:

```powershell
docker compose --profile logging up --build
```

Promtail reads Docker container logs from stdout and forwards parsed JSON fields to Loki at `http://localhost:3100`.

## Rate Limiting

The API uses a Redis-backed token bucket shared by all application replicas. Global middleware limits public HTTP traffic,
while FastAPI dependencies apply stricter limits to service registration, external health checks, and manual circuit
breaker trips. `/health`, `/ready`, and `/metrics` are excluded so Kubernetes probes and Prometheus scraping remain
available.

Successful limited responses include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset`. Rejected
requests return HTTP `429`, a structured `rate_limit_exceeded` error, and `Retry-After`.

Rate limiting is configured with:

- `RATE_LIMIT_ENABLED` and `RATE_LIMIT_FAIL_OPEN`
- `RATE_LIMIT_TRUST_FORWARDED_FOR`, enabled only behind a trusted reverse proxy
- `RATE_LIMIT_GLOBAL_REQUESTS` and `RATE_LIMIT_WINDOW_SECONDS`
- `RATE_LIMIT_REGISTER_SERVICE_REQUESTS`
- `RATE_LIMIT_HEALTH_CHECK_REQUESTS`
- `RATE_LIMIT_CIRCUIT_BREAKER_REQUESTS`

The Kubernetes Ingress adds a coarse per-IP connection and request limit per ingress-nginx controller replica before
traffic reaches the application. The Redis-backed application limit remains shared across pods when either the Deployment
or Argo Rollout scales.

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
The canary overlay starts with five replicas so its initial 20% step can assign one pod to the canary version. Its HPA
scales the Rollout between 5 and 10 replicas.

## Kubernetes Custom Metric Autoscaling

The HPA scales the API using CPU and the per-pod `health_checks_per_second` custom metric. The application exports the
zero-initialized `health_check_probes_total` counter for every pod. It counts uncached outbound health probes when they
start. Prometheus Adapter converts the counter to a two-minute per-second rate and publishes it through the Kubernetes
Custom Metrics API.

Install the pinned Prometheus stack. Its values select ServiceMonitors from the `monitoring` and
`resilience-platform` namespaces. The pinned chart requires Kubernetes 1.25 or newer:

```powershell
helm upgrade --install kube-prometheus-stack oci://ghcr.io/prometheus-community/charts/kube-prometheus-stack `
  --version 89.2.3 `
  --namespace monitoring `
  --create-namespace `
  --values infra/kube-prometheus-stack/values.yaml
```

Deploy either the standard manifests or the canary overlay, then add the API ServiceMonitor:

```powershell
kubectl apply -k k8s
kubectl apply -k k8s/observability
```

For a canary deployment, use `kubectl apply -k k8s/canary` instead of `kubectl apply -k k8s`.

Install the pinned Prometheus Adapter chart. The configured Prometheus URL assumes the release name and namespace from
the preceding command:

```powershell
helm upgrade --install prometheus-adapter oci://ghcr.io/prometheus-community/charts/prometheus-adapter `
  --version 5.3.0 `
  --namespace monitoring `
  --values infra/prometheus-adapter/values.yaml
```

The CPU metric also requires Metrics Server. Verify that it is available before testing the HPA:

```powershell
kubectl top pods -n resilience-platform
```

Verify that the adapter returns one custom-metric value for each API pod and that the HPA has no unknown metrics:

```powershell
kubectl get --raw "/apis/custom.metrics.k8s.io/v1beta1/namespaces/resilience-platform/pods/*/health_checks_per_second"
kubectl describe hpa -n resilience-platform resilience-platform-api
kubectl get hpa -n resilience-platform resilience-platform-api --watch
```

Generate uncached health checks above the configured average of two probes per second per pod for at least two minutes.
Confirm that the HPA increases replicas, respects its upper limit, and returns to its minimum after the five-minute
scale-down stabilization window.

## Telegram CI Notifications

GitHub Actions sends a Telegram notification after push workflows when these repository secrets are configured:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

If either secret is missing, the notification step is skipped without failing the pipeline.
