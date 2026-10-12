import { describe, expect, it } from "vitest";

import { languageExtensions } from "./codeLanguages";

// The components of the web UI, read as text.
const COMPONENTS = import.meta.glob<string>("./*.tsx", { query: "?raw", import: "default", eager: true });

// The props of every <CodeMirror> element of a component.
function codeMirrorProps(source: string): string[] {
  return [...source.matchAll(/<CodeMirror\b([\s\S]*?)\/>/g)].map(m => m[1]);
}

describe("the extensions of a code editor", () => {
  it("are the same array for the same language, render after render", () => {
    expect(languageExtensions("bash")).toBe(languageExtensions("bash"));
    expect(languageExtensions("python")).toBe(languageExtensions("python"));
    expect(languageExtensions("python")).not.toBe(languageExtensions("bash"));
  });

  it("never come from an array or a function written in the JSX of an editor", () => {
    const editors = Object.entries(COMPONENTS).flatMap(([path, source]) =>
      codeMirrorProps(source).map(props => ({ path, props })));
    expect(editors.length).toBeGreaterThan(5);
    for (const { path, props } of editors) {
      expect(props, path).not.toMatch(/extensions=\{\[/);
      expect(props, path).not.toMatch(/onChange=\{\s*\(?\w*\)?\s*=>/);
      expect(props, path).not.toMatch(/basicSetup=\{\{/);
    }
  });
});
