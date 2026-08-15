# Supabase Auth and JWT Setup

FinBrain uses Supabase Auth for identity and FastAPI for authorization. The browser receives a
short-lived Supabase access token and sends it in the `Authorization: Bearer` header. FastAPI
verifies the token against the project JWKS endpoint, loads the user's authoritative role from
`public.user_roles`, and applies that role to every protected operation.

## 1. Apply the migration

From the repository root:

```powershell
npx.cmd supabase login
npx.cmd supabase link --project-ref YOUR_PROJECT_REF
npx.cmd supabase db push
```

Migration `202608150002_supabase_auth_and_user_roles.sql` creates the role table, adds user
ownership and audit actor fields, and installs `public.custom_access_token_hook(jsonb)`.

## 2. Use an asymmetric JWT signing key

In Supabase Dashboard, open **Authentication > Signing Keys**. FinBrain accepts `RS256` and
`ES256` tokens and verifies them through:

```text
https://YOUR_PROJECT_REF.supabase.co/auth/v1/.well-known/jwks.json
```

If the project still uses the legacy shared JWT secret, rotate to an asymmetric signing key before
using authenticated FinBrain routes. Allow the Supabase JWKS caches to propagate before revoking
the old key.

## 3. Enable the access-token hook

In **Authentication > Hooks**, enable **Custom Access Token** and select:

```text
public.custom_access_token_hook
```

The hook copies the active backend role into the signed top-level `user_role` claim. FastAPI still
checks `public.user_roles` on every request, so disabling a user takes effect without waiting for
the access token to expire.

## 4. Create and provision users

Create demonstration users under **Authentication > Users**. Do not commit their passwords.

Obtain their IDs in the SQL editor:

```sql
select id, email from auth.users order by email;
```

Assign exactly one FinBrain role to each user:

```sql
insert into public.user_roles (user_id, user_role)
values
  ('USER_UUID_1', 'general_employee'),
  ('USER_UUID_2', 'finance_ops'),
  ('USER_UUID_3', 'owner_director'),
  ('USER_UUID_4', 'compliance')
on conflict (user_id) do update
set user_role = excluded.user_role,
    active = true,
    updated_at = now();
```

After changing a role, sign out and sign back in so the browser receives a refreshed custom claim.

## 5. Configure the backend

Add these values to ignored `backend/.env`:

```dotenv
SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_JWT_ISSUER=https://YOUR_PROJECT_REF.supabase.co/auth/v1
SUPABASE_JWT_AUDIENCE=authenticated
SUPABASE_JWT_ALGORITHMS=RS256,ES256
```

The backend needs neither the publishable key nor the JWT signing secret for asymmetric local
verification. Never place a secret key or service-role key in frontend files.

## 6. Configure the frontend

Create ignored `frontend/.env`:

```dotenv
VITE_API_URL=http://127.0.0.1:8000
VITE_SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=YOUR_PUBLISHABLE_KEY
```

The publishable key is safe to use in a public client. Database passwords and secret/service keys
are not.

## 7. Verify

Start FinBrain and sign in with each provisioned account. Confirm:

- `/auth/me` returns that account's assigned FinBrain role.
- A missing or modified access token returns HTTP 401.
- An unprovisioned or inactive user returns HTTP 403.
- Finance can create proposals but cannot approve them.
- Owner/director can approve and implement recommendations.
- Compliance can open both audit chains and compare role policies.
- General employees cannot ingest files, synchronize Gmail, view recommendations, or read audits.
- One account cannot load another account's conversation or citation by ID.

The health endpoint remains public. Gmail and Telegram workers remain trusted backend processes and
do not use browser user tokens.
