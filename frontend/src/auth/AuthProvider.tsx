import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { User } from "@supabase/supabase-js";
import type { Role } from "../api/client";
import { authConfigured, supabase } from "./supabase";

interface AuthIdentity {
  user_id: string;
  email: string | null;
  role: Role;
}

interface AuthContextValue {
  loading: boolean;
  user: User | null;
  identity: AuthIdentity | null;
  authError: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);
const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

class IdentityError extends Error {
  constructor(public readonly code: string, public readonly requestId: string | null) {
    super(code);
    this.name = "IdentityError";
  }
}

function identityErrorMessage(error: unknown): string {
  if (!(error instanceof IdentityError)) return "Unable to authorize this account.";
  const suffix = error.requestId ? ` Reference: ${error.requestId}` : "";
  if (error.code === "missing_tenant_claim") {
    return `Your session does not contain the latest workspace access claims. Please sign in again.${suffix}`;
  }
  if (error.code === "user_not_provisioned") {
    return `This account has not been assigned to a FinBrain workspace.${suffix}`;
  }
  if (error.code === "stale_user_role_claim") {
    return `Your assigned role changed. Please sign in again.${suffix}`;
  }
  if (error.code === "jwks_unavailable" || error.code === "signing_key_unavailable") {
    return `The authentication service is temporarily unavailable. Please retry.${suffix}`;
  }
  return `The backend could not verify this session (${error.code}).${suffix}`;
}

function invalidatesSession(error: unknown): boolean {
  return error instanceof IdentityError && new Set([
    "expired_access_token",
    "invalid_access_token",
    "invalid_signature",
    "invalid_issuer",
    "invalid_audience",
    "invalid_supabase_role",
    "missing_tenant_claim",
    "missing_exp_claim",
    "missing_iss_claim",
    "missing_sub_claim",
    "missing_aud_claim",
    "invalid_identity_claims",
  ]).has(error.code);
}

async function loadIdentity(token: string): Promise<AuthIdentity> {
  const response = await fetch(`${API_URL}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new IdentityError(
      body.detail ?? `request_failed_${response.status}`,
      response.headers.get("X-Request-ID"),
    );
  }
  return body as AuthIdentity;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(authConfigured);
  const [user, setUser] = useState<User | null>(null);
  const [identity, setIdentity] = useState<AuthIdentity | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);

  useEffect(() => {
    if (!authConfigured) {
      return;
    }
    let active = true;
    const applySession = async (token: string | null, sessionUser: User | null) => {
      if (!active) return;
      setUser(sessionUser);
      if (!token || !sessionUser) {
        setIdentity(null);
        setAuthError(null);
        setLoading(false);
        return;
      }
      try {
        const nextIdentity = await loadIdentity(token);
        if (active) {
          setIdentity(nextIdentity);
          setAuthError(null);
        }
      } catch (error) {
        if (active) {
          setIdentity(null);
          setAuthError(identityErrorMessage(error));
          if (invalidatesSession(error)) {
            await supabase.auth.signOut();
            setUser(null);
          }
        }
      } finally {
        if (active) setLoading(false);
      }
    };
    void supabase.auth.getSession().then(({ data }) =>
      applySession(data.session?.access_token ?? null, data.session?.user ?? null));
    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      void applySession(session?.access_token ?? null, session?.user ?? null);
    });
    return () => {
      active = false;
      data.subscription.unsubscribe();
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    if (!authConfigured) {
      throw new Error("Supabase Auth is not configured for this frontend.");
    }
    setAuthError(null);
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error || !data.session) {
      throw new Error(error?.message ?? "Sign in failed.");
    }
    try {
      const { data: refreshed, error: refreshError } = await supabase.auth.refreshSession(
        data.session,
      );
      if (refreshError || !refreshed.session) {
        throw new Error(refreshError?.message ?? "Unable to refresh the signed-in session.");
      }
      setUser(data.user);
      setIdentity(await loadIdentity(refreshed.session.access_token));
      setAuthError(null);
    } catch (cause) {
      await supabase.auth.signOut();
      setUser(null);
      setIdentity(null);
      const message = identityErrorMessage(cause);
      setAuthError(message);
      throw new Error(message, { cause });
    }
  }, []);

  const signOut = useCallback(async () => {
    await supabase.auth.signOut();
    setUser(null);
    setIdentity(null);
    setAuthError(null);
  }, []);

  const value = useMemo(
    () => ({ loading, user, identity, authError, signIn, signOut }),
    [authError, identity, loading, signIn, signOut, user],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// The auth hook intentionally shares the provider's private context.
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
