const state = { projects: [], projectId: '', revisions: [], revisionId: '' };
const $ = (id) => document.getElementById(id);
const el = (tag, className = '', text = '') => {
  const item = document.createElement(tag);
  item.className = className;
  item.textContent = text;
  return item;
};

async function api(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || `Request failed (${response.status}).`);
  return result;
}

function notify(message) {
  const toast = $('toast');
  toast.textContent = message;
  toast.classList.add('visible');
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => toast.classList.remove('visible'), 3500);
}

async function loadProjects() {
  state.projects = await api('/projects');
  renderProjects();
}

function renderProjects() {
  const list = $('project-list');
  list.replaceChildren();
  if (!state.projects.length) {
    list.append(el('p', 'muted', 'No projects yet.'));
    return;
  }
  for (const project of state.projects) {
    const button = el('button', `project-item ${state.projectId === project.project_id ? 'active' : ''}`);
    button.type = 'button';
    button.append(el('strong', '', project.title));
    button.append(el('span', '', project.latest_revision
      ? `Revision ${project.latest_revision.revision_number} · ${project.latest_revision.status.replace('_', ' ')}`
      : 'No revisions'));
    button.addEventListener('click', () => selectProject(project.project_id));
    list.append(button);
  }
}

async function selectProject(projectId) {
  try {
    state.projectId = projectId;
    const [revisions, meetings] = await Promise.all([
      api(`/projects/${encodeURIComponent(projectId)}/revisions`),
      api(`/projects/${encodeURIComponent(projectId)}/meetings`),
    ]);
    state.revisions = revisions;
    if (!revisions.some((revision) => revision.revision_id === state.revisionId)) {
      state.revisionId = revisions[0]?.revision_id || '';
    }
    $('project-title').textContent = state.projects.find((item) => item.project_id === projectId)?.title || 'Project';
    $('project-meta').textContent = `${meetings.length} meeting${meetings.length === 1 ? '' : 's'} stored · consent confirmed`;
    $('welcome').hidden = true;
    $('project-view').hidden = false;
    renderRevisionPicker();
    renderProjects();
  } catch (error) { notify(error.message); }
}

function renderRevisionPicker() {
  const select = $('revision-select');
  select.replaceChildren();
  for (const revision of state.revisions) {
    const option = el('option', '', `Revision ${revision.revision_number} · ${revision.status.replace('_', ' ')}`);
    option.value = revision.revision_id;
    select.append(option);
  }
  select.value = state.revisionId;
  const revision = state.revisions.find((item) => item.revision_id === state.revisionId);
  if (revision) renderRevision(revision);
}

function renderRevision(revision) {
  $('revision-status').textContent = revision.status.replace('_', ' ');
  $('revision-status').className = `status-badge ${revision.status === 'approved' ? 'approved' : ''}`;
  $('requirement-count').textContent = `${revision.analysis.requirements.length} items`;
  $('estimate-range').textContent = `${revision.estimate.low_hours}–${revision.estimate.high_hours} h`;
  $('change-panel').hidden = !revision.change_report.baseline_revision_id;
  $('baseline-label').textContent = revision.change_report.baseline_revision_id
    ? `Compared with approved ${revision.change_report.baseline_revision_id.slice(0, 8)}` : 'No approved baseline';
  $('change-summary').textContent = revision.change_report.summary;
  renderChanges(revision.change_report.items);
  renderRequirements(revision.analysis.requirements);
  renderEstimates(revision);
  renderSections($('scope-content'), [
    ['Project objective', [revision.scope.objective]], ['Current problem', [revision.scope.current_problem]],
    ['Agreed requirements', revision.scope.agreed_requirements.map((item) => `${item.requirement_id}: ${item.description}`)],
    ['Proposed solution', revision.scope.proposed_solution], ['Deliverables', revision.scope.deliverables],
    ['Exclusions', revision.scope.exclusions], ['Assumptions and dependencies', [...revision.scope.assumptions, ...revision.scope.dependencies]],
    ['Acceptance criteria', revision.scope.acceptance_criteria], ['Client responsibilities', revision.scope.client_responsibilities],
    ['Open questions and risks', revision.scope.open_questions_and_risks],
  ]);
  const proposal = revision.proposal;
  renderSections($('proposal-content'), [
    ['Executive summary', [proposal.executive_summary]], ['Client problem', [proposal.client_problem]],
    ['Proposed solution', proposal.proposed_solution], ['Scope and deliverables', proposal.scope_and_deliverables],
    ['Estimated effort', [proposal.effort_summary, proposal.timeline_note]], ['Pricing assumptions', proposal.pricing_assumptions],
    ['Client responsibilities', proposal.client_responsibilities], ['Exclusions and dependencies', proposal.exclusions_and_dependencies],
    ['Risks and open questions', proposal.risks_and_open_questions], ['Approval and next steps', proposal.approval_next_steps],
  ]);
  $('estimate-notes').textContent = [...revision.estimate.assumptions, ...revision.estimate.warnings].join('\n');
  renderApproval(revision);
  loadTranscript(revision);
}

function renderChanges(items) {
  const list = $('change-list');
  list.replaceChildren();
  for (const item of items) {
    const article = el('article', 'change-item');
    article.append(el('strong', '', item.kind.replace('_', ' ')), el('p', '', item.description), el('p', 'muted', item.reason));
    list.append(article);
  }
}

function renderRequirements(requirements) {
  const list = $('requirements-list');
  list.replaceChildren();
  if (!requirements.length) {
    list.append(el('p', 'muted', 'No actionable requirements were extracted. Review the transcript and ask for clarification.'));
    return;
  }
  for (const requirement of requirements) {
    const article = el('article', 'requirement');
    const top = el('div', 'requirement-top');
    top.append(el('h4', '', requirement.description), el('span', 'req-id', requirement.requirement_id));
    article.append(top);
    const tags = el('div', 'req-tags');
    tags.append(el('span', `tag ${requirement.status}`, requirement.status));
    tags.append(el('span', 'tag', requirement.priority.replace('_', ' ')));
    tags.append(el('span', `tag ${requirement.feasibility.classification}`, requirement.feasibility.classification.replaceAll('_', ' ')));
    article.append(tags);
    for (const source of requirement.source_references) {
      article.append(el('blockquote', 'source-quote', `Meeting lines ${source.line_start}-${source.line_end} · ${source.speaker}: “${source.quote}”`));
    }
    article.append(el('p', 'feasibility-text', requirement.feasibility.rationale));
    if (requirement.acceptance_criteria.length) article.append(el('p', 'feasibility-text', `Acceptance: ${requirement.acceptance_criteria.join('; ')}`));
    list.append(article);
  }
}

function renderEstimates(revision) {
  const list = $('estimate-list');
  list.replaceChildren();
  const head = el('div', 'estimate-row estimate-head');
  head.append(el('span', '', 'Engineering task'), el('span', '', 'Low'), el('span', '', 'Likely'), el('span', '', 'High'));
  list.append(head);
  for (const task of revision.estimate.tasks) {
    const row = el('div', 'estimate-row');
    row.append(el('strong', '', task.name), el('span', '', `${task.low_hours}h`), el('span', '', `${task.likely_hours}h`), el('span', '', `${task.high_hours}h`));
    row.append(el('p', 'estimate-reason', `${task.requirement_id} · ${task.confidence} confidence · ${task.reasoning}`));
    list.append(row);
  }
}

function renderSections(target, sections) {
  target.replaceChildren();
  for (const [title, items] of sections) {
    target.append(el('h4', '', title));
    if (!items.length) {
      target.append(el('p', 'muted', 'Not established from the transcript.'));
      continue;
    }
    const list = document.createElement('ul');
    for (const item of items) list.append(el('li', '', item));
    target.append(list);
  }
}

function renderApproval(revision) {
  const pending = revision.status === 'pending_review';
  $('approval-title').textContent = pending ? 'Human approval required' : `Revision ${revision.status.replace('_', ' ')}`;
  $('approval-description').textContent = pending
    ? 'Only an approved revision can become the client-facing baseline. This app does not send proposals.'
    : revision.status === 'approved' ? 'This approved revision is now the baseline for follow-up comparisons.' : 'Changes were requested; resolve review notes before approval.';
  $('approval-controls').hidden = !pending;
}

async function loadTranscript(revision) {
  try {
    const meeting = await api(`/projects/${encodeURIComponent(revision.project_id)}/meetings/${encodeURIComponent(revision.meeting_id)}`);
    $('transcript-meta').textContent = `${meeting.meeting_date} · SHA-256 ${meeting.transcript_hash}`;
    $('transcript-text').textContent = meeting.transcript;
  } catch (error) { notify(error.message); }
}

async function createProject() {
  const data = {
    title: $('new-title').value.trim(), meeting_date: $('new-date').value,
    transcript: $('new-transcript').value.trim(), consent_confirmed: $('new-consent').checked,
  };
  await runAction(async () => {
    const revision = await api('/projects', { method: 'POST', body: JSON.stringify(data) });
    $('new-project-dialog').close();
    await loadProjects();
    state.revisionId = revision.revision_id;
    await selectProject(revision.project_id);
    return 'Transcript analyzed. Revision is pending review.';
  });
}

async function addFollowup() {
  const data = {
    meeting_date: $('followup-date').value, transcript: $('followup-transcript').value.trim(),
    consent_confirmed: $('followup-consent').checked,
  };
  await runAction(async () => {
    const revision = await api(`/projects/${encodeURIComponent(state.projectId)}/meetings`, { method: 'POST', body: JSON.stringify(data) });
    $('followup-transcript').value = '';
    $('followup-consent').checked = false;
    await loadProjects();
    state.revisionId = revision.revision_id;
    await selectProject(revision.project_id);
    return 'Follow-up analyzed against the latest approved baseline.';
  });
}

async function review(decision) {
  const revision = state.revisions.find((item) => item.revision_id === state.revisionId);
  const reviewer = $('reviewer-name').value.trim();
  const note = decision === 'request_changes' ? (window.prompt('What should be revised?') || '') : '';
  await runAction(async () => {
    await api(`/projects/${encodeURIComponent(revision.project_id)}/revisions/${encodeURIComponent(revision.revision_id)}/review`, {
      method: 'POST', body: JSON.stringify({ reviewed_by: reviewer, decision, note }),
    });
    await loadProjects();
    await selectProject(revision.project_id);
    return decision === 'approve' ? 'Revision approved and set as baseline.' : 'Changes requested and recorded.';
  });
}

async function runAction(operation) {
  try { notify(await operation()); } catch (error) { notify(error.message); }
}

$('new-project-button').addEventListener('click', () => $('new-project-dialog').showModal());
$('welcome-create').addEventListener('click', () => $('new-project-dialog').showModal());
$('create-project-button').addEventListener('click', () => createProject());
$('submit-followup').addEventListener('click', () => addFollowup());
$('approve-button').addEventListener('click', () => review('approve'));
$('request-changes-button').addEventListener('click', () => review('request_changes'));
$('revision-select').addEventListener('change', (event) => {
  state.revisionId = event.currentTarget.value;
  const revision = state.revisions.find((item) => item.revision_id === state.revisionId);
  if (revision) renderRevision(revision);
});
$('new-date').value = new Date().toISOString().slice(0, 10);
$('followup-date').value = new Date().toISOString().slice(0, 10);
loadProjects().catch((error) => notify(error.message));
