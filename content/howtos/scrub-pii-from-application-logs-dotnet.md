---
title: "Scrub PII from Application Logs in .NET"
date: 2026-09-26
draft: false
excerpt: "Keep personal data out of your .NET logs before they leave the process: classify fields so the logger erases or pseudonymises them, scrub free text and exception messages in an OpenTelemetry processor, and prove nothing leaks."
readtime: 10
tags: ["GDPR", "Privacy", "Security", "Logs", "Compliance", "OpenTelemetry", "How-to"]
---

Your main control for PII in telemetry is the OTel Collector. [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/) covers that pipeline, and it protects every service at once. This how-to covers the layer in front of it: stopping personal data inside the .NET process, before it's ever exported.

You'll do it in two passes. First, you classify your data so the logger erases or pseudonymises it the moment it's logged. Then an OpenTelemetry processor catches what classification can't see: personal data baked into a message string, or echoed back in an exception message. By the end, a seeded email address, card number and IP address go in one end and nothing personal comes out the other. You'll check that yourself in step 5.

{{< obs-telemetry-controls-map here="app" >}}

## Before You Start

You need:

- .NET 8 or later
- `Microsoft.Extensions.Compliance.Redaction` and `Microsoft.Extensions.Telemetry` for classification and redaction
- `OpenTelemetry.Extensions.Hosting` plus an exporter: `OpenTelemetry.Exporter.OpenTelemetryProtocol` for production, `OpenTelemetry.Exporter.Console` for step 5
- A random 32-byte key, base64-encoded, stored wherever you keep secrets

Every sample below was compiled and run against `Microsoft.Extensions.Compliance.Redaction` 10.10.0 and OpenTelemetry .NET 1.19.1 on `net8.0`.

## Step 1: Classify Your Data

Start by telling the compiler which fields are personal. A taxonomy is a named set of classifications, and each classification gets an attribute you can put on a property or parameter:

```csharp
using Microsoft.Extensions.Compliance.Classification;

public static class PrivacyTaxonomy
{
    public static string Name => "Privacy";

    public static DataClassification PersonalData => new(Name, nameof(PersonalData));
    public static DataClassification Pseudonymous => new(Name, nameof(Pseudonymous));
}

public sealed class PersonalDataAttribute : DataClassificationAttribute
{
    public PersonalDataAttribute() : base(PrivacyTaxonomy.PersonalData) { }
}

public sealed class PseudonymousAttribute : DataClassificationAttribute
{
    public PseudonymousAttribute() : base(PrivacyTaxonomy.Pseudonymous) { }
}
```

Two classes are enough to start, and each one maps to a decision from [Data Masking in Telemetry](/guides/data-masking-in-telemetry/):

- **`PersonalData`** gets erased. Email addresses, names, phone numbers and IP addresses all go here.
- **`Pseudonymous`** gets a keyed hash, so you can still follow one user across log lines without knowing who they are. Internal user IDs go here.

Email addresses belong in `PersonalData`, not `Pseudonymous`, even though a keyed hash looks safe. Anyone who gets hold of the key can hash a list of known addresses and match every one, and a pseudonym built from an email still links the same person across every system that uses it. Save pseudonyms for internal IDs that mean nothing outside your service.

Now mark up the types you log:

```csharp
public record Customer(
    [property: Pseudonymous] string Id,
    [property: PersonalData] string Email,
    string Tier,
    string Country);
```

`Tier` and `Country` stay unclassified. They're business context, and they're what makes the log line useful.

## Step 2: Log Through Generated Methods

Classification only works if the logger can see it, and it sees it through the `[LoggerMessage]` source generator:

```csharp
using Microsoft.Extensions.Logging;

public static partial class Log
{
    [LoggerMessage(Level = LogLevel.Information, Message = "Checkout started")]
    public static partial void CheckoutStarted(ILogger logger, [LogProperties] Customer customer);

    [LoggerMessage(Level = LogLevel.Information, Message = "Password reset requested for {UserId}")]
    public static partial void PasswordResetRequested(ILogger logger, [Pseudonymous] string userId);
}
```

`[LogProperties]` expands the object into one tag per property (`customer.Id`, `customer.Email`, and so on) and carries each property's classification with it. A classified parameter like `userId` gets redacted in its tag and in the formatted message.

Anything you log as a plain string skips all of this. `logger.LogWarning($"Declined for {email}")` hands the logger a finished string, and there's no attribute left to find. Step 4 handles those.

## Step 3: Register the Redactors

Wire each classification to a redactor in `Program.cs`:

```csharp
using Microsoft.Extensions.Compliance.Classification;
using Microsoft.Extensions.Compliance.Redaction;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using OpenTelemetry.Logs;

var builder = Host.CreateApplicationBuilder(args);

builder.Logging.EnableRedaction();

builder.Services.AddRedaction(redaction =>
{
    redaction.SetRedactor<ErasingRedactor>(
        new DataClassificationSet(PrivacyTaxonomy.PersonalData));

#pragma warning disable EXTEXP0002 // HMAC redaction is marked experimental
    redaction.SetHmacRedactor(
        builder.Configuration.GetSection("Redaction:Hmac"),
        new DataClassificationSet(PrivacyTaxonomy.Pseudonymous));
#pragma warning restore EXTEXP0002
});
```

And give the HMAC redactor its key from your secret store, not from a file in the repo:

```json
{
  "Redaction": {
    "Hmac": {
      "KeyId": 1,
      "Key": "<base64, at least 44 characters>"
    }
  }
}
```

`EnableRedaction()` runs redaction inside the logger itself, so every logging provider gets the redacted values. `ErasingRedactor` swaps the value for an empty string. The HMAC redactor produces something like `1:ctQ7VjfIiA+r0ytHtF+uRA==`, where the `1:` is the key ID.

If the key is missing or shorter than 44 characters, the app refuses to start with an `OptionsValidationException`. That's the behaviour you want. A service that quietly logged raw IDs because a secret didn't load would be much worse.

Two details will trip you up if nobody tells you:

**The field name is part of the pseudonym.** By default, the logger mixes each tag's name into the hash. The same user ID logged as `UserId` in one place and `customer.Id` in another comes out as two different values, so the two lines won't join. Log the ID under the same name everywhere. If you really need to join across different names, set `EnableRedaction(o => o.ApplyDiscriminator = false)`.

**Rotating the key breaks correlation, on purpose.** A new key needs a new `KeyId`. Values with different key IDs are unrelated by design, so a user's trail starts fresh after rotation.

## Step 4: Scrub Free Text and Exceptions

Classification can't see inside a string that was built before it reached the logger. That covers two big leaks: your own interpolated messages, and exception messages from libraries that echo user input back ("Invalid email format: jane.doe@example.com").

An OpenTelemetry log processor runs on every record before the exporter does, and in recent OpenTelemetry .NET releases (checked on 1.19.1) it's allowed to rewrite the record. Here's one that scrubs the message, the body and every string attribute:

```csharp
using System.Text.RegularExpressions;
using OpenTelemetry;
using OpenTelemetry.Logs;

public sealed partial class PiiScrubbingProcessor : BaseProcessor<LogRecord>
{
    [GeneratedRegex(@"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63}){0,8}\.[A-Za-z]{2,24}",
        RegexOptions.CultureInvariant, matchTimeoutMilliseconds: 100)]
    private static partial Regex Email();

    // 13 to 19 digits, optionally split by spaces or hyphens. Luhn-checked below.
    [GeneratedRegex(@"\b\d(?:[ -]?\d){12,18}\b",
        RegexOptions.CultureInvariant, matchTimeoutMilliseconds: 100)]
    private static partial Regex CardCandidate();

    [GeneratedRegex(@"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b",
        RegexOptions.CultureInvariant, matchTimeoutMilliseconds: 100)]
    private static partial Regex IPv4();

    public override void OnEnd(LogRecord record)
    {
        record.FormattedMessage = Scrub(record.FormattedMessage);
        record.Body = Scrub(record.Body);

        var attributes = new List<KeyValuePair<string, object?>>();
        foreach (var (key, value) in record.Attributes ?? [])
        {
            if (record.Exception is not null && key.StartsWith("exception.", StringComparison.Ordinal))
                continue; // replaced below
            attributes.Add(new(key, value is string s ? Scrub(s) : value));
        }

        if (record.Exception is { } ex)
        {
            // Exception.Message is read-only, so export scrubbed
            // semantic-convention attributes instead of the live object.
            attributes.Add(new("exception.type", ex.GetType().FullName));
            attributes.Add(new("exception.message", Scrub(ex.Message)));
            attributes.Add(new("exception.stacktrace", Scrub(ex.ToString())));
            record.Exception = null;
        }

        record.Attributes = attributes;
    }

    public static string? Scrub(string? text)
    {
        if (string.IsNullOrEmpty(text)) return text;
        try
        {
            text = Email().Replace(text, "[REDACTED:EMAIL]");
            text = CardCandidate().Replace(text, m => PassesLuhn(m.Value) ? "[REDACTED:CARD]" : m.Value);
            return IPv4().Replace(text, "[REDACTED:IP]");
        }
        catch (RegexMatchTimeoutException)
        {
            return "[REDACTED:UNSCANNED]"; // fail closed
        }
    }

    private static bool PassesLuhn(string candidate)
    {
        int sum = 0;
        bool doubleIt = false;
        for (int i = candidate.Length - 1; i >= 0; i--)
        {
            if (!char.IsAsciiDigit(candidate[i])) continue;
            int d = candidate[i] - '0';
            if (doubleIt && (d *= 2) > 9) d -= 9;
            sum += d;
            doubleIt = !doubleIt;
        }
        return sum % 10 == 0;
    }
}
```

Register it ahead of the exporter, and clear the default providers while you're there. The first pitfall below explains why:

```csharp
builder.Logging.ClearProviders();
builder.Logging.AddOpenTelemetry(otel =>
{
    otel.IncludeFormattedMessage = true;
    otel.AddProcessor(new PiiScrubbingProcessor()); // before the exporter
    otel.AddOtlpExporter();
});
```

The exception handling deserves a closer look. You can't change `Exception.Message`, and rebuilding the exception would lose its type. So the processor exports the exception as `exception.type`, `exception.message` and `exception.stacktrace` attributes, the same names the OpenTelemetry semantic conventions use, with the text scrubbed. Then it drops the live object so the exporter can't serialise the raw message anyway.

The regexes run on every log line in production, and that's a terrible place to meet a pathological input:

{{< obs-regex-shame >}}

So every pattern has bounded quantifiers and a 100 ms match timeout, and a timeout fails closed: the whole string becomes `[REDACTED:UNSCANNED]` instead of going out unchecked. `[GeneratedRegex]` builds the matcher at compile time, so no pattern gets parsed while your service runs. The card pattern only redacts runs of digits that pass the Luhn check, which keeps most long order numbers readable. Not all of them, though: about one random digit run in ten passes Luhn by chance, so don't rely on a raw order number surviving a free-text message.

These three patterns are a floor, not a finished list. Add the identifiers your own data carries, such as IPv6 addresses, phone numbers or national ID formats, and test each new pattern against real log lines for false positives before you ship it.

## Step 5: Verify Nothing Leaks

Swap `AddOtlpExporter()` for `AddConsoleExporter()` and log one of everything:

```csharp
using var host = builder.Build();
var logger = host.Services.GetRequiredService<ILogger<Program>>();

Log.CheckoutStarted(logger, new Customer("usr_8f2c", "jane.doe@example.com", "gold", "PT"));
Log.PasswordResetRequested(logger, "usr_8f2c");
logger.LogWarning("Card 4111 1111 1111 1111 declined for jane.doe@example.com from 203.0.113.9");
logger.LogInformation("Order 1234567890123 shipped");
try { throw new InvalidOperationException("Invalid email format: jane.doe@example.com"); }
catch (Exception ex) { logger.LogError(ex, "Signup validation failed"); }
```

Run it, and the exporter shows this (trimmed to the interesting lines):

```text
customer.Email:
customer.Id: 1:ctQ7VjfIiA+r0ytHtF+uRA==
customer.Country: PT
customer.Tier: gold
LogRecord.FormattedMessage:        Password reset requested for 1:y3TRUgKhkw4++JMAOxuVag==
LogRecord.FormattedMessage:        Card [REDACTED:CARD] declined for [REDACTED:EMAIL] from [REDACTED:IP]
LogRecord.FormattedMessage:        Order 1234567890123 shipped
exception.type: System.InvalidOperationException
exception.message: Invalid email format: [REDACTED:EMAIL]
```

Your HMAC values will differ, because your key does. Now make it a check you can repeat:

```bash
! dotnet run | grep -E 'jane\.doe|4111 1111|203\.0\.113'
```

The `!` flips grep's exit code, so the command succeeds when nothing matches and fails, printing the leaked lines, when something does. That makes it a CI step as it stands. Put the same seeded lines in an integration test, point the OTLP exporter at a Collector with the `debug` exporter in staging, and the build fails the day someone adds a new leak.

## Common Pitfalls

**Other log providers skip step 4.** `Host.CreateApplicationBuilder` registers console, debug and EventSource providers by default. They get step 3's redaction, but the OTel processor never sees their output. In testing, the console provider printed the raw card number, email address and IP from step 5's free-text line. In a container, stdout usually ends up in a log shipper. That's why step 4 clears the providers. If you need console output, give it the same scrubbing or keep it out of production.

**Exception messages start at the throw.** The processor cleans up after the fact, but the cheapest fix is at the source. Put the field name in the message, not the value: `throw new ValidationException("Invalid email format")`, not one that echoes `submittedEmail`.

**Audit events don't belong in this pipeline.** A record of who accessed personal data is evidence, not a debugging aid. It can't be sampled, and your redaction rules shouldn't be allowed to change it. [Implementing Audit Trails with OpenTelemetry](/guides/audit-trail-implementation/) covers giving it a pipeline of its own.

**Classification works one field at a time.** Postcode, birth date and gender aren't personal on their own, but together they can single out one person:

{{< obs-quasi-id-risk >}}

The redactors can't see that combination, because each field looks harmless. Generalise before you log: a postcode prefix instead of the full code, an age band instead of a birth date, or just leave the field out.

## See Also

- [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/) — the Collector pipeline, your primary control across every service
- [Data Masking in Telemetry](/guides/data-masking-in-telemetry/) — when to erase, hash or tokenise, and why emails never get hashed
- [Observability Under Compliance](/guides/compliance-observability/) — what GDPR, HIPAA, SOC 2 and PCI DSS each ask of your telemetry
- [Implementing Audit Trails with OpenTelemetry](/guides/audit-trail-implementation/) — the separate pipeline access records need
