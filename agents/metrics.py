from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import APIRouter
from fastapi.responses import Response

router = APIRouter()

events_processed_total = Counter(
    "labmind_events_processed_total",
    "Total number of specimen events processed",
    ["event_type", "status"],
)

actions_proposed_total = Counter(
    "labmind_actions_proposed_total",
    "Total number of actions proposed by agents",
    ["agent_name", "action_type"],
)

actions_approved_total = Counter(
    "labmind_actions_approved_total",
    "Total number of actions approved by operators",
    ["action_type"],
)

actions_dismissed_total = Counter(
    "labmind_actions_dismissed_total",
    "Total number of actions dismissed by operators",
    ["action_type"],
)

llm_invocations_total = Counter(
    "labmind_llm_invocations_total",
    "Total number of LLM invocations",
    ["agent_name", "status"],
)

critical_values_detected_total = Counter(
    "labmind_critical_values_detected_total",
    "Total number of critical values detected",
)

specimens_active = Gauge(
    "labmind_specimens_active",
    "Number of active specimens in working memory",
)

pipeline_batch_size = Histogram(
    "labmind_pipeline_batch_size",
    "Number of events processed in each batch",
    buckets=[1, 2, 5, 10, 20, 50],
)

pipeline_processing_seconds = Histogram(
    "labmind_pipeline_processing_seconds",
    "Time to process a pipeline event",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0],
)

request_duration_seconds = Histogram(
    "labmind_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint", "status_code"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)


@router.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
