import type { Classification, EmailRecord } from '../types.js';

const protectedCategories = new Set(['project_request', 'refund_cancellation', 'complaint', 'quote_request']);

export function classifyEmail(email: Pick<EmailRecord, 'subject' | 'body'>): Classification {
  const text = `${email.subject} ${email.body}`.toLowerCase();
  let category: Classification['category'];

  if (/\b(complaint|unacceptable|very frustrated|broke our|broken since|not happy|unhappy|disappointed|ignored my)\b/.test(text)) {
    category = 'complaint';
  } else if (/\b(refund|cancel(?:lation)? (?:my|the|our|this)|charged after cancel|stop billing|not to renew|non[- ]?renewal|close (?:my|our|the) account|end service)\b/.test(text)) {
    category = 'refund_cancellation';
  } else if (/\b(quote|pricing|price|how much|what will .* cost|estimate .* cost|budget for)\b/.test(text)) {
    category = 'quote_request';
  } else if (/\b(build|develop|custom|new feature|feature request|integrate|booking flow|functionality|migrat\w*|members-only resource area|comparison page|add (?:a |an )?(?:new )?(?:feature|integration|booking|workflow))\b/.test(text)) {
    category = 'project_request';
  } else if (/\b(follow(?:ing)? up|checking (?:in|on|whether)|any update|did you (?:receive|get)|previous (?:email|message|request)|last week)\b/.test(text)) {
    category = 'follow_up';
  } else if (/\b(error|fail(?:s|ed)? to|failed|failure|not working|stopped working|can't|cannot|crash|timeout|times out|keeps .*|unable to|doesn't work|does not work|slow|never finishes loading|missing (?:email|notification|confirmation|result|data)|neither .{0,80} receives|not arriving|delayed)\b/.test(text)) {
    category = 'troubleshooting';
  } else {
    category = 'how_to';
  }

  const urgency: Classification['urgency'] = /\b(urgent|asap|today|outage|down|blocked|emergency|immediately)\b/.test(text)
    ? 'urgent'
    : 'normal';
  const securitySensitive = /\b(password|credential|authentication|account compromise|unauthorized access|hacked|security breach)\b/.test(text);
  const riskLevel: Classification['riskLevel'] = securitySensitive || protectedCategories.has(category)
    ? 'high'
    : category === 'follow_up' && /\b(refund|cancel|billing|account status)\b/.test(text)
      ? 'high'
    : category === 'follow_up'
      ? 'medium'
    : category === 'troubleshooting' || urgency === 'urgent'
      ? 'medium'
      : 'low';

  return { category, riskLevel, urgency, requiresHumanApproval: true };
}

export function isAutonomyProtected(category: Classification['category'], urgency: Classification['urgency']): boolean {
  return protectedCategories.has(category) || urgency === 'urgent';
}