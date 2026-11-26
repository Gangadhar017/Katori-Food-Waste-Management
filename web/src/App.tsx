import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { Loading } from "./components/ui";
import { Frame, Phone } from "./layouts";
import type { Role } from "./lib/api";
import { HOME } from "./lib/routes";
import { useSession, useTheme } from "./lib/session";
import { Board } from "./pages/Board";
import { Counter } from "./pages/kitchen/Counter";
import { Log } from "./pages/kitchen/Log";
import { Sheet } from "./pages/kitchen/Sheet";
import { Landing } from "./pages/Landing";
import { FoodChart } from "./pages/manager/FoodChart";
import { Forecast } from "./pages/manager/Forecast";
import { Models } from "./pages/manager/Models";
import { Overview } from "./pages/manager/Overview";
import { Waste } from "./pages/manager/Waste";
import { Line } from "./pages/resident/Line";
import { Play } from "./pages/resident/Play";
import { Ranks } from "./pages/resident/Ranks";
import { Today } from "./pages/resident/Today";
import { Week } from "./pages/resident/Week";

function Only({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user, ready } = useSession();
  if (!ready) return <div style={{ padding: 24 }}><Loading /></div>;
  if (!user) return <Navigate to="/" replace />;
  if (!roles.includes(user.role)) return <Navigate to={HOME[user.role]} replace />;
  return <>{children}</>;
}

export function App() {
  useTheme();
  const resident = (page: ReactNode) => (
    <Only roles={["student"]}>
      <Phone>{page}</Phone>
    </Only>
  );
  const staff = (page: ReactNode) => (
    <Only roles={["kitchen", "manager"]}>
      <Frame>{page}</Frame>
    </Only>
  );
  const manager = (page: ReactNode) => (
    <Only roles={["manager"]}>
      <Frame>{page}</Frame>
    </Only>
  );
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/board/:slug" element={<Board />} />
      <Route path="/home" element={resident(<Today />)} />
      <Route path="/week" element={resident(<Week />)} />
      <Route path="/line" element={resident(<Line />)} />
      <Route path="/play/:game" element={resident(<Play />)} />
      <Route path="/ranks" element={resident(<Ranks />)} />
      <Route path="/kitchen" element={staff(<Sheet />)} />
      <Route path="/kitchen/log" element={staff(<Log />)} />
      <Route path="/kitchen/line" element={staff(<Counter />)} />
      <Route path="/manage" element={manager(<Overview />)} />
      <Route path="/manage/forecast" element={manager(<Forecast />)} />
      <Route path="/manage/waste" element={manager(<Waste />)} />
      <Route path="/manage/chart" element={manager(<FoodChart />)} />
      <Route path="/manage/models" element={manager(<Models />)} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
