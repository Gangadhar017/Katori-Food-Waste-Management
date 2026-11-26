import type { Role } from "./api";

/** Where each role lands after signing in. */
export const HOME: Record<Role, string> = { student: "/home", kitchen: "/kitchen", manager: "/manage" };
