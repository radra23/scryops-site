---
title: "Monitoring LLMs Is Not Like Monitoring APIs"
date: 2026-06-15
draft: false
excerpt: "An API either returns the right data or it doesn't. An LLM can return a confident, well-formatted, completely wrong answer. Observability for generative AI requires an entirely different mental model."
readtime: 7
tags: ["LLM", "AI", "Observability", "AIOps"]
---

> "A 200 OK with a hallucinated answer is the hardest failure mode to catch — your monitors will never see it coming."
> — Anonymous

Your LLM service is running perfectly. Response times are under 500ms. Error rates are flat at 0.1%. Every request returns HTTP 200. Your monitoring dashboard is green, and the on-call engineer is at peace.

The LLM is confidently telling users that a medication they asked about has no known drug interactions. It is incorrect. Your observability stack has no idea.

This is the foundational problem with applying traditional monitoring to generative AI. Traditional services fail loudly — a 500 error, a timeout, an empty response. LLMs fail silently, with confidence, in complete sentences.

## The Metric That Lied to You

Latency, error rate, and throughput describe the transport layer of your LLM service. They tell you whether the model received a request and returned something in time. They tell you nothing about what it returned.

This is a category difference, not a gap to paper over with additional dashboards. You cannot derive output quality from latency. You cannot measure hallucination with p99. A model that has silently shifted its behavior — returning shorter answers, becoming more cautious, interpreting system prompts differently after a version update — will not appear in any of your existing signal streams.

Traditional monitoring answers: *did it respond?* LLM observability has to answer: *was the response correct, safe, and worth what it cost?*

## Four Signal Layers That Actually Matter

LLM observability works across four distinct layers, each measuring something the others cannot.

**The input layer** is where your instrumentation sees what users actually ask. Prompt patterns reveal whether your system prompt is being followed, whether users have found edge cases that produce bad outputs, and whether certain query types consistently fail. Tracking token count on inputs tells you when users are approaching context limits — a request that pushes a 128K context window is behaviorally different from a 500-token question, and hitting that ceiling silently truncates context in ways that corrupt the response. Metadata here — user ID, session ID, timestamp, model version, temperature setting — is the chain of custody that makes every other signal interpretable after the fact.

**The output layer** is where quality lives. Length and finish reason are the first signals: a response that terminates with `max_tokens` rather than `stop` was cut off. The model ran out of room to complete its answer, and the user received something truncated. Beyond mechanics, output quality requires evaluation. Does the response answer the question? Is it grounded in retrieved context for RAG applications, or free-floating? Hallucination detection is not solved at the infrastructure layer — it requires either human review, automated LLM-as-judge evaluation, or groundedness checks against source documents. The telemetry layer can log the response; whether it was correct is an evaluation problem that sits above the metrics.

**The cost layer** is where token economics land. Unlike traditional services where cost is dominated by fixed infrastructure, LLM operational cost is content-driven: every input token and every output token carries a price. A generative endpoint that returns a long response to a short question costs more than one that is concise. Monitoring token usage per request — and aggregating it by user, session, model, and prompt template — is simultaneously a reliability signal (context limit saturation) and the primary lever for cost control. A prompt template change that doubles average output length doubles cost per request, invisibly, until the invoice arrives.

**The safety layer** is where LLM-specific failure modes live that have no traditional parallel. Content filtering catch rates tell you what your guardrails are intercepting. PII detection tracks whether personal data is flowing through the model when it should not be. Prompt injection attempts — adversarial inputs designed to override your system prompt or exfiltrate model instructions — are a security observability concern that your WAF was not built to catch. Audit trails for sensitive operations are often a compliance requirement, not just a debugging convenience.

{{< mermaid >}}
graph TD
    subgraph "LLM Request Lifecycle"
        REQ[User Request] --> INPUT[Input Layer\ntokens · prompt pattern · metadata]
        INPUT --> MODEL[Model Inference\nlatency · GPU util · retries]
        MODEL --> OUTPUT[Output Layer\ncompletion · finish reason · length]
        OUTPUT --> EVAL[Evaluation Layer\ngroundedness · safety · cost]
    end

    INPUT --> SIG1[Prompt anomaly\nContext saturation]
    MODEL --> SIG2[Latency p99\nToken throughput]
    OUTPUT --> SIG3[Finish reason distribution\nOutput length drift]
    EVAL --> SIG4[Hallucination risk\nPolicy violations\nCost per query]
{{< /mermaid >}}

## The Standard Emerging Around This

The observability community has been converging on a shared vocabulary for LLM signals. OpenTelemetry's GenAI semantic conventions define a standard set of span attributes for LLM operations — a namespace that lets you instrument once and query consistently across providers, models, and tooling.

The core attributes cover the signals that matter most:

```yaml
gen_ai.system: "openai"               # which provider
gen_ai.operation.name: "chat"         # chat · text_completion · embeddings
gen_ai.request.model: "gpt-4o"        # model requested
gen_ai.response.model: "gpt-4o"       # model that actually responded
gen_ai.usage.input_tokens: 312        # prompt token count
gen_ai.usage.output_tokens: 87        # completion token count
gen_ai.response.finish_reasons:       # stop · max_tokens · content_filter
  - stop
```

With these attributes on every LLM span, cost analysis (`input_tokens × price + output_tokens × price`) and model version tracking come for free. LangChain and LlamaIndex both ship OTel integrations that emit these conventions automatically when you configure an OTLP exporter. For frameworks not yet instrumented, the attributes are stable enough to add manually in a middleware layer.

{{< insight >}}
**Watch `finish_reasons: [max_tokens]` as a soft failure.** A truncated response is not an error by any HTTP or infrastructure measure — it is a silent content failure. In a chat application, the user received an incomplete answer. In a summarization pipeline, you may have dropped the conclusion. Track truncation separately from errors and feed it back into your prompt length budget and `max_tokens` configuration.
{{< /insight >}}

## The Sampling Dilemma

Traditional distributed tracing commonly samples 1–10% of requests in high-volume systems. For LLM observability, that calculus breaks down in both directions at once.

Logging the full prompt and response for every request is expensive and legally complicated. Prompts frequently contain PII, sensitive business context, or information users expect to be ephemeral. A 100% capture policy is a data governance problem accumulating in your trace store.

Sampling away 90% of requests means missing the long tail of unusual outputs, edge case failures, and rare safety incidents — exactly the events that matter most. A 1% sample of hallucinations is not a useful dataset for evaluating model quality over time.

The practical resolution: log input/output metadata for every request — token counts, finish reasons, model version, latency, template ID. Log the full prompt and response for a configurable sample, with elevated capture rate for flagged outputs: anything that triggered a content filter, hit max_tokens, was rated low-confidence by a downstream evaluator, or was explicitly marked for review by the application. Store full traces in a cold tier with short retention; keep metadata in your primary observability store for longer. This gives you statistical coverage and forensic depth where it counts, without the compliance exposure of logging everything everywhere.

## Drift Is the Silent Killer

Drift in an LLM service looks nothing like drift in a traditional service.

A traditional service drifts when latency climbs or error rates tick up — both visible in time-series metrics. An LLM drifts when its response quality changes: it starts hedging answers it previously answered directly, it ignores constraints in the system prompt that it previously followed, or it responds differently to semantically identical prompts after a model version update. None of this is visible to your existing monitors.

Detecting output drift requires storing a baseline distribution of outputs and comparing current behavior against it. For structured tasks — classification, extraction, summarization with verifiable outputs — this is tractable with automated evaluation. For open-ended generation, it typically requires periodic human review of a sampled output set or an LLM-as-judge pipeline that scores responses against a rubric.

The instrumentation prerequisite is logging which model version, which system prompt version, and which prompt template version produced each response. Without that chain of custody, you cannot isolate what changed when quality shifts.

## Where to Start

The gap between "monitored" and "observable" for an LLM service is wide, and trying to close it all at once produces a complex system that is half-instrumented everywhere and fully reliable nowhere.

Start with token usage and finish reasons on every request. Add four span attributes if your framework does not already emit them: `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.response.finish_reasons`. That alone surfaces cost by model, detects truncation failures, and gives you a baseline distribution of response characteristics to compare future behavior against.

Layer in prompt metadata next — template ID, template version, session ID. This makes every other signal debuggable. When output length spikes or quality scores drop, you need to group by template to find the culprit, and you cannot do that without the label.

Quality evaluation comes last, because it requires an evaluation pipeline that sits outside the telemetry stack. Build the instrumentation first, so you have somewhere to write the scores when the evaluator exists.

Your dashboard will still be green. But now you will know what the green actually means — and what it cannot tell you.
