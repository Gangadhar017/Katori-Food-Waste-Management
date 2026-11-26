// Who is signed in, the colour theme, and small shared hooks.

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { api, API_BASE, ApiError, getToken, setToken, type LineSnapshot, type Role, type User } from "./api";
import { setTimeZone } from "./format";

interface Session {
  user: User | null;
  ready: boolean;
  enter: (role: Role) => Promise<User>;
  signIn: (email: string, password: string) => Promise<User>;
  signOut: () => void;
  refresh: () => Promise<void>;
  patch: (changes: Partial<Pick<User, "points" | "streak">>) => void;
}

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  const accept = useCallback((next: User) => {
    setTimeZone(next.tenant.timezone);
    setUser(next);
    return next;
  }, []);

  const refresh = useCallback(async () => {
    if (!getToken()) return;
    accept(await api<User>("/api/me"));
  }, [accept]);

  useEffect(() => {
    refresh()
      .catch(() => setToken(null))
      .finally(() => setReady(true));
    const signedOut = () => setUser(null);
    window.addEventListener("katori:signed-out", signedOut);
    return () => window.removeEventListener("katori:signed-out", signedOut);
  }, [refresh]);

  const value = useMemo<Session>(
    () => ({
      user,
      ready,
      refresh,
      enter: async (role) => {
        const result = await api<{ token: string; user: User }>("/api/auth/demo", { method: "POST", body: { role } });
        setToken(result.token);
        return accept(result.user);
      },
      signIn: async (email, password) => {
        const result = await api<{ token: string; user: User }>("/api/auth/login", { method: "POST", body: { email, password } });
        setToken(result.token);
        return accept(result.user);
      },
      signOut: () => {
        setToken(null);
        setUser(null);
      },
      patch: (changes) => setUser((current) => (current ? { ...current, ...changes } : current)),
    }),
    [user, ready, refresh, accept],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession outside SessionProvider");
  return session;
}

// ---------- theme ----------

export function useTheme(): [string, () => void] {
  const [theme, setTheme] = useState<string>(() => {
    try {
      const saved = localStorage.getItem("katori.theme");
      if (saved) return saved;
    } catch {
      /* ignore */
    }
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "dark" ? "#111415" : "#e9eceb");
  }, [theme]);
  const toggle = useCallback(() => {
    setTheme((current) => {
      const next = current === "dark" ? "light" : "dark";
      try {
        localStorage.setItem("katori.theme", next);
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);
  return [theme, toggle];
}

// ---------- data ----------

export interface Loaded<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  /** True while newer data is on its way and the old render is still on screen. */
  stale: boolean;
  reload: () => void;
  set: (next: T) => void;
}

/** Fetch a JSON resource; keep the previous result on screen while a new one loads. */
export function useApi<T>(path: string | null, refreshMs = 0): Loaded<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(path));
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    setLoading(true);
    api<T>(path, { signal: controller.signal })
      .then((result) => {
        setData(result);
        setError(null);
      })
      .catch((failure: ApiError) => {
        if (!controller.signal.aborted) setError(failure.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [path, nonce]);

  useEffect(() => {
    if (!refreshMs) return;
    const timer = window.setInterval(() => setNonce((n) => n + 1), refreshMs);
    return () => window.clearInterval(timer);
  }, [refreshMs]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data, error, loading: loading && data === null, stale: loading && data !== null, reload, set: setData };
}

/** A clock that re-renders on a slow tick, for countdowns. */
export function useNow(everyMs = 30000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), everyMs);
    return () => window.clearInterval(timer);
  }, [everyMs]);
  return now;
}

/**
 * The live serving line. Opens a server-sent event stream and falls back to polling
 * if the stream cannot be opened or drops.
 */
export function useLine(source: { kind: "member" } | { kind: "board"; slug: string }): {
  snapshot: LineSnapshot | null;
  live: boolean;
  push: (next: LineSnapshot) => void;
} {
  const [snapshot, setSnapshot] = useState<LineSnapshot | null>(null);
  const [live, setLive] = useState(false);
  const slug = source.kind === "board" ? source.slug : "";
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    let stream: EventSource | null = null;
    let poll = 0;
    let retry = 0;

    const fetchOnce = async () => {
      try {
        const next =
          source.kind === "member"
            ? await api<LineSnapshot>("/api/line")
            : (await api<{ line: LineSnapshot }>(`/api/public/${slug}/board`)).line;
        if (alive.current) setSnapshot(next);
      } catch {
        /* keep the last known state on screen */
      }
    };
    const startPolling = () => {
      if (!poll) poll = window.setInterval(fetchOnce, 3000);
    };
    const open = async () => {
      try {
        let url = `${API_BASE}/api/public/${slug}/board/stream`;
        if (source.kind === "member") {
          const { ticket } = await api<{ ticket: string }>("/api/line/stream-ticket", { method: "POST" });
          url = `${API_BASE}/api/line/stream?ticket=${encodeURIComponent(ticket)}`;
        }
        if (!alive.current) return;
        stream = new EventSource(url);
        stream.onopen = () => {
          setLive(true);
          window.clearInterval(poll);
          poll = 0;
        };
        stream.onmessage = (event) => setSnapshot(JSON.parse(event.data) as LineSnapshot);
        stream.onerror = () => {
          // The server ends streams after ten minutes and tickets are single-use: start a fresh one.
          stream?.close();
          setLive(false);
          startPolling();
          retry = window.setTimeout(open, 4000);
        };
      } catch {
        startPolling();
        retry = window.setTimeout(open, 8000);
      }
    };

    fetchOnce();
    open();
    return () => {
      alive.current = false;
      stream?.close();
      window.clearInterval(poll);
      window.clearTimeout(retry);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source.kind, slug]);

  return { snapshot, live, push: setSnapshot };
}
