// What the Help menu of the editor offers: links to the documentation, links
// to the project, and the reference of the article to cite. A link to the
// documentation names a page of rtdocs/source, so that a test can check that
// the page exists in the repository.

export const DOCS_URL = "https://debasher.readthedocs.io/en/latest/";

export const REPOSITORY_URL = "https://github.com/daormar/debasher";

export interface HelpLink {
  label: string;
  url: string;
}

// A page of the documentation, by the name of its source without `.rst`.
export function docsPageUrl(page: string): string {
  return `${DOCS_URL}${page}.html`;
}

export const DOCS_LINKS: HelpLink[] = [
  { label: "Technical documentation", url: DOCS_URL },
  { label: "Using the web interface", url: docsPageUrl("webui") },
];

export const PROJECT_LINKS: HelpLink[] = [
  { label: "Source code", url: REPOSITORY_URL },
  { label: "Report an issue", url: `${REPOSITORY_URL}/issues` },
];

// The article that describes DeBasher, as README.md asks to cite it.
export const CITATION = {
  articleUrl: "https://doi.org/10.1186/s12859-025-06108-1",
  text:
    "Ortiz-Martínez, D. DeBasher: a flow-based programming bash extension " +
    "for the implementation of complex and interactive workflows with " +
    "stateful processes. BMC Bioinformatics 26, 106 (2025). " +
    "https://doi.org/10.1186/s12859-025-06108-1",
  bibtex: [
    "@article{OrtizMartinez2025DeBasher,",
    "  author  = {Ortiz-Mart{\\'\\i}nez, Daniel},",
    "  title   = {{DeBasher}: a flow-based programming bash extension for the",
    "             implementation of complex and interactive workflows with",
    "             stateful processes},",
    "  journal = {BMC Bioinformatics},",
    "  volume  = {26},",
    "  pages   = {106},",
    "  year    = {2025},",
    "  doi     = {10.1186/s12859-025-06108-1},",
    "}",
  ].join("\n"),
};
