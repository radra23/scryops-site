---
title: "Five Things That Will Break Your Pyroscope Deployment"
date: 2026-06-16
draft: true
excerpt: "A troubleshooting guide built from real production failures: the security group that locked us out of our own server, the Elastic IP that didn't make the instance reachable, the S3 token that expired quietly, the data directory the container couldn't write to, and the certificate the Node SDK refused to trust."
readtime: 7
tags: ["Profiling", "Observability", "Operations", "Debugging"]
---

<!--
HOW-TO: Troubleshooting guide structured around real failure modes from a
real project. This is the most immediately publishable piece of the three
because the war stories section of the source material is almost ready to
go — it just needs voice alignment, tight formatting, and the two config
gotchas folded in.

FORMAT CONTRACT: Every failure has the same three-part structure:
1. The symptom (what you see — log output, behavior, error message)
2. The cause (why it happened — the underlying mechanism)
3. The fix (what to do — specific, actionable, not vague)

This structure is already present in the source material. Preserve it.
The tech-storyteller voice applies mostly to transitions and framing, not
to the individual failure entries — those should stay crisp and factual.

OPENING:
Set the scene: you've followed a setup guide, the components all report
healthy, and profiles aren't arriving. This is the first thing that happens
to everyone. The guide covers configuration; this document covers the things
that aren't wrong with the configuration — the environment assumptions that
the documentation takes for granted.

THE FIVE (PLUS TWO) FAILURES:

## 1. The Security Group That Locked You Out of Your Own Server

Symptom: the instance has a public Elastic IP, port 4040 is "open" in the
security group, and nothing connects. telnet / nc to the port times out.

Cause: the source project's setup script first opened port 4040 to 0.0.0.0/0,
then "hardened" it by adding a rule scoped to ${INSTANCE_PUBLIC_IP}/32 —
the instance's OWN IP. That rule means only the server can talk to the server.
Every other source is now blocked despite the earlier permissive rule, because
AWS security groups are evaluated per-rule and the CIDR match for the public
IP blocks everything else.

Fix: delete every rule for the port and re-add deliberately. For testing:
22 and 4040 from your source IP range. Never add a rule scoped to the
instance's own IP unless you specifically want intra-instance communication.
Narrow rules after verifying connectivity, not before.

## 2. The Elastic IP That Wasn't Enough

Symptom: the instance has an Elastic IP, the security group looks right,
and the internet still can't reach it.

Cause: this is the most common VPC misconception worth documenting plainly.
An Elastic IP gives you a stable address — it does not route traffic. A
subnet is only "public" because its route table has a route for 0.0.0.0/0
pointing at an Internet Gateway. Without that IGW route, no address will
make the instance reachable inbound.

The full requirement:
  - Public subnet (route table has 0.0.0.0/0 → igw-xxxxxxxx)
  - Internet Gateway attached to the VPC
  - Instance placed in the public subnet
  - Elastic IP is optional — it's just a stable address on top of this

Fix: check the subnet's route table first (not the security group). If
0.0.0.0/0 isn't pointing at an IGW, no amount of security group adjustment
will help.

Useful framing: the EIP is the lock. The IGW route is the door. You can
have the most impressive lock in the world; without the door, nobody gets in.

## 3. The S3 Token That Expired Quietly

Symptom: Pyroscope starts cleanly, the health check passes, and then the
logs fill with "The provided token has expired" — store-gateway, compactor,
and tenant-settings all failing to reach S3. Profiles stop being stored.
No crash, no alert — it fails silently until you look at the logs.

Cause: the container was running with temporary AWS credentials
(AWS_SESSION_TOKEN alongside ACCESS_KEY_ID and SECRET_ACCESS_KEY). Session
tokens have a lifetime (typically 1-12 hours for assumed roles, up to 36
hours for IAM Identity Center). When the token expires, all S3 calls fail.

Fix, in order of preference:
1. Attach an IAM role to the instance/task — the metadata service rotates
   credentials automatically, no tokens in env vars at all
2. If you must use credentials in env vars: make sure all three values
   (ACCESS_KEY_ID, SECRET_ACCESS_KEY, SESSION_TOKEN) are fresh and passed
   together. A stale SESSION_TOKEN with a valid KEY_ID/SECRET will fail.
3. Add a log alert on "provided token has expired" so this doesn't
   silently corrupt your storage.

## 4. The Data Directory the Container Couldn't Write To

Symptom: Pyroscope starts, all components report healthy in the logs, and
then: "mkdir data/anonymous/head/...: permission denied" and
"shipper run failed ... permission denied". The web UI may load but shows
no data. The server is running; it is storing nothing.

This is the insidious one: "healthy" Pyroscope that can't write is
indistinguishable from working Pyroscope until you check for data.

Cause: the container process runs as a non-root user (correct) but the
mounted host directory is owned by root (or a different UID). The UIDs
don't match so the container can't write.

Fix (two options, either works):
Option A — match UIDs in the Compose file:
```yaml
services:
  pyroscope:
    user: "1000:1000"   # match your host user UID:GID
    volumes:
      - ./data:/data
```

Option B — own the directory from the host:
```bash
mkdir -p ./data
sudo chown 1000:1000 ./data
```

Verification: after fixing, create a test profile and check that files
appear in ./data. A healthy server storing nothing will not tell you
anything is wrong.

## 5. The Certificate the Node SDK Refused to Trust

Symptom: TLS is configured in front of the Pyroscope server (Nginx,
ALB, or API Gateway). The Node.js client is pointed at the https:// URL.
Profiles never arrive. The Node process logs something like
"certificate verify failed" or "unable to verify the first TLS certificate".

Cause: the dev/self-signed certificate isn't in the Node.js trust store.
Node.js uses its own bundled CA list (not the OS trust store by default).
A certificate signed by a CA not in that list — including most self-signed
or internal CA certs — will be rejected.

Fix (in order of preference — only use earlier options):
1. Use a real certificate via ACM fronted by an ALB or Nginx. DNS-validated
   ACM certs are free and trusted everywhere.
2. Point the client at http:// if it's on a trusted internal network and
   TLS termination is handled elsewhere.
3. For non-production only: NODE_TLS_REJECT_UNAUTHORIZED=0 or a custom
   httpAgent. Document this explicitly as a development convenience and
   audit that it hasn't leaked into production config.

## Two Config Gotchas That Don't Log Helpfully

These aren't connectivity failures — they're YAML structure errors that
cause Pyroscope to start but behave incorrectly. Both come from the source
project and both are easy to hit:

### replication_factor in the wrong block
The ring config expects kvstore.store = memberlist. A stray replication_factor
at the wrong nesting level causes a startup error. Show the correct structure
vs the incorrect structure side by side with ❌ / ✅ markers.

### Retention settings in the wrong place
min_free_disk_gb, min_disk_available_percentage, and enforcement_interval
belong directly under the pyroscopedb: block, NOT in a nested
retention_policy: subkey. The server may start without erroring but retention
will silently not apply.

Show correct vs incorrect YAML for both.

## The Verification Checklist
End with the checklist from the source material — it's the right sequence
to walk when profiles aren't arriving:

```bash
# Are the ports listening?
sudo ss -tlnp | grep -E '4040|9095'

# Is the HTTP API responding?
curl http://<server>:4040/ready

# Is gRPC reachable from the client side?
nc -zv <server> 9095

# What does the server say?
docker-compose logs -f  # or: aws logs tail /ecs/pyroscope-task-definition
```

Mental checklist:
- Public subnet with IGW route (inbound) or NAT route (outbound to S3)?
- Security groups allow 4040, 9095, and 7946 (memberlist if clustered)?
- DNS resolves and IPs route between client and server?
- Data directory is writable by the container process?
- AWS credentials are an IAM role or fresh session (not an expired token)?
- Enable=pyroscope debug logging on the Node client before blaming the network

VOICE NOTES:
- This is a how-to, not an opinion piece. The voice should be warmer than
  a plain README but the structure is deliberately functional.
- The "insidious one" note on failure #4 (healthy server storing nothing)
  is the right tone — acknowledge the non-obvious failure mode with some
  emphasis.
- The opening should acknowledge that these failures aren't about misconfiguring
  Pyroscope itself — they're about the environment assumptions the documentation
  takes for granted. That reframe makes the reader feel less foolish.

CROSS-LINK TO:
- Guide: content/guides/pyroscope-nodejs-aws-setup.md
  (each failure links to the relevant setup section — network failures
  link to Layer 1, S3 token links to the Storage section, etc.)
- Article: content/articles/continuous-profiling-the-missing-signal.md
  (link in the introduction: "If you're not yet sure why you're running
  Pyroscope, start with the concepts article first.")
-->
