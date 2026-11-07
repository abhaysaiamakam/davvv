"use client";

import { useEffect, useState, useCallback } from "react";
import { HealthResponse } from "@croplens/shared-types";
import { apiClient } from "@/lib/api-client";

export interface HealthState {
  status: "connected" | "disconnected" | "checking";
  data: HealthResponse | null;
  error: string | null;
  lastChecked: Date | null;
}

export function useApiHealth() {
  const [state, setState] = useState<HealthState>({
    status: "checking",
    data: null,
    error: null,
    lastChecked: null,
  });

  const checkHealth = useCallback(async () => {
    setState((prev) => ({ ...prev, status: "checking" }));
    try {
      const data = await apiClient.getHealth();
      setState({
        status: "connected",
        data,
        error: null,
        lastChecked: new Date(),
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "API server unreachable";
      setState({
        status: "disconnected",
        data: null,
        error: msg,
        lastChecked: new Date(),
      });
    }
  }, []);

  useEffect(() => {
    checkHealth();
  }, [checkHealth]);

  return { ...state, refresh: checkHealth };
}

