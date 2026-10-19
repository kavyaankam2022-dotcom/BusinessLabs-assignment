import assert from 'node:assert/strict';
import test from 'node:test';
import { createServer as createHttpServer } from 'node:http';
import { mkdtemp, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

test('HTTP inbox calls the Knowledge Brain, fails closed, and hides evaluation labels', async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'inbox-api-'));
  process.env.INBOX_STATE_PATH = path.join(directory, 'state.json');
  const queryCalls: unknown[] = [];
  let knowledgeStatus = 200;
  let knowledgePayload: unknown = {
    answer: 'Insufficient evidence.',
    status: 'insufficient_evidence',
    sources: [],
    image_references: [],
    needs_human: true,
    escalation_reason: 'No relevant article was found.',
    escalation_id: 'kb-esc-1',
  };
  const knowledgeServer = createHttpServer(async (request, response) => {
    const buffers: Buffer[] = [];
    for await (const chunk of request) buffers.push(Buffer.from(chunk));
    queryCalls.push(JSON.parse(Buffer.concat(buffers).toString('utf8')) as unknown);
    response.writeHead(knowledgeStatus, { 'Content-Type': 'application/json' });
    response.end(JSON.stringify(knowledgePayload));
  });
  await new Promise<void>((resolve) => knowledgeServer.listen(0, '127.0.0.1', resolve));
  const knowledgeAddress = knowledgeServer.address();
  assert.ok(knowledgeAddress && typeof knowledgeAddress !== 'string');
  process.env.KB_API_URL = `http://127.0.0.1:${knowledgeAddress.port}`;
  const { createServer } = await import('../src/server.js');
  const inboxServer = createServer();
  await new Promise<void>((resolve) => inboxServer.listen(0, '127.0.0.1', resolve));
  const inboxAddress = inboxServer.address();
  assert.ok(inboxAddress && typeof inboxAddress !== 'string');
  const baseUrl = `http://127.0.0.1:${inboxAddress.port}`;

  try {
    const emailsResponse = await fetch(`${baseUrl}/api/emails`);
    const emailList = await emailsResponse.json() as { emails: Array<Record<string, unknown>> };
    assert.equal(emailList.emails.length, 70);
    assert.equal(emailList.emails.some((email) => email.id === 'IN-071'), false);
    assert.equal('split' in emailList.emails[0], false);
    assert.equal('expectedCategory' in emailList.emails[0], false);

    const draftResponse = await fetch(`${baseUrl}/api/emails/IN-001/draft`, { method: 'POST', body: '{}' });
    const draftBody = await draftResponse.json() as { interaction: { draftStatus: string; suggestedReply: string; knowledgeEscalationId: string } };
    assert.equal(draftBody.interaction.draftStatus, 'insufficient_evidence');
    assert.equal(draftBody.interaction.suggestedReply, '');
    assert.equal(draftBody.interaction.knowledgeEscalationId, 'kb-esc-1');
    assert.equal((queryCalls[0] as { top_k: number }).top_k, 5);

    knowledgeStatus = 503;
    knowledgePayload = { code: 'internal_error', message: 'Knowledge service failed.' };
    const failedResponse = await fetch(`${baseUrl}/api/emails/IN-002/draft`, { method: 'POST', body: '{}' });
    const failedBody = await failedResponse.json() as { interaction: { draftStatus: string; suggestedReply: string } };
    assert.equal(failedBody.interaction.draftStatus, 'knowledge_unavailable');
    assert.equal(failedBody.interaction.suggestedReply, '');
  } finally {
    await Promise.all([
      new Promise<void>((resolve, reject) => inboxServer.close((error) => error ? reject(error) : resolve())),
      new Promise<void>((resolve, reject) => knowledgeServer.close((error) => error ? reject(error) : resolve())),
    ]);
    await rm(directory, { recursive: true, force: true });
    delete process.env.INBOX_STATE_PATH;
    delete process.env.KB_API_URL;
  }
});