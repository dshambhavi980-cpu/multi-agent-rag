import { useQuery } from "@tanstack/react-query";

import { getJson } from "../../api/client";
import type { Health, Readiness, Version } from "./system.types";

const recoveryInterval = 10_000;
const normalStatusInterval = 30_000;

export function useHealth() {
  return useQuery({
    queryKey: ["system", "health"],
    queryFn: ({ signal }) => getJson<Health>("/health", signal),
    refetchInterval: (query) =>
      query.state.status === "error" ? recoveryInterval : normalStatusInterval,
  });
}

export function useReadiness() {
  return useQuery({
    queryKey: ["system", "readiness"],
    queryFn: ({ signal }) => getJson<Readiness>("/ready", signal),
    refetchInterval: (query) =>
      query.state.status === "error" ? recoveryInterval : normalStatusInterval,
  });
}

export function useVersion() {
  return useQuery({
    queryKey: ["system", "version"],
    queryFn: ({ signal }) => getJson<Version>("/version", signal),
    refetchInterval: (query) =>
      query.state.status === "error" ? recoveryInterval : false,
    staleTime: Number.POSITIVE_INFINITY,
  });
}
