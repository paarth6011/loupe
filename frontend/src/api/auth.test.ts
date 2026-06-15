import { afterEach, describe, expect, it, vi } from "vitest";

import { devLogin } from "./auth";
import { clearToken } from "./client";

const TOKEN_KEY = "cloudops_token";

function tokenResponse(token: string): Response {
  return new Response(
    JSON.stringify({ access_token: token, token_type: "bearer" }),
    { status: 200 },
  );
}

afterEach(() => {
  clearToken();
  localStorage.clear();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("devLogin", () => {
  it("stores the token and returns true on success (no retry)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(tokenResponse("dev-tok"));
    vi.stubGlobal("fetch", fetchMock);

    await expect(devLogin()).resolves.toBe(true);
    expect(localStorage.getItem(TOKEN_KEY)).toBe("dev-tok");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("returns false immediately on 404 (production) without retrying", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response("", { status: 404 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(devLogin()).resolves.toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it("retries transient boot failures, then succeeds", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch")) // conn refused
      .mockResolvedValueOnce(new Response("", { status: 503 })) // half-ready
      .mockResolvedValueOnce(tokenResponse("dev-tok"));
    vi.stubGlobal("fetch", fetchMock);

    const promise = devLogin();
    await vi.runAllTimersAsync();

    await expect(promise).resolves.toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(localStorage.getItem(TOKEN_KEY)).toBe("dev-tok");
  });

  it("gives up and returns false after exhausting retries", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetchMock);

    const promise = devLogin();
    await vi.runAllTimersAsync();

    await expect(promise).resolves.toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(5); // DEV_LOGIN_RETRIES + 1
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });
});
