import { useRef, useState } from "react";

interface Props {
  // The code prompt, composed by the editor from the code request.
  prompt: string;
  request: string;
  onRequestChange: (request: string) => void;
  // What to do with the answer, said once the prompt is copied.
  pasteHint: string;
}

/**
 * The prompt panel of a code editor: the code request, the code prompt, read
 * only, and "Copy". The code comes back by being pasted into the editor, like
 * any code: the panel takes nothing back and sends nothing anywhere.
 */
export default function CodePromptPanel({ prompt, request, onRequestChange, pasteHint }: Props) {

  const [copyNote, setCopyNote] = useState<string | null>(null);

  const promptRef = useRef<HTMLTextAreaElement>(null);

  // The clipboard is missing on a page opened from a file, and a browser
  // may refuse it: the prompt is then selected, for the keyboard to copy.
  async function handleCopy() {
    try {
      if (!navigator.clipboard) {
        throw new Error("no clipboard");
      }
      await navigator.clipboard.writeText(prompt);
      setCopyNote(`Copied. ${pasteHint}`);
    } catch {
      promptRef.current?.focus();
      promptRef.current?.select();
      setCopyNote("The browser did not let the page copy: the prompt is selected, copy it with the keyboard.");
    }
  }

  return (

    <div
      style={{
        flex: 1,
        minWidth: 0,
        display: "flex",
        flexDirection: "column",
        gap: 6,
        fontSize: 13,
      }}
    >

      <label htmlFor="code-request">
        What should the code do? (optional)
      </label>

      <textarea
        id="code-request"
        rows={3}
        value={request}
        placeholder="Blank: the code that the description asks for"
        onChange={event => onRequestChange(event.target.value)}
        style={{ resize: "vertical", flexShrink: 0 }}
      />

      <label htmlFor="code-prompt">
        Prompt, to copy into an AI tool of your choice
      </label>

      <textarea
        id="code-prompt"
        ref={promptRef}
        readOnly
        value={prompt}
        style={{
          flex: 1,
          minHeight: 200,
          fontFamily: "monospace",
          fontSize: 12,
          resize: "none",
        }}
      />

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >

        <button onClick={handleCopy}>
          Copy
        </button>

        <span style={{ color: "#555" }}>
          {copyNote ?? "Nothing is sent from here: the prompt only leaves through your copy."}
        </span>

      </div>

    </div>

  );

}

// The button of a code editor that opens and closes its prompt panel.
export function CodePromptButton({ isOpen, onToggle }: { isOpen: boolean; onToggle: () => void }) {
  return (
    <button
      title="Prompt for an AI tool"
      aria-pressed={isOpen}
      onClick={onToggle}
      style={{
        background: isOpen ? "#ede7f6" : undefined,
      }}
    >
      ✨ AI prompt
    </button>
  );
}
