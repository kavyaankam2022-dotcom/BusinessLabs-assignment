import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { emails } from '../src/email/catalog.js';
import { classifyEmail } from '../src/email/classifier.js';
import { emailRecordSchema } from '../src/types.js';

const holdout = emailRecordSchema.array().parse(JSON.parse(
  await readFile(new URL('../data/holdout-emails.json', import.meta.url), 'utf8'),
));

test('development corpus and separate holdout contain 70 and 20 labeled emails', () => {
  assert.equal(emails.length, 70);
  assert.ok(emails.every((email) => email.split === 'development'));
  assert.equal(holdout.length, 20);
  assert.ok(holdout.every((email) => email.split === 'test'));
  assert.equal(new Set([...emails, ...holdout].map((email) => email.id)).size, 90);
});

for (const email of holdout) {
  test(`holdout classification ${email.id}`, () => {
    const actual = classifyEmail(email);
    assert.equal(actual.category, email.expectedCategory);
    assert.equal(actual.riskLevel, email.expectedRisk);
  });
}