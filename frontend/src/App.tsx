import { useState } from "react";
import type { Workflow } from "./models/workflow";
import { WorkflowProvider } from "./store/WorkflowContext";
import HomeScreen from "./components/HomeScreen";
import WorkflowEditor from "./components/WorkflowEditor";

type Screen =
  | { name: "home" }
  | { name: "editor"; workflow: Workflow };

export default function App() {
  const [screen, setScreen] = useState<Screen>({ name: "home" });

  if (screen.name === "home") {
    return (
      <HomeScreen
        onOpen={workflow => setScreen({ name: "editor", workflow })}
      />
    );
  }

  return (
    <WorkflowProvider initialWorkflow={screen.workflow}>
      <WorkflowEditor
        onClose={() => setScreen({ name: "home" })}
      />
    </WorkflowProvider>
  );
}
