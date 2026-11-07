import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { unsubscribe } from "@/lib/api";
import UnsubscribePage from "./page";

vi.mock("@/lib/api", () => ({ unsubscribe: vi.fn() }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(query),
}));

let query = "";
const unsub = vi.mocked(unsubscribe);

beforeEach(() => {
  query = "";
  unsub.mockReset();
});

describe("Unsubscribe page", () => {
  it("unsubscribes with the link's uid and token", async () => {
    query = "uid=u1&token=t1";
    unsub.mockResolvedValue({ message: "ok" });
    render(<UnsubscribePage />);

    expect(await screen.findByRole("heading", { name: "Unsubscribed" })).toBeInTheDocument();
    expect(unsub).toHaveBeenCalledWith("u1", "t1");
  });

  it("explains a link with missing parts without calling the API", async () => {
    query = "uid=u1";
    render(<UnsubscribePage />);

    expect(await screen.findByRole("heading", { name: "Link invalid" })).toBeInTheDocument();
    expect(screen.getByText(/missing required parameters/)).toBeInTheDocument();
    expect(unsub).not.toHaveBeenCalled();
  });

  it("shows why the API turned the link down", async () => {
    query = "uid=u1&token=old";
    unsub.mockRejectedValue(new Error("This link has expired."));
    render(<UnsubscribePage />);

    expect(await screen.findByRole("heading", { name: "Link invalid" })).toBeInTheDocument();
    expect(screen.getByText("This link has expired.")).toBeInTheDocument();
  });
});
