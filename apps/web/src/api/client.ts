const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "/api";
const usesVercelProxy =
  typeof window !== "undefined" && window.location.hostname.endsWith(".vercel.app");

export const API_BASE_URL = usesVercelProxy ? "/api" : configuredApiBaseUrl;

export class ApiClientError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

async function parseError(response: Response): Promise<string> {
  try {
    const problem = (await response.json()) as { detail?: string };
    return problem.detail ?? `Request failed with status ${String(response.status)}.`;
  } catch {
    return `Request failed with status ${String(response.status)}.`;
  }
}

export async function requestJson<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });
  if (!response.ok) {
    throw new ApiClientError(await parseError(response), response.status);
  }
  return (await response.json()) as T;
}

export async function getJson<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Accept: "application/json" },
    signal: signal ?? null,
  });

  if (!response.ok) {
    throw new ApiClientError(
      `Request failed with status ${String(response.status)}.`,
      response.status,
    );
  }

  return (await response.json()) as T;
}

export type SseEvent = {
  event_type: string;
  sequence: number;
  [key: string]: unknown;
};

export async function streamSse(
  path: string,
  options: RequestInit,
  onEvent: (event: SseEvent) => void,
): Promise<void> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "text/event-stream");
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });
  if (!response.ok) {
    throw new ApiClientError(await parseError(response), response.status);
  }
  if (!response.body) throw new ApiClientError("The response stream was unavailable.", 502);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const data = frame
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim())
        .join("\n");
      if (data.length > 0) onEvent(JSON.parse(data) as SseEvent);
    }
    if (done) break;
  }
}
