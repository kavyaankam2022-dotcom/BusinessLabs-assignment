import assert from 'node:assert/strict';
import test from 'node:test';
import { queryKnowledge } from '../src/knowledge-client/client.js';

const answeredPayload = {
  answer: 'Open the documented settings page.',
  status: 'answered',
  sources: [{
    document_id: 'doc-1', chunk_id: 'chunk-1', title: 'Settings',
    url: 'https://support.brilliantdirectories.com/help/settings',
    section: 'Site settings', excerpt: 'Open Settings to continue.', relevance: 0.82, images: [],
  }],
  image_references: [],
  needs_human: false,
  escalation_reason: null,
  escalation_id: null,
};

test('Knowledge Brain client forwards context and preserves cited evidence', async () => {
  let sentBody = '';
  const result = await queryKnowledge('Where is this setting?', 'Customer already tried the dashboard.', async (_url, init) => {
    sentBody = String(init?.body);
    return new Response(JSON.stringify(answeredPayload), { status: 200 });
  });

  assert.equal(result.ok, true);
  if (result.ok) {
    assert.equal(result.response.sources[0].url, answeredPayload.sources[0].url);
    assert.equal(result.response.sources[0].relevance, 0.82);
  }
  assert.match(sentBody, /Customer already tried the dashboard/);
});

test('Knowledge Brain client fails closed on insufficient evidence', async () => {
  const result = await queryKnowledge('Unknown product behavior', 'No extra context.', async () => new Response(JSON.stringify({
    ...answeredPayload,
    answer: 'Insufficient evidence.',
    status: 'insufficient_evidence',
    sources: [],
    needs_human: true,
    escalation_reason: 'No source matched.',
    escalation_id: 'esc-1',
  }), { status: 200 }));

  assert.equal(result.ok, true);
  if (result.ok) assert.equal(result.response.needs_human, true);
});

test('Knowledge Brain client turns timeouts and HTTP errors into explicit failures', async () => {
  const timeout = await queryKnowledge('Any question?', 'Context.', async () => {
    throw new DOMException('Timed out', 'TimeoutError');
  });
  const unavailable = await queryKnowledge('Any question?', 'Context.', async () => new Response(
    JSON.stringify({ code: 'internal_error', message: 'Service failed.' }), { status: 503 },
  ));

  assert.deepEqual(timeout, { ok: false, error: 'Knowledge service request timed out.' });
  assert.deepEqual(unavailable, { ok: false, error: 'Service failed.', requestId: undefined });
});