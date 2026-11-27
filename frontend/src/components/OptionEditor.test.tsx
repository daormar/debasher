import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import OptionEditor from "./OptionEditor";
import { ProgramProvider, useProgram } from "../store/ProgramContext";
import { createEmptyProgram } from "../storage/programStorage";
import { createOption, type ProgramOption } from "../models/option";
import { createProcess, type ProgramProcess } from "../models/process";
import type { Program } from "../models/program";

afterEach(cleanup);

function processOf(id: string, name: string, options: ProgramOption[]): ProgramProcess {
  return { ...createProcess(id, name, {}, () => "o"), options };
}

// The options of the reader as the store holds them after the editor
// saved, shown as JSON for the test to read.
function SavedOptions() {
  const { program } = useProgram();
  return <pre data-testid="saved">{JSON.stringify(program.processes[1].options)}</pre>;
}

function saved(): ProgramOption[] {
  return JSON.parse(screen.getByTestId("saved").textContent ?? "");
}

function renderEditor(program: Program, option: ProgramOption) {
  render(
    <ProgramProvider initialProgram={program}>
      <OptionEditor processId="r" option={option} manualMode={false} onClose={() => {}} />
      <SavedOptions />
    </ProgramProvider>
  );
}

describe("OptionEditor", () => {

  it("saves a mirrored FIFO output", () => {
    const output = createOption("q", "-outq");
    const program = { ...createEmptyProgram("p"), processes: [processOf("w", "writer", []), processOf("r", "reader", [output])] };
    renderEditor(program, output);

    fireEvent.change(screen.getByDisplayValue("Direct value"), { target: { value: "fifo" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /Mirror/ }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(saved()[0]).toMatchObject({ label: "-outq", direction: "output", channel: "fifo", mirror: true });
  });

  it("corrects the draft as it is edited: an input leaves the process output directory, and a source excludes the other", () => {
    const output = createOption("d", "-outd", { channel: "process_outdir", dataType: "dir" });
    const program = { ...createEmptyProgram("p"), processes: [processOf("w", "writer", []), processOf("r", "reader", [output])] };
    renderEditor(program, output);

    // Only an output names a process output directory, which takes a subpath
    expect(screen.getByText("Subdirectory (optional)")).toBeInTheDocument();
    fireEvent.change(screen.getByDisplayValue("-outd"), { target: { value: "-ind" } });
    expect(screen.queryByText("Subdirectory (optional)")).toBeNull();

    const commandLine = screen.getByRole("checkbox", { name: /Command line/ });
    const fromSpec = screen.getByRole("checkbox", { name: /From process spec/ });
    fireEvent.click(commandLine);
    fireEvent.click(fromSpec);
    expect(fromSpec).toBeChecked();
    expect(commandLine).not.toBeChecked();
  });

  it("shows what a connected input reads and the data type of its output, which a save keeps", () => {
    const input = createOption("i", "-in");
    const program: Program = {
      ...createEmptyProgram("p"),
      processes: [
        processOf("w", "writer", [createOption("o", "-outf", { dataType: "int" })]),
        processOf("r", "reader", [input]),
      ],
      edges: [{ id: "e", sourceProcessId: "w", sourceOptionId: "o", targetProcessId: "r", targetOptionId: "i" }],
    };
    renderEditor(program, input);

    expect(screen.getByText("[writer;-outf]")).toBeInTheDocument();
    expect(screen.getByText("int (from connection)")).toBeInTheDocument();
    // normalizeProgram also keeps the saved fields of a connected input in
    // step with its connection
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(saved()[0]).toMatchObject({ channel: "none", dataType: "int", value: "[writer;-outf]" });
  });

});
