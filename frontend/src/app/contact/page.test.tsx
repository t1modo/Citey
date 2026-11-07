import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sendSupportMessage } from "@/lib/api";
import ContactPage from "./page";

vi.mock("@/lib/api", () => ({ sendSupportMessage: vi.fn() }));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: authUser }),
}));

let authUser: { email: string } | null = null;
const send = vi.mocked(sendSupportMessage);

beforeEach(() => {
  authUser = null;
  send.mockReset();
});

async function fillIn(message: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Your email"), "ada@uni.edu");
  await user.type(screen.getByLabelText("Message"), message);
  await user.click(screen.getByRole("button", { name: "Send message" }));
}

describe("Contact page", () => {
  it("asks for more than a few words", async () => {
    render(<ContactPage />);
    await fillIn("hi");

    expect(screen.getByRole("alert")).toHaveTextContent("Tell us a little more");
    expect(send).not.toHaveBeenCalled();
  });

  it("sends the message and confirms where the reply goes", async () => {
    send.mockResolvedValue("Thanks.");
    render(<ContactPage />);
    await fillIn("  My paper's citations look wrong.  ");

    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({
        email: "ada@uni.edu",
        message: "My paper's citations look wrong.",
        name: undefined,
        subject: undefined,
        website: "",
      }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("We'll reply to ada@uni.edu");
  });

  it("shows the API's error and keeps the form", async () => {
    send.mockRejectedValue(new Error("Too many messages. Try again later."));
    render(<ContactPage />);
    await fillIn("My paper's citations look wrong.");

    expect(await screen.findByRole("alert")).toHaveTextContent("Too many messages.");
    expect(screen.getByRole("button", { name: "Send message" })).toBeEnabled();
  });

  it("fills in a signed-in user's email", () => {
    authUser = { email: "me@uni.edu" };
    render(<ContactPage />);
    expect(screen.getByLabelText("Your email")).toHaveValue("me@uni.edu");
  });

  it("can't be sent without an email", () => {
    render(<ContactPage />);
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
  });
});
