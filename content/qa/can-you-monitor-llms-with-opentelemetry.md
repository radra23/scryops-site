---
title: "Can you monitor LLMs with OpenTelemetry?"
date: 2026-06-10
draft: true
answer: "Yes. OpenTelemetry has emerging semantic conventions for GenAI (gen_ai.*) that cover model name, token usage, prompt/response content, and finish reason. Libraries like LangChain and LlamaIndex have OTel integrations. You'll need to supplement with custom spans for output quality metrics, which OTel doesn't define."
excerpt: "Yes. OTel has GenAI semantic conventions (gen_ai.*) covering model, tokens, prompts, and finish reason. LangChain and LlamaIndex have OTel integrations. Output quality metrics still need custom spans."
readtime: 2
tags: ["LLM", "AI", "OpenTelemetry", "Observability"]
---

<!-- TODO: Draft this Q&A -->
<!--
Answer should cover:
- OTel GenAI semantic conventions status (as of 2026: experimental/stable status)
- Key gen_ai.* attributes: system, model, operation.name, usage.input_tokens, usage.output_tokens
- LangChain OTel integration: langchain-openai + OTel SDK
- LlamaIndex OTel support
- What OTel covers well: latency, token usage, error rate, model calls
- What OTel doesn't cover: output quality, hallucination rate, groundedness (needs custom spans + evals)
- Tools that layer on top: Langfuse, Phoenix, OpenLIT (use OTel internally)
-->
