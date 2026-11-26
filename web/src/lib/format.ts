// Formatting helpers. Times are always shown in the kitchen's own time zone.

import type { MealName } from "./api";

export const MEALS: MealName[] = ["breakfast", "lunch", "snacks", "dinner"];
export const MEAL_LABEL: Record<MealName, string> = { breakfast: "Breakfast", lunch: "Lunch", snacks: "Snacks", dinner: "Dinner" };
export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
export const WEEKDAYS_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

let zone = "Asia/Kolkata";
export function setTimeZone(timeZone: string): void {
  zone = timeZone;
}

export function clock(iso: string): string {
  return new Intl.DateTimeFormat("en-IN", { hour: "numeric", minute: "2-digit", hour12: true, timeZone: zone }).format(new Date(iso)).replace(" ", " ");
}

/** Parse "2026-11-26" as a calendar day, with no time-zone arithmetic. */
export function parseDay(day: string): { y: number; m: number; d: number; weekday: number } {
  const [y, m, d] = day.split("-").map(Number);
  const weekday = (new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7;
  return { y, m, d, weekday };
}

export function dayLabel(day: string, style: "short" | "long" | "tiny" = "short"): string {
  const { m, d, weekday } = parseDay(day);
  if (style === "tiny") return `${d} ${MONTHS[m - 1]}`;
  if (style === "long") return `${WEEKDAYS[weekday]}, ${d} ${MONTHS[m - 1]}`;
  return `${WEEKDAYS_SHORT[weekday]} ${d} ${MONTHS[m - 1]}`;
}

export function addDays(day: string, count: number): string {
  const { y, m, d } = parseDay(day);
  return new Date(Date.UTC(y, m - 1, d + count)).toISOString().slice(0, 10);
}

const whole = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const oneDecimal = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export function num(value: number | null | undefined, decimals = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "–";
  return decimals ? oneDecimal.format(value) : whole.format(value);
}

export function kg(value: number | null | undefined): string {
  if (value === null || value === undefined) return "–";
  return Math.abs(value) >= 100 ? whole.format(value) : oneDecimal.format(value);
}

export function rupees(value: number | null | undefined): string {
  if (value === null || value === undefined) return "–";
  if (Math.abs(value) >= 100000) return `₹${oneDecimal.format(value / 100000)} lakh`;
  return `₹${whole.format(value)}`;
}

export function pct(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined) return "–";
  return `${value.toFixed(decimals)}%`;
}

/** "about 2 min", "under a minute" */
export function waitText(seconds: number): string {
  if (seconds < 45) return "under a minute";
  const minutes = Math.round(seconds / 60);
  return `about ${minutes} min`;
}

export function countdown(iso: string, nowMs: number): string {
  const seconds = Math.max(0, Math.round((new Date(iso).getTime() - nowMs) / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours >= 24) return `${Math.floor(hours / 24)}d ${hours % 24}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes} min`;
  return "under a minute";
}

/** A clean axis ceiling and its ticks: 0, 250, 500, 750, 1000 */
export function axis(max: number, target = 4): { top: number; ticks: number[] } {
  if (!(max > 0)) return { top: 1, ticks: [0, 1] };
  const rough = max / target;
  const power = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((s) => s * power).find((s) => s >= rough) ?? 10 * power;
  const top = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let value = 0; value <= top + step / 1000; value += step) ticks.push(Number(value.toFixed(6)));
  return { top, ticks };
}
