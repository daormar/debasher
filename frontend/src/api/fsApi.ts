// FastAPI's default error body is `{"detail": "..."}`. Prefer that
// message when present, otherwise fall back to a generic one.
async function errorDetail(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") {
      return body.detail;
    }
  } catch {
    // Not JSON, fall through to the fallback message.
  }

  return fallback;
}

export interface FsEntry {
  name: string;
  path: string;
  type: "dir" | "file";
}

export interface ListDirsResult {
  path: string;
  parent: string | null;
  entries: FsEntry[];
}

export interface ListDirsOptions {
  // Include files alongside directories, for a file picker.
  // Directories are always listed regardless of this flag.
  includeFiles?: boolean;
  // Only meaningful with includeFiles: case-insensitive suffix filter
  // (e.g. [".sh"]) applied to files, not directories.
  extensions?: string[];
}

// Lists the immediate contents of `path` (the server's home directory
// when omitted), for a filesystem-browser picker.
export async function listDirs(
  path: string,
  options: ListDirsOptions = {}
): Promise<ListDirsResult> {
  const response = await fetch("/api/fs/list-dirs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      path,
      includeFiles: options.includeFiles ?? false,
      extensions: options.extensions ?? null,
    }),
  });

  if (!response.ok) {
    throw new Error(await errorDetail(response, "Failed to list directories."));
  }

  return response.json();
}
