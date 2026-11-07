import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Tests sign a user in by setting globalThis.Clerk (see lib/session-token).

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
