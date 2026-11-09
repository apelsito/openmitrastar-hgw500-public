export type Json = Record<string, unknown>;
export type Fetcher = typeof fetch;

export class ApiError extends Error {
  status: number;
  code: string;
  ambiguous: boolean;
  constructor(message: string, status = 0, code = "network", ambiguous = false) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.ambiguous = ambiguous;
  }
}

export function object(value: unknown): Json {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Json : {};
}

export async function requestApi(path: string, init: RequestInit = {}, fetcher: Fetcher = fetch): Promise<Json> {
  if (!/^\/api\/v1\/[a-z0-9/?=&_-]+$/.test(path)) throw new ApiError("Ruta de API no permitida", 0, "path");
  const post = init.method === "POST";
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), post ? 90000 : 10000);
  try {
    const response = await fetcher(path, { ...init, cache: "no-store", credentials: "same-origin", redirect: "error",
      headers: { Accept: "application/json", ...init.headers }, signal: controller.signal });
    if (response.status === 401 || response.status === 403) {
      throw new ApiError("Sesión caducada o solicitud no autorizada. Vuelve a iniciar sesión.", response.status, "auth");
    }
    let data: Json;
    try {
      const raw: unknown = await response.json();
      if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new Error("shape");
      data = raw as Json;
    } catch {
      throw new ApiError("Respuesta de API inválida", response.status, "invalid-json", post);
    }
    if (!response.ok || data.ok === false) {
      throw new ApiError(typeof data.detail === "string" ? data.detail : typeof data.error === "string" ? data.error : `HTTP ${response.status}`,
        response.status, typeof data.error === "string" ? data.error : "api", post && response.status >= 500);
    }
    return data;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(post ? "Resultado desconocido: relee el estado antes de repetir una operación." : "No se pudo leer la API.", 0, "network", post);
  } finally {
    clearTimeout(timer);
  }
}
