import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { clearTokenRefused, isTokenRefused, markTokenRefused, setTokenSource } from "../api/apiFetch";
import TokenNotice from "./TokenNotice";

describe("TokenNotice", () => {

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    setTokenSource(() => null);
    clearTokenRefused();
  });

  it("shows nothing while the backend takes the token", () => {
    render(<TokenNotice />);

    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says how to get a token when the page has none", () => {
    render(<TokenNotice />);
    act(() => markTokenRefused());

    expect(screen.getByRole("alert")).toHaveTextContent(/This page has no token of the backend/);
  });

  it("says to open the address again when the backend no longer knows the token", () => {
    setTokenSource(() => "old");
    render(<TokenNotice />);
    act(() => markTokenRefused());

    expect(screen.getByRole("alert")).toHaveTextContent(/restarted with another token/);
    expect(screen.getByRole("alert")).toHaveTextContent(/in this tab, which keeps its unsaved changes/);
  });

  it("goes away once the backend takes the token again", async () => {
    setTokenSource(() => "new");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ claudeCode: true }))));
    render(<TokenNotice />);
    act(() => markTokenRefused());

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(isTokenRefused()).toBe(false);
  });

  it("stays while the backend still refuses the token", async () => {
    setTokenSource(() => "old");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 401 })));
    render(<TokenNotice />);
    act(() => markTokenRefused());

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Retry" })).toBeEnabled());
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(isTokenRefused()).toBe(true);
  });

});
