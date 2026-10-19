import type { EmailCategory, Interaction } from './types.js';

interface EmailRow {
  id: string;
  split: 'development' | 'test';
  subject: string;
  from: string;
  body: string;
  category: EmailCategory;
  riskLevel: string;
  urgency: string;
  interaction: Interaction | null;
}

interface InboxStatus {
  totals: Record<string, number>;
  consecutiveApprovals: Record<string, number>;
  eligibleCategories: string[];
  autonomyTrialEnabled: boolean;
}
interface FeedbackRow {
  category: EmailCategory;
  edited: number;
  rejected: number;
  expertEscalated: number;
  recentCorrections: string[];
}

const categoryNames: Record<EmailCategory, string> = {
  how_to: 'How-to',
  troubleshooting: 'Troubleshooting',
  project_request: 'Project request',
  refund_cancellation: 'Refund / cancel',
  complaint: 'Complaint',
  quote_request: 'Quote request',
  follow_up: 'Follow-up',
};
const filterNames: Record<string, string> = { all: 'All mail', pending: 'Needs review', ...categoryNames };
const state = { emails: [] as EmailRow[], status: null as InboxStatus | null, category: 'all', search: '', selectedId: '' };

const emailList = element<HTMLDivElement>('email-list');
const categoryFilters = element<HTMLElement>('category-filters');
const toast = element<HTMLDivElement>('toast');

function element<T extends HTMLElement>(id: string): T {
  const result = document.getElementById(id);
  if (!result) throw new Error(`Missing UI element: ${id}`);
  return result as T;
}

function node<K extends keyof HTMLElementTagNameMap>(tag: K, className = '', text = ''): HTMLElementTagNameMap[K] {
  const result = document.createElement(tag);
  result.className = className;
  result.textContent = text;
  return result;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, headers: { 'Content-Type': 'application/json', ...init?.headers } });
  const body = await response.json() as T & { error?: string };
  if (!response.ok) throw new Error(body.error ?? `Request failed with status ${response.status}.`);
  return body;
}

async function refresh(): Promise<void> {
  try {
    const [emailResponse, status, feedbackResponse] = await Promise.all([
      request<{ emails: EmailRow[] }>('/api/emails'),
      request<InboxStatus>('/api/status'),
      request<{ feedback: FeedbackRow[] }>('/api/feedback'),
    ]);
    state.emails = emailResponse.emails;
    state.status = status;
    element('service-status').textContent = 'Inbox ready';
    document.querySelector('.service-indicator')?.classList.add('online');
    renderFilters();
    renderEmailList();
    renderAutonomy();
    renderFeedback(feedbackResponse.feedback);
    element('pending-count').textContent = String(status.totals.pending ?? 0);
    if (state.selectedId) {
      const selected = state.emails.find((email) => email.id === state.selectedId);
      if (selected) renderEmail(selected);
    }
  } catch (error) {
    element('service-status').textContent = 'Inbox service unavailable';
    showToast(messageOf(error));
  }
}

function renderFilters(): void {
  categoryFilters.replaceChildren();
  const entries = ['all', 'pending', ...Object.keys(categoryNames)];
  for (const key of entries) {
    const count = key === 'all'
      ? state.emails.length
      : key === 'pending'
        ? state.emails.filter((email) => email.interaction?.approvalOutcome === 'pending').length
        : state.emails.filter((email) => email.category === key).length;
    const button = node('button', `filter-button ${state.category === key ? 'active' : ''}`);
    button.type = 'button';
    button.append(node('span', '', filterNames[key]));
    button.append(node('span', 'filter-count', String(count)));
    button.addEventListener('click', () => {
      state.category = key;
      renderFilters();
      renderEmailList();
    });
    categoryFilters.append(button);
  }
}

function filteredEmails(): EmailRow[] {
  const needle = state.search.toLowerCase();
  return state.emails.filter((email) => {
    const categoryMatch = state.category === 'all'
      || (state.category === 'pending' ? email.interaction?.approvalOutcome === 'pending' : email.category === state.category);
    const searchMatch = !needle || `${email.subject} ${email.from} ${email.body}`.toLowerCase().includes(needle);
    return categoryMatch && searchMatch;
  });
}

function renderEmailList(): void {
  emailList.replaceChildren();
  const matches = filteredEmails();
  element('email-count').textContent = String(matches.length);
  if (!matches.length) {
    emailList.append(node('p', 'no-results', 'No emails match this view.'));
    return;
  }
  for (const email of matches) {
    const button = node('button', `email-item ${state.selectedId === email.id ? 'active' : ''}`);
    button.type = 'button';
    button.setAttribute('role', 'listitem');
    const top = node('div', 'email-item-top');
    top.append(node('strong', '', email.subject));
    top.append(node('time', '', email.id));
    button.append(top);
    button.append(node('p', '', email.body));
    if (email.interaction) {
      const label = email.interaction.approvalOutcome === 'pending'
        ? email.interaction.draftStatus === 'ready' ? 'Draft ready for review' : 'Human help needed'
        : email.interaction.approvalOutcome.replace('_', ' ');
      button.append(node('span', 'mini-status', label));
    }
    button.addEventListener('click', () => selectEmail(email.id));
    emailList.append(button);
  }
}

function renderAutonomy(): void {
  const container = element('autonomy-list');
  container.replaceChildren();
  const counters = state.status?.consecutiveApprovals ?? {};
  for (const category of ['how_to', 'troubleshooting'] as const) {
    const count = counters[category] ?? 0;
    const chip = node('span', `streak-chip ${count >= 20 ? 'eligible' : ''}`, `${categoryNames[category]} ${count}/20`);
    chip.title = count >= 20 ? 'Eligible for a controlled trial; sends still require review in this demo.' : 'Consecutive unedited approved sends.';
    container.append(chip);
  }
}

function renderFeedback(rows: FeedbackRow[]): void {
  const container = element('feedback-list');
  container.replaceChildren();
  const active = rows.filter((row) => row.edited || row.rejected || row.expertEscalated);
  if (!active.length) {
    container.append(node('span', 'muted', 'No corrections recorded.'));
    return;
  }
  for (const row of active) {
    const correction = row.recentCorrections.at(-1);
    const summary = `${categoryNames[row.category]}: ${row.edited} edits · ${row.rejected} rejections · ${row.expertEscalated} expert routes`;
    const line = node('span', '', summary);
    if (correction) line.title = correction;
    container.append(line);
  }
}

function selectEmail(id: string): void {
  state.selectedId = id;
  const email = state.emails.find((entry) => entry.id === id);
  if (email) renderEmail(email);
  renderEmailList();
}

function renderEmail(email: EmailRow): void {
  element('empty-state').hidden = true;
  element('review-view').hidden = false;
  element('message-subject').textContent = email.subject;
  element('message-sender').textContent = email.from;
  element('message-body').textContent = email.body;
  element('message-id').textContent = email.id;
  const category = email.interaction?.category ?? email.category;
  const risk = email.interaction?.riskLevel ?? email.riskLevel;
  element('category-badge').textContent = categoryNames[category];
  element('risk-badge').textContent = `${risk} risk`;
  element('risk-badge').className = `risk-badge ${risk}`;
  element('urgency-badge').hidden = email.interaction?.urgency !== 'urgent';
  element('draft-button').textContent = email.interaction?.approvalOutcome === 'rejected' ? 'Generate revised draft' : 'Generate draft';
  element<HTMLButtonElement>('draft-button').disabled = (email.interaction?.approvalOutcome === 'pending' && email.interaction.draftStatus === 'ready') || Boolean(email.interaction?.simulatedSendId);
  element('draft-button').onclick = () => void generateDraft(email.id);

  const interaction = email.interaction;
  if (!interaction) {
    element('knowledge-state').textContent = 'Not queried';
    element('knowledge-state').className = 'state-label';
    element('evidence-list').replaceChildren(node('p', 'muted', 'Generate a draft to query the shared Knowledge Brain.'));
    element('draft-status').textContent = 'No draft';
    element('draft-status').className = 'state-label';
    element('summary-field').textContent = 'No summary yet.';
    setDraftText('', true);
    element('blocking-state').hidden = true;
    element('next-action').hidden = true;
    element('review-controls').hidden = true;
    element('correction-fields').hidden = true;
    element('expert-fields').hidden = true;
    element('audit-section').hidden = true;
    return;
  }

  renderInteraction(interaction);
}

function renderInteraction(interaction: Interaction): void {
  const knowledgeLabel = interaction.knowledgeStatus === 'unavailable'
    ? 'Service unavailable'
    : interaction.knowledgeStatus.replace('_', ' ');
  element('knowledge-state').textContent = knowledgeLabel;
  element('knowledge-state').className = `state-label ${interaction.knowledgeStatus === 'answered' ? 'success' : 'warning'}`;
  renderSources(interaction);
  element('draft-status').textContent = interaction.draftStatus.replaceAll('_', ' ');
  element('draft-status').className = `state-label ${interaction.draftStatus === 'ready' ? 'success' : 'warning'}`;
  element('summary-field').textContent = interaction.summary || 'No draft summary was created.';
  setDraftText(interaction.suggestedReply, interaction.draftStatus !== 'ready' || interaction.approvalOutcome !== 'pending');
  const block = element('blocking-state');
  block.textContent = interaction.knowledgeError ?? (interaction.draftStatus === 'ready' ? '' : 'No customer reply is available. Human review is required.');
  block.hidden = interaction.draftStatus === 'ready' && interaction.approvalOutcome === 'pending';
  const nextAction = element('next-action');
  nextAction.textContent = interaction.nextAction ? `Next action: ${interaction.nextAction}` : '';
  nextAction.hidden = !interaction.nextAction;
  element('review-controls').hidden = interaction.approvalOutcome !== 'pending';
  element<HTMLButtonElement>('send-button').hidden = interaction.draftStatus !== 'ready';
  element<HTMLButtonElement>('reject-button').hidden = interaction.draftStatus !== 'ready';
  element<HTMLButtonElement>('expert-button').hidden = interaction.approvalOutcome !== 'pending';
  element('correction-fields').hidden = true;
  element('expert-fields').hidden = true;
  renderAudit(interaction);
}

function renderSources(interaction: Interaction): void {
  const container = element('evidence-list');
  container.replaceChildren();
  if (!interaction.sources.length) {
    container.append(node('p', 'muted', interaction.knowledgeError ?? 'No source evidence was returned.'));
    return;
  }
  for (const source of interaction.sources) {
    const item = node('article', 'source-item');
    const anchor = node('a', '', source.title);
    const url = safeWebUrl(source.url);
    if (url) {
      anchor.href = url;
      anchor.target = '_blank';
      anchor.rel = 'noreferrer';
    }
    item.append(anchor);
    item.append(node('p', '', source.excerpt));
    item.append(node('div', 'source-meta', `${source.section} · retrieval score ${source.relevance.toFixed(2)}`));
    container.append(item);
  }
}

function renderAudit(interaction: Interaction): void {
  const section = element('audit-section');
  section.hidden = false;
  element('audit-outcome').textContent = interaction.approvalOutcome.replace('_', ' ');
  const details = element('audit-details');
  details.replaceChildren();
  const values: Array<[string, string]> = [
    ['Model', interaction.modelVersion],
    ['Prompt', interaction.promptVersion],
    ['Generated', new Date(interaction.generatedAt).toLocaleString()],
    ['Knowledge escalation', interaction.knowledgeEscalationId ?? 'None'],
    ['Consecutive unchanged', String(interaction.qualifyingApprovals)],
    ['Autonomy eligible', interaction.autonomyEligible ? 'Yes, controlled trial only' : 'No'],
  ];
  if (interaction.wasEdited !== undefined) values.push(['Compared text', interaction.wasEdited ? 'Edited before send' : 'Unchanged draft']);
  if (interaction.simulatedSendId) values.push(['Simulated send ID', interaction.simulatedSendId]);
  if (interaction.correctionReason) values.push(['Correction reason', interaction.correctionReason]);
  for (const [label, value] of values) {
    details.append(node('dt', '', label), node('dd', '', value));
  }
}

function setDraftText(text: string, disabled: boolean): void {
  const field = element<HTMLTextAreaElement>('reply-field');
  field.value = text;
  field.disabled = disabled;
}

async function generateDraft(emailId: string): Promise<void> {
  await runAction(async () => {
    await request(`/api/emails/${encodeURIComponent(emailId)}/draft`, { method: 'POST', body: '{}' });
    await refresh();
    selectEmail(emailId);
  }, 'Draft request completed.');
}

async function sendDraft(): Promise<void> {
  const email = state.emails.find((entry) => entry.id === state.selectedId);
  if (!email?.interaction) return;
  const finalText = element<HTMLTextAreaElement>('reply-field').value;
  await runAction(async () => {
    const result = await request<{ duplicate: boolean }>('/api/reviews/' + encodeURIComponent(email.interaction!.id) + '/send', {
      method: 'POST', body: JSON.stringify({ finalText }),
    });
    await refresh();
    selectEmail(email.id);
    return result.duplicate ? 'This simulated send was already recorded.' : 'Approved and recorded as a simulated send.';
  }, 'Send recorded.');
}

async function saveRejection(): Promise<void> {
  const email = state.emails.find((entry) => entry.id === state.selectedId);
  if (!email?.interaction) return;
  const reason = element<HTMLInputElement>('correction-reason').value;
  const replacementText = element<HTMLTextAreaElement>('replacement-field').value;
  await runAction(async () => {
    await request(`/api/reviews/${encodeURIComponent(email.interaction!.id)}/reject`, {
      method: 'POST', body: JSON.stringify({ reason, replacementText }),
    });
    await refresh();
    selectEmail(email.id);
    return 'Rejection and replacement saved. Nothing was sent.';
  }, 'Correction saved.');
}

async function saveExpertRequest(): Promise<void> {
  const email = state.emails.find((entry) => entry.id === state.selectedId);
  if (!email?.interaction) return;
  const reason = element<HTMLInputElement>('expert-reason').value;
  await runAction(async () => {
    await request(`/api/reviews/${encodeURIComponent(email.interaction!.id)}/expert`, {
      method: 'POST', body: JSON.stringify({ reason }),
    });
    await refresh();
    selectEmail(email.id);
    return 'Marked for expert assistance.';
  }, 'Escalated.');
}

async function runAction(action: () => Promise<unknown>, successMessage: string): Promise<void> {
  try {
    const result = await action();
    showToast(typeof result === 'string' ? result : successMessage);
  } catch (error) {
    showToast(messageOf(error));
  }
}

function safeWebUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : null;
  } catch {
    return null;
  }
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : 'Unexpected error.';
}

let toastTimer: number | undefined;
function showToast(message: string): void {
  toast.textContent = message;
  toast.classList.add('visible');
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => toast.classList.remove('visible'), 3200);
}

element('search-input').addEventListener('input', (event) => {
  state.search = (event.currentTarget as HTMLInputElement).value;
  renderEmailList();
});
element('refresh-button').addEventListener('click', () => void refresh());
element('send-button').addEventListener('click', () => void sendDraft());
element('reject-button').addEventListener('click', () => {
  const email = state.emails.find((entry) => entry.id === state.selectedId);
  element<HTMLTextAreaElement>('replacement-field').value = element<HTMLTextAreaElement>('reply-field').value;
  element('correction-fields').hidden = false;
  element('expert-fields').hidden = true;
  if (email) element('correction-reason').focus();
});
element('save-rejection-button').addEventListener('click', () => void saveRejection());
element('expert-button').addEventListener('click', () => {
  element('expert-fields').hidden = false;
  element('correction-fields').hidden = true;
  element<HTMLInputElement>('expert-reason').focus();
});
element('save-expert-button').addEventListener('click', () => void saveExpertRequest());
window.addEventListener('keydown', (event) => {
  if (event.key === '/' && !(event.target instanceof HTMLInputElement) && !(event.target instanceof HTMLTextAreaElement)) {
    event.preventDefault();
    element<HTMLInputElement>('search-input').focus();
  }
});

void refresh();
