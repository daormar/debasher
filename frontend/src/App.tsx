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

  if (screen.name === "home") {
    return (
      <HomeScreen
        onOpen={program => setScreen({ name: "editor", program })}
      />
    );
  }

  return (
    <ProgramProvider initialProgram={screen.program}>
      <ProgramEditor
        onClose={() => setScreen({ name: "home" })}
      />
    </ProgramProvider>
  );
}
