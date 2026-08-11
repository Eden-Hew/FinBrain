# Detokenization Edge Function

This directory is reserved for the production detokenization boundary. The prototype intentionally
keeps decryption in FastAPI until Supabase Auth supplies verified role claims. Do not deploy an Edge
Function that accepts a caller-provided role or uses the service-role key without independently
validating the caller's JWT; doing so would bypass the RLS policy the migration is meant to add.

