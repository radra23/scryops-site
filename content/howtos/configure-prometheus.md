---
title: "How to Configure Prometheus for Your Service"
date: 2026-06-07
draft: false
excerpt: "From zero to a working Prometheus setup — scraping your .NET service, writing your first PromQL queries, and setting up recording rules for expensive calculations."
readtime: 8
tags: ["Prometheus", "Metrics", "How-to", "OpenTelemetry"]
---

> "A metric that nobody queries is just noise with a retention policy."
> — Anonymous

This how-to takes you from a blank `prometheus.yml` to a Prometheus instance scraping your .NET service, collecting business-aware metrics, and serving PromQL queries. It assumes Prometheus is running and you have a .NET service you control.

{{< mermaid >}}
flowchart LR
    svc[".NET Service<br/>/metrics endpoint"]
    prom["Prometheus<br/>scrape_configs"]
    rules["Recording Rules<br/>pre-computed series"]
    graf["Grafana<br/>panels + alerts"]
    am["Alertmanager<br/>routing"]

    svc -->|"15s scrape"| prom
    prom --> rules
    prom --> graf
    rules --> graf
    graf --> am

    style prom fill:#1A1A2E,stroke:#3A6FAF,color:#5B8DEF
    style rules fill:#1C2A1C,stroke:#1C7A2E,color:#28CA41
{{< /mermaid >}}

## Step 1: Wire Up the Prometheus Exporter in .NET

Add the required packages:

```bash
dotnet add package OpenTelemetry.Extensions.Hosting
dotnet add package OpenTelemetry.Instrumentation.AspNetCore
dotnet add package OpenTelemetry.Exporter.Prometheus.AspNetCore
```

In `Program.cs`, configure the OTel metrics pipeline with a Prometheus exporter:

```csharp
builder.Services.AddOpenTelemetry()
    .WithMetrics(metrics =>
    {
        metrics
            .AddMeter("MyService")                    // your custom meters
            .AddAspNetCoreInstrumentation()           // HTTP request metrics
            .AddHttpClientInstrumentation()           // outbound HTTP metrics
            .AddRuntimeInstrumentation()              // GC, thread pool, etc.
            .AddPrometheusExporter();                 // /metrics endpoint
    });

var app = builder.Build();

// Expose /metrics — Prometheus will scrape this endpoint
app.MapPrometheusScrapingEndpoint();

app.Run();
```

Verify the endpoint before configuring Prometheus:

```bash
curl http://localhost:5000/metrics
```

You should see `# HELP` and `# TYPE` lines followed by metric values.

## Step 2: Define Your Business Metrics

The instrumentation above gives you HTTP request rates, latencies, and runtime metrics automatically. For business metrics, define your own instruments on a named `Meter`:

```csharp
public class OrderService
{
    private static readonly Meter Meter = new("MyService", "1.0.0");

    // Use double, not decimal — the OTel .NET SDK does not support decimal on Counter
    private static readonly Counter<double> RevenueTotal = Meter.CreateCounter<double>(
        "revenue_total",
        unit: "dollars",
        description: "Total revenue processed");

    private static readonly Counter<long> OrdersTotal = Meter.CreateCounter<long>(
        "orders_total",
        description: "Orders processed, by status and customer tier");

    private static readonly Histogram<double> OrderDuration = Meter.CreateHistogram<double>(
        "order_processing_duration",
        unit: "seconds",
        description: "Time to process an order end-to-end");

    // UpDownCounter for values that go up and down: queue depth, in-flight count
    private static readonly UpDownCounter<long> ActiveOrders = Meter.CreateUpDownCounter<long>(
        "active_orders",
        description: "Orders currently being processed");

    public async Task<OrderResult> ProcessOrderAsync(CreateOrderRequest request)
    {
        var sw = Stopwatch.StartNew();

        ActiveOrders.Add(1, new KeyValuePair<string, object?>("tier", request.CustomerTier));

        try
        {
            var order = await _logic.ProcessAsync(request);
            sw.Stop();

            OrdersTotal.Add(1,
                new KeyValuePair<string, object?>("status", "success"),
                new KeyValuePair<string, object?>("tier", request.CustomerTier),
                new KeyValuePair<string, object?>("channel", request.Channel));

            RevenueTotal.Add((double)request.TotalAmount,
                new KeyValuePair<string, object?>("currency", request.Currency),
                new KeyValuePair<string, object?>("tier", request.CustomerTier));

            OrderDuration.Record(sw.Elapsed.TotalSeconds,
                new KeyValuePair<string, object?>("tier", request.CustomerTier));

            return new OrderResult { OrderId = order.Id, Success = true };
        }
        catch (Exception)
        {
            OrdersTotal.Add(1,
                new KeyValuePair<string, object?>("status", "error"),
                new KeyValuePair<string, object?>("tier", request.CustomerTier));
            throw;
        }
        finally
        {
            ActiveOrders.Add(-1, new KeyValuePair<string, object?>("tier", request.CustomerTier));
        }
    }
}
```

### Observable gauges for metrics that require a query

Some metrics cannot be measured in the hot path — MRR, active subscription counts, aggregated totals. For these, use `CreateObservableGauge`, which registers a callback Prometheus invokes at each scrape:

```csharp
var meter = new Meter("MyService.Business");

// Single value
meter.CreateObservableGauge<double>(
    "monthly_recurring_revenue",
    unit: "dollars",
    description: "Current MRR",
    observeValues: () => new[] { new Measurement<double>(_cache.GetMRR()) });

// Multiple values with labels (one measurement per tier)
meter.CreateObservableGauge<long>(
    "active_subscriptions",
    description: "Active subscriptions by tier",
    observeValues: () =>
        _cache.GetSubscriptionCounts().Select(c =>
            new Measurement<long>(c.Count,
                new KeyValuePair<string, object?>("tier", c.Tier))));
```

The callback runs on Prometheus's scrape thread. Keep it fast — pull from a cache updated by a background job rather than querying the database on each scrape.

### Histogram bucket configuration

Default histogram buckets are generic and often miss the interesting part of your latency distribution. Configure explicit boundaries via `ExplicitBucketHistogramConfiguration`:

```csharp
builder.Services.AddOpenTelemetry()
    .WithMetrics(metrics =>
    {
        metrics
            .AddMeter("MyService")
            .AddView(
                instrumentName: "order_processing_duration",
                new ExplicitBucketHistogramConfiguration
                {
                    // Tuned for sub-second order processing
                    Boundaries = new[] { 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0 }
                })
            .AddPrometheusExporter();
    });
```

If your p99 latency is 300ms and your largest bucket boundary is 500ms, you cannot see how requests distribute between 300ms and 500ms. Instrument first, examine early data to understand the real distribution, then tune.

## Step 3: Configure prometheus.yml

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: "myservice"
    metrics_path: /metrics
    static_configs:
      - targets: ["myservice:5000"]

  # Multiple replicas: list each
  - job_name: "myservice-fleet"
    metrics_path: /metrics
    static_configs:
      - targets:
          - "myservice-1:5000"
          - "myservice-2:5000"
          - "myservice-3:5000"
```

Confirm the scrape is working at `http://localhost:9090/targets`. Your service should show `State: UP` with a `Last Scrape` timestamp.

## Step 4: Write Your First PromQL Queries

**Request rate:**
```promql
rate(http_server_request_duration_count{job="myservice"}[5m])
```

**Error rate (fraction of 5xx responses):**
```promql
rate(http_server_request_duration_count{job="myservice", http_response_status_code=~"5.."}[5m])
/
rate(http_server_request_duration_count{job="myservice"}[5m])
```

**P99 latency:**
```promql
histogram_quantile(0.99,
  rate(http_server_request_duration_bucket{job="myservice"}[5m])
)
```

**Revenue rate (dollars per minute):**
```promql
rate(revenue_total{job="myservice"}[5m]) * 60
```

**Order success rate by tier:**
```promql
sum by (tier) (rate(orders_total{job="myservice", status="success"}[5m]))
/
sum by (tier) (rate(orders_total{job="myservice"}[5m]))
```

## Step 5: Set Up Recording Rules

Recording rules pre-compute expensive queries and store the result as a new time series — making dashboard panel loads and alert evaluations instant lookups rather than full re-computations on every request.

```yaml
# rules/myservice.yml
groups:
  - name: myservice-derived
    interval: 1m
    rules:
      - record: "job:error_rate:rate5m"
        expr: |
          rate(orders_total{status!="success"}[5m])
          / rate(orders_total[5m])

      - record: "job:order_duration_p99_by_tier:rate5m"
        expr: |
          histogram_quantile(0.99,
            rate(order_processing_duration_bucket[5m])
          ) by (tier)

      - record: "job:revenue_per_minute:rate5m"
        expr: rate(revenue_total[5m]) * 60
```

Reference the rules file in `prometheus.yml`:

```yaml
rule_files:
  - "rules/*.yml"
```

After restarting Prometheus, the recording rules appear as directly-queryable metrics:

```promql
job:error_rate:rate5m{job="myservice"}
job:order_duration_p99_by_tier:rate5m{tier="enterprise"}
```

## Storage

```bash
prometheus \
  --storage.tsdb.retention.time=30d \
  --storage.tsdb.retention.size=50GB \
  --config.file=prometheus.yml
```

Set both limits. The size limit catches cardinality bursts that would otherwise fill your disk before the time limit applies.

---

- [How to Create Your First Dashboard](/howtos/create-your-first-dashboard/) — Grafana panels on top of these PromQL queries
- [Set Up SLO Burn Rate Alerts](/howtos/set-up-slo-burn-rate-alerts/) — error budget alerts using the recording rules you just defined
- [Cardinality Management](/guides/cardinality-management/) — what to do when your label set grows unexpectedly

<!-- TODO: Add section on Kubernetes service discovery with pod annotations -->
<!-- TODO: Add section on the Pushgateway for batch job metrics -->
