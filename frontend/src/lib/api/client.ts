import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type S = components["schemas"];

export const api = createClient<paths>({ baseUrl: "" });

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

type Detail = { detail?: string | { loc?: (string | number)[]; msg?: string }[] };

export function errorMessage(error: unknown, fallback = "Something went wrong"): string {
  const detail = (error as Detail | undefined)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((d) => [d.loc?.filter((part) => part !== "body").join("."), d.msg].filter(Boolean).join(": "))
      .join("; ");
  }
  return error instanceof Error ? error.message : fallback;
}

/** Resolve an openapi-fetch call to its data, or throw ApiError with FastAPI's detail message. */
export async function unwrap<T>(call: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await call;
  if (!response.ok) throw new ApiError(response.status, errorMessage(error, response.statusText));
  return data as T;
}
