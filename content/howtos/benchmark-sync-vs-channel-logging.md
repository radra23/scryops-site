---
title: "How to Benchmark Synchronous vs Channel Logging"
date: 2026-06-07
lastmod: 2026-09-23
draft: false
excerpt: "Async logging is supposed to take I/O off the request thread. Measure it: a sync-vs-channel benchmark under concurrent producers, in .NET, Go, or Python, and how to read the result."
readtime: 6
tags: ["Logs", "Python", "How-to"]
series: "High-throughput logging"
series_part: 3
series_title: "Try it: benchmark sync vs channel"
---

Every decision in [High-Throughput Logging: Keeping the Hot Path Fast](/guides/high-throughput-logging/) rests on one claim: synchronous logging makes the calling thread wait for I/O, and a queue or channel takes that wait off the hot path. That is worth measuring rather than asserting — and each language has a native way to do it: [BenchmarkDotNet](https://benchmarkdotnet.org/) in .NET, the `testing` package's parallel benchmarks in Go, and `perf_counter` around `QueueHandler` in Python. Each harness below pits a synchronous, locked write against a queue/channel enqueue under concurrent producers — the regime a high-throughput service actually runs in.

## What you'll need

- **.NET:** the .NET 8 SDK and the `BenchmarkDotNet` NuGet package (`System.Threading.Channels` ships in the runtime)
- **Go:** Go 1.21+ for `log/slog`
- **Python:** Python 3.8+; the harness uses the standard library only

## Step 1 — Write the Harness

Each harness runs the same comparison: a synchronous write behind the sink's lock, against an enqueue that a single background consumer drains.

{{< langswitch >}}
```csharp
// requires: BenchmarkDotNet, System.Threading.Channels
[MemoryDiagnoser]
[SimpleJob(warmupCount: 3, iterationCount: 10)]
public class LoggingThroughputBenchmark
{
    private StreamWriter _sink   = null!;
    private readonly object _sinkLock = new();
    private Channel<string> _channel = null!;
    private Task _drain = null!;

    [Params(1, 8, 32)]   // 1, 8, 32 concurrent producer threads
    public int Producers;

    [GlobalSetup]
    public void Setup()
    {
        // A sink that performs a real write+flush, like a file or console
        _sink = new StreamWriter(File.Create(Path.GetTempFileName())) { AutoFlush = true };

        _channel = Channel.CreateBounded<string>(new BoundedChannelOptions(100_000)
        {
            FullMode     = BoundedChannelFullMode.DropOldest,
            SingleReader = true,
            SingleWriter = false
        });
        // One background consumer drains the queue and pays the I/O cost off the hot path
        _drain = Task.Run(async () =>
        {
            await foreach (var line in _channel.Reader.ReadAllAsync())
                _sink.Write(line);
        });
    }

    // Synchronous: the caller serializes AND writes, serialized behind a lock —
    // exactly what a thread-safe synchronous sink does under concurrency.
    [Benchmark(Baseline = true)]
    public void SynchronousWrite() => Parallel.For(0, Producers * 10_000,
        new ParallelOptions { MaxDegreeOfParallelism = Producers },
        _ => { var line = Render(); lock (_sinkLock) _sink.Write(line); });

    // Channel: the caller serializes and enqueues; the drain task absorbs the I/O.
    [Benchmark]
    public void ChannelEnqueue() => Parallel.For(0, Producers * 10_000,
        new ParallelOptions { MaxDegreeOfParallelism = Producers },
        _ => _channel.Writer.TryWrite(Render()));

    private static string Render() =>
        $"{DateTime.UtcNow:O} INFO order processed id={Random.Shared.Next()}";

    [GlobalCleanup]
    public void Cleanup()
    {
        _channel.Writer.Complete();
        _drain.Wait();
        _sink.Dispose();
    }
}
```
```python
# Standard library only. Threads simulate concurrent producers; the GIL bounds
# parallelism, but the queue still moves the write off the calling thread.
import logging, queue, threading, time
from logging.handlers import QueueHandler, QueueListener

THREADS, PER_THREAD = 32, 50_000

def run(setup, label):
    logger = logging.getLogger(label); logger.handlers.clear(); logger.setLevel(logging.INFO)
    listener = setup(logger)
    gate = threading.Barrier(THREADS)               # release all producers together
    def worker():
        gate.wait()
        for i in range(PER_THREAD):
            logger.info("order processed id=%d", i)
    threads = [threading.Thread(target=worker) for _ in range(THREADS)]
    t0 = time.perf_counter()
    for t in threads: t.start()
    for t in threads: t.join()
    caller_secs = time.perf_counter() - t0          # time the producers were busy
    if listener: listener.stop()
    print(f"{label:11} {THREADS * PER_THREAD / caller_secs:>11,.0f} msg/s (caller-side)")

def synchronous(logger):                            # caller writes+flushes, behind the handler lock
    logger.addHandler(logging.FileHandler("/dev/null"))
    return None

def channel(logger):                                # caller enqueues; listener drains on its own thread
    q = queue.Queue(maxsize=100_000)
    logger.addHandler(QueueHandler(q))
    listener = QueueListener(q, logging.FileHandler("/dev/null"))
    listener.start()
    return listener

run(synchronous, "synchronous")
run(channel,     "channel")
```
```go
// logging_bench_test.go — run: go test -bench=. -benchmem
package logbench

import (
	"context"
	"io"
	"log/slog"
	"testing"
)

// Synchronous: every caller encodes and writes through the handler, serialized by its mutex.
func BenchmarkSyncLogging(b *testing.B) {
	logger := slog.New(slog.NewJSONHandler(io.Discard, nil))
	b.ResetTimer()
	b.RunParallel(func(pb *testing.PB) {
		for pb.Next() {
			logger.Info("order processed", "id", 42)
		}
	})
}

// Channel-based: the caller hands the record to a buffered channel; a goroutine drains it.
func BenchmarkChannelLogging(b *testing.B) {
	sink := slog.NewJSONHandler(io.Discard, nil)
	ch := make(chan slog.Record, 100_000)
	done := make(chan struct{})
	go func() {
		for rec := range ch {
			_ = sink.Handle(context.Background(), rec) // encode + I/O happen here, off the hot path
		}
		close(done)
	}()

	logger := slog.New(&channelHandler{ch: ch})
	b.ResetTimer()
	b.RunParallel(func(pb *testing.PB) {
		for pb.Next() {
			logger.Info("order processed", "id", 42)
		}
	})
	b.StopTimer()
	close(ch)
	<-done
}

// channelHandler enqueues records instead of encoding and writing them.
type channelHandler struct{ ch chan slog.Record }

func (h *channelHandler) Enabled(context.Context, slog.Level) bool { return true }
func (h *channelHandler) Handle(_ context.Context, r slog.Record) error {
	select {
	case h.ch <- r: // non-blocking enqueue
	default:        // queue full: drop rather than stall the caller
	}
	return nil
}
func (h *channelHandler) WithAttrs([]slog.Attr) slog.Handler { return h }
func (h *channelHandler) WithGroup(string) slog.Handler      { return h }
```
{{< /langswitch >}}

## Step 2 — Run It

Benchmarks lie in Debug builds and on busy laptops. Build in release mode and close whatever else is competing for the CPU:

```bash
# .NET — Program.cs needs one line: BenchmarkRunner.Run<LoggingThroughputBenchmark>();
# BenchmarkDotNet refuses to run a Debug build
dotnet run -c Release

# Go — -benchmem adds allocations per op; -cpu varies producer parallelism
go test -bench=. -benchmem -cpu=1,8,32

# Python — save the harness as logging_bench.py
python3 logging_bench.py
```

## Step 3 — Read the Result

The absolute numbers depend entirely on your sink and host, so run it for your own — but the *shape* is stable across hardware. A synchronous write makes each caller wait for the serialize and the flush behind a shared lock, so its per-call cost is the sink's I/O latency, and that cost climbs as producers contend for the lock. A bounded-channel `TryWrite` is an in-memory enqueue — tens of nanoseconds uncontended, and even with many writers it stays far below the cost of one I/O flush — so it holds roughly flat as producers scale. Once the sink does real I/O, the per-call gap is frequently two to three orders of magnitude, and it *widens* with concurrency. Python is the asterisk here: the GIL caps raw parallelism, so its throughput gap is narrower than Go's or .NET's — but moving the write off the calling thread still protects request-handling latency, which is the whole point.

Two cautions when you run this. Measure caller latency — the time the request thread is blocked — not just total wall-clock; that blocked time is what your p99 pays. And measure under saturation, not just steady state: the channel's speed comes with a trade-off the synchronous path does not have. Once producers outrun the drain task, `DropOldest` sheds records. The question the benchmark answers is not "which is faster when nothing is contended" but "which one protects the request thread when everything is."
