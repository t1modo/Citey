import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import TrackedWorkCard from "@/components/TrackedWorkCard";
import type { TrackedWork } from "@/lib/types";

function work(overrides: Partial<TrackedWork> = {}): TrackedWork {
  return {
    id: "w1",
    doi: "10.1234/abc",
    title: "Attention Is All You Need",
    authors: ["A. Vaswani", "N. Shazeer", "N. Parmar", "J. Uszkoreit", "L. Jones"],
    year: 2017,
    venue: "NeurIPS",
    work_type: "article",
    topics: [],
    last_checked_at: null,
    added_at: null,
    citation_count: 0,
    new_citations_30d: 0,
    s2_citation_count: 900,
    openalex_citation_count: 1200,
    ...overrides,
  };
}

describe("TrackedWorkCard", () => {
  it("shows the paper like a reference list entry", () => {
    render(<TrackedWorkCard work={work()} onRemove={() => {}} />);

    expect(screen.getByRole("heading", { name: "Attention Is All You Need" })).toBeInTheDocument();
    expect(screen.getByText(/A\. Vaswani, N\. Shazeer, N\. Parmar and 2 more/)).toBeInTheDocument();
    expect(screen.getByText("NeurIPS, 2017")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "doi:10.1234/abc" })).toHaveAttribute(
      "href",
      "https://doi.org/10.1234/abc",
    );
  });

  it("shows the higher of the two lifetime counts", () => {
    render(<TrackedWorkCard work={work()} onRemove={() => {}} />);
    expect(screen.getByText(`Cited by ${(1200).toLocaleString()}`)).toBeInTheDocument();
  });

  it("leaves the count out when no index has one yet", () => {
    render(
      <TrackedWorkCard
        work={work({ s2_citation_count: null, openalex_citation_count: null })}
        onRemove={() => {}}
      />,
    );
    expect(screen.queryByText(/Cited by/)).not.toBeInTheDocument();
    expect(screen.getByText("Not checked yet")).toBeInTheDocument();
  });

  it("highlights new citations this month", () => {
    render(<TrackedWorkCard work={work({ new_citations_30d: 3 })} onRemove={() => {}} />);
    expect(screen.getByText("3 new this month")).toBeInTheDocument();
  });

  it("falls back to a placeholder title", () => {
    render(<TrackedWorkCard work={work({ title: null })} onRemove={() => {}} />);
    expect(screen.getByRole("heading", { name: "Untitled work" })).toBeInTheDocument();
  });

  it("asks before it stops tracking a paper", async () => {
    const user = userEvent.setup();
    const onRemove = vi.fn();
    render(<TrackedWorkCard work={work()} onRemove={onRemove} />);

    await user.click(screen.getByRole("button", { name: "Stop tracking" }));
    expect(onRemove).not.toHaveBeenCalled();
    expect(screen.getByText("Remove it and its citations?")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Stop tracking" }));
    expect(onRemove).toHaveBeenCalledWith("w1");
  });

  it("can back out of stopping", async () => {
    const user = userEvent.setup();
    const onRemove = vi.fn();
    render(<TrackedWorkCard work={work()} onRemove={onRemove} />);

    await user.click(screen.getByRole("button", { name: "Stop tracking" }));
    await user.click(screen.getByRole("button", { name: "Keep" }));

    expect(onRemove).not.toHaveBeenCalled();
    expect(screen.queryByText("Remove it and its citations?")).not.toBeInTheDocument();
  });
});
