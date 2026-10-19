import assert from 'node:assert/strict';
import test from 'node:test';
import { containsUnapprovedCommitment } from '../src/drafting/draft.js';

test('draft safety rejects explicit refunds, dates, and prices', () => {
  assert.equal(containsUnapprovedCommitment('We will refund the last payment.'), true);
  assert.equal(containsUnapprovedCommitment('Your refund was approved.'), true);
  assert.equal(containsUnapprovedCommitment('We will be completed by Friday.'), true);
  assert.equal(containsUnapprovedCommitment('The project costs $500.'), true);
});

test('draft safety permits non-committal acknowledgements', () => {
  assert.equal(containsUnapprovedCommitment('I have routed this request for review.'), false);
});