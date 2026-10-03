import { useEffect } from "react";

import Toolbar from "./Toolbar";
import ExternalChangeBanner from "./ExternalChangeBanner";
import { useProgram } from "../store/ProgramContext";
import ProgramCanvas from "./ProgramCanvas";
import Inspector from "./Inspector";

interface Props {
  onClose: (runMessage: string | null) => void;
}

export default function ProgramEditor({ onClose }: Props) {

  const { unsavedChanges } = useProgram();

  // Closing or reloading the browser tab with unsaved changes asks first;
  // the browser words the question.
  useEffect(() => {
    if (!unsavedChanges) {
      return;
    }
    function handleBeforeUnload(event: BeforeUnloadEvent) {
      event.preventDefault();
    }
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [unsavedChanges]);

  return (

    <div
      style={{
        width: "100%",
        height: "100vh",
        display: "flex",
        flexDirection: "column",
      }}
    >

      <Toolbar onClose={onClose} />

      <ExternalChangeBanner />


      <div
        style={{
          flex: 1,
          display: "flex",
          minHeight: 0,
        }}
      >

        <div
          style={{
            flex: 1,
          }}
        >

          <ProgramCanvas />

        </div>


        <Inspector />


      </div>


    </div>

  );

}
