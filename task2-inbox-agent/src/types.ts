import { z } from 'zod';

export const emailCategories = [
  'how_to',
  'troubleshooting',
  'project_request',
  'refund_cancellation',
  'complaint',
  'quote_request',
  'follow_up',
] as const;

export const emailCategorySchema = z.enum(emailCategories);
export type EmailCategory = z.infer<typeof emailCategorySchema>;
export type EmailRisk = 'low' | 'medium' | 'high';
export type Urgency = 'normal' | 'urgent';

export const emailRecordSchema = z.object({
  id: z.string(),
  split: z.enum(['development', 'test']),
  subject: z.string().min(1),
  from: z.string().min(1),
  body: z.string().min(1),
  expectedCategory: emailCategorySchema,
  expectedRisk: z.enum(['low', 'medium', 'high']),
  expectedFacts: z.array(z.string()),
  expectedBehavior: z.string(),
});
export type EmailRecord = z.infer<typeof emailRecordSchema>;
export type CustomerEmail = Pick<EmailRecord, 'id' | 'subject' | 'from' | 'body'>;

export const knowledgeSourceSchema = z.object({
  document_id: z.string(),
  chunk_id: z.string(),
  title: z.string(),
  url: z.string().url(),
  section: z.string(),
  excerpt: z.string(),
  relevance: z.number().min(0).max(1),
  images: z.array(z.record(z.string(), z.string())).default([]),
});

export const knowledgeResponseSchema = z.object({
  answer: z.string(),
  status: z.enum(['answered', 'insufficient_evidence', 'needs_human']),
  sources: z.array(knowledgeSourceSchema),
  image_references: z.array(z.record(z.string(), z.string())).default([]),
  needs_human: z.boolean(),
  escalation_reason: z.string().nullable().optional(),
  escalation_id: z.string().nullable().optional(),
});
export type KnowledgeResponse = z.infer<typeof knowledgeResponseSchema>;

export const modelDraftSchema = z.object({
  summary: z.string().min(1).max(500),
  suggestedReply: z.string().min(1).max(5000),
  nextAction: z.string().min(1).max(500),
});
export type ModelDraft = z.infer<typeof modelDraftSchema>;

export type DraftStatus = 'ready' | 'knowledge_unavailable' | 'insufficient_evidence' | 'model_unavailable' | 'unsafe_output';
export type ApprovalOutcome = 'pending' | 'approved' | 'edited' | 'rejected' | 'needs_expert';

export interface Classification {
  category: EmailCategory;
  riskLevel: EmailRisk;
  urgency: Urgency;
  requiresHumanApproval: true;
}

export interface Interaction {
  id: string;
  emailId: string;
  originalEmail: CustomerEmail;
  category: EmailCategory;
  riskLevel: EmailRisk;
  urgency: Urgency;
  summary: string;
  suggestedReply: string;
  nextAction: string;
  sources: KnowledgeResponse['sources'];
  knowledgeStatus: KnowledgeResponse['status'] | 'unavailable';
  knowledgeError?: string;
  knowledgeEscalationId?: string | null;
  draftStatus: DraftStatus;
  requiresHumanApproval: true;
  modelVersion: string;
  promptVersion: string;
  generatedAt: string;
  approvalOutcome: ApprovalOutcome;
  correctionReason?: string;
  replacementText?: string;
  finalSentText?: string;
  wasEdited?: boolean;
  simulatedSendId?: string;
  sentAt?: string;
  qualifyingApprovals: number;
  autonomyEligible: boolean;
}