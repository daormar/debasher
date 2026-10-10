// DEBASHER_MOD_DIR, the directories where the engine looks for the modules
// that a program loads. The program keeps it the way the engine reads it, a
// single string with the directories separated by MOD_DIR_SEP; the editor
// shows it one directory per line, which is easier to read and to edit when
// the paths are long.

// Matches engine/debasher_lib.sh's DEBASHER_MOD_DIR_SEP.
export const MOD_DIR_SEP = ":";

/**
 * The directories of a DEBASHER_MOD_DIR value, whether they are separated by
 * MOD_DIR_SEP, by line breaks or by both, without surrounding blanks and
 * without empty entries (an empty entry would make the engine look for
 * modules in the root directory).
 */
export function splitModDir(value: string): string[] {
  return value
    .split(/[:\n]/)
    .map(entry => entry.trim())
    .filter(Boolean);
}

/** The value kept in the program for the directories typed in the editor. */
export function modDirFromLines(text: string): string {
  return splitModDir(text).join(MOD_DIR_SEP);
}

/** The text that the editor shows for a value kept in the program. */
export function modDirToLines(value: string): string {
  return splitModDir(value).join("\n");
}
