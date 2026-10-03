// Every client of the backend sends its requests through apiFetch, which adds
// the token of the backend to each one (`Authorization: Bearer <token>`): the
// backend refuses every request to its API without it. The token comes from a
// token source: in the browser, the local storage, where the page keeps the
// token that the address it was opened with brought (`#token=...`); under the
// MCP server, which runs the same clients under Node.js, the token file.

const TOKEN_KEY = "debasher_token";

export type TokenSource = () => string | null;

// The token of a tab whose browser refuses the local storage: the tab then
// works alone, and another tab needs the address with the token again.
let tokenInMemory: string | null = null;

function storedToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY) ?? tokenInMemory;
  } catch {
    return tokenInMemory;
  }
}

function keepToken(token: string): void {
  tokenInMemory = token;
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Kept in memory only.
  }
}

let tokenSource: TokenSource = () => (typeof window === "undefined" ? null : storedToken());

export function setTokenSource(source: TokenSource): void {
  tokenSource = source;
}

export function hasToken(): boolean {
  return tokenSource() !== null;
}

/**
 * Keeps the token that the address of the page brings in its fragment
 * (`#token=...`), and takes the fragment out of the address, so that the token
 * stays neither in the address bar, nor in the history, nor in a link copied
 * from it. The browser never sends the fragment to the server. Tells whether
 * the address brought a token.
 */
export function takeTokenFromAddress(
  location: Pick<Location, "hash" | "pathname" | "search"> = window.location,
  history: Pick<History, "replaceState" | "state"> = window.history,
): boolean {
  const token = new URLSearchParams(location.hash.slice(1)).get("token");
  if (!token) {
    return false;
  }
  keepToken(token);
  history.replaceState(history.state, "", location.pathname + location.search);
  return true;
}

// Whether the backend refused the token of this tab (or the tab has none):
// the editor then says how to get one, and stops polling.
let tokenRefused = false;

const refusalListeners = new Set<() => void>();

export function isTokenRefused(): boolean {
  return tokenRefused;
}

function setTokenRefused(refused: boolean): void {
  if (tokenRefused !== refused) {
    tokenRefused = refused;
    refusalListeners.forEach(listener => listener());
  }
}

export function markTokenRefused(): void {
  setTokenRefused(true);
}

export function clearTokenRefused(): void {
  setTokenRefused(false);
}

export function subscribeTokenRefused(listener: () => void): () => void {
  refusalListeners.add(listener);
  return () => {
    refusalListeners.delete(listener);
  };
}

// A path of the backend itself: the token goes to no other site.
function isBackendPath(input: string): boolean {
  return input.startsWith("/") && !input.startsWith("//");
}

/**
 * fetch for a path of the backend (`/api/...`), with the token added. The
 * fetch called is the one of the moment, which the MCP server and the tests
 * replace. A request refused for its token (401) marks the token refused.
 */
export async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  const token = isBackendPath(input) ? tokenSource() : null;

  let response: Response;
  if (token === null) {
    response = await (init === undefined ? fetch(input) : fetch(input, init));
  } else {
    const headers = new Headers(init?.headers);
    headers.set("Authorization", `Bearer ${token}`);
    response = await fetch(input, { ...init, headers });
  }

  if (response.status === 401 && isBackendPath(input)) {
    markTokenRefused();
  }
  return response;
}
