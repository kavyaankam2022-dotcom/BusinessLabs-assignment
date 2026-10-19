export function isUneditedDraft(draftText: string, finalText: string): boolean {
  return draftText.replace(/\r\n?/g, '\n').trim() === finalText.replace(/\r\n?/g, '\n').trim();
}
