---
title: "Scrub PII from Application Logs in .NET"
date: 2026-06-11
draft: true
excerpt: "Defense-in-depth for PII in logs: detect and mask sensitive values in .NET application code before they reach the OTel SDK, using compiled regex detection, smart redaction, and data minimisation patterns."
readtime: 8
tags: ["GDPR", "Privacy", "Security", "Logs", "Compliance", "OpenTelemetry", "How-to"]
---

The primary control for PII in telemetry is the OTel Collector — see [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/) for the Collector pipeline that strips PII from spans and logs uniformly across all services. This how-to covers the application-level layer: detecting and masking PII in .NET before it reaches the OTel SDK.

Application-level scrubbing handles two categories the Collector cannot easily catch: PII embedded in log message strings (not structured attributes), and PII in exception messages that propagate through the stack. Neither belongs in telemetry. Neither is easy to strip with OTTL transforms after the fact.

The sections below are a reference set of independent patterns, not a strict step-by-step sequence — pick the ones that match your PII categories and skip the rest.

{{< obs-telemetry-controls-map here="app" >}}

## PII Categories in Application Logs

The most common sources in a typical .NET service:

| Category | Examples | GDPR sensitivity | Default action |
|---|---|---|---|
| Credit card numbers | `4111-1111-1111-1111` | Critical | Mask to first 4 + last 4 |
| Social Security Numbers | `123-45-6789` | Critical | Remove entirely |
| Email addresses | `user@example.com` | High | Mask or remove |
| Phone numbers | `(415) 555-1234` | High | Mask |
| IP addresses | `192.168.1.100` | High (GDPR Article 4) | Remove |
| Business identifiers | Order IDs, transaction IDs | Medium | Hash (correlatable) |

IP addresses are personal data under GDPR: they identify a natural person's device and, combined with timestamps and other attributes, can identify the person. They must not appear in log records or span attributes.

## Quasi-Identifier Risk

Direct identifiers — email addresses, SSNs, card numbers — are straightforward to find and remove. Quasi-identifiers are harder: fields that are individually innocuous but identifying when logged together.

The combination `{ zip_code, birth_date, gender }` is a documented example: three low-risk fields together can uniquely identify a large fraction of the population. Risk compounds non-linearly with each additional attribute.

`QuasiIdentifierRiskAnalyzer` helps quantify this before deciding what to log:

```csharp
/// <summary>
/// Quantifies re-identification risk from quasi-identifier combinations.
/// Risk scores are illustrative defaults — calibrate to your data distribution
/// and jurisdiction before using this for compliance decisions.
/// </summary>
public class QuasiIdentifierRiskAnalyzer
{
    private readonly Dictionary<string, double> _baseRiskScores = new()
    {
        ["zip_code"]        = 0.35,
        ["birth_date"]      = 0.40,
        ["gender"]          = 0.15,
        ["job_title"]       = 0.25,
        ["income_range"]    = 0.30,
        ["education_level"] = 0.20,
        ["marital_status"]  = 0.18
    };

    /// <summary>Returns true when the combination crosses the 0.6 risk threshold.</summary>
    public bool ShouldProtectCombination(IEnumerable<string> fieldNames)
        => CalculateCombinedRisk(fieldNames.ToList()) > 0.6;

    public double CalculateCombinedRisk(List<string> quasiIds)
    {
        var present = quasiIds
            .Where(_baseRiskScores.ContainsKey)
            .ToList();

        if (present.Count == 0) return 0;
        if (present.Count == 1) return _baseRiskScores[present[0]];

        // Risk compounds non-linearly: three quasi-IDs together are
        // far more identifying than the sum of their individual scores
        var baseRisk         = present.Sum(id => _baseRiskScores[id]);
        var compoundingFactor = Math.Pow(1.3, present.Count - 1);
        return Math.Min(baseRisk * compoundingFactor, 1.0);
    }
}
```

Use `ShouldProtectCombination` before writing a log field combination:

```csharp
var analyzer = new QuasiIdentifierRiskAnalyzer();

// { zip_code, birth_date, gender } → risk ≈ 1.0 (three-field compounding)
if (analyzer.ShouldProtectCombination(logFields.Keys))
{
    // Options: remove quasi-identifiers, generalise (postal prefix only,
    // age range instead of birth date), or route to restricted-access storage
}
```

Run every combination through it once and the pattern practically draws itself:

{{< obs-quasi-id-risk >}}

Generalisation strategy: replace specific values with ranges or prefixes — `"94107"` → `"94"` (postal district), `"1985-03-22"` → `"1980s"`, `"male"` → omit or use only for aggregate statistics. This preserves diagnostic signal while raising the bar for re-identification.

## Detection

`PIIDetector` scans text for known PII patterns using compiled regex. Compiled regexes are safe for concurrent use across threads.

Before you write one, it's worth knowing what a bad pattern costs. A PII detector runs against every log line in production, and that's about the worst place you could pick to meet a pathological input:

{{< obs-regex-shame >}}

Two defences, both cheap. Bound your quantifiers instead of trusting greedy matching, and give `Regex` construction a `matchTimeout` so a pathological input takes down one log line, not your whole thread pool.

```csharp
public class PIIDetector
{
    // RegexOptions.Compiled: compiled to IL at construction time, thread-safe
    private readonly Dictionary<string, Regex> _patterns = new()
    {
        ["credit_card"] = new Regex(
            @"\b(?:\d{4}[-\s]?){3}\d{4}\b",
            RegexOptions.Compiled),

        ["ssn"] = new Regex(
            @"\b\d{3}-?\d{2}-?\d{4}\b",
            RegexOptions.Compiled),

        // Note: [A-Za-z] not [A-Z|a-z] — the | is a literal character in a character class
        ["email"] = new Regex(
            @"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
            RegexOptions.Compiled),

        ["phone"] = new Regex(
            @"\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b",
            RegexOptions.Compiled),

        // IP addresses are PII under GDPR
        ["ip_address"] = new Regex(
            @"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b",
            RegexOptions.Compiled),
    };

    public PIIDetectionResult Analyze(string text)
    {
        var findings = new List<PIIFinding>();
        foreach (var (category, pattern) in _patterns)
        {
            foreach (Match match in pattern.Matches(text))
            {
                findings.Add(new PIIFinding(category, match.Index, match.Length));
            }
        }
        return new PIIDetectionResult(findings.Count > 0, findings);
    }

    public string ScrubText(string text)
    {
        foreach (var (category, pattern) in _patterns)
        {
            text = pattern.Replace(text, $"[REDACTED:{category.ToUpperInvariant()}]");
        }
        return text;
    }
}

public record PIIFinding(string Category, int Position, int Length);
public record PIIDetectionResult(bool HasPII, IReadOnlyList<PIIFinding> Findings);
```

## Masking Strategies

Static helpers for the most common masking operations:

```csharp
public static class RedactionStrategies
{
    public static string MaskCreditCard(string cardNumber)
    {
        if (string.IsNullOrEmpty(cardNumber) || cardNumber.Length < 8)
            return "[REDACTED:CARD]";
        var digits = cardNumber.Replace("-", "").Replace(" ", "");
        return $"{digits[..4]}****{digits[^4..]}";
    }

    /// <summary>
    /// Masks the local part while preserving the domain for support/debugging.
    /// For high-risk scenarios (healthcare, finance) consider removing entirely.
    /// </summary>
    public static string MaskEmail(string email)
    {
        if (string.IsNullOrEmpty(email) || !email.Contains('@'))
            return "[REDACTED:EMAIL]";
        var parts = email.Split('@');
        return $"{parts[0][0]}***@{parts[1]}";
    }

    public static string MaskPhone(string phone)
    {
        var digits = new string(phone.Where(char.IsDigit).ToArray());
        if (digits.Length < 7)
            return "[REDACTED:PHONE]";
        return $"({digits[..3]}) ***-**{digits[^2..]}";
    }

    /// <summary>
    /// Produces a correlatable pseudonym for business identifiers (order IDs, transaction IDs).
    /// For personal identifiers (email, user identity), use HMAC-SHA256 with a rotating secret
    /// key — see the guidance in /guides/pii-in-telemetry/.
    /// </summary>
    public static string HashIdentifier(string identifier, string salt)
    {
        var hashBytes = SHA256.HashData(Encoding.UTF8.GetBytes(identifier + salt));
        return Convert.ToBase64String(hashBytes)[..12];
    }
}
```

`SHA256.HashData` (static, .NET 5+) avoids the `IDisposable` pattern of `SHA256.Create()`.

The default `MaskEmail` uses minimal masking (preserves domain for support debugging). For stricter contexts, choose the level explicitly:

```csharp
public enum EmailMaskingLevel
{
    Minimal,    // j***@example.com — preserves domain and first character
    Standard,   // ***@example.com — preserves domain only
    DomainOnly, // [USER]@example.com — no user-part information
    Complete    // [REDACTED:EMAIL]
}

// Overload — the parameterless MaskEmail() corresponds to EmailMaskingLevel.Minimal
public static string MaskEmail(string email, EmailMaskingLevel level)
{
    if (string.IsNullOrEmpty(email) || !email.Contains('@'))
        return "[REDACTED:EMAIL]";

    var parts = email.Split('@');
    return level switch
    {
        EmailMaskingLevel.Minimal    => $"{parts[0][0]}***@{parts[1]}",
        EmailMaskingLevel.Standard   => $"***@{parts[1]}",
        EmailMaskingLevel.DomainOnly => $"[USER]@{parts[1]}",
        EmailMaskingLevel.Complete   => "[REDACTED:EMAIL]",
        _                            => $"{parts[0][0]}***@{parts[1]}"
    };
}
```

Healthcare and financial services contexts typically require `DomainOnly` or `Complete`. If your organisation processes sensitive categories of personal data (GDPR Article 9), prefer `Complete` and rely on tokenised identifiers in audit logs rather than email values for correlation.

## Smart Redaction: Preserving Business Context

Removing all user-related data makes logs useless for debugging. Smart redaction keeps the business context (tier, region, order size) while eliminating personal identifiers:

```csharp
public class SmartRedactor
{
    private readonly RedactionPolicy _policy;

    public object Redact(object logData) => logData switch
    {
        UserContext user => new
        {
            // Hash the ID for correlation without exposing the value
            user_id          = _policy.HashIds
                ? RedactionStrategies.HashIdentifier(user.Id, _policy.Salt)
                : "[USER_ID_REDACTED]",
            user_tier        = user.Tier,                  // Business context, not PII
            user_region      = user.Region?[..2],          // Country code only
            session_age_min  = (DateTime.UtcNow - user.SessionStart).TotalMinutes,
            is_authenticated = user.IsAuthenticated,
            // Never log: user.Email, user.Phone, user.Address, user.IPAddress
        },

        PaymentContext payment => new
        {
            payment_id       = _policy.HashIds
                ? RedactionStrategies.HashIdentifier(payment.Id, _policy.Salt)
                : "[PAYMENT_ID_REDACTED]",
            amount           = payment.Amount,            // Business metric, not PII
            currency         = payment.Currency,
            payment_method   = payment.Method,            // "card", "paypal", etc.
            card_type        = payment.CardType,          // "visa", "mastercard", etc.
            // Last 4 digits are safe for support correlation
            card_last_four   = payment.CardNumberLastFour,
            gateway          = payment.GatewayProvider,
            success          = payment.Success,
            // Never log: full card number, CVV, billing address, cardholder name
        },

        AddressContext address => new
        {
            country          = address.Country,
            state_province   = address.StateProvince,
            postal_prefix    = address.PostalCode?[..3],  // Rough geographic area
            address_type     = address.Type,              // "residential", "business"
            // Never log: street, city, full postal code — these are direct identifiers
        },

        _ => logData
    };
}
```

{{< insight bookmark >}}
`payment.CardNumberLastFour` should be a dedicated field on your model, not derived from a full card number at log time. If you have the full card number in memory long enough to call `[^4..]`, your application is holding PII longer than necessary. PCI DSS requires minimising where full PANs exist.
{{< /insight >}}

## Policy Configuration

Make the redaction level configurable per environment:

```csharp
public class RedactionPolicy
{
    public string   Version             { get; init; } = "1.0";
    public string[] ComplianceFrameworks { get; init; } = [];
    public bool     HashIds             { get; init; } = true;
    public string   Salt                { get; init; } = string.Empty;
    public RedactionLevel Level         { get; init; } = RedactionLevel.Standard;

    public static RedactionPolicy ForEnvironment(string environment) =>
        environment.ToLowerInvariant() switch
        {
            "production" => new RedactionPolicy
            {
                ComplianceFrameworks = ["GDPR", "CCPA", "PCI_DSS"],
                HashIds  = true,
                Level    = RedactionLevel.Aggressive
            },
            "staging" => new RedactionPolicy
            {
                ComplianceFrameworks = ["GDPR", "CCPA"],
                HashIds  = true,
                Level    = RedactionLevel.Standard
            },
            _ => new RedactionPolicy   // development
            {
                ComplianceFrameworks = [],
                HashIds  = false,
                Level    = RedactionLevel.Minimal
            }
        };
}

public enum RedactionLevel
{
    Minimal,     // Basic regex patterns only — development
    Standard,    // Common PII patterns — staging
    Aggressive   // Comprehensive detection + conservative redaction — production
}
```

## Privacy-Safe Logging

Wrap `ILogger<T>` to apply redaction at the call site before values reach the structured log:

```csharp
public class PrivacySafeLogger<T>
{
    private readonly ILogger<T> _logger;
    private readonly SmartRedactor _redactor;

    public void LogUserAction(string action, object context)
    {
        var safeContext = _redactor.Redact(context);
        _logger.LogInformation(
            "User action {Action} completed for {UserTier} in {UserRegion}",
            action,
            safeContext.GetType().GetProperty("user_tier")?.GetValue(safeContext),
            safeContext.GetType().GetProperty("user_region")?.GetValue(safeContext));
    }

    public void LogError(Exception ex, string operation, object? context = null)
    {
        var safeContext = context is not null ? _redactor.Redact(context) : null;

        // Do NOT reconstruct the exception — pass it directly so the logger captures
        // the original stack trace. Keep PII out of the message template parameters.
        _logger.LogError(
            ex,
            "Operation {Operation} failed with {ErrorType}",
            operation,
            ex.GetType().Name);

        // If the exception message itself may contain PII (e.g., from a third-party
        // library that includes user input), log it as a separate scrubbed field
        // rather than re-creating the exception.
        if (safeContext is not null)
        {
            _logger.LogDebug("Error context: {@SafeContext}", safeContext);
        }
    }
}
```

**Do not** reconstruct `Exception` objects to scrub their messages:
```csharp
// ❌ Discards exception type, corrupts stack trace formatting
return new Exception($"{scrubbedMessage}\n{ex.StackTrace}");

// ✅ Pass the original exception; keep PII out of structured fields separately
_logger.LogError(ex, "Operation {Operation} failed", operation);
```

## Data Minimisation

The most effective PII protection is not collecting PII in the first place. Log the minimum data that serves the diagnostic purpose:

```csharp
public class DataMinimisationLogger
{
    private readonly ILogger _logger;

    public void LogBusinessEvent(string eventType, object rawContext)
    {
        var minimised = MinimiseForEvent(eventType, rawContext);
        _logger.LogInformation(
            "Business event {EventType}",
            eventType);
        // Log the minimised context as a structured object
        _logger.LogDebug("Event context {@EventContext}", minimised);
    }

    private static object MinimiseForEvent(string eventType, object raw) =>
        eventType switch
        {
            "user_login" => new
            {
                login_method    = ExtractLoginMethod(raw),   // "password", "oauth", "sso"
                success         = ExtractSuccess(raw),
                geographic_market = ExtractMarket(raw),      // "EU", "US", "APAC"
                device_category = ExtractDeviceCategory(raw), // "mobile", "desktop"
                // Not logged: username, email, IP address, user agent
            },
            "purchase_completed" => new
            {
                order_value_range    = ExtractValueRange(raw),   // "0-50", "50-200", "200+"
                product_categories   = ExtractCategories(raw),
                payment_method_type  = ExtractPaymentType(raw),  // "card", "wallet"
                customer_tier        = ExtractCustomerTier(raw),
                // Not logged: order ID (hash it), customer name, shipping address
            },
            _ => new { event_type = eventType }
        };
}
```

## Audit Logging

GDPR and CCPA require audit trails for personal data access. Log the access event, not the data itself:

```csharp
public class PIIAccessAuditLogger
{
    private readonly ILogger<PIIAccessAuditLogger> _audit;

    public void RecordAccess(string requestId, string accessorRole,
        string dataSubjectToken, string[] dataCategories, string legalBasis)
    {
        _audit.LogInformation(
            "PII access: request={RequestId} role={AccessorRole} " +
            "subject={DataSubjectToken} categories={DataCategories} basis={LegalBasis}",
            requestId,
            accessorRole,
            dataSubjectToken,        // Hashed/tokenised, not raw identifier
            string.Join(",", dataCategories),
            legalBasis);             // "legitimate_interest", "consent", "contract"
    }

    public void RecordDeletion(string requestId, string dataSubjectToken,
        int logsAffected, bool succeeded)
    {
        _audit.LogInformation(
            "PII deletion: request={RequestId} subject={DataSubjectToken} " +
            "records={LogsAffected} result={Result}",
            requestId,
            dataSubjectToken,
            logsAffected,
            succeeded ? "fulfilled" : "failed");
    }
}
```

## Regulatory Quick Reference

| Regulation | Scope | Key log obligations | Right to erasure |
|---|---|---|---|
| GDPR | EU residents | No sensitive-category data without legal basis; data minimisation; third-party sink agreements required | 30 days |
| CCPA | California residents | Disclose what personal data is logged; honour deletion requests | 45 days |
| HIPAA | US health data | PHI prohibited in application logs; Business Associate Agreement required for third-party sinks | No |
| PCI DSS | Cardholder data | No full PAN in logs; no CVV; BIN (first 6) + last 4 digits are permissible | N/A |

For the Collector-side controls that implement these obligations uniformly across services, see [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/).

## Common Pitfalls

**The development data problem.** Production data in development environments means developers see real customer PII. Apply `RedactionPolicy.ForEnvironment("development")` in all environments — lower-fidelity redaction in dev is fine, but the policy must exist everywhere.

**The exception message leak.** Third-party libraries and ORMs sometimes include user input or query parameters in exception messages. The most common offender is a validation exception that echoes the input value:

```csharp
// ❌ Exception message contains the submitted value
throw new ValidationException($"Invalid email format: {submittedEmail}");

// ✅ Use a structured exception that separates code from data
throw new ValidationException("Invalid email format")
{
    Data = { ["field"] = "email" }  // Not the value — the field name only
};
```

**The third-party sink leak.** Sending raw structured log objects to an external sink (DataDog, Splunk, third-party APM) without a scrubbing filter sends PII to a system you don't fully control. Register a `PIIFilteringProcessor` or configure the scrubbing enricher before the external exporter, not just before your own backend.

## What Not to Use: The OTel Processor Trap

The obvious place to scrub PII in an OTel-instrumented service is a `BaseProcessor<LogRecord>`. It is not a safe option. In the OTel .NET SDK, `LogRecord.Attributes` and `LogRecord.FormattedMessage` are read-only — you cannot assign to them in `OnEnd`. Attempts to do so will silently fail or throw at runtime.

Scrub before the record is created — at the `ILogger` call site using `BeginScope`, Serilog destructuring policies, or a wrapper like the `PrivacySafeLogger` above — or after the record reaches the Collector, using OTTL `delete_key` and `set` transforms as documented in [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/).

<!-- TODO: Add Serilog destructuring policy example showing how to register a custom IDestructuringPolicy that calls SmartRedactor on matched types -->
<!-- TODO: Add integration test pattern for verifying PII detection coverage: property-based tests that generate realistic log strings and assert no matches reach the sink -->

## See Also

- [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/) — the OTel Collector approach: the primary control, covering spans and logs across all services
- [Data Masking in Telemetry](/guides/data-masking-in-telemetry/) — transformation techniques: hashing, tokenisation, coarsening, and quality gates
- [Structured Logging in .NET](/howtos/implement-structured-logging-dotnet/) — the logging patterns that application-level PII controls integrate with
