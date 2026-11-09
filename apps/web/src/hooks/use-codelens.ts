"use client";

import { useEffect, useState } from "react";
export function useCodeLens() {
  const [enabled, setEnabled] = useState(false);
  useEffect(() => {
    setEnabled(localStorage.getItem("croplens-codelens") === "on");
    const handler = (event: Event) => setEnabled((event as CustomEvent<boolean>).detail);
    window.addEventListener("croplens:codelens", handler);
    return () => window.removeEventListener("croplens:codelens", handler);
  }, []);
  return enabled;
}
