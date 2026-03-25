"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth/auth-provider";
import { getCollection, changePassword, deleteAccount, exportUserData, authMe, updateUserProfile, type AuthMeResponse } from "@/lib/api";
import { Loader2, User, LogOut, Download, ChevronDown, ChevronUp, Shield, Trash2 } from "lucide-react";

const USER_TYPE_OPTIONS = [
  { value: "kolekcjoner", label: "Kolekcjoner" },
  { value: "okazjonalny_kupujacy", label: "Okazjonalny kupujący" },
  { value: "sprzedajacy", label: "Sprzedający" },
];

const COLLECTION_SIZE_OPTIONS = [
  { value: "0-5", label: "0–5" },
  { value: "6-20", label: "6–20" },
  { value: "21-50", label: "21–50" },
  { value: "50+", label: "50+" },
];

const USER_TYPE_LABELS: Record<string, string> = {
  kolekcjoner: "Kolekcjoner",
  okazjonalny_kupujacy: "Okazjonalny kupujący",
  sprzedajacy: "Sprzedający",
};

function SectionHeader({ title }: { title: string }) {
  return (
    <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">{title}</p>
  );
}

export default function AccountPage() {
  const { user, loading: authLoading, logout } = useAuth();
  const router = useRouter();
  const [itemCount, setItemCount] = useState<number | null>(null);
  const [profile, setProfile] = useState<AuthMeResponse | null>(null);

  // Profil
  const [editingProfile, setEditingProfile] = useState(false);
  const [profileUserType, setProfileUserType] = useState("");
  const [profileCollectionSize, setProfileCollectionSize] = useState("");
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileSaved, setProfileSaved] = useState(false);

  // Zmiana hasła (accordion)
  const [pwOpen, setPwOpen] = useState(false);
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [newPwConfirm, setNewPwConfirm] = useState("");
  const [pwError, setPwError] = useState<string | null>(null);
  const [pwSuccess, setPwSuccess] = useState(false);
  const [pwLoading, setPwLoading] = useState(false);

  // Usuń konto
  const [confirmDeleteAccount, setConfirmDeleteAccount] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { router.replace("/login?next=/account"); return; }
    getCollection()
      .then((items) => setItemCount(items.length))
      .catch(() => setItemCount(0));
    authMe()
      .then((data) => {
        setProfile(data);
        setProfileUserType(data.user_type ?? "");
        setProfileCollectionSize(data.collection_size_range ?? "");
      })
      .catch(() => {});
  }, [user, authLoading, router]);

  const handleLogout = () => {
    logout();
    router.replace("/analyze");
  };

  async function handleChangePassword() {
    setPwError(null);
    setPwSuccess(false);
    if (!currentPw || !newPw || !newPwConfirm) { setPwError("Wypełnij wszystkie pola."); return; }
    if (newPw !== newPwConfirm) { setPwError("Nowe hasła nie są identyczne."); return; }
    if (newPw.length < 8) { setPwError("Nowe hasło musi mieć co najmniej 8 znaków."); return; }
    setPwLoading(true);
    try {
      await changePassword(currentPw, newPw);
      setPwSuccess(true);
      setCurrentPw(""); setNewPw(""); setNewPwConfirm("");
      setTimeout(() => setPwOpen(false), 1500);
    } catch (e: any) {
      setPwError(e.message || "Nie udało się zmienić hasła.");
    } finally {
      setPwLoading(false);
    }
  }

  async function handleSaveProfile() {
    setProfileSaving(true);
    setProfileSaved(false);
    try {
      await updateUserProfile(profileUserType || null, profileCollectionSize || null);
      setProfile((prev) => prev ? { ...prev, user_type: profileUserType || null, collection_size_range: profileCollectionSize || null } : prev);
      setProfileSaved(true);
      setEditingProfile(false);
    } catch { /* ignoruj */ } finally {
      setProfileSaving(false);
    }
  }

  async function handleExport() {
    try {
      const data = await exportUserData();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "legitscore-export.json";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      alert(e.message || "Nie udało się pobrać danych.");
    }
  }

  async function handleDeleteAccount() {
    setDeleteLoading(true);
    try {
      await deleteAccount();
      logout();
      router.replace("/analyze");
    } catch (e: any) {
      alert(e.message || "Nie udało się usunąć konta.");
      setDeleteLoading(false);
    }
  }

  if (authLoading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-emerald-400" />
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="flex flex-1 flex-col gap-5 py-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-slate-50">Moje konto</h1>
        <p className="mt-0.5 text-xs text-muted-foreground">Ustawienia i dane konta</p>
      </div>

      {/* ── PROFIL ─────────────────────────────────────────────── */}
      <div className="glass-card p-5 space-y-4">
        <div className="flex items-center justify-between">
          <SectionHeader title="Profil" />
          {!editingProfile && (
            <button
              onClick={() => { setEditingProfile(true); setProfileSaved(false); }}
              className="text-xs text-slate-500 hover:text-slate-300 transition"
            >
              Edytuj
            </button>
          )}
        </div>

        {/* Email + ikona */}
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-400 shrink-0">
            <User className="h-4 w-4" />
          </div>
          <div>
            <p className="text-sm font-medium text-slate-100">{user.email}</p>
            <p className="text-[11px] text-muted-foreground">Konto LegitScore</p>
          </div>
        </div>

        {!editingProfile ? (
          <div className="space-y-2 border-t border-border/30 pt-3">
            <div className="flex justify-between text-xs">
              <span className="text-slate-500">Typ użytkownika</span>
              <span className="text-slate-200">
                {profile?.user_type ? USER_TYPE_LABELS[profile.user_type] ?? profile.user_type : <span className="text-slate-600">Nie podano</span>}
              </span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-slate-500">Rozmiar kolekcji</span>
              <span className="text-slate-200">
                {profile?.collection_size_range ?? <span className="text-slate-600">Nie podano</span>}
              </span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-slate-500">Koszulki w kolekcji</span>
              <span className="text-slate-200">{itemCount === null ? "…" : itemCount}</span>
            </div>
            {profileSaved && <p className="text-xs text-emerald-400">Zapisano.</p>}
          </div>
        ) : (
          <div className="space-y-4 border-t border-border/30 pt-3">
            <div className="space-y-2">
              <p className="text-xs text-slate-400">Typ użytkownika</p>
              <div className="flex flex-col gap-1.5">
                {USER_TYPE_OPTIONS.map((o) => (
                  <button
                    key={o.value}
                    type="button"
                    onClick={() => setProfileUserType(o.value)}
                    className={`rounded-xl border px-4 py-2 text-sm text-left transition ${
                      profileUserType === o.value
                        ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-300"
                        : "border-border/60 bg-slate-900/40 text-slate-300 hover:border-slate-500"
                    }`}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="space-y-2">
              <p className="text-xs text-slate-400">Rozmiar kolekcji</p>
              <div className="grid grid-cols-4 gap-2">
                {COLLECTION_SIZE_OPTIONS.map((o) => (
                  <button
                    key={o.value}
                    type="button"
                    onClick={() => setProfileCollectionSize(o.value)}
                    className={`rounded-xl border px-2 py-2 text-sm text-center transition ${
                      profileCollectionSize === o.value
                        ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-300"
                        : "border-border/60 bg-slate-900/40 text-slate-300 hover:border-slate-500"
                    }`}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={handleSaveProfile}
                disabled={profileSaving}
                className="rounded-full bg-emerald-500 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-emerald-400 disabled:opacity-60"
              >
                {profileSaving ? "Zapisywanie..." : "Zapisz"}
              </button>
              <button
                onClick={() => { setEditingProfile(false); setProfileUserType(profile?.user_type ?? ""); setProfileCollectionSize(profile?.collection_size_range ?? ""); }}
                className="text-xs text-slate-500 hover:text-slate-300"
              >
                Anuluj
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── BEZPIECZEŃSTWO ─────────────────────────────────────── */}
      <div className="glass-card p-5 space-y-3">
        <SectionHeader title="Bezpieczeństwo" />
        <button
          onClick={() => { setPwOpen((v) => !v); setPwError(null); setPwSuccess(false); }}
          className="flex w-full items-center justify-between rounded-lg py-1 text-sm text-slate-300 hover:text-slate-100 transition"
        >
          <span className="flex items-center gap-2">
            <Shield className="h-4 w-4 text-slate-500" />
            Zmień hasło
          </span>
          {pwOpen ? <ChevronUp className="h-4 w-4 text-slate-500" /> : <ChevronDown className="h-4 w-4 text-slate-500" />}
        </button>

        {pwOpen && (
          <div className="space-y-3 border-t border-border/30 pt-3">
            <input
              type="password"
              placeholder="Obecne hasło"
              value={currentPw}
              onChange={(e) => { setCurrentPw(e.target.value); setPwError(null); setPwSuccess(false); }}
              className="w-full rounded-xl border border-border/60 bg-slate-900/60 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-emerald-500/60"
            />
            <input
              type="password"
              placeholder="Nowe hasło (min. 8 znaków)"
              value={newPw}
              onChange={(e) => { setNewPw(e.target.value); setPwError(null); setPwSuccess(false); }}
              className="w-full rounded-xl border border-border/60 bg-slate-900/60 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-emerald-500/60"
            />
            <input
              type="password"
              placeholder="Powtórz nowe hasło"
              value={newPwConfirm}
              onChange={(e) => { setNewPwConfirm(e.target.value); setPwError(null); setPwSuccess(false); }}
              className="w-full rounded-xl border border-border/60 bg-slate-900/60 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-emerald-500/60"
            />
            {pwError && <p className="text-xs text-red-400">{pwError}</p>}
            {pwSuccess && <p className="text-xs text-emerald-400">Hasło zostało zmienione.</p>}
            <button
              onClick={handleChangePassword}
              disabled={pwLoading}
              className="rounded-full bg-emerald-500 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-emerald-400 disabled:opacity-60"
            >
              {pwLoading ? "Zapisywanie..." : "Zmień hasło"}
            </button>
          </div>
        )}
      </div>

      {/* ── DANE I PRYWATNOŚĆ ──────────────────────────────────── */}
      <div className="glass-card p-5 space-y-3">
        <SectionHeader title="Dane i prywatność" />
        <button
          onClick={handleExport}
          className="flex items-center gap-2 rounded-lg py-1 text-sm text-slate-300 hover:text-slate-100 transition"
        >
          <Download className="h-4 w-4 text-slate-500" />
          Pobierz moje dane (JSON)
        </button>
      </div>

      {/* ── STREFA NIEBEZPIECZNA ───────────────────────────────── */}
      <div className="glass-card p-5 space-y-3 border border-red-500/10">
        <SectionHeader title="Strefa niebezpieczna" />
        <p className="text-xs text-slate-400">
          Usunięcie konta jest nieodwracalne — trwale usuwa kolekcję i wszystkie analizy.
        </p>
        {!confirmDeleteAccount ? (
          <button
            onClick={() => setConfirmDeleteAccount(true)}
            className="flex items-center gap-2 rounded-full border border-red-500/40 px-4 py-2 text-sm text-red-400 hover:border-red-400 hover:text-red-300 transition"
          >
            <Trash2 className="h-4 w-4" />
            Usuń konto
          </button>
        ) : (
          <div className="space-y-2">
            <p className="text-xs text-red-400 font-medium">Czy na pewno? Tej operacji nie można cofnąć.</p>
            <div className="flex gap-2">
              <button
                onClick={handleDeleteAccount}
                disabled={deleteLoading}
                className="rounded-full bg-red-500/80 px-4 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-60"
              >
                {deleteLoading ? "Usuwanie..." : "Tak, usuń konto"}
              </button>
              <button
                onClick={() => setConfirmDeleteAccount(false)}
                className="rounded-full border border-slate-600/50 px-4 py-2 text-sm text-slate-400 hover:text-slate-200"
              >
                Anuluj
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── AKCJE ─────────────────────────────────────────────── */}
      <div className="glass-card p-5 space-y-2">
        <SectionHeader title="Akcje" />
        <button
          onClick={handleLogout}
          className="flex items-center gap-2 rounded-lg py-2 text-sm text-slate-400 transition hover:text-red-400"
        >
          <LogOut className="h-4 w-4" />
          Wyloguj się
        </button>
      </div>
    </div>
  );
}
