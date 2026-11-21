import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { login as loginRequest } from "../api/auth";
import { getMe } from "../api/users";
import { setUnauthorizedHandler } from "../api/client";
import { ROLES, STORAGE_KEYS } from "../utils/constants";

const AuthContext = createContext(null);

function readStoredUser() {
  try {
    return JSON.parse(sessionStorage.getItem(STORAGE_KEYS.USER));
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(readStoredUser);
  // true while we confirm a stored token after a page refresh
  const [checking, setChecking] = useState(() => Boolean(sessionStorage.getItem(STORAGE_KEYS.TOKEN)));
  const [sessionMessage, setSessionMessage] = useState(null);

  const clearSession = useCallback(() => {
    sessionStorage.removeItem(STORAGE_KEYS.TOKEN);
    sessionStorage.removeItem(STORAGE_KEYS.USER);
    setUser(null);
  }, []);

  const login = useCallback(async (email, password) => {
    const res = await loginRequest(email, password);
    sessionStorage.setItem(STORAGE_KEYS.TOKEN, res.access_token);
    sessionStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(res.user));
    setSessionMessage(null);
    setUser(res.user);
    return res.user;
  }, []);

  const logout = useCallback(() => {
    clearSession();
    setSessionMessage(null);
  }, [clearSession]);

  // Any request that comes back with an expired/invalid token signs the user out
  useEffect(() => {
    setUnauthorizedHandler((err) => {
      clearSession();
      setSessionMessage(err.message);
    });
    return () => setUnauthorizedHandler(null);
  }, [clearSession]);

  // After a refresh: check the stored token still works and get the current role
  useEffect(() => {
    if (!sessionStorage.getItem(STORAGE_KEYS.TOKEN)) return undefined;
    let cancelled = false;
    getMe()
      .then((me) => {
        if (cancelled) return;
        setUser(me);
        sessionStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(me));
      })
      .catch(() => {
        // 401s are handled by the unauthorized handler; on network errors we keep the stored user
      })
      .finally(() => {
        if (!cancelled) setChecking(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo(
    () => ({ user, isManager: user?.role === ROLES.MANAGER, checking, sessionMessage, login, logout }),
    [user, checking, sessionMessage, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
