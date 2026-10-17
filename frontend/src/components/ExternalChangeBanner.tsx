import { useState } from "react";

import { useProgram } from "../store/ProgramContext";
import ChangedElsewhereBanner from "./ChangedElsewhereBanner";

// Shown under the toolbar when someone else saved the program while the tab
// held unsaved changes, or when a write of the tab was refused because they
// did: the user loads what was saved, losing the changes of the tab, or saves
// the tab over it, losing what was saved.
export default function ExternalChangeBanner() {

  const { externalDigest, loadExternal, saveOverExternal } = useProgram();

  const [error, setError] = useState<string | null>(null);

  const [pending, setPending] = useState(false);

  if (externalDigest === null) {
    return null;
  }

  async function act(action: () => Promise<void>) {
    setError(null);
    setPending(true);
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <ChangedElsewhereBanner
      message="The program was written from elsewhere (another tab, an agent, or an edit of its files) since this tab loaded it."
      error={error}
      actions={[
        { label: "Load it (lose my changes)", onClick: () => act(loadExternal), disabled: pending },
        { label: "Save mine over it", onClick: () => act(saveOverExternal), disabled: pending },
      ]}
    />
  );

}
