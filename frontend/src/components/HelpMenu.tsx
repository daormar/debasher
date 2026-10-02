import { useCallback, useRef, useState } from "react";
import type { CSSProperties } from "react";

import { DOCS_LINKS, PROJECT_LINKS } from "../models/helpLinks";
import type { HelpLink } from "../models/helpLinks";
import CitationDialog from "./CitationDialog";
import { useClickOutside } from "./useClickOutside";

const ITEM_STYLE: CSSProperties = {
  textAlign: "left",
  padding: "8px 12px",
  border: "none",
  background: "none",
  cursor: "pointer",
  color: "inherit",
  font: "inherit",
  textDecoration: "none",
  whiteSpace: "nowrap",
};

// The Help menu of the toolbar: links to the documentation and to the
// project, each opened in a new tab of the browser so that the editor, and
// what it holds unsaved, stays as it is, and the reference of the article to
// cite.
export default function HelpMenu() {

  const [isOpen, setOpen] =
    useState(false);

  const [isCitationOpen, setCitationOpen] =
    useState(false);

  const containerRef =
    useRef<HTMLDivElement>(null);

  const closeMenu = useCallback(() => setOpen(false), []);

  useClickOutside(containerRef, isOpen, closeMenu);

  function renderLink(link: HelpLink) {
    return (
      <a
        key={link.url}
        role="menuitem"
        href={link.url}
        target="_blank"
        rel="noopener noreferrer"
        onClick={closeMenu}
        style={ITEM_STYLE}
      >
        {link.label}
      </a>
    );
  }

  return (

    <div
      ref={containerRef}
      style={{
        position: "relative",
      }}
    >

      <button
        onClick={() => setOpen(open => !open)}
      >
        Help
      </button>

      {isOpen && (

        <div
          role="menu"
          style={{
            position: "absolute",
            top: "100%",
            // At the right end of the toolbar, the menu opens towards the
            // left so that it stays inside the window.
            right: 0,
            marginTop: 4,
            background: "#fff",
            border: "1px solid #ccc",
            borderRadius: 4,
            boxShadow: "0 2px 8px rgba(0, 0, 0, 0.15)",
            display: "flex",
            flexDirection: "column",
            minWidth: 220,
            zIndex: 1000,
          }}
        >

          {DOCS_LINKS.map(renderLink)}

          <div
            role="separator"
            style={{ borderTop: "1px solid #eee" }}
          />

          <button
            role="menuitem"
            onClick={() => {
              closeMenu();
              setCitationOpen(true);
            }}
            style={ITEM_STYLE}
          >
            How to cite DeBasher...
          </button>

          {PROJECT_LINKS.map(renderLink)}

        </div>

      )}

      {isCitationOpen && (
        <CitationDialog
          onClose={() => setCitationOpen(false)}
        />
      )}

    </div>

  );

}
