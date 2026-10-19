import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtemp, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { InboxStore } from '../src/feedback/store.js';
import type { NewInteraction } from '../src/feedback/store.js';

function interactionInput(id: string): NewInteraction {
  return {
    emailId: id,
    originalEmail: {
      id,
      subject: 'Where are settings?',
      from: 'Person <person@example.test>',
      body: 'How can I find settings?',
    },
    category: 'how_to',
    riskLevel: 'low',
    urgency: 'normal',
    summary: 'Customer needs a supported settings path.',
    suggestedReply: 'Please open the documented settings page.',
    nextAction: 'Review cited article.',
    sources: [],
    knowledgeStatus: 'answered',
    draftStatus: 'ready',
    modelVersion: 'test-model',
    promptVersion: 'test-prompt-v1',
  };
}

async function withStore(run: (store: InboxStore) => Promise<void>): Promise<void> {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'inbox-store-'));
  try {
    await run(new InboxStore(path.join(directory, 'state.json')));
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}

test('send comparison is text-based, auditable, and idempotent', async () => {
  await withStore(async (store) => {
    const created = await store.createInteraction(interactionInput('IN-001'));
    const first = await store.sendReply(created.id, `\r\n${created.suggestedReply}\r\n`);
    const duplicate = await store.sendReply(created.id, created.suggestedReply);

    assert.equal(first.interaction?.wasEdited, false);
    assert.equal(first.interaction?.qualifyingApprovals, 1);
    assert.equal(duplicate.duplicate, true);
    assert.equal((await store.summary()).consecutiveApprovals.how_to, 1);
  });
});

test('20 consecutive unchanged low-risk approvals create eligibility, not automatic sends', async () => {
  await withStore(async (store) => {
    let twentiethId = '';
    for (let index = 1; index <= 20; index += 1) {
      const created = await store.createInteraction(interactionInput(`IN-${index}`));
      const result = await store.sendReply(created.id, created.suggestedReply);
      if (index === 20) twentiethId = result.interaction!.id;
    }

    const summary = await store.summary();
    const twentieth = await store.getInteraction(twentiethId);
    assert.equal(summary.consecutiveApprovals.how_to, 20);
    assert.ok(summary.eligibleCategories.includes('how_to'));
    assert.equal(twentieth?.autonomyEligible, true);
    assert.equal(twentieth?.approvalOutcome, 'approved');
  });
});

test('edited replies reset the category streak', async () => {
  await withStore(async (store) => {
    for (let index = 1; index <= 3; index += 1) {
      const created = await store.createInteraction(interactionInput(`IN-${index}`));
      await store.sendReply(created.id, created.suggestedReply);
    }
    const edited = await store.createInteraction(interactionInput('IN-004'));
    await store.sendReply(edited.id, `${edited.suggestedReply} Please reply with any questions.`);

    assert.equal((await store.summary()).consecutiveApprovals.how_to, 0);
  });
});

test('a rejected replacement becomes a new pending draft requiring approval', async () => {
  await withStore(async (store) => {
    const original = await store.createInteraction(interactionInput('IN-REJECT'));
    const replacementText = 'Thank you. A specialist will review this and follow up.';
    const replacement = await store.reject(original.id, 'Original answer was too specific.', replacementText);

    assert.ok(replacement);
    assert.notEqual(replacement?.id, original.id);
    assert.equal(replacement?.suggestedReply, replacementText);
    assert.equal(replacement?.approvalOutcome, 'pending');
    assert.equal(replacement?.modelVersion, 'human-review');
    assert.equal((await store.getInteraction(original.id))?.approvalOutcome, 'rejected');
  });
});

test('approved human-written replacements never advance the model autonomy streak', async () => {
  await withStore(async (store) => {
    const original = await store.createInteraction(interactionInput('IN-HUMAN'));
    const replacement = await store.reject(original.id, 'Rewrite needed.', 'A human-written replacement.');
    assert.ok(replacement);
    await store.sendReply(replacement!.id, replacement!.suggestedReply);

    assert.equal((await store.summary()).consecutiveApprovals.how_to, 0);
  });
});

test('feedback summary exposes category-level corrections for reviewed improvements', async () => {
  await withStore(async (store) => {
    const created = await store.createInteraction(interactionInput('IN-FEEDBACK'));
    await store.reject(created.id, 'Ask for the relevant article first.', 'Could you share the article you are viewing?');
    const feedback = await store.feedbackSummary();
    const howTo = feedback.find((item) => item.category === 'how_to');

    assert.equal(howTo?.rejected, 1);
    assert.deepEqual(howTo?.recentCorrections, ['Ask for the relevant article first.']);
  });
});

test('high-risk unchanged replies do not count toward autonomy', async () => {
  await withStore(async (store) => {
    const input = interactionInput('IN-HIGH');
    input.riskLevel = 'high';
    const created = await store.createInteraction(input);
    const sent = await store.sendReply(created.id, created.suggestedReply);

    assert.equal(sent.interaction?.wasEdited, false);
    assert.equal(sent.interaction?.qualifyingApprovals, 0);
    assert.equal((await store.summary()).consecutiveApprovals.how_to, 0);
  });
});

test('protected categories cannot be enabled for an autonomy trial', async () => {
  await withStore(async (store) => {
    const result = await store.setAutonomy('refund_cancellation', true);
    assert.equal(result.eligible, false);
    assert.equal(result.enabled, false);
  });
});