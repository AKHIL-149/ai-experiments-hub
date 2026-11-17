import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../src/api";
import Login from "../src/components/Login";
import { CONFIG, USER, withAuth } from "./helpers";

vi.mock("../src/api", async () => {
  const actual = await vi.importActual("../src/api");
  const api = Object.fromEntries(Object.keys(actual.api).map((k) => [k, vi.fn()]));
  return { ...actual, api };
});
const { api } = await import("../src/api");

async function show(config = CONFIG) {
  api.authConfig.mockResolvedValue(config);
  api.me.mockRejectedValue(new ApiError(401, "Not signed in"));
  withAuth(<Login />);
  await screen.findByRole("tab", { name: "Sign in" });
}

beforeEach(() => { api.logout.mockResolvedValue({ success: true }); });

describe("Login", () => {
  it("shows sign in with guest access and says what a guest gets", async () => {
    await show();
    expect(screen.getByLabelText("Username")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue as a guest" })).toBeInTheDocument();
    expect(screen.getByText(/temporary \(24 hours\) and can hold 3 documents/)).toBeInTheDocument();
  });

  it("signs in with what was typed", async () => {
    await show();
    api.login.mockResolvedValue(USER);
    await userEvent.type(screen.getByLabelText("Username"), "ann");
    await userEvent.type(screen.getByLabelText("Password"), "correct horse");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(api.login).toHaveBeenCalledWith("ann", "correct horse");
  });

  it("shows the server's reason when the sign-in fails, and lets you try again", async () => {
    await show();
    api.login.mockRejectedValueOnce(new ApiError(401, "Wrong username or password"));
    await userEvent.type(screen.getByLabelText("Username"), "ann");
    await userEvent.type(screen.getByLabelText("Password"), "nope nope");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Wrong username or password");
    expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
  });

  it("removes the old error as soon as you try again", async () => {
    await show();
    api.login.mockRejectedValueOnce(new ApiError(401, "Wrong username or password"));
    await userEvent.type(screen.getByLabelText("Username"), "ann");
    await userEvent.type(screen.getByLabelText("Password"), "nope nope");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await screen.findByRole("alert");
    api.login.mockReturnValue(new Promise(() => {}));
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("disables the button while it waits", async () => {
    await show();
    let finish;
    api.login.mockReturnValue(new Promise((r) => { finish = r; }));
    await userEvent.type(screen.getByLabelText("Username"), "ann");
    await userEvent.type(screen.getByLabelText("Password"), "correct horse");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(screen.getByRole("button", { name: "Please wait…" })).toBeDisabled();
    finish(USER);
    await waitFor(() => expect(api.login).toHaveBeenCalledTimes(1));
  });

  it("creates an account with an optional display name and explains the rules", async () => {
    await show();
    await userEvent.click(screen.getByRole("tab", { name: "Create account" }));
    expect(screen.getByLabelText(/Display name/)).toBeInTheDocument();
    expect(screen.getByText(/At least 8 characters/)).toBeInTheDocument();
    api.register.mockResolvedValue({ ...USER, adopted_documents: 2 });
    await userEvent.type(screen.getByLabelText("Username"), "ann");
    await userEvent.type(screen.getByLabelText(/Display name/), "Ann Lee");
    await userEvent.type(screen.getByLabelText("Password"), "correct horse");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(api.register).toHaveBeenCalledWith("ann", "correct horse", "Ann Lee");
  });

  it("clears an old error when you switch tabs", async () => {
    await show();
    api.login.mockRejectedValueOnce(new ApiError(401, "Wrong username or password"));
    await userEvent.type(screen.getByLabelText("Username"), "a");
    await userEvent.type(screen.getByLabelText("Password"), "b");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await screen.findByRole("alert");
    await userEvent.click(screen.getByRole("tab", { name: "Create account" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("starts a guest session", async () => {
    await show();
    api.guest.mockResolvedValue({ ...USER, is_guest: true });
    await userEvent.click(screen.getByRole("button", { name: "Continue as a guest" }));
    expect(api.guest).toHaveBeenCalledTimes(1);
  });

  it("hides what the server has turned off", async () => {
    await show({ ...CONFIG, registration: false, guests: false });
    expect(screen.queryByRole("tab", { name: "Create account" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Continue as a guest" })).not.toBeInTheDocument();
  });

  it("shows a guest error such as the rate limit", async () => {
    await show();
    api.guest.mockRejectedValueOnce(new ApiError(429, "Too many attempts, try again later"));
    await userEvent.click(screen.getByRole("button", { name: "Continue as a guest" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many attempts");
  });
});
