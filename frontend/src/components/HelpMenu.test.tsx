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
    render(<HelpMenu />);
    expect(screen.queryByRole("menu")).toBeNull();
    openMenu();
    expect(screen.getAllByRole("menuitem").map(item => item.textContent)).toEqual([
      ...DOCS_LINKS.map(link => link.label),
      "How to cite DeBasher...",
      ...PROJECT_LINKS.map(link => link.label),
    ]);
  });

  it("opens every link in a new tab, without access to the editor", () => {
    render(<HelpMenu />);
    openMenu();
    const links = screen.getAllByRole("menuitem").filter(item => item.tagName === "A");
    expect(links).toHaveLength(DOCS_LINKS.length + PROJECT_LINKS.length);
    for (const link of links) {
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    }
  });

  it("closes when a link is followed", () => {
    render(<HelpMenu />);
    openMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: DOCS_LINKS[0].label }));
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("closes when the mouse is pressed outside it", () => {
    render(
      <div>
        <HelpMenu />
        <p>outside</p>
      </div>
    );
    openMenu();
    fireEvent.mouseDown(screen.getByText("outside"));
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("closes when its button is pressed again", () => {
    render(<HelpMenu />);
    openMenu();
    openMenu();
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("shows the reference to cite, and copies it", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    render(<HelpMenu />);
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
    render(<HelpMenu />);
    openMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: "How to cite DeBasher..." }));
    fireEvent.click(screen.getAllByRole("button", { name: "Copy" })[0]);
    expect(await screen.findByText(/copy it with the keyboard/)).toBeInTheDocument();
    expect(document.activeElement).toBe(screen.getByRole("textbox", { name: "Reference" }));
  });

});
