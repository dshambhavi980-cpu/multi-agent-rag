export interface Health {
  status: "ok";
  time: string;
  cold_start: boolean;
}

export type ReadinessStatus = "ready" | "degraded" | "unavailable";

export interface Readiness {
  status: ReadinessStatus;
  dependencies: Record<string, ReadinessStatus>;
}

export interface Version {
  version: string;
  commit: string;
  environment: string;
}
