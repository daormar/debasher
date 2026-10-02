import { useRef, useState } from "react";

import { CITATION } from "../models/helpLinks";
import { copyOrSelect } from "../utils/clipboard";

interface Props {
  onClose: () => void;
}

interface CitationFormatProps {
  label: string;
  text: string;
  rows: number;
}

// One form of the reference, read only, with "Copy".
function CitationFormat({ label, text, rows }: CitationFormatProps) {

  const [copyNote, setCopyNote] = useState<string | null>(null);

  const textRef = useRef<HTMLTextAreaElement>(null);

  async function handleCopy() {
    setCopyNote(
      await copyOrSelect(text, textRef.current)
        ? "Copied."
        : "The browser did not let the page copy: the text is selected, copy it with the keyboard."
    );
  }

  return (

    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 4,
      }}
    >

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          fontSize: 13,
        }}
      >
        <span style={{ fontWeight: "bold" }}>{label}</span>
        <button onClick={handleCopy}>Copy</button>
        {copyNote && <span style={{ color: "#555" }}>{copyNote}</span>}
      </div>

      <textarea
        ref={textRef}
        aria-label={label}
        readOnly
        rows={rows}
        value={text}
        style={{
          fontFamily: "ui-monospace, Consolas, monospace",
          fontSize: 12,
          resize: "none",
        }}
      />

    </div>

  );

}

// "How to cite DeBasher" of the Help menu: the reference of the article that
// describes DeBasher, as text and as BibTeX, each ready to copy, and a link to
// the article.
export default function CitationDialog({ onClose }: Props) {

  return (

    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0, 0, 0, 0.4)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >

      <div
        role="dialog"
        aria-label="How to cite DeBasher"
        style={{
          width: "60%",
          maxWidth: 720,
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >

        <h3 style={{ margin: 0 }}>
          How to cite DeBasher
        </h3>

        <p style={{ margin: 0, fontSize: 14 }}>
          If you use DeBasher in your research, please cite{" "}
          <a
            href={CITATION.articleUrl}
            target="_blank"
            rel="noopener noreferrer"
          >
            the article
          </a>{" "}
          that describes it:
        </p>

        <CitationFormat label="Reference" text={CITATION.text} rows={4} />

        <CitationFormat label="BibTeX" text={CITATION.bibtex} rows={11} />

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
          }}
        >
          <button onClick={onClose}>
            Close
          </button>
        </div>

      </div>

    </div>

  );

}
