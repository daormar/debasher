import { describe, expect, it } from "vitest";

import { CITATION, DOCS_LINKS, DOCS_URL, PROJECT_LINKS, REPOSITORY_URL } from "./helpLinks";

// The sources of the documentation and the README, read from the repository.
// The sources of the documentation are not distributed with the package, so
// the check on them is skipped where they are absent.
const DOCS_SOURCES = import.meta.glob<string>(
  "../../../rtdocs/source/*.rst",
  { query: "?raw", import: "default", eager: true },
);

const README = Object.values(import.meta.glob<string>(
  "../../../README.md",
  { query: "?raw", import: "default", eager: true },
))[0];

const ALL_LINKS = [...DOCS_LINKS, ...PROJECT_LINKS];

describe("the Help menu links", () => {

  it("open on the documentation or the repository", () => {
    for (const link of DOCS_LINKS) {
      expect(link.url.startsWith(DOCS_URL), link.url).toBe(true);
    }
    for (const link of PROJECT_LINKS) {
      expect(link.url.startsWith(REPOSITORY_URL), link.url).toBe(true);
    }
  });

  it("each have their own label", () => {
    const labels = ALL_LINKS.map(link => link.label);
    expect(new Set(labels).size).toBe(labels.length);
  });

  it.skipIf(Object.keys(DOCS_SOURCES).length === 0)(
    "lead to pages that the documentation has",
    () => {
      const pageLinks = DOCS_LINKS.filter(link => link.url !== DOCS_URL);
      expect(pageLinks.length).toBeGreaterThan(0);
      for (const link of pageLinks) {
        const source = link.url.slice(DOCS_URL.length).replace(/\.html$/, ".rst");
        expect(
          Object.keys(DOCS_SOURCES).some(path => path.endsWith(`/${source}`)),
          link.url,
        ).toBe(true);
      }
    },
  );

});

describe("CITATION", () => {

  it("is the reference that README.md asks to cite", () => {
    const readme = README.replace(/\s+/g, " ");
    expect(readme).toContain(CITATION.text);
  });

  it("links to the article by its DOI, as the BibTeX entry names it", () => {
    const doi = CITATION.articleUrl.replace("https://doi.org/", "");
    expect(CITATION.bibtex).toContain(`doi     = {${doi}}`);
    expect(CITATION.text).toContain(CITATION.articleUrl);
  });

});
