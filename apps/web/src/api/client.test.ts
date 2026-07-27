import { ApiClientError, getJson, requestJson } from "./client";

test("returns parsed JSON for a successful request", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ status: "ok" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  await expect(getJson<{ status: string }>("/health")).resolves.toEqual({
    status: "ok",
  });
});

test("throws a typed error for a failed response", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 503 }));

  await expect(getJson("/ready")).rejects.toEqual(
    new ApiClientError("Request failed with status 503.", 503),
  );
});

test("sends authenticated JSON and returns problem detail", async () => {
  const fetchMock = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ created: true }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    )
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Checksum mismatch." }), {
        status: 422,
        headers: { "Content-Type": "application/problem+json" },
      }),
    );

  await expect(
    requestJson("/documents", {
      method: "POST",
      headers: { Authorization: "Bearer token" },
      body: JSON.stringify({ name: "one" }),
    }),
  ).resolves.toEqual({ created: true });
  const headers = new Headers(fetchMock.mock.calls[0]?.[1]?.headers);
  expect(headers.get("content-type")).toBe("application/json");
  await expect(requestJson("/documents")).rejects.toEqual(
    new ApiClientError("Checksum mismatch.", 422),
  );
});

test("falls back when an error response is not JSON", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response("bad gateway", { status: 502 }),
  );
  await expect(requestJson("/documents")).rejects.toEqual(
    new ApiClientError("Request failed with status 502.", 502),
  );
});
