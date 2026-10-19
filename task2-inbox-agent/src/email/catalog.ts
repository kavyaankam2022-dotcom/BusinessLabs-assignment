import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { emailRecordSchema, type EmailRecord } from '../types.js';

const datasetUrl = new URL('../../data/emails.json', import.meta.url);
const rawDataset = JSON.parse(await readFile(fileURLToPath(datasetUrl), 'utf8')) as unknown;
export const emails: EmailRecord[] = emailRecordSchema.array().parse(rawDataset)
  .filter((email) => email.split === 'development');

export function findEmail(id: string): EmailRecord | undefined {
  return emails.find((email) => email.id === id);
}
