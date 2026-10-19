import 'dotenv/config';
import { createServer as createHttpServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { z } from 'zod';
import { classifyEmail } from './email/classifier.js';
import { emails, findEmail } from './email/catalog.js';
import { createDraft, PROMPT_VERSION } from './drafting/draft.js';
import { queryKnowledge } from './knowledge-client/client.js';
import { InboxStore } from './feedback/store.js';
import { emailCategorySchema, type Interaction } from './types.js';

const rootDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const store = new InboxStore();
const sendRequestSchema = z.object({ finalText: z.string().trim().min(1).max(5000) });
const rejectRequestSchema = z.object({
  reason: z.string().trim().min(3).max(1000),
  replacementText: z.string().trim().min(1).max(5000),
});
const expertRequestSchema = z.object({ reason: z.string().trim().min(3).max(1000) });
const autonomyRequestSchema = z.object({ enabled: z.boolean() });

function customerEmail(email: (typeof emails)[number]) {
  return { id: email.id, subject: email.subject, from: email.from, body: email.body };
}

export function createServer() {
  return createHttpServer((request, response) => {
    void handleRequest(request, response).catch((error: unknown) => {
      console.error('Inbox request failed', error);
      sendJson(response, 500, { error: 'The inbox request could not be completed.' });
    });
  });
}

async function handleRequest(request: IncomingMessage, response: ServerResponse): Promise<void> {
  const url = new URL(request.url ?? '/', 'http://127.0.0.1');
  if (request.method === 'GET' && url.pathname === '/') return serveFile(response, 'web/index.html', 'text/html; charset=utf-8');
  if (request.method === 'GET' && url.pathname === '/styles.css') return serveFile(response, 'web/styles.css', 'text/css; charset=utf-8');
  if (request.method === 'GET' && url.pathname === '/ui.js') return serveFile(response, 'dist/ui.js', 'text/javascript; charset=utf-8');
  if (request.method === 'GET' && url.pathname === '/api/health') {
    return sendJson(response, 200, { status: 'ok', service: 'inbox-agent', delivery: 'simulated' });
  }

  if (request.method === 'GET' && url.pathname === '/api/emails') {
    const interactions = await store.listInteractions();
    const latestByEmail = new Map<string, Interaction>();
    for (const interaction of interactions) {
      if (!latestByEmail.has(interaction.emailId)) latestByEmail.set(interaction.emailId, interaction);
    }
    return sendJson(response, 200, {
      emails: emails.map((email) => ({
        id: email.id,
        subject: email.subject,
        from: email.from,
        body: email.body,
        ...(latestByEmail.get(email.id)
          ? {
              category: latestByEmail.get(email.id)!.category,
              riskLevel: latestByEmail.get(email.id)!.riskLevel,
              urgency: latestByEmail.get(email.id)!.urgency,
            }
          : classifyEmail(email)),
        interaction: latestByEmail.get(email.id) ?? null,
      })),
    });
  }

  if (request.method === 'GET' && url.pathname === '/api/interactions') {
    return sendJson(response, 200, { interactions: await store.listInteractions() });
  }

  if (request.method === 'GET' && url.pathname === '/api/feedback') {
    return sendJson(response, 200, { feedback: await store.feedbackSummary() });
  }

  if (request.method === 'GET' && url.pathname === '/api/status') {
    return sendJson(response, 200, {
      ...(await store.summary()),
      delivery: 'simulated',
      knowledgeBaseUrl: process.env.KB_API_URL ?? 'http://127.0.0.1:8000',
      autonomyTrialEnabled: process.env.INBOX_AUTONOMY_ENABLED === 'true',
    });
  }

  const emailMatch = url.pathname.match(/^\/api\/emails\/([^/]+)\/draft$/);
  if (request.method === 'POST' && emailMatch) {
    return draftEmail(decodeURIComponent(emailMatch[1]), response);
  }

  const reviewMatch = url.pathname.match(/^\/api\/reviews\/([^/]+)\/(send|reject|expert)$/);
  if (request.method === 'POST' && reviewMatch) {
    const interactionId = decodeURIComponent(reviewMatch[1]);
    const action = reviewMatch[2];
    if (action === 'send') return sendDraft(interactionId, request, response);
    if (action === 'reject') return rejectDraft(interactionId, request, response);
    return requestExpert(interactionId, request, response);
  }

  const autonomyMatch = url.pathname.match(/^\/api\/autonomy\/([^/]+)$/);
  if (request.method === 'PUT' && autonomyMatch) {
    return setAutonomy(decodeURIComponent(autonomyMatch[1]), request, response);
  }

  sendJson(response, 404, { error: 'Route not found.' });
}

async function draftEmail(emailId: string, response: ServerResponse): Promise<void> {
  const email = findEmail(emailId);
  if (!email) return sendJson(response, 404, { error: 'Email not found.' });
  const previous = await store.getInteractionForEmail(emailId);
  if (previous && ((previous.approvalOutcome === 'pending' && previous.draftStatus === 'ready') || previous.simulatedSendId)) {
    return sendJson(response, 200, { interaction: previous, reused: true });
  }

  const classification = classifyEmail(email);
  const lookup = await queryKnowledge(`${email.subject}\n${email.body}`, 'Customer support email inquiry.');
  if (!lookup.ok) {
    const interaction = await store.createInteraction({
      emailId, originalEmail: customerEmail(email), ...classification,
      summary: '', suggestedReply: '', nextAction: 'Retry knowledge lookup or route to a human specialist.',
      sources: [], knowledgeStatus: 'unavailable', knowledgeError: lookup.error,
      draftStatus: 'knowledge_unavailable', modelVersion: 'not-called', promptVersion: PROMPT_VERSION,
    });
    return sendJson(response, 200, { interaction });
  }

  const knowledge = lookup.response;
  if (knowledge.status !== 'answered' || knowledge.needs_human || knowledge.sources.length === 0) {
    const status = knowledge.status === 'answered' ? 'insufficient_evidence' : knowledge.status;
    const interaction = await store.createInteraction({
      emailId, originalEmail: customerEmail(email), ...classification,
      summary: '', suggestedReply: '',
      nextAction: knowledge.escalation_reason ?? 'Review the Knowledge Brain escalation before replying.',
      sources: knowledge.sources, knowledgeStatus: status,
      knowledgeError: knowledge.escalation_reason ?? 'The knowledge service did not provide sufficient evidence.',
      knowledgeEscalationId: knowledge.escalation_id,
      draftStatus: status === 'insufficient_evidence' ? 'insufficient_evidence' : 'knowledge_unavailable',
      modelVersion: 'not-called', promptVersion: PROMPT_VERSION,
    });
    return sendJson(response, 200, { interaction });
  }

  const generated = await createDraft(email, classification.category, classification.riskLevel, knowledge);
  if (generated.status !== 'ready') {
    const interaction = await store.createInteraction({
      emailId, originalEmail: customerEmail(email), ...classification,
      summary: '', suggestedReply: '', nextAction: generated.reason,
      sources: knowledge.sources, knowledgeStatus: knowledge.status,
      knowledgeError: generated.reason, draftStatus: generated.status,
      modelVersion: generated.modelVersion, promptVersion: generated.promptVersion,
    });
    return sendJson(response, 200, { interaction });
  }

  const interaction = await store.createInteraction({
    emailId, originalEmail: customerEmail(email), ...classification,
    summary: generated.draft.summary,
    suggestedReply: generated.draft.suggestedReply,
    nextAction: generated.draft.nextAction,
    sources: knowledge.sources,
    knowledgeStatus: knowledge.status,
    draftStatus: 'ready',
    modelVersion: generated.modelVersion,
    promptVersion: generated.promptVersion,
  });
  return sendJson(response, 200, { interaction });
}

async function sendDraft(id: string, request: IncomingMessage, response: ServerResponse): Promise<void> {
  const body = sendRequestSchema.safeParse(await readJson(request));
  if (!body.success) return sendJson(response, 422, { error: 'finalText is required and must be 1-5000 characters.' });
  const existing = await store.getInteraction(id);
  if (!existing) return sendJson(response, 404, { error: 'Draft not found.' });
  if (existing.draftStatus !== 'ready') return sendJson(response, 409, { error: 'This interaction has no safe, grounded draft to send.' });
  const result = await store.sendReply(id, body.data.finalText);
  if (!result.interaction) return sendJson(response, 404, { error: 'Draft not found.' });
  if (result.interaction.approvalOutcome === 'pending') return sendJson(response, 409, { error: 'Draft is no longer pending review.' });
  return sendJson(response, 200, { interaction: result.interaction, duplicate: result.duplicate, delivery: 'simulated' });
}

async function rejectDraft(id: string, request: IncomingMessage, response: ServerResponse): Promise<void> {
  const body = rejectRequestSchema.safeParse(await readJson(request));
  if (!body.success) return sendJson(response, 422, { error: 'A correction reason and replacement text are required.' });
  const interaction = await store.reject(id, body.data.reason, body.data.replacementText);
  if (!interaction) return sendJson(response, 404, { error: 'Pending draft not found.' });
  return sendJson(response, 200, { interaction, replacedInteractionId: id, delivery: 'not-sent' });
}

async function requestExpert(id: string, request: IncomingMessage, response: ServerResponse): Promise<void> {
  const body = expertRequestSchema.safeParse(await readJson(request));
  if (!body.success) return sendJson(response, 422, { error: 'A reason for expert review is required.' });
  const interaction = await store.requestExpert(id, body.data.reason);
  if (!interaction) return sendJson(response, 404, { error: 'Pending interaction not found.' });
  return sendJson(response, 200, { interaction, delivery: 'not-sent' });
}

async function setAutonomy(categoryText: string, request: IncomingMessage, response: ServerResponse): Promise<void> {
  const category = emailCategorySchema.safeParse(categoryText);
  const body = autonomyRequestSchema.safeParse(await readJson(request));
  if (!category.success || !body.success) return sendJson(response, 422, { error: 'A supported category and boolean enabled value are required.' });
  if (process.env.INBOX_AUTONOMY_ENABLED !== 'true') {
    return sendJson(response, 403, { error: 'Autonomy trial is disabled by configuration.' });
  }
  const result = await store.setAutonomy(category.data, body.data.enabled);
  if (body.data.enabled && !result.eligible) {
    return sendJson(response, 409, { error: 'Category has not met the 20-consecutive unedited approval threshold.', ...result });
  }
  return sendJson(response, 200, result);
}

async function readJson(request: IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of request) {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += buffer.length;
    if (size > 64 * 1024) throw new Error('Request body too large.');
    chunks.push(buffer);
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8')) as unknown;
  } catch {
    return null;
  }
}

async function serveFile(response: ServerResponse, relativePath: string, contentType: string): Promise<void> {
  try {
    const content = await readFile(path.join(rootDirectory, relativePath));
    response.writeHead(200, { 'Content-Type': contentType, 'Cache-Control': 'no-store' });
    response.end(content);
  } catch {
    sendJson(response, 404, { error: 'UI asset not found. Run the TypeScript build first.' });
  }
}

function sendJson(response: ServerResponse, status: number, body: unknown): void {
  response.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  response.end(JSON.stringify(body));
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const port = Number(process.env.INBOX_PORT ?? 3002);
  createServer().listen(port, '127.0.0.1', () => {
    console.log(`Inbox Agent listening at http://127.0.0.1:${port}`);
  });
}