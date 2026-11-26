// The two shells: a rail-and-page frame for staff, a phone column for residents.

import type { ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";

import { Brand, Icon, useToast } from "./components/ui";
import type { MySummary, Role } from "./lib/api";
import { num } from "./lib/format";
import { HOME as ROLE_HOME } from "./lib/routes";
import { useApi, useSession, useTheme } from "./lib/session";

const ROLE_NAME: Record<Role, string> = { student: "Resident", kitchen: "Kitchen", manager: "Manager" };
const ROLE_TITLE: Record<Role, string> = { student: "Resident", kitchen: "Head cook", manager: "Mess manager" };

/** In the demo anyone can step into another role with one click. */
function RoleSwitch() {
  const { user, enter } = useSession();
  const navigate = useNavigate();
  const toast = useToast();
  if (!user?.tenant.is_demo) return null;
  return (
    <span className="row" style={{ gap: 6 }}>
      <span className="label">View as</span>
      {(Object.keys(ROLE_NAME) as Role[]).map((role) => (
        <button
          key={role}
          className={`btn small ${role === user.role ? "" : "ghost"}`}
          style={{ minHeight: 26, padding: "0 9px", fontSize: 12 }}
          aria-pressed={role === user.role}
          onClick={async () => {
            if (role === user.role) return;
            try {
              await enter(role);
              navigate(ROLE_HOME[role]);
            } catch (error) {
              toast((error as Error).message);
            }
          }}
        >
          {ROLE_NAME[role]}
        </button>
      ))}
    </span>
  );
}

function ThemeButton() {
  const [theme, toggle] = useTheme();
  return (
    <button className="btn ghost small" onClick={toggle} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`} title="Light / dark">
      <Icon name={theme === "dark" ? "sun" : "moon"} size={16} />
    </button>
  );
}

function SignOut() {
  const { signOut } = useSession();
  const navigate = useNavigate();
  return (
    <button
      className="btn ghost small"
      onClick={() => {
        signOut();
        navigate("/");
      }}
      aria-label="Sign out"
      title="Sign out"
    >
      <Icon name="exit" size={16} />
    </button>
  );
}

export function Frame({ children }: { children: ReactNode }) {
  const { user } = useSession();
  if (!user) return null;
  const link = (to: string, icon: string, text: string, end = false) => (
    <NavLink to={to} end={end} className={({ isActive }) => (isActive ? "active" : "")}>
      <Icon name={icon} />
      {text}
    </NavLink>
  );
  return (
    <div className="frame">
      <aside className="rail">
        <Link to={ROLE_HOME[user.role]} style={{ textDecoration: "none" }}>
          <Brand sub={user.tenant.name} />
        </Link>
        <nav className="nav" aria-label="Sections">
          {user.role === "manager" && (
            <>
              {link("/manage", "gauge", "Overview", true)}
              {link("/manage/forecast", "trend", "Forecast")}
              {link("/manage/waste", "bin", "Waste")}
              {link("/manage/chart", "table", "Food chart")}
              {link("/manage/models", "nodes", "Models")}
              <span className="label" style={{ padding: "14px 18px 4px" }}>Kitchen</span>
            </>
          )}
          {link("/kitchen", "sheet", "Cook sheet", true)}
          {link("/kitchen/log", "scale", "Weigh-in")}
          {link("/kitchen/line", "bell", "Counter")}
        </nav>
        <div className="rail-foot">
          <div className="who">
            <b>{user.name}</b>
            <span className="label">{ROLE_TITLE[user.role]}</span>
          </div>
          <div className="row" style={{ gap: 6 }}>
            <ThemeButton />
            <SignOut />
            <Link className="btn ghost small" to={`/board/${user.tenant.slug}`} target="_blank" title="Open the dining-hall display">
              Wall display
            </Link>
          </div>
        </div>
      </aside>
      <main className="main">
        {user.tenant.is_demo && (
          <div className="demo-strip no-print">
            <span className="tag copper">Demo</span>
            <span style={{ flex: 1, minWidth: 180 }}>
              {user.tenant.name} is a simulated hostel of {num(user.tenant.strength)} residents. Changes reset when the server restarts.
            </span>
            <RoleSwitch />
          </div>
        )}
        <div className="page">{children}</div>
      </main>
    </div>
  );
}

export function Phone({ children }: { children: ReactNode }) {
  const { user } = useSession();
  const summary = useApi<MySummary>(user ? "/api/me/summary" : null, 60000);
  if (!user) return null;
  const tab = (to: string, icon: string, text: string) => (
    <NavLink to={to} className={({ isActive }) => (isActive ? "active" : "")}>
      <Icon name={icon} size={22} />
      {text}
    </NavLink>
  );
  return (
    <div className="phone">
      <header className="phone-head">
        <div className="spread">
          <div>
            <div className="brand-name">Katori</div>
            <div className="label" style={{ marginTop: 4 }}>{user.tenant.name} · Room {user.room}</div>
          </div>
          <div className="row" style={{ gap: 6 }}>
            <ThemeButton />
            <SignOut />
          </div>
        </div>
        <div className="phone-stats">
          <div>
            <span className="label">Points</span>
            <span className="figure">{num(user.points)}</span>
          </div>
          <div>
            <span className="label">Streak</span>
            <span className="figure">{user.streak}<span className="unit">days</span></span>
          </div>
          <div>
            <span className="label">Rank of {num(user.tenant.strength)}</span>
            <span className="figure">{summary.data ? `#${summary.data.rank}` : "–"}</span>
          </div>
        </div>
      </header>
      {user.tenant.is_demo && (
        <div className="demo-strip no-print" style={{ margin: 0 }}>
          <span className="tag copper">Demo</span>
          <RoleSwitch />
        </div>
      )}
      <div className="phone-body">{children}</div>
      <nav className="tabbar" aria-label="Sections">
        {tab("/home", "plate", "Today")}
        {tab("/week", "week", "Chart")}
        {tab("/line", "line", "Line")}
        {tab("/ranks", "trophy", "Board")}
      </nav>
    </div>
  );
}
