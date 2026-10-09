# Security model (principles; enforcement not yet implemented)
Service-role keys server-only; RLS on all tenant tables; server-side entitlement checks; prompt-injection defence for news
(untrusted input, schema-validated LLM output, no tool access to execution); secrets via env only; audit logging.
