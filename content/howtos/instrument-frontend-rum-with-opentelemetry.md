---
title: "How to Instrument a Web Frontend with OpenTelemetry RUM"
date: 2026-06-10
draft: true
excerpt: "Add OpenTelemetry instrumentation to a React application to capture page load traces, user interaction spans, API request durations, and JavaScript errors — and connect them to your backend traces."
readtime: 7
tags: ["RUM", "OpenTelemetry", "Tracing", "Metrics", "How-to"]
---

This how-to covers adding OpenTelemetry instrumentation to a React/TypeScript application. By the end you'll have automatic tracing for page loads, fetch calls, and user interactions; histogram and counter metrics for request duration and error rate; and an ErrorBoundary that records React component errors as OTel spans.

## Project Structure

Keep instrumentation setup files separate from application code:

```
src/
├── instrumentation/
│   ├── tracer.ts      # WebTracerProvider setup and auto-instrumentation
│   ├── metrics.ts     # MeterProvider and metric instruments
├── hooks/
│   └── telemetry.ts   # Custom hooks for components
└── components/
    └── ErrorBoundary.tsx
```

## 1. Install Packages

```bash
# Core SDK
npm install @opentelemetry/api \
            @opentelemetry/sdk-trace-web \
            @opentelemetry/sdk-metrics

# OTLP exporters (HTTP)
npm install @opentelemetry/exporter-trace-otlp-http \
            @opentelemetry/exporter-metrics-otlp-http

# Auto-instrumentation
npm install @opentelemetry/instrumentation \
            @opentelemetry/instrumentation-document-load \
            @opentelemetry/instrumentation-user-interaction \
            @opentelemetry/instrumentation-fetch \
            @opentelemetry/instrumentation-xml-http-request

# Resources and semantic conventions
npm install @opentelemetry/resources \
            @opentelemetry/semantic-conventions
```

## 2. Configure Tracing

```typescript
// src/instrumentation/tracer.ts
import * as opentelemetry from '@opentelemetry/api';
import { WebTracerProvider, BatchSpanProcessor } from '@opentelemetry/sdk-trace-web';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { Resource } from '@opentelemetry/resources';
import { ATTR_SERVICE_NAME, ATTR_SERVICE_VERSION } from '@opentelemetry/semantic-conventions';
import { registerInstrumentations } from '@opentelemetry/instrumentation';
import { DocumentLoadInstrumentation } from '@opentelemetry/instrumentation-document-load';
import { UserInteractionInstrumentation } from '@opentelemetry/instrumentation-user-interaction';
import { FetchInstrumentation } from '@opentelemetry/instrumentation-fetch';

const resource = Resource.default().merge(
  new Resource({
    [ATTR_SERVICE_NAME]: 'my-frontend',
    [ATTR_SERVICE_VERSION]: '1.0.0',
  }),
);

const provider = new WebTracerProvider({ resource });

const exporter = new OTLPTraceExporter({
  url: 'http://localhost:4318/v1/traces',
});

provider.addSpanProcessor(new BatchSpanProcessor(exporter));
provider.register();

registerInstrumentations({
  instrumentations: [
    new DocumentLoadInstrumentation(),
    new UserInteractionInstrumentation({
      eventNames: ['click', 'submit'],
      shouldPreventSpanCreation: (eventType, element, span) => {
        if (element.id) span.setAttribute('target.id', element.id);
        if (element.className) span.setAttribute('target.class', element.className);
        return false;
      },
    }),
    new FetchInstrumentation({
      // Inject W3C trace context headers on requests to these origins
      propagateTraceHeaderCorsUrls: [/https?:\/\/api\.example\.com/],
    }),
  ],
});

export const tracer = opentelemetry.trace.getTracer('my-frontend');
```

`propagateTraceHeaderCorsUrls` injects `traceparent` headers on matching fetch calls, enabling end-to-end trace correlation from the browser through to your backend services. The backend must be configured to accept these CORS headers.

## 3. Configure Metrics

```typescript
// src/instrumentation/metrics.ts
import { metrics } from '@opentelemetry/api';
import { MeterProvider, PeriodicExportingMetricReader } from '@opentelemetry/sdk-metrics';
import { OTLPMetricExporter } from '@opentelemetry/exporter-metrics-otlp-http';
import { Resource } from '@opentelemetry/resources';
import { ATTR_SERVICE_NAME, ATTR_SERVICE_VERSION } from '@opentelemetry/semantic-conventions';

const resource = Resource.default().merge(
  new Resource({
    [ATTR_SERVICE_NAME]: 'my-frontend',
    [ATTR_SERVICE_VERSION]: '1.0.0',
  }),
);

const meterProvider = new MeterProvider({
  resource,
  readers: [
    new PeriodicExportingMetricReader({
      exporter: new OTLPMetricExporter({
        url: 'http://localhost:4318/v1/metrics',
      }),
      exportIntervalMillis: 10_000,
    }),
  ],
});

metrics.setGlobalMeterProvider(meterProvider);

const meter = meterProvider.getMeter('my-frontend');

export const apiRequestDuration = meter.createHistogram('api.request.duration', {
  description: 'API request round-trip time',
  unit: 'ms',
});

export const userInteractionCounter = meter.createCounter('user.interaction.count', {
  description: 'User interaction events',
});

export const componentLifetimeDuration = meter.createHistogram('component.lifetime.duration', {
  description: 'Time a component is mounted (mount to unmount)',
  unit: 'ms',
});

export const errorCounter = meter.createCounter('error.count', {
  description: 'Application errors caught by ErrorBoundary',
});
```

## 4. Custom Hooks

Rather than scattering span and metric calls throughout component code, encapsulate them in hooks.

```typescript
// src/hooks/telemetry.ts
import { useEffect, useCallback } from 'react';
import { tracer } from '../instrumentation/tracer';
import { componentLifetimeDuration, userInteractionCounter } from '../instrumentation/metrics';

/**
 * Records a span covering the component's mounted lifetime.
 * Note: this measures mount-to-unmount duration, not React render time.
 * For true render-time measurement, use the React Profiler API or a profiling tool.
 */
export function useTraceComponentLifetime(componentName: string) {
  useEffect(() => {
    const startTime = performance.now();
    const span = tracer.startSpan(`${componentName}.mounted`);

    return () => {
      const duration = performance.now() - startTime;
      componentLifetimeDuration.record(duration, { component: componentName });
      span.end();
    };
  }, [componentName]);
}

/**
 * Returns a stable callback that records a span and increments the
 * interaction counter when the user triggers an event.
 */
export function useTrackInteraction(actionName: string) {
  return useCallback(
    (event: React.SyntheticEvent) => {
      const span = tracer.startSpan('user.interaction');
      try {
        userInteractionCounter.add(1, {
          action: actionName,
          target_id: (event.target as HTMLElement).id || 'unknown',
        });
        span.setAttribute('action.name', actionName);
        span.setAttribute('action.timestamp', Date.now());
      } finally {
        span.end();
      }
    },
    [actionName],
  );
}
```

{{< insight >}}
`target_id` on the interaction counter must be a bounded label. If element IDs are dynamically generated or unique per record (e.g., `item-12345`), strip the numeric suffix before recording — otherwise each distinct ID becomes a separate time series.
{{< /insight >}}

## 5. Instrument a Component

```typescript
// src/components/NumberFact.tsx
import { SpanStatusCode } from '@opentelemetry/api';
import { useTraceComponentLifetime, useTrackInteraction } from '../hooks/telemetry';
import { tracer } from '../instrumentation/tracer';
import { apiRequestDuration } from '../instrumentation/metrics';

function NumberFact({ number }: { number: string }) {
  useTraceComponentLifetime('NumberFact');

  const handleClick = useTrackInteraction('getFact');

  const fetchFact = async () => {
    const startTime = performance.now();
    const span = tracer.startSpan('get_number_fact');

    try {
      span.setAttribute('number', number);

      const response = await fetch(`http://numbersapi.com/${number}`);
      const fact = await response.text();

      apiRequestDuration.record(performance.now() - startTime, {
        success: 'true',
        number,
      });

      span.setStatus({ code: SpanStatusCode.OK });
      return fact;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'unknown';
      span.setStatus({ code: SpanStatusCode.ERROR, message });
      throw err;
    } finally {
      span.end();
    }
  };

  return (
    <div>
      <button onClick={handleClick}>Get Fact for {number}</button>
      {/* rest of component */}
    </div>
  );
}
```

## 6. Catch React Errors with an ErrorBoundary

React's `componentDidCatch` lifecycle is the right place to record component-tree errors as OTel spans. The full component stack goes on the span; only the error type goes on the counter — using the stack as a metric attribute would generate one unique series per distinct component tree, which is unbounded.

```typescript
// src/components/ErrorBoundary.tsx
import { Component, ErrorInfo, ReactNode } from 'react';
import { SpanStatusCode } from '@opentelemetry/api';
import { tracer } from '../instrumentation/tracer';
import { errorCounter } from '../instrumentation/metrics';

interface Props { children?: ReactNode }
interface State { hasError: boolean }

export class TelemetryErrorBoundary extends Component<Props, State> {
  public state: State = { hasError: false };

  public static getDerivedStateFromError(_: Error): State {
    return { hasError: true };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    const span = tracer.startSpan('error.boundary');

    // errorType has bounded cardinality — safe as a metric attribute
    errorCounter.add(1, { error_type: error.name });

    // Full stack trace belongs on the span, not the metric
    span.setAttribute('error.message', error.message);
    span.setAttribute('error.stack', error.stack ?? '');
    span.setAttribute('error.component_stack', errorInfo.componentStack ?? '');
    span.setStatus({ code: SpanStatusCode.ERROR, message: error.message });
    span.end();
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div>
          <h1>Something went wrong</h1>
          <p>This error has been recorded.</p>
        </div>
      );
    }
    return this.props.children;
  }
}
```

Wrap it at the application root or around any subtree that should be isolated:

```tsx
<TelemetryErrorBoundary>
  <App />
</TelemetryErrorBoundary>
```

## What This Instrumentation Covers

{{< mermaid >}}
flowchart TD
    A[Frontend Telemetry] --> B[Performance]
    A --> C[User Interactions]
    A --> D[Errors]

    B --> B1[Page load — DocumentLoadInstrumentation]
    B --> B2[Component lifetime — useTraceComponentLifetime]
    B --> B3[API round-trip — fetchFact span + histogram]

    C --> C1[Click events — UserInteractionInstrumentation]
    C --> C2[Form submits — UserInteractionInstrumentation]
    C --> C3[Custom actions — useTrackInteraction]

    D --> D1[React component errors — TelemetryErrorBoundary]
    D --> D2[Fetch failures — FetchInstrumentation + manual span]
{{< /mermaid >}}

<!-- TODO: Add step for capturing Core Web Vitals (LCP, CLS, FID/INP) using the web-vitals library -->
<!-- TODO: Add Collector configuration for CORS headers (required for OTLP/HTTP from browser) -->
<!-- TODO: Add step for verifying traces appear end-to-end in Grafana Tempo or Jaeger -->
<!-- TODO: Add privacy checklist — what not to include in browser spans (user IDs, session tokens, form field values) -->
<!-- TODO: Cover Grafana Faro as an alternative receiving backend -->
<!-- TODO: Cover async context propagation if using concurrent React features (React 18+ concurrent rendering) -->
