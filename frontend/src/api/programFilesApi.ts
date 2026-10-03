import { throwIfFileVersionConflict } from "./fileVersionConflict";
import { apiFetch } from "./apiFetch";

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

export interface FileEntry {
  name: string;
  path: string;
  type: "file" | "dir";
  readonly: boolean;
  children: FileEntry[] | null;
}

interface FileTreeResponse {
  entries: FileEntry[];
}

// A file read, with the file version of what was read (see file_version in
// api/routers/program_files.py).
export type FileContent =
  | { kind: "file"; content: string; version: string }
  | { kind: "binary"; version: string }
  | { kind: "missing" };

export async function getFileTree(homeDir: string, programName: string): Promise<FileEntry[]> {
  const response = await apiFetch("/api/program-files/tree", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ homeDir, programName }),
  });

  if (!response.ok) {
    throw new Error(await errorDetail(response, "Failed to list program files."));
  }

  const { entries }: FileTreeResponse = await response.json();
  return entries;
}

export async function getFileContent(homeDir: string, path: string): Promise<FileContent> {
  const response = await apiFetch("/api/program-files/content", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ homeDir, path }),
  });

  if (!response.ok) {
    throw new Error(await errorDetail(response, `Failed to read ${path}.`));
  }

  return response.json();
}

export async function createFolder(
  homeDir: string,
  programName: string,
  path: string
): Promise<FileEntry[]> {
  const response = await apiFetch("/api/program-files/mkdir", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ homeDir, programName, path }),
  });

  if (!response.ok) {
    throw new Error(await errorDetail(response, `Failed to create folder ${path}.`));
  }

  const { entries }: FileTreeResponse = await response.json();
  return entries;
}

// The version of a file, without reading it; null when there is no file.
export async function getFileVersion(homeDir: string, path: string): Promise<string | null> {
  const response = await apiFetch("/api/program-files/version", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ homeDir, path }),
  });

  if (!response.ok) {
    throw new Error(await errorDetail(response, `Failed to read the version of ${path}.`));
  }

  const { version } = await response.json();
  return version;
}

interface WriteContentRequest {
  homeDir: string;
  programName: string;
  path: string;
  content: string;
  create: boolean;
  expectedVersion?: string;
}

async function postWriteContent(request: WriteContentRequest): Promise<{ entries: FileEntry[]; version: string | null }> {
  const response = await apiFetch("/api/program-files/write-content", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  await throwIfFileVersionConflict(response);

  if (!response.ok) {
    throw new Error(await errorDetail(response, `Failed to save ${request.path}.`));
  }

  const { entries, version } = await response.json();
  return { entries, version: version ?? null };
}

// Writes the content of a user file. Without `create`, only a file that
// exists, as the panel's editor does; with it, also a new file, with the
// directories above it, as "Add test" and the MCP server do.
export async function writeFileContent(
  homeDir: string,
  programName: string,
  path: string,
  content: string,
  create = false
): Promise<FileEntry[]> {
  const { entries } = await postWriteContent({ homeDir, programName, path, content, create });
  return entries;
}

// Writes the content of a file that exists, as the panel's editor does, only
// if it still holds `expectedVersion`, the version read; throws a
// FileVersionConflict (see api/fileVersionConflict.ts) otherwise. Answers
// with the tree and the version written.
export async function saveFileContent(
  homeDir: string,
  programName: string,
  path: string,
  content: string,
  expectedVersion: string
): Promise<{ entries: FileEntry[]; version: string | null }> {
  return postWriteContent({ homeDir, programName, path, content, create: false, expectedVersion });
}

export async function deleteEntry(
  homeDir: string,
  programName: string,
  path: string
): Promise<FileEntry[]> {
  const response = await apiFetch("/api/program-files/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ homeDir, programName, path }),
  });

  if (!response.ok) {
    throw new Error(await errorDetail(response, `Failed to delete ${path}.`));
  }

  const { entries }: FileTreeResponse = await response.json();
  return entries;
}

export async function moveEntry(
  homeDir: string,
  programName: string,
  srcPath: string,
  dstPath: string
): Promise<FileEntry[]> {
  const response = await apiFetch("/api/program-files/move", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ homeDir, programName, srcPath, dstPath }),
  });

  if (!response.ok) {
    throw new Error(await errorDetail(response, `Failed to move ${srcPath}.`));
  }

  const { entries }: FileTreeResponse = await response.json();
  return entries;
}

export async function uploadFiles(
  homeDir: string,
  programName: string,
  path: string,
  files: File[]
): Promise<FileEntry[]> {
  const formData = new FormData();
  formData.set("homeDir", homeDir);
  formData.set("programName", programName);
  formData.set("path", path);
  for (const file of files) {
    formData.append("files", file);
  }

  const response = await apiFetch("/api/program-files/upload", {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await errorDetail(response, "Failed to upload file(s)."));
  }

  const { entries }: FileTreeResponse = await response.json();
  return entries;
}
