// The API client and the shapes it returns.

export const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
const TOKEN_KEY = "katori.token";

export type Role = "student" | "kitchen" | "manager";
export type MealName = "breakfast" | "lunch" | "snacks" | "dinner";
export type SittingState = "open" | "cooking" | "serving" | "done";

export interface TenantInfo {
  slug: string;
  name: string;
  city: string;
  kind: string;
  strength: number;
  service_level: number;
  counters_open: number;
  katori_since: string | null;
  is_demo: boolean;
  simulated: boolean;
  today: string;
  timezone: string;
}
export interface User {
  id: number;
  name: string;
  email: string;
  role: Role;
  room: string;
  diet: string;
  points: number;
  streak: number;
  tenant: TenantInfo;
}
export interface DishRef {
  id: number;
  name: string;
  category?: string;
  veg: boolean;
  slow?: boolean;
}
export interface CalendarNote {
  kind: string;
  label: string;
}
export interface Meal {
  day: string;
  meal: MealName;
  starts_at: string;
  ends_at: string;
  cutoff_at: string;
  state: SittingState;
  rsvp: "eat" | "skip";
  dishes: DishRef[];
  expected: number | null;
  notices: number;
  rated: boolean;
  can_rate: boolean;
}
export interface DayMeals {
  day: string;
  weekday: string;
  calendar: CalendarNote | null;
  meals: Meal[];
}
export interface MealsResponse {
  today: string;
  now: string;
  points: number;
  streak: number;
  days: DayMeals[];
}
export interface Ticket {
  token: number;
  status: "waiting" | "called" | "served";
  counter: number | null;
  ahead: number;
  eta_s: number;
  eta_upper_s: number;
  joined_at: string;
  quoted_wait_s: number;
  waited_s: number;
}
export interface LineSnapshot {
  service: {
    day: string;
    meal: MealName;
    phase: "open" | "upcoming";
    opens_at: string;
    closes_at: string;
    preview: boolean;
    menu: DishRef[];
  };
  line: {
    waiting: number;
    counters: number;
    now_serving: { counter: number; token: number }[];
    next_tokens: number[];
    join_wait_s: number;
    join_wait_upper_s: number;
    simulated: boolean;
  };
  ticket: Ticket | null;
}
export interface LeaderRow {
  rank: number;
  name: string;
  block: string;
  points: number;
  streak: number;
  me: boolean;
}
export interface Leaderboard {
  rows: LeaderRow[];
  me: { rank: number; points: number; streak: number };
  residents: number;
}
export interface MySummary {
  rank: number;
  residents: number;
  points: number;
  streak: number;
  notices: number;
  plates_saved_kg: number;
  events: { reason: string; ref: string; points: number; at: string }[];
}
export interface SheetDish {
  dish_id: number;
  name: string;
  category: string;
  veg: boolean;
  advised_kg: number | null;
  rule_kg: number | null;
  pieces: number | null;
  per_head_g: number | null;
  standard_g: number;
  ingredients: { name: string; kg: number }[];
}
export interface CookSheet {
  day: string;
  meal: MealName;
  state: SittingState;
  starts_at: string;
  cutoff_at: string;
  final: boolean;
  calendar: CalendarNote | null;
  headcount: {
    expected: number | null;
    low: number | null;
    high: number | null;
    roll: number;
    notices: number;
    model: string | null;
    last_week: number | null;
  };
  dishes: SheetDish[];
  totals: { advised_kg: number; rule_kg: number; saving_kg: number; saving_cost: number };
  service_level: number;
  sittings: { day: string; meal: MealName }[];
}
export interface LogDish {
  dish_id: number;
  name: string;
  category: string;
  veg: boolean;
  advised_kg: number | null;
  prepared_kg: number | null;
  leftover_kg: number | null;
  ran_out: boolean;
  short_heads: number;
}
export interface SittingLog {
  day: string;
  meal: MealName;
  logged: boolean;
  logged_by: string;
  logged_at: string | null;
  served: number | null;
  expected: number | null;
  prep_waste_kg: number | null;
  plate_waste_kg: number | null;
  dishes: LogDish[];
  sittings?: { day: string; meal: MealName }[];
}
export interface Period {
  sittings: number;
  days?: number;
  served?: number;
  waste_kg?: number;
  leftover_kg?: number;
  plate_kg?: number;
  prep_kg?: number;
  prepared_kg?: number;
  waste_per_head_g?: number | null;
  leftover_pct?: number | null;
  runout_pct?: number | null;
  cost?: number;
  co2_kg?: number;
  meals_equivalent?: number;
  waste_kg_per_day?: number;
  forecast_mape?: number | null;
  forecast_mae?: number | null;
}
export interface Adoption {
  since: string;
  before: Period;
  after: Period;
  saved_kg: number;
  saved_kg_per_week: number;
  saved_cost_per_month: number;
  saved_co2_kg: number;
  saved_meals: number;
  old_rule_runout_pct: number;
}
export interface TrendWeek {
  week: string;
  leftover_kg: number;
  plate_kg: number;
  prep_kg: number;
  waste_per_head_g: number | null;
  leftover_pct: number | null;
  runout_pct: number | null;
  served: number;
  forecast_mae: number | null;
  phase: "habit" | "sheet";
  labels: string[];
}
export interface Insight {
  tone: "waste" | "good" | "info";
  title: string;
  body: string;
  metric: string;
}
export interface Overview {
  tenant: TenantInfo;
  empty: boolean;
  range: { from: string; to: string; days: number };
  current: Period;
  previous: Period;
  adoption: Adoption | null;
  trend: TrendWeek[];
  daily: { day: string; leftover_kg: number; plate_kg: number; prep_kg: number; served: number; kind: string }[];
  insights: Insight[];
}
export interface DishWaste {
  dish_id: number;
  name: string;
  category: string;
  veg: boolean;
  times: number;
  prepared_kg: number;
  leftover_kg: number;
  leftover_pct: number | null;
  runouts: number;
  rating: number | null;
  ratings: number;
  cost: number;
  turnout_lift: number | null;
}
export interface WasteView {
  empty: boolean;
  range: { from: string; to: string; days: number };
  totals: Period;
  by_dish: DishWaste[];
  heatmap: { weekday: number; meal: MealName; waste_per_head_g: number | null; leftover_pct: number | null }[];
  by_meal: (Period & { meal: MealName })[];
  by_category: { category: string; leftover_kg: number; leftover_pct: number | null }[];
}
export interface ForecastPoint {
  day: string;
  meal: MealName;
  forecast?: number | null;
  expected?: number | null;
  low: number | null;
  high: number | null;
  actual?: number;
  final?: boolean;
  skips?: number;
  kind: string;
  label?: string;
}
export interface ForecastView {
  strength: number;
  upcoming: ForecastPoint[];
  recent: ForecastPoint[];
  live: { sittings: number; mae: number | null; mape: number | null; in_band_pct: number | null; by_meal: { meal: MealName; mae: number | null }[] };
}
export interface Candidate {
  key: string;
  label: string;
  baseline: boolean;
  mae: number | null;
  mape?: number | null;
  wape?: number | null;
}
export interface ModelCard {
  kind: string;
  title: string;
  unit: string;
  blurb: string;
  trained: boolean;
  run_id?: number;
  algorithm?: string;
  trained_at?: string;
  train_through?: string | null;
  rows?: number;
  metrics?: Record<string, number | string | null>;
  candidates?: Candidate[];
  importance?: { group: string; share: number; mae_rise: number }[];
  by_meal?: Record<string, number>;
  policy?: Record<string, number>;
}
export interface ModelsView {
  models: ModelCard[];
  runs: { id: number; kind: string; title: string; algorithm: string; status: string; trained_at: string; mae: number | null; baseline_mae: number | null; note: string }[];
  training: boolean;
  last_result: string;
  stale: boolean;
  service_level: number;
}
export interface MenuDish {
  id: number;
  name: string;
  category: string;
  veg: boolean;
  slow: boolean;
  portion_g: number;
  cost_per_kg: number;
  times: number;
  rating: number | null;
  leftover_pct: number | null;
  turnout_lift: number | null;
}
export interface MenuView {
  chart: { weekday: number; meals: Record<MealName, number[]> }[];
  dishes: MenuDish[];
  suggestions: { weekday: number; meal: MealName; remove: MenuDish; add: MenuDish; reasons: string[]; turnout_gain: number | null; cost_per_plate: number }[];
}
export interface PublicSummary {
  slug: string;
  demo: boolean;
  hostel: string;
  city: string;
  residents: number;
  sittings_logged: number;
  weeks: number;
  forecast_mape: number | null;
  leftover_before_pct: number | null;
  leftover_after_pct: number | null;
  saved_kg_per_week: number | null;
  simulated: boolean;
  data_through: string | null;
  today: string;
}
export interface BoardView {
  hostel: string;
  city: string;
  today: string;
  sittings: { meal: MealName; starts_at: string; ends_at: string; state: SittingState; dishes: DishRef[] }[];
  yesterday: { served: number; plate_waste_kg: number; plate_waste_per_head_g: number | null; plates: number };
  line: LineSnapshot;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private browsing: the session simply lasts until the tab closes */
  }
  memoryToken = token;
}

let memoryToken: string | null = getToken();

interface Options {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
}

export async function api<T>(path: string, options: Options = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (memoryToken) headers.Authorization = `Bearer ${memoryToken}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const controller = new AbortController();
  const timer = options.timeoutMs ? window.setTimeout(() => controller.abort(), options.timeoutMs) : 0;
  options.signal?.addEventListener("abort", () => controller.abort());
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
    });
  } catch {
    throw new ApiError(0, "Could not reach the kitchen's server");
  } finally {
    if (timer) window.clearTimeout(timer);
  }
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const detail = (await response.json()).detail;
      if (typeof detail === "string") message = detail;
      else if (Array.isArray(detail) && detail[0]?.msg) message = String(detail[0].msg);
    } catch {
      /* not JSON */
    }
    if (response.status === 401 && memoryToken) {
      setToken(null);
      window.dispatchEvent(new Event("katori:signed-out"));
    }
    throw new ApiError(response.status, message);
  }
  return (await response.json()) as T;
}
