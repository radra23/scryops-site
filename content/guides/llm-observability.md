---
title: "LLM Observability: Monitoring What You Cannot Threshold"
date: 2026-06-10
draft: true
excerpt: "Large language models fail in ways that traditional monitoring cannot detect. A guide to building observability for LLM-powered systems — covering latency, token costs, output quality, safety, and the emerging OpenTelemetry GenAI conventions."
readtime: 10
tags: ["LLM", "AI", "Observability", "OpenTelemetry", "AIOps"]
---

<!-- TODO: Draft this guide -->
<!--
Sections to cover:
1. What makes LLM observability different from API observability
2. The signals that matter: latency (TTFT, total), token usage, error rate, cost
3. Output quality signals: groundedness, relevance, safety scores
4. OpenTelemetry GenAI semantic conventions (gen_ai.* attributes)
5. Instrumenting LangChain and LlamaIndex with OTel
6. Prompt and response logging: what to capture vs what to omit (privacy)
7. Hallucination detection patterns (LLM-as-judge, retrieval grounding checks)
8. Token cost as a reliability signal: budget burn rate for LLM APIs
9. Prompt injection monitoring
10. Tracing multi-step LLM chains end-to-end
11. Tools: Langfuse, Phoenix (Arize), OpenLIT
-->
