import { useQuery } from "@tanstack/react-query";

import { getJson } from "../../api/client";
import type { Health, Readiness, Version } from "./system.types";

export function useHealth() {
  return useQuery({
    queryKey: ["system", "health"],
    queryFn: ({ signal }) => getJson<Health>("/health", signal),
    refetchInterval: 30_000,
  });
}

export function useReadiness() {
  return useQuery({
    queryKey: ["system", "readiness"],
    queryFn: ({ signal }) => getJson<Readiness>("/ready", signal),
    refetchInterval: 30_000,
  });
}

export function useVersion() {
  return useQuery({
    queryKey: ["system", "version"],
    queryFn: ({ signal }) => getJson<Version>("/version", signal),
    staleTime: Number.POSITIVE_INFINITY,
  });
}
