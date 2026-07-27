# Emergency Operations

## ZX-42 reset

Rotate the emergency access token, invalidate the previous credential, and then
verify that the audit event was recorded. The on-call reviewer must confirm the
new token before the incident is closed.

## Audit review

The audit event must include the operator, workspace, timestamp, and affected
credential identifier. Never include the token value in an audit record.
