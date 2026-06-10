---
title: "How to Detect Metric Anomalies with Prometheus and Grafana"
date: 2026-06-10
draft: true
excerpt: "Move beyond static thresholds by using Prometheus recording rules and Grafana ML to detect anomalous patterns in your metrics — without deploying a separate ML platform."
readtime: 7
tags: ["AIOps", "Prometheus", "Grafana", "Alerting", "How-to"]
---

<!-- TODO: Draft this how-to -->
<!--
Steps to cover:
1. Baseline approach: predict_linear() for trend-based alerting in Prometheus
2. Z-score anomaly detection with PromQL recording rules
3. Grafana ML: enabling the plugin and configuring a forecast model
4. Setting up seasonal baselines (hourly/daily/weekly patterns)
5. Creating anomaly alerts from ML-generated prediction bands
6. Tuning: adjusting sensitivity to reduce false positives
7. Evaluating your detector: tracking false positive and false negative rates
8. When to escalate to a dedicated ML platform

Include: PromQL snippets for each approach, Grafana panel configuration
-->
