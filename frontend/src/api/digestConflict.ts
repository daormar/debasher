// A request that writes the program was refused because the artifact in
// the home directory holds another digest than the one the program names:
// someone else wrote the program since it was loaded (see "Loading, saving
// and the local state" in doc/design_doc_webui.md).
export class DigestConflict extends Error {
  readonly digest: string;

  constructor(message: string, digest: string) {
    super(message);
    this.digest = digest;
  }
}

// The code of the conflict in the detail of the backend's answer (see
// api/saving.py).
const DIGEST_CONFLICT_CODE = "digest";

// Throws a DigestConflict when `response` is one.
export async function throwIfDigestConflict(response: Response): Promise<void> {
  if (response.status !== 409) {
    return;
  }
  const body = await response.clone().json().catch(() => null);
  if (body?.detail?.code === DIGEST_CONFLICT_CODE) {
    throw new DigestConflict(String(body.detail.message), String(body.detail.digest));
  }
}
