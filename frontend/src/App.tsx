import { useState } from "react";
import type { Program } from "./models/program";
import { ProgramProvider } from "./store/ProgramContext";
import HomeScreen from "./components/HomeScreen";
import ProgramEditor from "./components/ProgramEditor";

type Screen =
  | { name: "home" }
  | { name: "editor"; program: Program };

export default function App() {
  const [screen, setScreen] = useState<Screen>({ name: "home" });

  // Where a run left in progress goes on, said on the home screen after
  // leaving the editor: nothing stops the run, and the web UI keeps no
  // record of it.
  const [notice, setNotice] = useState<string | null>(null);

  if (screen.name === "home") {
    return (
      <HomeScreen
        notice={notice}
        onDismissNotice={() => setNotice(null)}
        onOpen={program => {
          setNotice(null);
          setScreen({ name: "editor", program });
        }}
      />
    );
  }

  return (
    <ProgramProvider initialProgram={screen.program}>
      <ProgramEditor
        onClose={runNotice => {
          setNotice(runNotice);
          setScreen({ name: "home" });
        }}
      />
    </ProgramProvider>
  );
}
