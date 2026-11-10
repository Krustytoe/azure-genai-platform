# Incident Response Runbook

Owner: Site Reliability Engineering.

## Severity levels

A Sev1 incident is a full outage or data exposure affecting customers. A Sev2 incident is a significant degradation with a workaround available. A Sev3 incident is a minor issue with limited customer impact.

## Response targets

For a Sev1 incident, the on-call engineer must acknowledge the page within 5 minutes, and the incident commander posts status updates every 30 minutes. For a Sev2 incident, acknowledge within 15 minutes and post updates every 60 minutes.

## Postmortems

Every Sev1 and Sev2 incident requires a blameless postmortem, published within 5 business days of resolution, with action items tracked in the engineering backlog.
