---
title: "Monitoring LLMs Is Not Like Monitoring APIs"
date: 2026-06-10
draft: true
excerpt: "An API either returns the right data or it doesn't. An LLM can return a confident, well-formatted, completely wrong answer. Observability for generative AI requires an entirely different mental model."
readtime: 7
tags: ["LLM", "AI", "Observability", "AIOps"]
---

<!-- TODO: Draft this article -->
<!--
Key angles to cover:
- Why traditional latency/error-rate metrics are insufficient for LLMs
- What you actually need to monitor: accuracy, groundedness, safety, cost
- Hallucination as an observability problem, not just a model problem
- Token usage as a reliability and cost signal
- Prompt injection as a security observability concern
- Tracing LLM chains: LangChain, LlamaIndex, and OpenTelemetry semantic conventions
- The emerging standard: OpenTelemetry GenAI semantic conventions
- When to sample vs when to log everything (cost vs coverage tradeoff)
-->
