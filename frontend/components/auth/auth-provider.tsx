"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { getToken, setToken, clearToken, type AuthUser } from "@/lib/auth";
import { authMe, authLogin, authRegister, authGoogle, authFacebook } from "@/lib/api";

type Consent = { regulaminVersion: string; privacyVersion: string };

type AuthContextType = {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (
    email: string,
    password: string,
    passwordConfirm: string,
    consent: Consent,
    promoCode?: string
  ) => Promise<void>;
  loginWithGoogle: (idToken: string, consent?: Consent) => Promise<void>;
  loginWithFacebook: (accessToken: string, consent?: Consent) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setLoading(false);
      return;
    }
    authMe()
      .then(setUser)
      .catch(() => clearToken())
      .finally(() => setLoading(false));
  }, []);

  const login = async (email: string, password: string) => {
    const res = await authLogin(email, password);
    setToken(res.token);
    setUser(res.user);
  };

  const register = async (
    email: string,
    password: string,
    passwordConfirm: string,
    consent: { regulaminVersion: string; privacyVersion: string },
    promoCode?: string
  ) => {
    const res = await authRegister(email, password, passwordConfirm, consent, promoCode);
    setToken(res.token);
    setUser(res.user);
  };

  const loginWithGoogle = async (idToken: string, consent?: Consent) => {
    const res = await authGoogle(idToken, consent);
    setToken(res.token);
    setUser(res.user);
  };

  const loginWithFacebook = async (accessToken: string, consent?: Consent) => {
    const res = await authFacebook(accessToken, consent);
    setToken(res.token);
    setUser(res.user);
  };

  const logout = () => {
    clearToken();
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{ user, loading, login, register, loginWithGoogle, loginWithFacebook, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
