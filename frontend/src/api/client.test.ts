import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch, clearToken, setToken } from "./client";

afterEach(() => {
  clearToken();
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("apiFetch", () => {
  it("attaches the bearer token when one is stored", async () => {
    setToken("tok123");
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/workloads");

    const options = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = options.headers as Record<string, string>;
    expect(headers["Authorization"]).toBe("Bearer tok123");
  });

  it("throws ApiError and clears the token on 401", async () => {
    setToken("tok123");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("", { status: 401 })),
    );

    await expect(apiFetch("/workloads")).rejects.toBeInstanceOf(ApiError);
    expect(getStoredToken()).toBeNull();
  });
});

function getStoredToken(): string | null {
  return localStorage.getItem("cloudops_token");
}
