import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_WEBUI_INFO } from "../api/webuiApi";
import type { WebuiInfo } from "../api/webuiApi";
import HelpMenu from "./HelpMenu";
import { CITATION, DOCS_LINKS, PROJECT_LINKS } from "../models/helpLinks";

function openMenu() {
  fireEvent.click(screen.getByRole("button", { name: "Help" }));
}

// The backend of the dialog of Claude Code, which tells whether it is offered,
// and how.
function stubWebuiInfo(claudeCode: boolean, more: Partial<WebuiInfo> = {}) {
  const info = { ...DEFAULT_WEBUI_INFO, claudeCode, ...more };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(info))));
}

// The dialog shows what it offers once the backend has answered: the tests
// wait for it with findBy.
function openClaudeCodeDialog() {
  openMenu();
  fireEvent.click(screen.getByRole("menuitem", { name: "Claude Code..." }));
}

describe("HelpMenu", () => {

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
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
    stubWebuiInfo(true);
    render(<HelpMenu homeDir="/home/me/my programs/wc" unsavedChanges={false} />);
    openClaudeCodeDialog();

    const command = await screen.findByRole("textbox", { name: "Command" });
    expect(command).toHaveValue(
      `debasher_claude --home-dir '/home/me/my programs/wc' --url ${window.location.origin}`
    );
    for (const skill of ["/debasher:help", "/debasher:design", "/debasher:implement", "/debasher:review"]) {
      expect(screen.getByText(skill)).toBeInTheDocument();
    }
    expect(screen.queryByText(/unsaved changes/)).toBeNull();

    fireEvent.change(screen.getByRole("textbox", { name: /Backend URL/ }), { target: { value: "http://127.0.0.1:9000" } });
    expect(command).toHaveValue("debasher_claude --home-dir '/home/me/my programs/wc' --url http://127.0.0.1:9000");

    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(
      "debasher_claude --home-dir '/home/me/my programs/wc' --url http://127.0.0.1:9000"
    ));

    fireEvent.change(screen.getByRole("combobox", { name: /Conversation/ }), { target: { value: "continue" } });
    expect(command).toHaveValue(
      "debasher_claude --home-dir '/home/me/my programs/wc' --url http://127.0.0.1:9000 -- --continue"
    );
  });

  it("shows only what the way chosen to run Claude Code needs, where the backend offers both", async () => {
    stubWebuiInfo(true, { claudeCodeTerminal: true });
    render(<HelpMenu homeDir="/home/me/wc" unsavedChanges={false} />);
    openClaudeCodeDialog();

    const where = await screen.findByRole("radiogroup", { name: "Where" });
    const inEditor = within(where).getByRole("radio", { name: "In this editor" });
    const ownTerminal = within(where).getByRole("radio", { name: "In a terminal of your own" });
    // The editor first, the more direct way.
    expect(inEditor).toBeChecked();
    expect(screen.getByRole("button", { name: "Open in the page" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Command" })).toBeNull();
    expect(screen.queryByRole("textbox", { name: /Backend URL/ })).toBeNull();

    fireEvent.click(ownTerminal);
    expect(screen.getByRole("textbox", { name: "Command" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /Backend URL/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open in the page" })).toBeNull();

    // The conversation is for both ways, and the command follows it.
    fireEvent.change(screen.getByRole("combobox", { name: /Conversation/ }), { target: { value: "continue" } });
    expect(screen.getByRole("textbox", { name: "Command" })).toHaveValue(
      `debasher_claude --home-dir /home/me/wc --url ${window.location.origin} -- --continue`
    );
  });

  it("keeps its size whichever way of running Claude Code is chosen", async () => {
    stubWebuiInfo(true, { claudeCodeTerminal: true });
    render(<HelpMenu homeDir="/home/me/wc" unsavedChanges={false} />);
    openClaudeCodeDialog();

    const dialog = await screen.findByRole("dialog", { name: "Claude Code" });
    await screen.findByRole("radiogroup", { name: "Where" });
    const height = dialog.style.height;
    expect(height).not.toBe("");

    fireEvent.click(screen.getByRole("radio", { name: "In a terminal of your own" }));
    expect(dialog.style.height).toBe(height);
  });

  it("makes the box of the command as tall as the command", async () => {
    // jsdom lays nothing out: the command takes 90 pixels, as a browser
    // would measure it.
    vi.spyOn(HTMLTextAreaElement.prototype, "scrollHeight", "get").mockReturnValue(90);
    stubWebuiInfo(true);
    render(<HelpMenu homeDir="/home/me/wc" unsavedChanges={false} />);
    openClaudeCodeDialog();

    const command = await screen.findByRole("textbox", { name: "Command" });
    expect(command.style.height).toBe("90px");
  });

  it("says how to install Claude Code whichever way is chosen", async () => {
    stubWebuiInfo(true, {
      claudeCodeTerminal: true,
      claudeCodeInstall: "docker compose exec -it debasher install-claude-code",
    });
    render(<HelpMenu homeDir="/home/me/wc" unsavedChanges={false} />);
    openClaudeCodeDialog();

    expect(await screen.findByText("docker compose exec -it debasher install-claude-code")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "In a terminal of your own" }));
    expect(screen.getByText("docker compose exec -it debasher install-claude-code")).toBeInTheDocument();
  });

  it("gives the command alone, with no choice of where, where the backend offers no session in the page", async () => {
    stubWebuiInfo(true);
    render(<HelpMenu homeDir="/home/me/wc" unsavedChanges={false} />);
    openClaudeCodeDialog();

    await screen.findByRole("textbox", { name: "Command" });
    expect(screen.queryByRole("radiogroup", { name: "Where" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Open in the page" })).toBeNull();
  });

  it("asks to save a program first, before giving a command", async () => {
    stubWebuiInfo(true);
    render(<HelpMenu homeDir="" unsavedChanges={true} />);
    openClaudeCodeDialog();

    expect(await screen.findByText(/save this one first/)).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Command" })).toBeNull();
  });

  it("warns that Claude Code does not see the unsaved changes", async () => {
    stubWebuiInfo(true);
    render(<HelpMenu homeDir="/home/me/wc" unsavedChanges={true} />);
    openClaudeCodeDialog();

    expect(await screen.findByText(/unsaved changes, which Claude Code does not see/)).toBeInTheDocument();
  });

  it("gives no command where the backend does not offer Claude Code", async () => {
    stubWebuiInfo(false);
    render(<HelpMenu homeDir="/home/me/wc" unsavedChanges={false} />);
    openClaudeCodeDialog();

    expect(await screen.findByText(/Claude Code is not available with this web UI/)).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Command" })).toBeNull();
    expect(fetch).toHaveBeenCalledWith("/api/webui/info");
  });

  it("names the backend by the URL that the backend gives", async () => {
    stubWebuiInfo(true, { backendUrl: "http://127.0.0.1:8001" });
    render(<HelpMenu homeDir="/home/me/wc" unsavedChanges={false} />);
    openClaudeCodeDialog();

    expect(await screen.findByRole("textbox", { name: "Command" })).toHaveValue(
      "debasher_claude --home-dir /home/me/wc --url http://127.0.0.1:8001"
    );
  });

  it("runs the command inside the container of the backend, and says how to install Claude Code there", async () => {
    stubWebuiInfo(true, {
      claudeCodePrefix: "docker compose exec -it debasher",
      claudeCodeInstall: "docker compose exec -it debasher install-claude-code",
      backendUrl: "http://127.0.0.1:8000",
    });
    render(<HelpMenu homeDir="/data/wc" unsavedChanges={false} />);
    openClaudeCodeDialog();

    expect(await screen.findByRole("textbox", { name: "Command" })).toHaveValue(
      "docker compose exec -it debasher debasher_claude --home-dir /data/wc --url http://127.0.0.1:8000"
    );
    expect(screen.getByRole("dialog")).toHaveTextContent(/in its container/);
    expect(screen.getByText("docker compose exec -it debasher install-claude-code")).toBeInTheDocument();
  });

  it("gives the command when the backend cannot say whether it offers Claude Code", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    render(<HelpMenu homeDir="/home/me/wc" unsavedChanges={false} />);
    openClaudeCodeDialog();

    expect(await screen.findByRole("textbox", { name: "Command" })).toBeInTheDocument();
  });

});
