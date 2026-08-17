# Vercel Deployment for FinBrain Frontend

Date: 2026-08-17

## Problem

Host the FinBrain frontend (Vite + React SPA) on Vercel, separate from the backend which is
deployed to Railway via Docker. The frontend is a static SPA with no URL-based routing, so
deployment is a standard Vite build served as static files.

## Goal

A Vercel deployment that:
- Builds the frontend with `npm run build` (tsc + vite build) into `dist`.
- Serves the SPA with a fallback rewrite to `index.html`.
- Reads `VITE_API_URL`, `VITE_SUPABASE_URL`, and `VITE_SUPABASE_PUBLISHABLE_KEY` from Vercel
  environment variables at build time.

## Scope

- `frontend/vercel.json` (new)
- `frontend/.env.example` (update comments/example)
- `README.md` (deployment subsection)
- Backend `CORS_ORIGINS` / `CORS_ORIGIN_REGEX` documentation only (no code change; the settings
  already exist in `app/config.py`).

No application code changes: `main.tsx`, `supabase.ts`, `client.ts`, and `AuthProvider.tsx`
already read `import.meta.env.VITE_*`.

## vercel.json

```json
{
  "framework": "vite",
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
}
```

The SPA rewrite is defensive: the app has no client-side routes, and Supabase Auth redirects use
URL hash fragments, but the rewrite guarantees any deep link resolves to the app.

## Vercel environment variables (build-time, public)

- `VITE_API_URL` = Railway backend URL (e.g. `https://<service>.up.railway.app`)
- `VITE_SUPABASE_URL` = `https://<ref>.supabase.co`
- `VITE_SUPABASE_PUBLISHABLE_KEY` = publishable key

`VITE_*` values are inlined at build time; `.env` is gitignored, so these must be set in the
Vercel project settings.

## Supabase Auth configuration (dashboard, no code)

- Set **Site URL** to the Vercel URL.
- Add the Vercel URL to **Redirect URLs** so email-confirmation/OAuth links return to Vercel.
- `supabase.ts` already uses `detectSessionInUrl: true`.

## Backend CORS (Railway env)

Set `CORS_ORIGINS` and `CORS_ORIGIN_REGEX` to include the Vercel domain, otherwise the browser
blocks cross-origin API calls. The default regex in `app/config.py` only matches localhost.

## Vercel root directory

Set the Vercel project Root Directory to `frontend` (monorepo layout with `backend/` alongside).

## Out of scope

- Backend/Railway deployment (covered by `Dockerfile` + `railway.json`).
- Supabase migrations/seeding.
- Custom domains.