import { useState } from "react";
import type { Program } from "./models/program";
import { ProgramProvider } from "./store/ProgramContext";
import HomeScreen from "./components/HomeScreen";
import ProgramEditor from "./components/ProgramEditor";
import TokenNotice from "./components/TokenNotice";

type Screen =
  | { name: "home" }
  | { name: "editor"; program: Program };

export default function App() {
  const [screen, setScreen] = useState<Screen>({ name: "home" });

  // Where a run left in progress goes on, said on the home screen after
  // leaving the editor: nothing stops the run, and the web UI keeps no
  // record of it.
  const [runMessage, setRunMessage] = useState<string | null>(null);

  return (
    <>
      <TokenNotice />
      {screen.name === "home" ? (
        <HomeScreen
          runMessage={runMessage}
          onDismissRunMessage={() => setRunMessage(null)}
          onOpen={program => {
            setRunMessage(null);
            setScreen({ name: "editor", program });
          }}
        />
      ) : (
        <ProgramProvider initialProgram={screen.program}>
          <ProgramEditor
            onClose={message => {
              setRunMessage(message);
              setScreen({ name: "home" });
            }}
          />
        </ProgramProvider>
      )}
    </>
  );
}
