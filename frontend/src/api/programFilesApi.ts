// FastAPI's default error body is `{"detail": "..."}`. Prefer that
// message when present, otherwise fall back to a generic one.
async function errorDetail(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") {
      return body.detail;
    }
  } catch {
    // Not JSON — fall through to the fallback message.
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

export type FileContent =
  | { kind: "file"; content: string }
  | { kind: "binary" }
  | { kind: "missing" };

export async function getFileTree(homeDir: string, programName: string): Promise<FileEntry[]> {
  const response = await fetch("/api/program-files/tree", {
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
  const response = await fetch("/api/program-files/content", {
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
  const response = await fetch("/api/program-files/mkdir", {
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

export async function writeFileContent(
  homeDir: string,
  programName: string,
  path: string,
  content: string
): Promise<FileEntry[]> {
  const response = await fetch("/api/program-files/write-content", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ homeDir, programName, path, content }),
  });

  if (!response.ok) {
    throw new Error(await errorDetail(response, `Failed to save ${path}.`));
  }

  const { entries }: FileTreeResponse = await response.json();
  return entries;
}

export async function deleteEntry(
  homeDir: string,
  programName: string,
  path: string
): Promise<FileEntry[]> {
  const response = await fetch("/api/program-files/delete", {
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
  const response = await fetch("/api/program-files/move", {
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

  const response = await fetch("/api/program-files/upload", {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await errorDetail(response, "Failed to upload file(s)."));
  }

  const { entries }: FileTreeResponse = await response.json();
  return entries;
}
