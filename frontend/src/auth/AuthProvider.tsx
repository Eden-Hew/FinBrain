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
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);
const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function loadIdentity(token: string): Promise<AuthIdentity> {
  const response = await fetch(`${API_URL}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail ?? "Unable to authorize this account.");
  return body as AuthIdentity;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(authConfigured);
  const [user, setUser] = useState<User | null>(null);
  const [identity, setIdentity] = useState<AuthIdentity | null>(null);

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
        setLoading(false);
        return;
      }
      try {
        const nextIdentity = await loadIdentity(token);
        if (active) setIdentity(nextIdentity);
      } catch {
        if (active) setIdentity(null);
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
    setLoading(true);
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error || !data.session) {
      setLoading(false);
      throw new Error(error?.message ?? "Sign in failed.");
    }
    try {
      setUser(data.user);
      setIdentity(await loadIdentity(data.session.access_token));
    } catch (cause) {
      await supabase.auth.signOut();
      setUser(null);
      setIdentity(null);
      throw cause;
    } finally {
      setLoading(false);
    }
  }, []);

  const signOut = useCallback(async () => {
    await supabase.auth.signOut();
    setUser(null);
    setIdentity(null);
  }, []);

  const value = useMemo(
    () => ({ loading, user, identity, signIn, signOut }),
    [identity, loading, signIn, signOut, user],
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
