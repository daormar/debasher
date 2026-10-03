// A save of a user file was refused because the file holds another file
// version than the one the save names: someone else wrote the file since it
// was read (see "Reserved names and user files" in doc/design_doc_webui.md).
// `version` is the one it holds, null when the file is gone.
export class FileVersionConflict extends Error {
  readonly version: string | null;

  constructor(message: string, version: string | null) {
    super(message);
    this.version = version;
  }
}

// The code of the conflict in the detail of the backend's answer (see
// api/routers/program_files.py).
const FILE_VERSION_CONFLICT_CODE = "file-version";

// Throws a FileVersionConflict when `response` is one.
export async function throwIfFileVersionConflict(response: Response): Promise<void> {
  if (response.status !== 409) {
    return;
  }
  const body = await response.clone().json().catch(() => null);
  if (body?.detail?.code === FILE_VERSION_CONFLICT_CODE) {
    throw new FileVersionConflict(String(body.detail.message), body.detail.version ?? null);
  }
}
