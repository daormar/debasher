import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createOption } from "../models/option";
import type { OptionChannel, ProgramOption } from "../models/option";
import ProcessIOModal from "./ProcessIOModal";

afterEach(cleanup);

// The row of an option, found by its label.
function row(label: string): HTMLElement {
  return screen.getByText(label, { selector: "label" }).parentElement!;
}

function renderModal(options: ProgramOption[], deliveryChannels: Map<string, OptionChannel>) {
  const resolvedValues = Object.fromEntries(options.map(o => [o.label, `/out/${o.label.slice(1)}`]));
  render(
    <ProcessIOModal
      processName="sum"
      options={options}
      resolvedValues={resolvedValues}
      families={[]}
      deliveryChannels={deliveryChannels}
      isViewPending={false}
      onViewPath={vi.fn()}
      onPickFanoutIndex={vi.fn()}
      onClose={vi.fn()}
    />,
  );
}

describe("ProcessIOModal", () => {
  it("offers View on a value descriptor, whatever the data type of its value", () => {
    const outv = createOption("outv", "-outv", { direction: "output", channel: "value_desc", dataType: "int" });
    const total = createOption("total", "-total", { dataType: "string" });
    // A row of a fanin family whose family reads value descriptors
    const part = { ...createOption("part", "-part-ith", { dataType: "float" }), id: "part:0", label: "-part0" };
    renderModal([outv, total, part], new Map<string, OptionChannel>([
      ["outv", "value_desc"],
      ["total", "value_desc"],
      ["part", "value_desc"],
    ]));
    for (const label of ["-outv", "-total", "-part0"]) {
      expect(within(row(label)).queryByRole("button", { name: "View" })).not.toBeNull();
    }
  });

  it("offers no View on a FIFO, nor on a value that is not a path", () => {
    const outf = createOption("outf", "-outf", { direction: "output", channel: "fifo", dataType: "file" });
    const inf = createOption("inf", "-inf", { dataType: "file" });
    const n = createOption("n", "-n", { dataType: "int" });
    renderModal([outf, inf, n], new Map<string, OptionChannel>([
      ["outf", "fifo"],
      ["inf", "fifo"],
      ["n", "none"],
    ]));
    for (const label of ["-outf", "-inf", "-n"]) {
      expect(within(row(label)).queryByRole("button", { name: "View" })).toBeNull();
    }
  });

  it("offers View on a file and on a directory channel", () => {
    const data = createOption("data", "-data", { dataType: "file" });
    const outd = createOption("outd", "-outd", { direction: "output", channel: "process_outdir", dataType: "dir" });
    renderModal([data, outd], new Map<string, OptionChannel>([
      ["data", "none"],
      ["outd", "process_outdir"],
    ]));
    for (const label of ["-data", "-outd"]) {
      expect(within(row(label)).queryByRole("button", { name: "View" })).not.toBeNull();
    }
  });
});
