import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// The real module throws without the NEXT_PUBLIC_FIREBASE_* config and would
// talk to Firebase. Tests sign a user in by setting auth.currentUser.
vi.mock("@/lib/firebase", () => ({
  app: {},
  auth: { currentUser: null },
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
