import type { z } from "zod";
import { config } from "@/lib/flags";
import { currentPersonaId, useUi } from "@/lib/store";
import { mocksReady } from "./mocks-ready";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function headers(): HeadersInit {
  // Auth adapter: the mock provider sends the impersonated persona. A real SSO provider sends a bearer token instead.
  return { "content-type": "application/json", "x-persona": currentPersonaId() };
}

async function parse<T>(res: Response, schema: z.ZodType<T>, path: string): Promise<T> {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError((body as { error?: string }).error ?? `${res.status} ${res.statusText}`, res.status);
  const result = schema.safeParse(body);
  if (!result.success) {
    throw new ApiError(`Response for ${path} does not match its contract: ${result.error.issues[0]?.path.join(".")} ${result.error.issues[0]?.message}`, 502);
  }
  return result.data;
}

export function tenantPath(path: string) {
  return `${config.apiBaseUrl}/api/t/${useUi.getState().tenantId}/${path}`;
}

export async function apiGet<T>(path: string, schema: z.ZodType<T>, signal?: AbortSignal): Promise<T> {
  await mocksReady();
  const res = await fetch(tenantPath(path), { headers: headers(), signal });
  return parse(res, schema, path);
}

export async function apiPost<T>(path: string, body: unknown, schema: z.ZodType<T>): Promise<T> {
  await mocksReady();
  const res = await fetch(tenantPath(path), { method: "POST", headers: headers(), body: JSON.stringify(body ?? {}) });
  return parse(res, schema, path);
}

export async function apiGlobal<T>(path: string, schema: z.ZodType<T>): Promise<T> {
  await mocksReady();
  const res = await fetch(`${config.apiBaseUrl}/api/${path}`, { headers: headers() });
  return parse(res, schema, path);
}
