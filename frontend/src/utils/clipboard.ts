// Copies `text` to the clipboard, and returns whether it could. The clipboard
// is missing on a page opened from a file, and a browser may refuse it: the
// text area that shows the text is then selected instead, for the keyboard to
// copy.
export async function copyOrSelect(
  text: string,
  textArea: HTMLTextAreaElement | null,
): Promise<boolean> {
  try {
    if (!navigator.clipboard) {
      throw new Error("no clipboard");
    }
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    textArea?.focus();
    textArea?.select();
    return false;
  }
}
