---
title: "Observability for IoT Fleets: Monitoring at Machine Scale"
date: 2026-06-10
draft: true
excerpt: "Monitoring a thousand identical devices is a different problem from monitoring a thousand microservices. Fleet-level observability requires aggregation-first thinking, anomaly detection across devices, and tolerance for data loss."
readtime: 9
tags: ["IoT", "Edge", "Observability", "Metrics", "AIOps"]
---

<!-- TODO: Draft this guide -->
<!--
Sections to cover:
1. IoT observability vs traditional service observability
2. Scale challenges: 10K+ devices, limited bandwidth, heterogeneous hardware
3. Fleet-level vs device-level monitoring: when to aggregate vs drill down
4. Key signals for IoT: device health, connectivity, sensor readings, firmware version
5. Collection architecture: MQTT → OTel Collector → central backend
6. Time-series data management for sensor data (down-sampling, roll-up policies)
7. Anomaly detection across a fleet: detecting outlier devices
8. OTA update observability: tracking firmware rollout success rate
9. Device lifecycle management: tracking provisioning, active, decommissioned states
10. Tools: InfluxDB, TimescaleDB, Thingsboard, AWS IoT + OTel integration
-->
