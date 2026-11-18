/** The owner's style profile in Settings ("Your style"): what counts as a change, and the character count. */

/** The count turns to the warning colour this close to the longest text allowed. */
export const STYLE_WARN_WITHIN = 200;

/** The text as the server keeps it: no space at either end, every line break as "\n". */
export function tidyStyle(text: string): string {
  return text.replace(/\r\n?/g, '\n').trim();
}

/** Whether saving the text being written would change the profile in force. */
export function styleChanged(draft: string, inForce: string): boolean {
  return tidyStyle(draft) !== tidyStyle(inForce);
}

/** "123 / 4000", and whether it is in the last few characters allowed. */
export function styleCount(length: number, max: number): { text: string; warn: boolean } {
  return { text: `${length} / ${max}`, warn: length > max - STYLE_WARN_WITHIN };
}
