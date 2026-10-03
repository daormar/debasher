// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";

import { sendRequestsTo } from "./backend";

describe("sendRequestsTo", () => {

  const nodeFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = nodeFetch;
  });

  it("sends a path of the backend to its URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}"));
    globalThis.fetch = fetchMock;
    sendRequestsTo("http://127.0.0.1:8123");

    await fetch("/api/webui/info");

    expect(String(fetchMock.mock.calls[0][0])).toBe("http://127.0.0.1:8123/api/webui/info");
  });

  it("says where the token came from when the backend refuses it", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(new Response("{}", { status: 401 }));
    sendRequestsTo("http://127.0.0.1:8123", () => "Read from the token file.");

    await expect(fetch("/api/webui/info")).rejects.toThrow(
      "The backend at http://127.0.0.1:8123 refused the request: it carries no valid token. Read from the token file."
    );
  });

});
