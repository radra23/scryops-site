---
title: "Anomaly Detection in Production: Patterns That Actually Work"
date: 2026-06-10
draft: true
excerpt: "Static thresholds miss gradual degradation. Anomaly detection catches it — but naive implementations generate more noise than signal. This guide covers the statistical and ML approaches that work in production observability."
readtime: 10
tags: ["AIOps", "AI", "Alerting", "Metrics", "Observability"]
---

<!-- TODO: Draft this guide -->
<!--
Sections to cover:
1. Why static thresholds fail for anomaly detection
2. Statistical approaches: Z-score, MAD, seasonal decomposition (STL)
3. Prometheus-native anomaly detection with predict_linear and deriv
4. Grafana ML plugin: DBSCAN and prophet-based anomaly detection
5. When to use supervised vs unsupervised approaches
6. Seasonality: handling daily/weekly patterns without false positives
7. Alert fatigue from anomaly detectors: how to tune signal-to-noise
8. Evaluation: how do you know your anomaly detector is working?
9. Open-source tools: Prometheus, Grafana ML, Thanos Ruler
10. Integration with existing alerting pipelines
-->
