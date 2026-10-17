import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import ArrayConfigEditor from "./ArrayConfigEditor";
import MethodBodyEditor from "./MethodBodyEditor";
import { ProgramProvider, useProgram } from "../store/ProgramContext";
import { createEmptyProgram } from "../storage/programStorage";
import { createProcess, type ProgramProcess } from "../models/process";
import { ARRAY_TASKS_PY_TEMPLATE, SKIP_PY_TEMPLATE } from "../models/codeTemplates";

afterEach(cleanup);

function programWith(process: ProgramProcess) {
  return { ...createEmptyProgram("p"), processes: [process] };
}

function work(changes: Partial<ProgramProcess> = {}): ProgramProcess {
  return { ...createProcess("w", "work", {}, () => "o"), ...changes };
}

// The process as the store holds it after the editor saved, shown as JSON
// for the test to read.
function SavedProcess() {
  const { program } = useProgram();
  return <pre data-testid="saved">{JSON.stringify(program.processes[0])}</pre>;
}

function saved(): ProgramProcess {
  return JSON.parse(screen.getByTestId("saved").textContent ?? "");
}

function renderEditor(process: ProgramProcess, editor: React.ReactNode) {
  render(
    <ProgramProvider initialProgram={programWith(process)}>
      {editor}
      <SavedProcess />
    </ProgramProvider>
  );
}

describe("MethodBodyEditor", () => {

  it("takes the Conda environments as data by default, and saves no row with an empty field", () => {
    const process = work();
    renderEditor(process, <MethodBodyEditor process={process} methodKey="condaEnvsCode" onClose={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: "Add environment" }));
    const save = screen.getByRole("button", { name: "Save" });
    expect(save).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: " py27 " } });
    fireEvent.change(screen.getByLabelText("YAML file"), { target: { value: "py27.yml" } });
    expect(save).toBeEnabled();
    fireEvent.click(save);

    expect(saved().additionalMethods.condaEnvs).toEqual([{ name: "py27", file: "py27.yml" }]);
    expect(saved().additionalMethods.condaEnvsCode).toBeUndefined();
  });

  it("opens a Bash body of the Docker images as a body, and saving it empties the data", () => {
    const process = work({ additionalMethods: { dockerImgsCode: "pull_docker_img img" } });
    renderEditor(process, <MethodBodyEditor process={process} methodKey="dockerImgsCode" onClose={() => {}} />);

    expect(screen.getByLabelText("Given as")).toHaveValue("body");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(saved().additionalMethods.dockerImgsCode).toBe("pull_docker_img img");
    expect(saved().additionalMethods.dockerImgs).toEqual([]);
  });

  it("saves a skip file in Python from its template", () => {
    const process = work({ additionalMethods: { skipCode: "return 1" } });
    renderEditor(process, <MethodBodyEditor process={process} methodKey="skipCode" onClose={() => {}} />);

    fireEvent.change(screen.getByLabelText("Language"), { target: { value: "python" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(saved().additionalMethods.skipLanguage).toBe("python");
    expect(saved().additionalMethods.skipCode).toBe(SKIP_PY_TEMPLATE);
  });

  it("keeps the draft of each language while switching between them", () => {
    const process = work({ additionalMethods: { skipCode: "return 1" } });
    renderEditor(process, <MethodBodyEditor process={process} methodKey="skipCode" onClose={() => {}} />);

    fireEvent.change(screen.getByLabelText("Language"), { target: { value: "python" } });
    fireEvent.change(screen.getByLabelText("Language"), { target: { value: "bash" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(saved().additionalMethods.skipLanguage).toBe("bash");
    expect(saved().additionalMethods.skipCode).toBe("return 1");
  });

});

describe("ArrayConfigEditor", () => {

  it("saves a tasks file in Python with its language", () => {
    const process = work({ optionsHandler: { mode: "array", arrayCode: "local array=(a b)" } });
    renderEditor(process, <ArrayConfigEditor process={process} onClose={() => {}} />);

    fireEvent.change(screen.getByLabelText("Language"), { target: { value: "python" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(saved().optionsHandler).toEqual({ mode: "array", arrayCode: ARRAY_TASKS_PY_TEMPLATE, language: "python" });
  });

});
