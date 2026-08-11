# Supabase migration

Apply `schema.sql`, followed by `rls_policies.sql`, in the Supabase SQL editor.
The production migration also requires:

1. Replacing SQLite JSON embeddings with `pgvector` and native cosine search.
2. Adding verified `user_role` custom claims through a Supabase Auth hook.
3. Moving detokenization behind a server-only service or Edge Function.
4. Storing `TOKEN_ROOT_SECRET` in the platform secret manager, never the browser.

Do not expose the service-role key or vault decryption secret to the frontend.

