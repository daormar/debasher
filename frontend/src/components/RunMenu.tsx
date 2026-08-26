import { useEffect, useRef, useState } from "react";

import EnvVarsEditor from "./EnvVarsEditor";
import OutputDirEditor from "./OutputDirEditor";

const MENU_ITEMS = [
  "Set environment variables",
  "Set output directory",
  "Set execution options",
  "Set workflow options",
  "Run workflow",
  "Stop workflow",
] as const;

export default function RunMenu() {

  const [isOpen, setOpen] =
    useState(false);

  const [isEnvVarsOpen, setEnvVarsOpen] =
    useState(false);

  const [isOutputDirOpen, setOutputDirOpen] =
    useState(false);

  const containerRef =
    useRef<HTMLDivElement>(null);

  function handleItemClick(item: (typeof MENU_ITEMS)[number]) {

    setOpen(false);

    if (item === "Set environment variables") {
      setEnvVarsOpen(true);
    } else if (item === "Set output directory") {
      setOutputDirOpen(true);
    }

  }

  useEffect(() => {

    if (!isOpen) {
      return;
    }

    function handleClickOutside(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside, true);

    return () =>
      document.removeEventListener("mousedown", handleClickOutside, true);

  }, [isOpen]);

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
        Run
      </button>

      {isOpen && (

        <div
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            marginTop: 4,
            background: "#fff",
            border: "1px solid #ccc",
            borderRadius: 4,
            boxShadow: "0 2px 8px rgba(0, 0, 0, 0.15)",
            display: "flex",
            flexDirection: "column",
            minWidth: 200,
            zIndex: 1000,
          }}
        >

          {MENU_ITEMS.map(item => (

            <button

              key={item}

              onClick={() => handleItemClick(item)}

              style={{
                textAlign: "left",
                padding: "8px 12px",
                border: "none",
                background: "none",
                cursor: "pointer",
              }}

            >
              {item}
            </button>

          ))}

        </div>

      )}

      {isEnvVarsOpen && (
        <EnvVarsEditor
          onClose={() => setEnvVarsOpen(false)}
        />
      )}

      {isOutputDirOpen && (
        <OutputDirEditor
          onClose={() => setOutputDirOpen(false)}
        />
      )}

    </div>

  );

}
