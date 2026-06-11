---
title: "Log Levels: When to Whisper, Speak, or Shout"
date: 2026-06-07
draft: true
excerpt: "Log levels are the emotional register of your system's voice. The definitive guide to using ERROR, WARN, INFO, DEBUG, and TRACE correctly — with real examples, anti-patterns, and cost impact."
readtime: 10
tags: ["Logs", "Observability", "Best Practices"]
---

# Log Levels: When to Whisper, Speak, or Shout

Log levels exist to let operators filter signal from noise. Without them, every event competes equally for attention — a startup trace lands next to a payment failure, and neither gets the response it deserves. The level is a contract between the code that emits the log and the person or system that reads it.

## **RFC 5424: The Numeric Severity Scale**

RFC 5424 (the IETF syslog standard) defines eight severity levels, numbered 0–7, with 0 being most severe. Most application frameworks map to a subset of these, typically collapsing the top three into FATAL or CRITICAL.

{{< mermaid >}}
graph TD
    A[RFC 5424 Severity Levels] --> B[0 - Emergency]
    A --> C[1 - Alert] 
    A --> D[2 - Critical]
    A --> E[3 - Error]
    A --> F[4 - Warning]
    A --> G[5 - Notice]
    A --> H[6 - Informational]
    A --> I[7 - Debug]
    
    B --> J[System Unusable]
    C --> K[Immediate Action Required]
    D --> L[Critical Conditions]
    E --> M[Error Conditions]
    F --> N[Warning Conditions]
    G --> O[Normal but Significant]
    H --> P[Informational Messages]
    I --> Q[Debug-level Messages]
    
    style A fill:#4ecdc4
    style E fill:#ff6b6b
    style F fill:#ffa726
    style H fill:#66bb6a
{{< /mermaid >}}

| Level | Name | Use Case | Example Scenario |
|-------|------|----------|------------------|
| 0 | Emergency | System unusable | Kernel panic, total system failure |
| 1 | Alert | Immediate action required | Security breach detected |
| 2 | Critical | Critical conditions | Primary database down |
| 3 | Error | Error conditions | Payment processing failed |
| 4 | Warning | Warning conditions | Memory usage high |
| 5 | Notice | Normal but significant | Configuration changed |
| 6 | Informational | Informational messages | User logged in |
| 7 | Debug | Debug-level messages | Variable values during execution |

## **ERROR - The Operation Failed**

ERROR means the operation failed and a human needs to know. It should be rare enough that every occurrence warrants attention. If an operator sees an ERROR and has no clear next step, either the log lacks context or the level is wrong.

Use ERROR when the failure affects a user or degrades a business process — a payment that didn't go through, a database connection that dropped, an external integration that returned an unrecoverable status. Do not use ERROR for expected failures like a user entering a wrong password; those are application flow, not system errors.

**Use ERROR for:**
- System failures that affect users
- Database connection failures  
- Payment processing failures
- Security incidents
- Integration failures with external services

**Perfect ERROR Log Example:**
```json
{
  "timestamp": "2024-03-21T13:45:30Z",
  "level": "ERROR",
  "service": "payment-api",
  "trace_id": "abc123def456",
  "message": "Payment processing failed - gateway timeout after 30 seconds",
  "error": {
    "type": "GatewayTimeoutException",
    "gateway": "stripe",
    "response_time_ms": 30000,
    "retry_count": 3,
    "error_code": "GATEWAY_TIMEOUT"
  },
  "business_impact": {
    "affected_orders": 1,
    "revenue_at_risk": 299.99,
    "customer_tier": "premium"
  },
  "context": {
    "order_id": "ord_12345",
    "customer_id": "cust_789"
  }
}
```

## **WARN - Degraded but Not Broken**

WARN signals that something is wrong but the system is still functioning. The operation succeeded, or recovered, but in a way that may not hold. The distinction from ERROR is operational: an ERROR demands investigation now; a WARN demands investigation before it becomes an ERROR.

Good WARN logs are actionable on a schedule. Memory at 85% of threshold, a retry that eventually succeeded, a deprecated API call that will break in the next version — these belong at WARN. If left unaddressed they become errors; addressed proactively, they never do.

**Use WARN for:**
- Performance degradation
- Deprecated feature usage
- Resource constraints approaching thresholds
- Retry attempts that succeeded
- Configuration mismatches (non-fatal)

**Perfect WARN Log Example:**
```json
{
  "timestamp": "2024-03-21T13:45:30Z",
  "level": "WARN",
  "service": "inventory-service",
  "message": "Memory usage at 85% - approaching configured threshold of 90%",
  "system_health": {
    "memory_used_mb": 6800,
    "memory_total_mb": 8000,
    "threshold_percent": 90,
    "trend": "increasing"
  },
  "alerts": {
    "should_scale": true,
    "estimated_time_to_critical": "15_minutes"
  }
}
```

## **INFO - Significant Events in Normal Operation**

INFO records events that matter for understanding what the system did, without recording every step of how it did it. A completed order, a user login, a configuration reload — these belong at INFO. An operator reading INFO logs should get a coherent picture of system activity without drowning in implementation detail.

The test: would you want this event in a daily summary? If yes, it's INFO. If it appears dozens of times per second under normal load, it's too frequent for INFO unless the volume is genuinely meaningful. High-frequency INFO logging has real cost implications at scale — route it to cold storage or sample it.

**Use INFO for:**
- Successful business operations
- State changes and milestones
- Configuration changes
- Important system lifecycle events
- User actions with business significance

**Perfect INFO Log Example:**
```json
{
  "timestamp": "2024-03-21T13:45:30Z",
  "level": "INFO",
  "service": "order-service",
  "trace_id": "order_trace_456",
  "message": "Order #12345 processed successfully - payment captured, inventory updated, notification sent",
  "order_flow": {
    "payment_captured": true,
    "inventory_reserved": true,
    "customer_notified": true,
    "total_processing_time_ms": 847
  },
  "business_metrics": {
    "order_value": 299.99,
    "customer_tier": "premium",
    "fulfillment_center": "warehouse_west"
  }
}
```

## **DEBUG - Internal State for Development and Incident Investigation**

DEBUG captures the internal state and decision points that explain why the system behaved as it did. It is disabled in production by default because it generates high volume and the overhead adds up in tight loops. Enable it per-service when actively investigating a problem, then disable it again.

A DEBUG log should answer "why did this code take this path?" — variable values, decision branch outcomes, intermediate computation results. If you find yourself reaching for DEBUG to understand normal operation, that's a signal the INFO logs need work.

**Use DEBUG for:**
- Detailed operation flow
- Variable values and decision points
- Performance measurements
- Integration points
- Algorithm decision reasoning

**Perfect DEBUG Log Example:**
```json
{
  "timestamp": "2024-03-21T13:45:30Z",
  "level": "DEBUG",
  "service": "recommendation-engine",
  "trace_id": "rec_trace_789",
  "message": "Processing payment: amount=$99.99, customer_tier=premium, payment_method=credit_card, gateway_response_time=245ms",
  "debug_context": {
    "validation_steps": ["amount_check", "fraud_check", "limits_check"],
    "gateway_selection_reason": "lowest_fees_for_premium",
    "algorithm_version": "v2.3.1",
    "feature_flags": {
      "enhanced_fraud_detection": true,
      "premium_fast_track": true
    }
  }
}
```

## **TRACE - Step-by-Step Execution Detail**

TRACE records method-level execution: entry and exit points, loop iterations, granular timing. It is the most expensive level by volume and belongs only in development or during targeted debugging sessions. Leaving TRACE enabled in production generates enough noise to mask the signal you're trying to find.

**Use TRACE for:**
- Method entry/exit points
- Loop iterations and detailed processing steps
- Variable state changes
- Granular performance timing

**Perfect TRACE Log Example:**
```json
{
  "timestamp": "2024-03-21T13:45:30Z",
  "level": "TRACE", 
  "service": "payment-validator",
  "trace_id": "validation_trace_123",
  "message": "Entering ValidatePayment() -> checking format -> validating checksum -> calling gateway -> result: valid",
  "execution_flow": {
    "method": "ValidatePayment",
    "step": "gateway_validation",
    "duration_microseconds": 1247,
    "memory_allocated_bytes": 1024,
    "cpu_cycles": 45123
  }
}
```

## **Real-World Cost Impact: Harness Case Study**

A common outcome of criticality-based routing:

{{< mermaid >}}
graph TD
    A[Original Log Volume] --> B{Criticality-Based Routing}
    
    B -->|ERROR/CRITICAL| C[Hot Storage: Real-time]
    B -->|WARN| D[Warm Storage: 1hr delay]
    B -->|INFO| E[Cold Storage: Daily batch]
    B -->|DEBUG/TRACE| F[Local Only / Discard]
    
    C --> G[Immediate alerting]
    D --> H[Trend analysis]
    E --> I[Historical reports]
    F --> J[Dev environment only]
    
    style A fill:#ff6b6b
    style C fill:#ff9999
    style D fill:#ffcc99
    style E fill:#99ccff
    style F fill:#cccccc
{{< /mermaid >}}

**Implementation Strategy:**
- **Critical/Error**: Immediate storage for real-time alerting
- **Warning**: 1-hour delayed ingestion for trend analysis
- **Info**: Daily batch processing for historical reports
- **Debug/Trace**: Local environment only, not shipped to central logging

## **Performance Impact**

Verbosity has a cost. The relative processing overhead increases sharply as you move to more verbose levels — debug and trace logging can add substantial overhead in tight loops:

{{< mermaid >}}
graph LR
    A[TRACE] --> B[Highest Overhead]
    C[DEBUG] --> D[High Overhead]
    E[INFO] --> F[Moderate Overhead]
    G[WARN] --> H[Low Overhead]
    I[ERROR] --> J[Minimal Overhead]
    
    style A fill:#ff6b6b
    style C fill:#ff9999
    style E fill:#ffcc99
    style G fill:#99ccff
    style I fill:#66bb6a
{{< /mermaid >}}

## **Anti-Pattern Analysis**

These are the most common logging anti-patterns seen in production codebases:

### **1. Log-and-Throw**
```csharp
// ❌ Don't do this - logs the same error multiple times
try
{
    ProcessPayment(order);
}
catch (PaymentException ex)
{
    _logger.LogError(ex, "Payment failed");  // Logged here
    throw;  // And caught and logged again upstream
}

// ✅ Do this - log once at the appropriate level
try
{
    ProcessPayment(order);
}
catch (PaymentException ex)
{
    _logger.LogError(ex, "Payment failed for order {OrderId}", order.Id);
    return PaymentResult.Failed(ex.Message);
}
```

### **2. Exception Swallowing**
```csharp
// ❌ Silent failures without logging
try
{
    SendNotification(user);
}
catch
{
    // Swallowed - nobody knows this failed
}

// ✅ Log the failure appropriately
try
{
    SendNotification(user);
}
catch (Exception ex)
{
    _logger.LogWarning(ex, "Failed to send notification to user {UserId} - will retry later", user.Id);
}
```

### **3. Flooding Patterns**
```csharp
// ❌ Logging in tight loops without rate limiting
foreach (var item in millionsOfItems)
{
    _logger.LogDebug("Processing item {ItemId}", item.Id);  // Flooding!
}

// ✅ Use sampling or batch logging
var processedCount = 0;
foreach (var item in millionsOfItems)
{
    // Log every 1000th item
    if (++processedCount % 1000 == 0)
    {
        _logger.LogDebug("Processed {Count} items, current: {ItemId}", processedCount, item.Id);
    }
}
```

## **Dynamic Level Management Implementation**

```csharp
public class SmartLogLevelManager
{
    private readonly ILogger<SmartLogLevelManager> _logger;
    private readonly IOptionsMonitor<LoggingOptions> _options;
    private LogLevel _currentLevel = LogLevel.Information;
    
    public async Task<OrderResult> ProcessOrder(Order order)
    {
        // Adapt log level based on system pressure
        AdaptLogLevel();
        
        if (ShouldLog(LogLevel.Trace))
        {
            _logger.LogTrace("Entering ProcessOrder for order {OrderId}", order.Id);
        }
        
        try
        {
            if (ShouldLog(LogLevel.Debug))
            {
                _logger.LogDebug("Validating order {OrderId} with amount {Amount}", 
                    order.Id, order.Amount);
            }
            
            await ValidateOrder(order);
            
            // Always log important business events
            _logger.LogInformation("Order {OrderId} validated successfully, processing payment", 
                order.Id);
            
            var paymentResult = await ProcessPayment(order);
            
            if (!paymentResult.IsSuccess)
            {
                _logger.LogWarning("Payment failed for order {OrderId}, attempt {Attempt}: {Reason}", 
                    order.Id, paymentResult.AttemptCount, paymentResult.FailureReason);
                return OrderResult.PaymentFailed(paymentResult.FailureReason);
            }
            
            _logger.LogInformation("Order {OrderId} completed successfully", order.Id);
            return OrderResult.Success(order.Id);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Critical error processing order {OrderId}", order.Id);
            throw;
        }
        finally
        {
            if (ShouldLog(LogLevel.Trace))
            {
                _logger.LogTrace("Exiting ProcessOrder for order {OrderId}", order.Id);
            }
        }
    }
    
    private void AdaptLogLevel()
    {
        var systemLoad = GetSystemLoad();
        _currentLevel = systemLoad switch
        {
            > 0.9 => LogLevel.Error,      // High load - only errors
            > 0.7 => LogLevel.Warning,    // Medium load - warnings and above
            > 0.5 => LogLevel.Information, // Normal load - info and above
            _ => LogLevel.Debug           // Low load - detailed logging
        };
    }
    
    private bool ShouldLog(LogLevel level) => level >= _currentLevel;
}
```

## **Choosing the Right Level Under Pressure**

When an incident is active and you need more signal, the instinct is to turn everything up to DEBUG or TRACE. Resist it. Verbose logging under load adds CPU and I/O pressure to a system that's already struggling, and the extra volume makes it harder to find the relevant lines — not easier.

Instead, enable DEBUG scoped to the specific service or request path you're investigating. RFC 5424's numeric scale is a useful anchor here: if you're unsure between two levels, pick the one closer to 0. Emitting too little at a given level is better than log flooding.

A well-structured INFO log from a streaming service demonstrates what level-appropriate context looks like:

```json
{
  "level": "INFO",
  "service": "content-delivery",
  "event_type": "stream_quality_adjusted",
  "user_session": "session_abc123",
  "quality_change": {
    "from": "1080p",
    "to": "720p",
    "reason": "bandwidth_constraints"
  },
  "adaptive_streaming": {
    "algorithm_version": "v3.2",
    "buffer_health": "low"
  }
}
```

A practical level-to-impact mapping that reflects how on-call teams actually triage:
- **ERROR**: Anything that directly affects user experience
- **WARN**: Anything that might affect user experience if left unaddressed
- **INFO**: Anything that helps reconstruct what a user experienced
- **DEBUG**: Anything that helps diagnose why it happened

## **Automated Log Level Optimization**

```csharp
public class AutoLogLevelOptimizer
{
    private readonly IMetrics _metrics;
    private readonly Dictionary<string, LogLevelStats> _serviceStats = new();
    
    public void OptimizeLogLevels()
    {
        foreach (var (service, stats) in _serviceStats)
        {
            var recommendation = CalculateOptimalLevel(stats);
            
            _logger.LogInformation("Log level optimization for {Service}", new
            {
                service = service,
                current_level = stats.CurrentLevel,
                recommended_level = recommendation.Level,
                reasoning = recommendation.Reasoning,
                cost_impact = recommendation.EstimatedCostReduction,
                performance_impact = recommendation.EstimatedPerformanceGain
            });
        }
    }
    
    private LogLevelRecommendation CalculateOptimalLevel(LogLevelStats stats)
    {
        // Algorithm considers:
        // - Log volume vs value ratio
        // - Error detection effectiveness  
        // - Performance impact
        // - Storage costs
        // - Team debugging needs
        
        if (stats.DebugLogsPercentage > 80 && stats.DebugUtilization < 5)
        {
            return new LogLevelRecommendation
            {
                Level = LogLevel.Information,
                Reasoning = "High debug volume with low utilization",
                EstimatedCostReduction = 0.65,
                EstimatedPerformanceGain = 0.25
            };
        }
        
        return new LogLevelRecommendation { Level = stats.CurrentLevel };
    }
}
```

## **Quick Reference**

| Level | Trigger | Operator action | Production default |
|-------|---------|-----------------|-------------------|
| ERROR | Operation failed, user impact | Investigate now | Always on |
| WARN | Degraded or at-risk, system still up | Investigate soon | Always on |
| INFO | Significant business event completed | Read during review | Always on |
| DEBUG | Internal state for diagnosis | Enable when investigating | Off |
| TRACE | Method-level execution steps | Enable in dev or targeted sessions | Off |

---

**Next**: [Structured Logging: Making Your Logs Machine-Readable](/guides/structured-logging-machine-readable/)
