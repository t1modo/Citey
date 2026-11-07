import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { auth } from "@/lib/firebase";
import {
  addWorkChecked,
  detailMessage,
  getProfile,
  importByAuthor,
  sendSupportMessage,
  unsubscribe,
} from "@/lib/api";

const API = "http://api.test/api";

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function signIn(token = "id-token") {
  (auth as { currentUser: unknown }).currentUser = { getIdToken: async () => token };
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  (auth as { currentUser: unknown }).currentUser = null;
});

afterEach(() => {
  vi.useRealTimers();
});

describe("detailMessage", () => {
  it("passes a plain string through", () => {
    expect(detailMessage("Paper not found.", "fallback")).toBe("Paper not found.");
  });

  it("reads the first Pydantic validation error without its prefix", () => {
    expect(detailMessage([{ msg: "Value error, Enter a valid DOI." }], "fallback")).toBe(
      "Enter a valid DOI.",
    );
  });

  it("says how long to wait after a rate limit", () => {
    expect(detailMessage({ message: "Too many requests.", retry_after_seconds: 30 }, "x")).toBe(
      "Too many requests. You can try again in 30 seconds.",
    );
    expect(detailMessage({ message: "Too many requests.", retry_after_seconds: 60 }, "x")).toBe(
      "Too many requests. You can try again in 1 minute.",
    );
    expect(detailMessage({ message: "Too many requests.", retry_after_seconds: 150 }, "x")).toBe(
      "Too many requests. You can try again in 3 minutes.",
    );
  });

  it("falls back for anything else", () => {
    expect(detailMessage(undefined, "fallback")).toBe("fallback");
    expect(detailMessage({ code: 42 }, "fallback")).toBe("fallback");
  });
});

describe("signed-in requests", () => {
  it("refuses to call the API when nobody is signed in", async () => {
    await expect(getProfile()).rejects.toThrow("Not authenticated");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends the Firebase ID token to the /api route", async () => {
    signIn("abc123");
    fetchMock.mockResolvedValue(json(200, { uid: "u1" }));

    await expect(getProfile()).resolves.toEqual({ uid: "u1" });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${API}/profile`);
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer abc123");
  });

  it("turns the API's error detail into the error message", async () => {
    signIn();
    fetchMock.mockResolvedValue(json(404, { detail: "Profile not found." }));
    await expect(getProfile()).rejects.toThrow("Profile not found.");
  });

  it("retries a GET while the API is waking up", async () => {
    vi.useFakeTimers();
    signIn();
    fetchMock
      .mockResolvedValueOnce(new Response("", { status: 503 }))
      .mockResolvedValueOnce(json(200, { uid: "u1" }));

    const result = getProfile();
    await vi.runAllTimersAsync();

    await expect(result).resolves.toEqual({ uid: "u1" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not resend a POST after a gateway timeout, since it may have run", async () => {
    signIn();
    fetchMock.mockResolvedValue(new Response("", { status: 504 }));
    await expect(addWorkChecked("10.1/x")).rejects.toThrow("Request failed: 504");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("addWorkChecked", () => {
  it("returns the added paper", async () => {
    signIn();
    fetchMock.mockResolvedValue(json(200, { id: "w1", doi: "10.1/x" }));

    const result = await addWorkChecked("10.1/x");

    expect(result).toEqual({ status: "added", work: { id: "w1", doi: "10.1/x" } });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ doi: "10.1/x", force: false });
  });

  it("reports when the linked author is not on the paper", async () => {
    signIn();
    fetchMock.mockResolvedValue(
      json(422, {
        detail: {
          code: "author_not_found",
          linked_author: "Ada Lovelace",
          paper_title: "On Engines",
          paper_authors: ["Charles Babbage"],
        },
      }),
    );

    await expect(addWorkChecked("10.1/x")).resolves.toEqual({
      status: "author_not_found",
      linkedAuthor: "Ada Lovelace",
      paperTitle: "On Engines",
      paperAuthors: ["Charles Babbage"],
    });
  });
});

describe("importByAuthor", () => {
  it("asks before merging into a different linked author", async () => {
    signIn();
    fetchMock.mockResolvedValue(
      json(409, { detail: { code: "merge_required", existing_author_name: "A. Lovelace" } }),
    );

    await expect(importByAuthor("A1", "Ada Lovelace")).resolves.toEqual({
      status: "merge_required",
      existing_author_name: "A. Lovelace",
    });
  });

  it("returns the import counts", async () => {
    signIn();
    fetchMock.mockResolvedValue(json(200, { imported: 4, skipped: 1 }));

    await expect(importByAuthor("A1", "Ada", "dblp", true, ["openalex"])).resolves.toEqual({
      status: "imported",
      imported: 4,
      skipped: 1,
    });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      author_id: "A1",
      author_name: "Ada",
      source: "dblp",
      confirm_merge: true,
      extra_sources: ["openalex"],
    });
  });
});

describe("requests that work signed out", () => {
  it("unsubscribes with the link's uid and token", async () => {
    fetchMock.mockResolvedValue(json(200, { message: "Unsubscribed." }));

    await expect(unsubscribe("u1", "t1")).resolves.toEqual({ message: "Unsubscribed." });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${API}/profile/unsubscribe`);
    expect(JSON.parse(init.body)).toEqual({ uid: "u1", token: "t1" });
  });

  it("explains a bad unsubscribe link", async () => {
    fetchMock.mockResolvedValue(json(400, { detail: "This link has expired." }));
    await expect(unsubscribe("u1", "bad")).rejects.toThrow("This link has expired.");
  });

  it("sends a contact message without a token when signed out", async () => {
    fetchMock.mockResolvedValue(json(200, { message: "Thanks!" }));

    await expect(
      sendSupportMessage({ email: "a@b.co", message: "Hello there, a question.", elapsed_ms: 5000 }),
    ).resolves.toBe("Thanks!");

    const init = fetchMock.mock.calls[0][1];
    expect(init.headers.Authorization).toBeUndefined();
  });

  it("attaches the token to a contact message when signed in", async () => {
    signIn("tok");
    fetchMock.mockResolvedValue(json(200, {}));

    await expect(
      sendSupportMessage({ email: "a@b.co", message: "Hello there, a question.", elapsed_ms: 5000 }),
    ).resolves.toBe("Thanks. We'll reply to your email.");
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer tok");
  });

  it("shows the form's validation error", async () => {
    fetchMock.mockResolvedValue(json(422, { detail: [{ msg: "Value error, Enter a valid email." }] }));
    await expect(
      sendSupportMessage({ email: "nope", message: "Hello there, a question.", elapsed_ms: 5000 }),
    ).rejects.toThrow("Enter a valid email.");
  });
});
