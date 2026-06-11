---
title: "Data Masking in Telemetry: The Art of Safe Transformation"
date: 2026-06-07
draft: true
excerpt: "Telemetry data carries the same PII risks as any other data store. Here is how to transform sensitive fields while preserving analytical value — hashing, tokenising, coarsening, and knowing which to use when."
readtime: 9
tags: ["Privacy", "OpenTelemetry", "Security", "Observability", "Collector", "Logs", "GDPR"]
---

This guide covers transformation techniques. For PII risk, compliance obligations, and which fields to target, start with [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/).

## The Data Transformation Pipeline

Masking order matters: each stage assumes the previous one has already run, and skipping a step exposes fields the later stages depend on being clean:

{{< mermaid >}}
graph TD
    A[Raw Telemetry] --> B{Need Masking?}
    B -->|Yes| C[Transform]
    B -->|No| D[Pass Through]
    C --> E[Quality Check]
    E -->|Pass| F[Export]
    E -->|Fail| G[Adjust]

    C --> C1[Hash]
    C --> C2[Tokenize]
    C --> C3[Truncate]
    C --> C4[Aggregate]
    
    style A fill:#1C1C1C,stroke:#3A6FAF,color:#5B8DEF
    style F fill:#1C2A1C,stroke:#1C7A2E,color:#28CA41
    style G fill:#2A0A0A,stroke:#CC4444,color:#FF6060
{{< /mermaid >}}

1. **Raw Telemetry**: The raw, sensitive data as it's initially collected. It contains PII that, if exported unchanged, lands in your trace backend indexed and searchable — a GDPR audit waiting to happen.

2. **Masking Decision**: Identifies which fields require redaction and which can pass through. System metrics and anonymous usage statistics contain no personal identifiers and pass through unchanged.

3. **Transformation**: This is where we actually apply various masking techniques to the data based on its type and sensitivity:
   - **Hashing**: Hashing transforms sensitive data, like user IDs or email addresses, into a fixed-length, irreversible representation. The original data is unrecoverable, but the hash allows for analytics and correlation.
   - **Tokenization**: Tokenization replaces sensitive data with a random, unique token. A secure lookup table maps tokens back to original values — only accessible to authorised systems that need re-identification.

## Transformation Examples

### User Activity Telemetry

Before transformation:

```json
{
  "event": "user_login",
  "timestamp": "2024-02-15T10:30:00Z",
  "attributes": {
    "user.email": "sarah.jones@company.com",
    "user.ip": "192.168.1.100",
    "device.id": "d789-xyz-456",
    "location": "San Francisco, CA",
    "browser": "Chrome 120.0.0",
    "login_success": true
  }
}
```

After transformation:

```json
{
  "event": "user_login",
  "timestamp": "2024-02-15T10:30:00Z",
  "attributes": {
    "user.id": "<hash_value>",
    "user.ip_prefix": "192.168.0.0/16",
    "device.type": "web_browser",
    "location.region": "US-WEST",
    "browser.family": "Chrome",
    "login_success": true
  }
}
```

## Transformation Patterns


{{< mermaid >}}
graph LR
    A@{ shape: das, label: "Data input"} --> B(Identifiers)
    A --> C(Locations)
    A --> D(Metrics)
    A --> E(Timestamps)

    B --> B1[Hash]
    C --> C1[Generalize]
    D --> D1[Round]
    E --> E1[Bucket]
    
    style A fill:#1C1C1C,stroke:#3A6FAF,color:#5B8DEF
    classDef second fill:#161616,stroke:#3A6FAF,color:#5B8DEF
    classDef third fill:#1C1C1C,stroke:#2A2A2A,color:#A8A8A0

    class B,C,D,E second;
    class B1,C1,D1,E1 third;
{{< /mermaid >}}

## Quality Control Gates

Each gate validates a structural property of the transformed data before it reaches the exporter:

{{< mermaid >}}

stateDiagram-v2
    direction LR

    classDef pass fill:#1C2A1C,stroke:#1C7A2E,color:#28CA41
    classDef fail fill:#2A0A0A,stroke:#CC4444,color:#FF6060
   data_quality: Quality Gates
   State2: Format Check
   State3: Pattern Check
   State4: Value Check
   State21: Valid Structure
   State31: Expected Pattern
   State41: Value Range

    state fork_state <<fork>>
      [*] --> data_quality
      data_quality --> fork_state
      fork_state --> State2
      fork_state --> State3
      fork_state --> State4
      State3 --> State31
      State2 --> State21
      State4 --> State41
  
      state join_state <<join>>
      State21 --> join_state
      State31 --> join_state
      State41 --> join_state

      state if_state <<choice>>
        join_state --> if_state
        if_state --> Pass: if valid data
        if_state --> Fail : if invalid data

    Fail:::fail --> [*]
    Pass:::pass --> [*]

{{< /mermaid >}}

## Transformation Matrix

| Data Type  | Example              | Transformation | Rationale         | Result Example       |
| ---------- | -------------------- | -------------- | ----------------- | -------------------- |
| Email      | <user@company.com>     | Remove         | PII — no safe hash | *(deleted)*         |
| IP Address | 192.168.1.100        | Subnet Mask    | Network analysis  | 192.168.0.0/16       |
| Location   | San Francisco, CA    | Region Code    | Geographic trends | US-WEST              |
| Timestamp  | 2024-02-15T10:30:00Z | Time Bucket    | Pattern analysis  | 2024-02-15T10:00:00Z |

## Data Utility Preservation

The transformation must preserve the relationships between fields — statistical distributions, cross-span correlations, and time-series patterns — or the data loses its diagnostic value:

{{< mermaid >}}

graph TB
    A[Data Value] --> B[Statistical]
    A --> C[Relational]
    A --> D[Temporal]

    B --> B1[Distributions]
    B --> B2[Aggregates]
    
    C --> C1[Dependencies]
    C --> C2[Hierarchies]
    
    D --> D1[Sequences]
    D --> D2[Patterns]
    
{{< /mermaid >}}

## Common Pitfalls and Solutions

These are the two failures that break pipelines in practice:

1. **Inconsistent Masking**

   ```json
   // Bad: Same value masked differently
   {
     "user_id": "hash1",
     "referenced_user": "hash2"  // Same user, different hash!
   }
   
   // Good: Consistent masking
   {
     "user_id": "hash1",
     "referenced_user": "hash1"  // Same user, same hash
   }
   ```

2. **Over-Masking**

   ```json
   // Bad: Losing analytical value
   {
     "region": "****",
     "response_time_ms": "****"  // Don't mask metrics!
   }
   
   // Good: Preserve useful data
   {
     "region": "US-WEST",
     "response_time_ms": 123
   }
   ```

{{< insight bookmark >}}
A well-designed process for data masking transforms raw, sensitive data while maintaining its analytical value. The key is choosing the right transformation for each data type and applying it consistently throughout your telemetry pipeline.

{{< /insight >}}

## Application-Layer Masking in .NET

The OTel Collector pipeline removes PII before it reaches your backend — but some scenarios require masking earlier, at the application layer: compliance requirements may mandate that certain data never leave the process, on-premise deployments may not have a Collector in the data path, or the SDK's own structured logging needs protection before it reaches the exporter.

### Detecting PII at the Source

A regex-based detector handles common structured patterns — credit card numbers, SSNs, email addresses, phone numbers, and IP addresses:

```csharp
public class PIIDetector
{
    private readonly Dictionary<string, Regex> _patterns = new()
    {
        ["credit_card"] = new Regex(@"\b(?:\d{4}[-\s]?){3}\d{4}\b",
            RegexOptions.Compiled),
        ["ssn"]         = new Regex(@"\b\d{3}-?\d{2}-?\d{4}\b",
            RegexOptions.Compiled),
        ["email"]       = new Regex(
            @"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
            RegexOptions.Compiled),
        ["phone"]       = new Regex(
            @"\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b",
            RegexOptions.Compiled),
        ["ip_address"]  = new Regex(@"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b",
            RegexOptions.Compiled),
    };
    
    public PIIDetectionResult AnalyzeText(string text)
    {
        var findings = new List<PIIFinding>();
        foreach (var (category, pattern) in _patterns)
        {
            foreach (Match match in pattern.Matches(text))
            {
                findings.Add(new PIIFinding
                {
                    Category = category,
                    Value    = match.Value,
                    Position = match.Index,
                });
            }
        }
        return new PIIDetectionResult { HasPII = findings.Count > 0, Findings = findings };
    }
    
    public string ScrubText(string text)
    {
        var result = text;
        foreach (var (category, pattern) in _patterns)
            result = pattern.Replace(result, $"[{category.ToUpperInvariant()}_REDACTED]");
        return result;
    }
}
```

`RegexOptions.Compiled` is important here — the detector runs on every log write, so JIT compilation happens once at startup rather than per-call. Note that regex detection catches structured patterns. Free-text descriptions ("order for Jane Smith at 123 Main St") won't match — regex is a necessary baseline, not a complete solution.

### Redaction Strategies

Once you have identified a field that needs masking, the treatment depends on whether downstream correlation is required. For business identifiers (order IDs, customer IDs), consistent hashing lets you correlate across spans without re-identifying: all records for the same order share the same hash.

```csharp
public static class RedactionStrategies
{
    public static string MaskCreditCard(string cardNumber)
    {
        if (string.IsNullOrEmpty(cardNumber) || cardNumber.Length < 8)
            return "[REDACTED]";
        var digits = cardNumber.Replace("-", "").Replace(" ", "");
        return $"{digits[..4]}****{digits[^4..]}";
    }
    
    public static string MaskEmail(string email)
    {
        if (string.IsNullOrEmpty(email) || !email.Contains('@'))
            return "[REDACTED]";
        var parts = email.Split('@');
        return $"{parts[0][0]}***@{parts[1]}";
    }
    
    public static string MaskPhone(string phone)
    {
        var digits = new string(phone.Where(char.IsDigit).ToArray());
        if (digits.Length < 7) return "[REDACTED]";
        return $"({digits[..3]}) ***-**{digits[^2..]}";
    }
    
    /// <summary>
    /// Deterministic hash for correlation without re-identification. Truncated to
    /// 12 characters — sufficient for uniqueness within a service, compact enough
    /// to keep attribute payloads small.
    /// </summary>
    public static string HashIdentifier(string identifier, string salt)
    {
        using var sha256 = SHA256.Create();
        var bytes = sha256.ComputeHash(Encoding.UTF8.GetBytes(identifier + salt));
        return Convert.ToBase64String(bytes)[..12];
    }
}
```

### Object-Level Redaction

Redacting individual string fields by regex works for message text, but log contexts are typed objects. A switch-based redactor applies each domain type's sensitivity profile — preserving business context while removing personal identifiers:

```csharp
public class SmartRedactor
{
    private readonly RedactionPolicy _policy;
    
    public SmartRedactor(RedactionPolicy policy) => _policy = policy;
    
    public object RedactLogObject(object logData) => logData switch
    {
        UserContext user => new
        {
            user_id          = _policy.HashPersonalIds
                ? RedactionStrategies.HashIdentifier(user.Id, _policy.Salt)
                : "[USER_ID_REDACTED]",
            user_tier        = user.Tier,                    // Keep: business context
            user_region      = user.Region?.Length >= 2      // State/country prefix only
                ? user.Region[..2] : user.Region,
            is_authenticated = user.IsAuthenticated,
            session_age_minutes = (DateTime.UtcNow - user.SessionStart).TotalMinutes,
        },
        
        PaymentInfo payment => new
        {
            payment_id       = _policy.HashPersonalIds
                ? RedactionStrategies.HashIdentifier(payment.Id, _policy.Salt)
                : "[PAYMENT_ID_REDACTED]",
            amount           = payment.Amount,               // Keep: business metric
            currency         = payment.Currency,
            payment_method   = payment.Method,
            card_type        = payment.CardType,
            card_last_four   = payment.CardNumber?.Length >= 4
                ? payment.CardNumber[^4..] : null,
            gateway_provider = payment.GatewayProvider,
            success          = payment.Success,
        },
        
        AddressInfo address => new
        {
            country              = address.Country,
            state_province       = address.StateProvince,
            postal_code_prefix   = address.PostalCode?.Length >= 3
                ? address.PostalCode[..3] : address.PostalCode,
            address_type         = address.Type,
        },
        
        _ => logData
    };
}
```

### Privacy-Safe Logger Wrapper

Wire the redactor into an `ILogger` wrapper that applies redaction before structured log records reach the provider:

```csharp
public class PrivacySafeLogger
{
    private readonly ILogger _logger;
    private readonly PIIDetector _detector;
    private readonly SmartRedactor _redactor;
    
    public PrivacySafeLogger(ILogger logger, PIIDetector detector, SmartRedactor redactor)
    {
        _logger   = logger;
        _detector = detector;
        _redactor = redactor;
    }
    
    public void LogUserAction<T>(string action, T context)
    {
        var safeContext = _redactor.RedactLogObject(context!);
        _logger.LogInformation(
            "User action {Action} completed {@Context}", action, safeContext);
    }
    
    public void LogError(Exception ex, string message, object? context = null)
    {
        var safeContext = context != null ? _redactor.RedactLogObject(context) : null;
        var safeMessage = _detector.ScrubText(ex.Message);
        _logger.LogError(ex, "{Message} {@Context}", safeMessage, safeContext);
    }
}
```

### Environment-Driven Policy

Redaction behaviour changes by environment — production requires aggressive masking under GDPR and PCI DSS, development can be more permissive for debugging:

```csharp
public class RedactionPolicy
{
    public string   Version               { get; set; } = "1.0";
    public string[] ApplicableFrameworks  { get; set; } = [];
    public bool     HashPersonalIds       { get; set; } = true;
    public string   Salt                  { get; set; } = string.Empty;
    public RedactionLevel Level           { get; set; } = RedactionLevel.Standard;
    
    public static RedactionPolicy ForEnvironment(string environment) =>
        environment.ToLowerInvariant() switch
        {
            "production" => new RedactionPolicy
            {
                ApplicableFrameworks = ["GDPR", "CCPA", "PCI_DSS"],
                HashPersonalIds = true,
                Level = RedactionLevel.Aggressive,
            },
            "staging" => new RedactionPolicy
            {
                ApplicableFrameworks = ["GDPR", "CCPA"],
                HashPersonalIds = true,
                Level = RedactionLevel.Standard,
            },
            "development" => new RedactionPolicy
            {
                ApplicableFrameworks = [],
                HashPersonalIds = false,
                Level = RedactionLevel.Minimal,
            },
            _ => new RedactionPolicy()
        };
}

public enum RedactionLevel { None, Minimal, Standard, Aggressive }
```

### OTel Resource Attributes

Resource attributes identify the process producing telemetry. Some — host name, process ID — are fine in development but represent unnecessary surface area in production:

```csharp
public static class PrivacyAwareResourceBuilder
{
    public static ResourceBuilder Create(IConfiguration config, RedactionPolicy policy)
    {
        var builder = ResourceBuilder.CreateDefault()
            .AddService(
                serviceName:    config["ServiceName"]!,
                serviceVersion: config["ServiceVersion"])
            .AddAttributes(new Dictionary<string, object>
            {
                ["deployment.environment"]  = config["Environment"]!,
                ["deployment.region"]       = config["Region"]!,
                ["business.domain"]         = config["BusinessDomain"]!,
                ["privacy.policy_version"]  = policy.Version,
                ["privacy.frameworks"]      = string.Join(",", policy.ApplicableFrameworks),
                ["privacy.redaction_level"] = policy.Level.ToString(),
            });
        
        if (config["Environment"] != "production")
        {
            builder.AddAttributes(new Dictionary<string, object>
            {
                ["host.name"]   = Environment.MachineName,
                ["process.pid"] = Environment.ProcessId,
            });
        }
        
        return builder;
    }
}
```

### Compliance Audit Logging

GDPR and CCPA require audit trails of PII access — who accessed what, when, and under which legal basis. These audit records are distinct from operational logs and must be generated even when PII is stripped from the operational stream:

```csharp
public class PIIAuditLogger
{
    private readonly ILogger<PIIAuditLogger> _logger;
    
    public PIIAuditLogger(ILogger<PIIAuditLogger> logger) => _logger = logger;
    
    public void LogPIIAccess(PIIAccessEvent e)
    {
        _logger.LogInformation(
            "PII access {EventType} by {Role} for {DataCategories}",
            "pii_access", e.UserRole, string.Join(",", e.DataCategories));
        
        // Structured payload carries the compliance detail
        _logger.LogInformation("PII access detail {@AccessDetail}", new
        {
            access_time              = DateTimeOffset.UtcNow,
            accessing_user           = e.UserId,              // Already hashed before logging
            user_role                = e.UserRole,
            data_subject             = e.DataSubjectId,       // Pre-hashed
            data_categories          = e.DataCategories,
            legal_basis              = e.LegalBasis,
            gdpr_lawful_basis        = e.GDPRLawfulBasis,
            data_minimization_applied = true,
        });
    }
    
    public void LogPIIRedaction(PIIRedactionEvent e)
    {
        _logger.LogInformation(
            "PII redaction applied to log {LogId}: {Categories}",
            e.LogId, string.Join(", ", e.DetectedCategories));
    }
}
```

Keep audit logs in a separate sink with longer retention. Operational logs are deleted frequently; audit logs must be retained to demonstrate compliance.

### Testing PII Protection

Verify both that PII is removed and that business context survives:

```csharp
[Test]
public void PIIDetector_CreditCard_MatchesVariousFormats()
{
    var detector = new PIIDetector();
    
    Assert.That(detector.AnalyzeText("card 4111-1111-1111-1111").HasPII, Is.True);
    Assert.That(detector.AnalyzeText("card 4111111111111111").HasPII, Is.True);
    Assert.That(detector.ScrubText("card 4111-1111-1111-1111"),
        Does.Not.Contain("4111-1111-1111-1111"));
}

[Test]
public void SmartRedactor_UserContext_PreservesBusinessFields()
{
    var policy  = RedactionPolicy.ForEnvironment("production");
    var redactor = new SmartRedactor(policy);
    var user = new UserContext
    {
        Id = "user123", Email = "test@example.com",
        Tier = "premium", Region = "US-West",
        SessionStart = DateTime.UtcNow.AddMinutes(-30),
    };
    
    dynamic result = redactor.RedactLogObject(user);
    
    Assert.That((string)result.user_tier,   Is.EqualTo("premium"));
    Assert.That((string)result.user_region, Is.EqualTo("US"));
    Assert.That((string)result.user_id,     Does.Not.Contain("user123"));
}
```

{{< insight >}}
**Collector vs application layer.** Prefer the [OTel Collector `transform` processor](/guides/pii-in-telemetry/) for PII stripping — it applies uniformly across all services regardless of language or SDK version. Application-layer masking (the patterns in this section) is the right complement when: data must never leave the process boundary, you are operating without a Collector in the export path, or compliance audit trails must be generated within the service itself. The two approaches work together; they are not alternatives.
{{< /insight >}}

{{< obs-mascot class="cleric" quip="I have anointed your logs with the holy redaction. The secrets are sealed, the PII is at rest. Go forth and ship." >}}
