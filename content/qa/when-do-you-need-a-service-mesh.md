---
title: "Do I need a service mesh for observability?"
date: 2026-06-10
draft: true
answer: "No. A service mesh gives you automatic network-layer telemetry without touching application code — useful, but not required. You can get equivalent observability with OTel SDK instrumentation in each service. The mesh becomes valuable when you have many services and cannot instrument them all, or when you need mTLS and traffic policy alongside observability."
excerpt: "No. A service mesh gives you automatic network-layer telemetry without touching application code, but OTel SDK instrumentation achieves equivalent coverage. The mesh earns its complexity at scale or when you need mTLS alongside observability."
readtime: 2
tags: ["Service Mesh", "Kubernetes", "OpenTelemetry", "Observability"]
---

<!-- TODO: Draft this Q&A -->
<!--
Answer should cover:
- What a service mesh provides automatically: RED metrics, basic traces, mTLS
- What it doesn't provide: application context, business logic spans, log correlation
- The complexity cost of a service mesh (Istio is not simple)
- OTel SDK as the alternative: more work per service, more context in the data
- The hybrid case: mesh for infra telemetry + OTel SDK for application telemetry
- Decision heuristic: <10 services → OTel SDK only; large fleet → consider mesh
-->
