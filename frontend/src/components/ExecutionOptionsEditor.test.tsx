import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ExecutionOptionsEditor from "./ExecutionOptionsEditor";
import { ProgramProvider } from "../store/ProgramContext";
import { createEmptyProgram } from "../storage/programStorage";

vi.mock("../api/executionApi", () => ({
  listSchedulers: async () => ["BUILTIN", "SLURM"],
}));

afterEach(cleanup);

describe("ExecutionOptionsEditor", () => {

  it("keeps the fields of every scheduler in place, showing only those of the one chosen", async () => {
    render(
      <ProgramProvider initialProgram={createEmptyProgram("p")}>
        <ExecutionOptionsEditor onClose={() => {}} />
      </ProgramProvider>
    );
    const scheduler = await screen.findByRole("combobox");
    await screen.findByRole("option", { name: "SLURM" });

    fireEvent.change(scheduler, { target: { value: "BUILTIN" } });
    expect(screen.getByPlaceholderText("e.g. 4")).toBeVisible();
    expect(screen.getByPlaceholderText("e.g. node01,node02 or node[01-04]")).not.toBeVisible();

    fireEvent.change(scheduler, { target: { value: "SLURM" } });
    expect(screen.getByPlaceholderText("e.g. 4")).not.toBeVisible();
    expect(screen.getByPlaceholderText("e.g. node01,node02 or node[01-04]")).toBeVisible();
  });

});
