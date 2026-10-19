const questionInput = document.getElementById('question-input');
const askButton = document.getElementById('ask-button');
const clearButton = document.getElementById('clear-button');
const answerBox = document.getElementById('answer-box');
const statusPill = document.getElementById('status-pill');
const resultState = document.getElementById('result-state');
const sourceList = document.getElementById('source-list');
const imageList = document.getElementById('image-list');

function setStatus(state, label) {
  statusPill.className = `status-pill ${state}`;
  statusPill.textContent = label;
  resultState.className = `state-badge ${state}`;
  resultState.textContent = label;
}

function renderSources(items) {
  if (!items || items.length === 0) {
    sourceList.innerHTML = '<li>None yet.</li>';
    return;
  }

  sourceList.innerHTML = items
    .map((item) => {
      const title = item.title || item.source || 'Knowledge source';
      const snippet = item.content ? item.content.slice(0, 180) : '';
      return `<li><strong>${title}</strong><br />${snippet}</li>`;
    })
    .join('');
}

function renderImages(items) {
  if (!items || items.length === 0) {
    imageList.innerHTML = '<li>None yet.</li>';
    return;
  }

  imageList.innerHTML = items
    .map((item) => `<li>${item.label || item.caption || 'Image reference'}</li>`)
    .join('');
}

function renderEmptyState(message) {
  answerBox.innerHTML = `<div class="empty-state">${message}</div>`;
}

function renderAnswer(payload) {
  const answerText = payload.answer || 'No answer was returned.';
  answerBox.innerHTML = `<div>${answerText}</div>`;

  if (payload.status === 'insufficient_evidence') {
    setStatus('error', 'Unanswered');
    renderSources([]);
    renderImages([]);
    return;
  }

  if (payload.needs_human) {
    setStatus('warning', 'Escalation');
  } else {
    setStatus('success', 'Answered');
  }

  renderSources(payload.sources || []);
  renderImages(payload.image_references || []);
}

async function askKnowledge() {
  const question = questionInput.value.trim();
  if (!question) {
    renderEmptyState('Please enter a question before submitting.');
    setStatus('warning', 'Input required');
    return;
  }

  setStatus('pending', 'Thinking');
  answerBox.innerHTML = '<div class="empty-state">Searching the knowledge base...</div>';

  try {
    const response = await fetch('/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, top_k: 5 })
    });

    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}));
      const message = errorPayload.message || 'The knowledge service is unavailable.';
      renderEmptyState(message);
      setStatus('error', 'Unavailable');
      return;
    }

    const payload = await response.json();
    renderAnswer(payload);
  } catch (error) {
    console.error(error);
    renderEmptyState('Knowledge service unavailable. Please check the API and try again.');
    setStatus('error', 'Unavailable');
  }
}

askButton.addEventListener('click', askKnowledge);
clearButton.addEventListener('click', () => {
  questionInput.value = '';
  renderEmptyState('No answer yet. Ask a product question to retrieve grounded documentation.');
  setStatus('idle', 'Ready');
  renderSources([]);
  renderImages([]);
});

questionInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
    askKnowledge();
  }
});
