---
title: "How to Instrument a Web Frontend with OpenTelemetry RUM"
date: 2026-06-10
draft: true
excerpt: "Add OpenTelemetry instrumentation to a web application to capture Core Web Vitals, page load traces, user interaction spans, and JavaScript errors — and connect them to your backend traces."
readtime: 7
tags: ["RUM", "OpenTelemetry", "Tracing", "How-to"]
---

<!-- TODO: Draft this how-to -->
<!--
Steps to cover:
1. Install @opentelemetry/sdk-trace-web and auto-instrumentation packages
2. Configure the tracer provider and exporters (OTLP/HTTP to Collector)
3. Enable document load and fetch instrumentation
4. Add W3C Trace Context to fetch calls for backend correlation
5. Capture Core Web Vitals as OTel spans (using web-vitals library)
6. Capture JavaScript errors as span events
7. Configure Grafana Faro as the receiving backend
8. Verify traces appear and link to backend spans
9. Privacy checklist: what not to include in browser spans

Include: working code snippets (TypeScript/JS), Collector config for CORS headers
-->
