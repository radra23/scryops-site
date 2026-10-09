---
title: "LLM Observability: Monitoring What You Cannot Threshold"
date: 2026-06-10
draft: false
excerpt: "An LLM can return a confident, well-formatted, wrong answer with a 200 OK. What to measure, how OpenTelemetry's GenAI conventions name it, and how to trace, budget and evaluate LLM calls."
readtime: 12
tags: ["LLM", "AI", "OpenTelemetry", "Observability"]
card:
  title: "Monitoring LLMs You Can't Threshold"
---

An API either returns the right data or it doesn't. An LLM can return a confident, well-formatted, completely wrong answer, with a 200 OK and a latency well inside your SLO.

That breaks most of the monitoring you already have. Error rate and p99 still matter, but they stop being the whole story. The failure that hurts users is the one that looks like success.

This guide is for platform and SRE engineers who have just inherited a service that calls a model: a chat feature, a RAG pipeline, an agent with tools.

## A 200 OK proves nothing here

Four things make an LLM call a different animal from the REST calls your dashboards were built for.

**It isn't deterministic.** The same prompt can produce different answers on consecutive calls, and providers don't promise identical output even at temperature zero. You can't write a synthetic check that asserts on the response body, because there is no single correct body.

**Success and correctness are separate.** HTTP reports success when the model produced *something*. Whether that something is grounded in your documents or answers the question asked is invisible to it. A hallucinated refund policy and a correct one share a status code.

{{< obs-llm-truncated-call >}}

**Latency follows output length.** Models generate one token at a time, so a 500-token answer takes far longer than a 20-token one. A latency spike might be an overloaded provider, or a prompt change that made answers three times longer. Without token counts next to the duration, you can't tell which.

**Cost per call isn't a constant.** Providers bill per token, usually at different rates for input and output. A 200-token question with a 50-token answer and a 15,000-token RAG context with a 1,500-token answer differ by 75× on input and 30× on output, before anyone switches to a pricier model. Two orders of magnitude between calls on one endpoint is ordinary.

## The signals worth collecting

Before any conventions, here's what you want to know about every model call:

| Signal | Why it matters |
|---|---|
| Time to first token | What a streaming user perceives as "is it working?" |
| Total duration | What your upstream timeout and SLO see |
| Input and output tokens | The driver of both latency and cost |
| Finish reason | Whether the model stopped on its own or was cut off |
| Errors, rate limits, retries | Provider health and quota headroom |
| Cost | Derived: tokens × your price table |
| Quality | Grounded, relevant, safe? Not defined by OTel |

**Time to first token (TTFT) versus total duration.** For a streamed UI, TTFT is the latency the user feels; total duration mostly tracks answer length. Track both, and read duration next to output tokens.

**Finish reasons, and the silent failure.** Every completion says why it stopped. `stop` means the model finished. `length` means it hit `max_tokens` and was cut off mid-thought. The response is still a 200, the text still looks plausible, and if you asked for JSON it is now invalid JSON that will fail three services downstream. A rising share of `length` finish reasons is one of the cheapest quality alarms you can build. It usually means a prompt or context change made answers outgrow their budget.

## The OpenTelemetry GenAI conventions, as of October 2026

OpenTelemetry's GenAI semantic conventions give these signals shared names. The headline caveat: **they are still in Development status.** Every GenAI attribute, span and metric is marked Development, not Stable, and names have changed between releases.

Two moves this year matter before you build dashboards:

- **The conventions moved repositories.** Since [semantic conventions v1.42.0](https://github.com/open-telemetry/semantic-conventions/releases/tag/v1.42.0) (June 2026), the GenAI definitions live in a dedicated [semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai) repository, and the [GenAI spec pages on opentelemetry.io](https://opentelemetry.io/docs/specs/semconv/gen-ai/) say so. The last core release that still defines them is v1.41.1. The new repository hasn't cut a release yet, so its `main` branch is a moving target.
- **The Python instrumentation moved too.** The official OpenAI instrumentation is now `opentelemetry-instrumentation-genai-openai`, published from [opentelemetry-python-genai](https://github.com/open-telemetry/opentelemetry-python-genai). It continues `opentelemetry-instrumentation-openai-v2`, which now only gets security patches.

The rule that follows: **pin your instrumentation versions, and treat attribute and metric names as a contract you re-check on every upgrade.** The old `openai-v2` package emits v1.30-era names, including the deprecated `gen_ai.system`, unless you set `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`. The new package emits the latest experimental conventions unconditionally; there is no switch.

### Spans

A model call is a `CLIENT` span named `{gen_ai.operation.name} {gen_ai.request.model}`, such as `chat gpt-4o-mini`. If the client retries a transient failure, the span covers the whole logical operation, retries included. The attributes you'll lean on:

- `gen_ai.operation.name`: `chat`, `embeddings`, `retrieval`, `execute_tool`, `invoke_agent` and a few more.
- `gen_ai.provider.name`: `openai`, `aws.bedrock`, `gcp.vertex_ai` and so on. It replaced `gen_ai.system`, which is deprecated. Queries that filter on `gen_ai.system` go quiet after an upgrade.
- `gen_ai.request.model` and `gen_ai.response.model`: what you asked for and what answered. Aliases resolve to dated snapshots, so they differ.
- `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens`.
- `gen_ai.response.finish_reasons`: an array, one entry per returned choice.
- `gen_ai.request.max_tokens`, `gen_ai.request.temperature` and other request parameters.
- `gen_ai.request.stream` and `gen_ai.response.time_to_first_chunk` on streaming calls.
- `error.type` when the call failed.

What isn't there: cost. The conventions record tokens, not money; prices change and differ per contract.

### Metrics

The released client instrumentation emits:

- `gen_ai.client.operation.duration`: a histogram, in seconds.
- `gen_ai.client.token.usage`: a histogram of tokens per call, split by `gen_ai.token.type` (`input` or `output`).
- `gen_ai.client.operation.time_to_first_chunk` and `gen_ai.client.operation.time_per_output_chunk` for streaming.

If you run your own model server, there are server-side metrics too, including `gen_ai.server.time_to_first_token`, `gen_ai.server.time_per_output_token` and `gen_ai.server.request.duration`.

The moving-target problem in one example: on the GenAI repository's `main` branch, `gen_ai.client.token.usage` and its `gen_ai.token.type` attribute have already been replaced by per-direction histograms (`gen_ai.client.inference.operation.input_tokens` and `.output_tokens`) plus counters. No released instrumentation emits those yet. Build dashboards against the name you actually receive, and expect to migrate them.

### Message content

Prompts, system instructions and completions are captured only on request; the spec says instrumentations should not capture them by default. Opted in, they land in `gen_ai.input.messages`, `gen_ai.output.messages` and `gen_ai.system_instructions`, as span attributes or on a `gen_ai.client.inference.operation.details` event. The Python instrumentation reads `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`: `span_only`, `event_only`, `span_and_event`, or `no_content` (the default). The legacy `openai-v2` package also accepts `true`, which only applies in its old-conventions mode.

The spec also describes a hook that uploads content to external storage and records a reference on the span.

### Agents and tools

Agent frameworks get their own spans. `invoke_agent {gen_ai.agent.name}` wraps an agent run. `execute_tool {gen_ai.tool.name}` wraps each tool call, with `gen_ai.tool.call.id` and opt-in `gen_ai.tool.call.arguments` and `gen_ai.tool.call.result`. `retrieval {gen_ai.data_source.id}` covers a vector-store lookup. There are `create_agent` and `invoke_workflow` spans too.

## Instrumenting a Python service

Here's the official instrumentation wired to console exporters, so you can see exactly what it emits. To run without an API key or a bill, the client points at a fake OpenAI-compatible endpoint on localhost: a few dozen lines of `http.server` that wait 350 ms, then stream a canned answer that stops at the `max_tokens` limit.

```bash
pip install "opentelemetry-instrumentation-genai-openai==1.2b0" openai opentelemetry-sdk
```

```python
from openai import OpenAI
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader, ConsoleMetricExporter
from opentelemetry.instrumentation.genai.openai import OpenAIInstrumentor

trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
metrics.set_meter_provider(MeterProvider(
    metric_readers=[PeriodicExportingMetricReader(ConsoleMetricExporter())]))

OpenAIInstrumentor().instrument()

# Fake local endpoint: no key, no network, no bill.
client = OpenAI(base_url="http://127.0.0.1:8765/v1", api_key="unused")

stream = client.chat.completions.create(
    model="gpt-4o-mini",
    max_tokens=16,
    stream=True,
    stream_options={"include_usage": True},
    messages=[{"role": "user", "content": "What is the refund policy?"}],
)
print("".join(c.choices[0].delta.content or "" for c in stream if c.choices))
metrics.get_meter_provider().shutdown()
```

This ran with `opentelemetry-instrumentation-genai-openai` 1.2b0, `opentelemetry-util-genai` 1.2b0, `opentelemetry-sdk` 1.45.0, `openai` 3.24.0 and Python 3.12. The span, trimmed:

```json
{
    "name": "chat gpt-4o-mini",
    "kind": "SpanKind.CLIENT",
    "status": { "status_code": "UNSET" },
    "attributes": {
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": "gpt-4o-mini",
        "gen_ai.provider.name": "openai",
        "server.address": "127.0.0.1",
        "server.port": 8765,
        "gen_ai.request.stream": true,
        "gen_ai.request.max_tokens": 16,
        "gen_ai.response.finish_reasons": ["length"],
        "gen_ai.response.model": "gpt-4o-mini-2024-07-18",
        "gen_ai.response.id": "chatcmpl-fake-002",
        "gen_ai.usage.input_tokens": 412,
        "gen_ai.usage.output_tokens": 16,
        "gen_ai.response.time_to_first_chunk": 0.3795130830258131
    }
}
```

Look at the status: `UNSET`, not `ERROR`. The answer was truncated (`finish_reasons: ["length"]`, output tokens exactly equal to `max_tokens`), and nothing in the status says so. That's the silent failure, caught in the act. Note too that the model you asked for isn't the model that answered.

The metrics from the same run, buckets trimmed:

```text
gen_ai.client.operation.time_to_first_chunk   s        sum=0.3795
gen_ai.client.operation.time_per_output_chunk s        sum=0.3128
gen_ai.client.operation.duration              s        sum=0.6929
gen_ai.client.token.usage                     {token}  gen_ai.token.type=input   sum=412
gen_ai.client.token.usage                     {token}  gen_ai.token.type=output  sum=16
```

Data points carry operation, provider, models and server, plus exemplars linking back to the trace. Finish reasons are *not* a metric attribute. To alert on truncation, count spans by `gen_ai.response.finish_reasons` in your trace backend, or emit your own counter.

With `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=span_only`, the same span gains the conversation as JSON strings:

```json
"gen_ai.input.messages": "[{\"role\":\"user\",\"parts\":[{\"content\":\"What is the refund policy?\",\"type\":\"text\"}],\"name\":null}]",
"gen_ai.output.messages": "[{\"role\":\"assistant\",\"parts\":[{\"content\":\"Refunds are accepted within 30 days\",\"type\":\"text\"}],\"finish_reason\":\"length\",\"name\":null}]"
```

### Retries hide inside one span

Point the client at an endpoint that always answers `429 Too Many Requests` and the fake server logs three requests: the first try plus the OpenAI client's two default retries. The trace shows one span:

```json
{
    "name": "chat gpt-4o-mini",
    "status": { "status_code": "ERROR", "description": "Error code: 429 - ..." },
    "attributes": {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "openai",
        "error.type": "openai.RateLimitError"
    }
}
```

That matches the spec, and it hides retry pressure. If quota headroom matters, add HTTP client instrumentation underneath so each attempt becomes a child span. Alert on rate limits separately from other failures: a burst of `RateLimitError` is a capacity conversation, not a bug.

### Pin the whole set

A fresh `pip install opentelemetry-instrumentation-openai-v2` today pulls 2.4b0 with the newest `opentelemetry-util-genai`, and fails at import with `No module named 'opentelemetry.util.genai.instruments'`. It also needs `openai<3`, because it imports `httpx` and `openai` 3.x no longer installs it. Pinning `opentelemetry-util-genai==0.4b0` and `openai<3` made it run. That's Development status in practice. Lock files aren't optional.

## The rest of the ecosystem

How the other instrumentation you'll meet relates to the conventions:

- **[OpenLLMetry](https://github.com/traceloop/openllmetry)** (Traceloop) instruments many providers, vector stores and frameworks on OpenTelemetry. It uses `gen_ai.*` names but also emits attributes the spec doesn't define (`gen_ai.usage.total_tokens`, for one) and its own `traceloop.*` namespace. Naming trap: the PyPI packages `opentelemetry-instrumentation-langchain` and `opentelemetry-instrumentation-llamaindex` are OpenLLMetry's, not the OpenTelemetry project's.
- **[OpenInference](https://github.com/Arize-ai/openinference)** (Arize, behind Phoenix) ships over OTLP but defines **its own attribute conventions**: `openinference.span.kind`, `llm.model_name`, `llm.token_count.prompt`, `input.value`. A backend expecting `gen_ai.*` needs a mapping.
- **[Langfuse](https://langfuse.com/integrations/native/opentelemetry)** accepts OTLP over HTTP at `/api/public/otel` and maps `gen_ai.*` attributes; its current SDK is a thin layer over the OpenTelemetry client.
- **[OpenLIT](https://github.com/openlit/openlit)** describes itself as OpenTelemetry-native, following `gen_ai.*` and exporting plain OTLP.
- **LangChain** has no OTel exporter of its own. LangChain and LangGraph emit spans through the [LangSmith SDK](https://docs.langchain.com/langsmith/trace-with-opentelemetry) with `LANGSMITH_OTEL_ENABLED=true`; `LANGSMITH_OTEL_ONLY=true` sends them only to your OTLP endpoint. The OpenTelemetry project now also publishes `opentelemetry-instrumentation-genai-langchain`.
- **LlamaIndex** publishes `llama-index-observability-otel`, and the OpenTelemetry project publishes `opentelemetry-instrumentation-genai-llama-index`.

*Checked against each project's docs or package metadata; not run.*

The choice that matters is which attribute namespace your alerts will depend on. Pick one per estate, or every query gets written twice.

## Prompts and responses are user data

Content capture is the most useful debugging switch in this stack, and the most dangerous. Users paste account numbers and health details into chat boxes. A span holding the conversation is personal data, in a backend with broader access and longer retention than your production database.

The spec's capture-nothing default is deliberate. Keep it in production unless you have a reason and a plan:

- **Prefer metadata over content.** Tokens, finish reasons, model, prompt template name and version (`gen_ai.prompt.name`, `gen_ai.prompt.version`) and a response ID answer most operational questions without a single user word.
- **If you need content, store it separately.** That's what the upload hook is for: content goes to a store with its own access controls and retention, and the span carries a reference. Traces stay shareable with the whole on-call rotation; prompts don't.
- **Scrub before export.** [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/#the-fix-lives-in-the-collector-not-the-application) covers redaction in the Collector, and [Scrub PII from Application Logs in .NET](/howtos/scrub-pii-from-application-logs-dotnet/) the in-process side. Neither justifies capturing raw prompts by default: pattern-based redaction misses free text.
- **Sample content harder than spans, and keep it for less time.** A small sample retained for days, not months, is usually enough to debug a prompt regression. If you tail-sample traces, as in [Your Sampling Strategy Is Lying to You](/articles/sampling-strategy/), check that the error traces you keep aren't the ones carrying the most sensitive content.

## Quality and safety live outside the request path

Quality is the signal OpenTelemetry doesn't measure for you, and grading every answer inline doubles latency and cost on the hot path. Instead, sample a fraction of traffic and evaluate it in a separate job:

- **LLM-as-judge:** a second model scores answers for relevance or correctness against a rubric. It's a model grading a model, so calibrate it against human labels before trusting its numbers.
- **Retrieval-grounding checks:** for RAG, test whether the answer's claims are supported by the chunks actually retrieved. This catches the confident fabrication no status code ever will.
- **Deterministic checks:** does the JSON parse, match the schema, cite a document that exists. Cheap and exact; run them on every response.

Record results as telemetry linked to the call they judge. The conventions define a `gen_ai.evaluation.result` event with `gen_ai.evaluation.name`, `gen_ai.evaluation.score.value` and a low-cardinality `gen_ai.evaluation.score.label`. It should be parented to the evaluated span, or carry `gen_ai.response.id` when that isn't possible. In practice, store trace and span IDs with each sampled response so the eval job can attach its verdict hours later. "Quality dropped after the prompt change" then becomes a query, not a hunch.

{{< obs-llm-eval-paths >}}

**Prompt injection deserves honesty.** There is no reliable detector, only heuristics with false positives and false negatives: a classifier score on inputs, a canary string in the system prompt that should never appear in output, tool calls the request shouldn't need, retrieved documents containing instruction-like text. Record them as attributes or events and watch their rates. A spike is a reason to look, never proof. The actual controls (least-privilege tools, confirmation before side effects) live in the application, not the telemetry.

## Tokens are a budget, so treat them like one

Token spend behaves like an error budget: a fixed amount per period, consumed at a variable rate. The SLO toolkit fits.

Derive cost at query time, not in the span: sum tokens per `gen_ai.response.model` and multiply by your price table.

```promql
# Output tokens per model over the last hour
sum by (gen_ai_response_model) (
  increase(gen_ai_client_token_usage_sum{gen_ai_token_type="output"}[1h])
)
```

*Checked against the Prometheus OTLP translation docs; not run. Names assume dots become underscores and histograms gain a `_sum` series; check what your pipeline produces.*

Then frame spend as a burn rate. With a monthly budget B, the sustainable pace is B/30 per day, and burn rate is current spend divided by that pace. The arithmetic matches [SLOs and Error Budgets](/guides/slos-and-error-budgets/#burn-rate-alerts): at 14.4×, a 30-day budget lasts 30 ÷ 14.4 ≈ 2.1 days, about 50 hours. Not 14 hours, and not one. That's a page with days, not minutes, to find the cause; a slow 2× burn is a ticket.

Cost burns rarely come from traffic. Check these first:

- A prompt or retrieval change that inflated input tokens per call.
- An agent stuck in a tool-calling loop, making dozens of model calls per request. Count model-call spans per trace, and cap iterations in code.
- A quiet switch to a pricier model, visible in `gen_ai.response.model`.
- Retries multiplying spend during a provider incident.

Each shows up in tokens per request long before it shows up on the invoice.

## One trace per question

Real features chain calls: retrieve, call the model, call a tool, call the model again. When the answer is wrong, you need the whole chain for that one request, in order, with tokens and finish reason at every step. That means one trace per user request, with model calls, retrievals and tool executions as its children:

{{< obs-waterfall title="One support question, one trace" total="6400" critical="6"
      units="milliseconds, illustrative · solid = self time, hatched = waiting on children"
      caption="Fig. — One trace for one support question: the agent span parents every model call, retrieval and tool call, and the tool's own HTTP call nests beneath it. The second model call owns the latency because it writes the long answer." >}}
[ {"name":"POST /support/chat","start":0,"duration":6240,"self":40,"depth":0},
  {"name":"invoke_agent","start":20,"duration":6200,"self":100,"depth":1,"kind":"manual"},
  {"name":"chat gpt-4o-mini","start":40,"duration":1180,"depth":2},
  {"name":"execute_tool","start":1240,"duration":360,"self":40,"depth":2,"kind":"manual"},
  {"name":"GET /orders/{id}","start":1260,"duration":320,"depth":3},
  {"name":"retrieval","start":1620,"duration":280,"depth":2,"kind":"manual"},
  {"name":"chat gpt-4o-mini","start":1920,"duration":4280,"depth":2} ]
{{< /obs-waterfall >}}

Three things hold the tree together:

- **Context flows into every step.** Model spans parent under whatever span is current, so the request needs a span (server instrumentation usually provides it), and async work and thread pools must carry context. Tools calling other services need propagation over the wire; [Context Propagation](/guides/otel-context-propagation/) covers where that breaks.
- **Name homegrown steps after the conventions.** If your framework has no instrumentation, create `invoke_agent`, `execute_tool` and `retrieval` spans by hand with the documented names. A GenAI-aware backend then renders your agent like any other.
- **Put identity on the trace.** `gen_ai.agent.name`, your prompt template version and `gen_ai.conversation.id` let you group traces by what the user was talking to. Set the conversation ID only when you genuinely have one; the spec says not to invent it from a trace ID.

Then "why did the bot quote the wrong refund window" stops being archaeology: the trace shows retrieval returning the 2024 policy and the model faithfully summarising it. Fix the index, not the prompt.

{{< obs-mascot class="bard" tag="your chatbot, confidently" quip="Ask me the refund policy and I shall answer in flawless verse: thirty days, sixty, a lifetime guarantee, whichever scans. Status 200. Finish reason: I ran out of tokens mid-rhyme. You are welcome." caption="Bawk Dylan, who has never once answered 'I don't know'." >}}

## Where to start

Not everything on day one. In order:

1. **Instrument the client** with the official instrumentation, versions pinned, content capture off.
2. **Dashboard TTFT, duration, tokens per call and finish reasons** per model and route. Alert on a rising share of `length` finish reasons and on rate-limit errors.
3. **Turn token metrics into a budget** with burn-rate alerts, using your SLO logic.
4. **Make one request one trace**, with agent, tool and retrieval spans beneath it.
5. **Add sampled, asynchronous evaluation**, linked back to traces by ID.
6. **Decide on content capture deliberately**: separate storage, scrubbing, short retention, or not at all.

New to OpenTelemetry itself? [OpenTelemetry: What It Is and How It Fits Together](/guides/opentelemetry-overview/) covers the signals and Collector this guide builds on.

The models will keep changing, and for now so will the conventions. The shift underneath won't: for LLM features, "did it respond" and "was it right" are separate questions, and only one of them comes for free.
