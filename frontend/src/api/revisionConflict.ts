// A request that writes the program metadata was refused because the
// metadata holds another revision than the one the program names: someone
// else saved the program since it was loaded (see "Revisions of the program
// metadata" in doc/design_doc_webui.md).
export class RevisionConflict extends Error {
  readonly revision: number;

  constructor(message: string, revision: number) {
    super(message);
    this.revision = revision;
  }
}

// The code of the conflict in the detail of the backend's answer (see
// api/saving.py).
const REVISION_CONFLICT_CODE = "revision";

// Throws a RevisionConflict when `response` is one.
export async function throwIfRevisionConflict(response: Response): Promise<void> {
  if (response.status !== 409) {
    return;
  }
  const body = await response.clone().json().catch(() => null);
  if (body?.detail?.code === REVISION_CONFLICT_CODE) {
    throw new RevisionConflict(String(body.detail.message), Number(body.detail.revision));
  }
}
