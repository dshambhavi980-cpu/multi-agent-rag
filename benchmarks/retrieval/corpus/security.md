# Private Security Notes

Private credentials and recovery secrets must never appear in retrieval traces.
Store only hashes, ranks, timings, and stable identifiers in diagnostic records.

Leaked or expired tokens must be revoked before replacement credentials are
issued.
