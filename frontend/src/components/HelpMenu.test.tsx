import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import HelpMenu from "./HelpMenu";
import { CITATION, DOCS_LINKS, PROJECT_LINKS } from "../models/helpLinks";

function openMenu() {
  fireEvent.click(screen.getByRole("button", { name: "Help" }));
}

describe("HelpMenu", () => {

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("shows its items only once opened", () => {
    render(<HelpMenu homeDir="/home/me/wc" unsavedChanges={false} />);
    expect(screen.queryByRole("menu")).toBeNull();
    openMenu();
    expect(screen.getAllByRole("menuitem").map(item => item.textContent)).toEqual([
      ...DOCS_LINKS.map(link => link.label),
      "How to cite DeBasher...",
      ...PROJECT_LINKS.map(link => link.label),
      "Claude Code...",
    ]);
  });

  it("opens every link in a new tab, without access to the editor", () => {
    render(<HelpMenu homeDir="/home/me/wc" unsavedChanges={false} />);
    openMenu();
    const links = screen.getAllByRole("menuitem").filter(item => item.tagName === "A");
    expect(links).toHaveLength(DOCS_LINKS.length + PROJECT_LINKS.length);
    for (const link of links) {
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    }
  });

  it("closes when a link is followed", () => {
    render(<HelpMenu homeDir="/home/me/wc" unsavedChanges={false} />);
    openMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: DOCS_LINKS[0].label }));
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("closes when the mouse is pressed outside it", () => {
    render(
      <div>
        <HelpMenu homeDir="/home/me/wc" unsavedChanges={false} />
        <p>outside</p>
      </div>
    );
    openMenu();
    fireEvent.mouseDown(screen.getByText("outside"));
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("closes when its button is pressed again", () => {
    render(<HelpMenu homeDir="/home/me/wc" unsavedChanges={false} />);
    openMenu();
    openMenu();
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("shows the reference to cite, and copies it", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    render(<HelpMenu homeDir="/home/me/wc" unsavedChanges={false} />);
    openMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: "How to cite DeBasher..." }));
    expect(screen.queryByRole("menu")).toBeNull();
    const dialog = screen.getByRole("dialog", { name: "How to cite DeBasher" });
    expect(screen.getByRole("textbox", { name: "Reference" })).toHaveValue(CITATION.text);
    expect(screen.getByRole("textbox", { name: "BibTeX" })).toHaveValue(CITATION.bibtex);
    expect(screen.getByRole("link", { name: "the article" })).toHaveAttribute("href", CITATION.articleUrl);
    fireEvent.click(screen.getAllByRole("button", { name: "Copy" })[1]);
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(CITATION.bibtex));
    expect(await screen.findByText("Copied.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(dialog).not.toBeInTheDocument();
  });

  it("selects the reference when the browser does not let it be copied", async () => {
    vi.stubGlobal("navigator", { ...navigator, clipboard: undefined });
    render(<HelpMenu homeDir="/home/me/wc" unsavedChanges={false} />);
    openMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: "How to cite DeBasher..." }));
    fireEvent.click(screen.getAllByRole("button", { name: "Copy" })[0]);
    expect(await screen.findByText(/copy it with the keyboard/)).toBeInTheDocument();
    expect(document.activeElement).toBe(screen.getByRole("textbox", { name: "Reference" }));
  });

  it("shows the command that starts Claude Code on the program, and copies it", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    render(<HelpMenu homeDir="/home/me/my programs/wc" unsavedChanges={false} />);
    openMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: "Claude Code..." }));

    const command = screen.getByRole("textbox", { name: "Command" });
    expect(command).toHaveValue(
      `debasher_claude --home-dir '/home/me/my programs/wc' --url ${window.location.origin}`
    );
    expect(screen.getByText("/debasher:design")).toBeInTheDocument();
    expect(screen.queryByText(/unsaved changes/)).toBeNull();

    fireEvent.change(screen.getByRole("textbox", { name: /Backend URL/ }), { target: { value: "http://127.0.0.1:9000" } });
    expect(command).toHaveValue("debasher_claude --home-dir '/home/me/my programs/wc' --url http://127.0.0.1:9000");

    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(
      "debasher_claude --home-dir '/home/me/my programs/wc' --url http://127.0.0.1:9000"
    ));
  });

  it("asks to save a program first, before giving a command", () => {
    render(<HelpMenu homeDir="" unsavedChanges={true} />);
    openMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: "Claude Code..." }));

    expect(screen.queryByRole("textbox", { name: "Command" })).toBeNull();
    expect(screen.getByRole("dialog")).toHaveTextContent(/save this one first/);
  });

  it("warns that Claude Code does not see the unsaved changes", () => {
    render(<HelpMenu homeDir="/home/me/wc" unsavedChanges={true} />);
    openMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: "Claude Code..." }));

    expect(screen.getByRole("dialog")).toHaveTextContent(/unsaved changes, which Claude Code does not see/);
  });

});
