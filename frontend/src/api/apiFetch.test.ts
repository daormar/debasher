import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  apiFetch,
  clearTokenRefused,
  isTokenRefused,
  setTokenSource,
  takeTokenFromAddress,
} from "./apiFetch";

describe("apiFetch", () => {

  beforeEach(() => {
    clearTokenRefused();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    setTokenSource(() => null);
    clearTokenRefused();
  });

  function stubFetch(status = 200) {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status }));
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("adds the token to a request for the backend, keeping its own headers", async () => {
    const fetchMock = stubFetch();
    setTokenSource(() => "tok");

    await apiFetch("/api/programs/load", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });

    const [input, init] = fetchMock.mock.calls[0];
    expect(input).toBe("/api/programs/load");
    expect(init.method).toBe("POST");
    expect(init.body).toBe("{}");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer tok");
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
  });

  it("sends the token to no other site", async () => {
    const fetchMock = stubFetch();
    setTokenSource(() => "tok");

    await apiFetch("https://example.org/api/x");
    await apiFetch("//example.org/api/x");

    expect(fetchMock.mock.calls).toEqual([["https://example.org/api/x"], ["//example.org/api/x"]]);
  });

  it("passes a request on as it is when there is no token", async () => {
    const fetchMock = stubFetch();
    const init = { method: "POST", body: "{}" };

    await apiFetch("/api/execution/run", init);
    await apiFetch("/api/execution/schedulers");

    expect(fetchMock.mock.calls).toEqual([["/api/execution/run", init], ["/api/execution/schedulers"]]);
  });

  it("marks the token refused when the backend refuses a request for it", async () => {
    stubFetch(401);

    const response = await apiFetch("/api/webui/info");

    expect(response.status).toBe(401);
    expect(isTokenRefused()).toBe(true);
  });

  it("does not take another error for a refused token", async () => {
    stubFetch(500);

    await apiFetch("/api/webui/info");

    expect(isTokenRefused()).toBe(false);
  });

});

describe("takeTokenFromAddress", () => {

  afterEach(() => {
    window.localStorage.clear();
  });

  it("keeps the token of the fragment and takes the fragment out of the address", () => {
    const replaceState = vi.fn();

    takeTokenFromAddress(
      { hash: "#token=abc123", pathname: "/", search: "" },
      { replaceState, state: null },
    );

    expect(window.localStorage.getItem("debasher_token")).toBe("abc123");
    expect(replaceState).toHaveBeenCalledWith(null, "", "/");
  });

  it("leaves an address with no token as it is", () => {
    const replaceState = vi.fn();

    takeTokenFromAddress({ hash: "", pathname: "/", search: "" }, { replaceState, state: null });

    expect(replaceState).not.toHaveBeenCalled();
    expect(window.localStorage.getItem("debasher_token")).toBeNull();
  });

});

describe("the token source of the browser", () => {

  afterEach(() => {
    window.localStorage.clear();
  });

  it("reads the token that another tab stored", async () => {
    // The default source, which the tests above replaced, reads the storage.
    vi.resetModules();
    const fresh = await import("./apiFetch");
    expect(fresh.hasToken()).toBe(false);

    window.localStorage.setItem("debasher_token", "from-another-tab");

    expect(fresh.hasToken()).toBe(true);
  });

});
