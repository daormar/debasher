import { useEffect } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import Inspector from "./Inspector";
import { ProgramProvider, useProgram } from "../store/ProgramContext";
import { createEmptyProgram } from "../storage/programStorage";
import { createProcess, type ProgramProcess } from "../models/process";

afterEach(cleanup);

// Selects the only process on mount, as a click on its node does, and
// shows it as the store holds it, as JSON for the test to read.
function SelectedProcess() {
  const { program, selectProcess } = useProgram();
  useEffect(() => selectProcess(program.processes[0].id), []);
  return <pre data-testid="saved">{JSON.stringify(program.processes[0])}</pre>;
}

function saved(): ProgramProcess {
  return JSON.parse(screen.getByTestId("saved").textContent ?? "");
}

describe("Inspector", () => {

  it("sets the language of the options handler back to Bash when the manual mode is chosen", async () => {
    const process: ProgramProcess = {
      ...createProcess("w", "work", {}, () => "o"),
      optionsHandler: { mode: "array", arrayCode: "def tasks(run):\n    pass\n", language: "python" },
    };
    render(
      <ProgramProvider initialProgram={{ ...createEmptyProgram("p"), processes: [process] }}>
        <Inspector />
        <SelectedProcess />
      </ProgramProvider>
    );

    // The option definition of a manual process is a Bash function, which
    // script generation refuses in Python
    const mode = await screen.findByDisplayValue("array");
    fireEvent.change(mode, { target: { value: "manual" } });

    expect(saved().optionsHandler.mode).toBe("manual");
    expect(saved().optionsHandler.language).toBe("bash");
  });

  it("adds an option with the label typed, without the spaces around it", async () => {
    render(
      <ProgramProvider initialProgram={{ ...createEmptyProgram("p"), processes: [createProcess("w", "work", {}, () => "o")] }}>
        <Inspector />
        <SelectedProcess />
      </ProgramProvider>
    );

    // The engine would keep the spaces as part of the label
    fireEvent.change(await screen.findByPlaceholderText("Option label"), { target: { value: " -in " } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    expect(saved().options.map(option => option.label)).toEqual(["-in"]);
  });

});
