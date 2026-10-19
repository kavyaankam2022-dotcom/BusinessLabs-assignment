import { randomUUID } from 'node:crypto';
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { isAutonomyProtected } from '../email/classifier.js';
import { isUneditedDraft } from './feedback.js';
import { emailCategories, type ApprovalOutcome, type CustomerEmail, type EmailCategory, type EmailRisk, type Interaction, type Urgency } from '../types.js';

interface InboxState {
  version: 1;
  interactions: Interaction[];
  consecutiveApprovals: Record<EmailCategory, number>;
  autonomyEnabled: Record<EmailCategory, boolean>;
}

export interface NewInteraction {
  emailId: string;
  originalEmail: CustomerEmail;
  category: EmailCategory;
  riskLevel: EmailRisk;
  urgency: Urgency;
  summary: string;
  suggestedReply: string;
  nextAction: string;
  sources: Interaction['sources'];
  knowledgeStatus: Interaction['knowledgeStatus'];
  knowledgeError?: string;
  knowledgeEscalationId?: string | null;
  draftStatus: Interaction['draftStatus'];
  modelVersion: string;
  promptVersion: string;
}

const defaultState = (): InboxState => ({
  version: 1,
  interactions: [],
  consecutiveApprovals: Object.fromEntries(emailCategories.map((category) => [category, 0])) as Record<EmailCategory, number>,
  autonomyEnabled: Object.fromEntries(emailCategories.map((category) => [category, false])) as Record<EmailCategory, boolean>,
});

const autonomyCategories = new Set<EmailCategory>(['how_to', 'troubleshooting']);

export class InboxStore {
  private readonly statePath: string;
  private writeQueue: Promise<void> = Promise.resolve();

  constructor(statePath = process.env.INBOX_STATE_PATH ?? path.resolve('.inbox-state', 'state.json')) {
    this.statePath = statePath;
  }

  async listInteractions(): Promise<Interaction[]> {
    return (await this.readState()).interactions.sort((left, right) => right.generatedAt.localeCompare(left.generatedAt));
  }

  async getInteraction(id: string): Promise<Interaction | undefined> {
    return (await this.readState()).interactions.find((interaction) => interaction.id === id);
  }

  async getInteractionForEmail(emailId: string): Promise<Interaction | undefined> {
    return (await this.readState()).interactions
      .filter((interaction) => interaction.emailId === emailId)
      .sort((left, right) => right.generatedAt.localeCompare(left.generatedAt))[0];
  }

  async createInteraction(input: NewInteraction): Promise<Interaction> {
    return this.mutate((state) => {
      const existing = state.interactions.find((interaction) => interaction.emailId === input.emailId && interaction.approvalOutcome === 'pending');
      if (input.draftStatus !== 'ready') state.consecutiveApprovals[input.category] = 0;
      if (existing) {
        Object.assign(existing, input, { generatedAt: new Date().toISOString() });
        return existing;
      }
      const interaction: Interaction = {
        ...input,
        id: randomUUID(),
        requiresHumanApproval: true,
        generatedAt: new Date().toISOString(),
        approvalOutcome: 'pending',
        qualifyingApprovals: state.consecutiveApprovals[input.category],
          autonomyEligible: state.consecutiveApprovals[input.category] >= 20
            && autonomyCategories.has(input.category)
            && input.riskLevel !== 'high'
            && input.urgency === 'normal'
            && input.draftStatus === 'ready',
      };
      state.interactions.push(interaction);
      return interaction;
    });
  }

  async sendReply(id: string, finalText: string): Promise<{ interaction?: Interaction; duplicate: boolean }> {
    return this.mutate((state) => {
      const interaction = state.interactions.find((entry) => entry.id === id);
      if (!interaction) return { duplicate: false };
      if (interaction.simulatedSendId) return { interaction, duplicate: true };
      if (interaction.draftStatus !== 'ready' || interaction.approvalOutcome !== 'pending') return { interaction, duplicate: false };

      const wasEdited = !isUneditedDraft(interaction.suggestedReply, finalText);
      const autonomySafe = interaction.riskLevel !== 'high'
        && interaction.modelVersion !== 'human-review'
        && !isAutonomyProtected(interaction.category, interaction.urgency);
      const nextCount = wasEdited || !autonomySafe ? 0 : state.consecutiveApprovals[interaction.category] + 1;
      state.consecutiveApprovals[interaction.category] = nextCount;
      interaction.approvalOutcome = wasEdited ? 'edited' : 'approved';
      interaction.wasEdited = wasEdited;
      interaction.finalSentText = finalText;
      interaction.sentAt = new Date().toISOString();
      interaction.simulatedSendId = randomUUID();
      interaction.qualifyingApprovals = nextCount;
      interaction.autonomyEligible = nextCount >= 20 && autonomyCategories.has(interaction.category);
      return { interaction, duplicate: false };
    });
  }

  async reject(id: string, reason: string, replacementText: string): Promise<Interaction | undefined> {
    return this.mutate((state) => {
      const interaction = state.interactions.find((entry) => entry.id === id);
      if (!interaction || interaction.approvalOutcome !== 'pending') return undefined;
      state.consecutiveApprovals[interaction.category] = 0;
      interaction.approvalOutcome = 'rejected';
      interaction.correctionReason = reason;
      interaction.replacementText = replacementText;
      interaction.qualifyingApprovals = 0;
      interaction.autonomyEligible = false;
      const replacement: Interaction = {
        ...interaction,
        id: randomUUID(),
        suggestedReply: replacementText,
        nextAction: 'Human-authored replacement is awaiting separate approval.',
        modelVersion: 'human-review',
        promptVersion: `${interaction.promptVersion}+human-replacement`,
        generatedAt: new Date().toISOString(),
        approvalOutcome: 'pending',
        replacementText: undefined,
        finalSentText: undefined,
        wasEdited: undefined,
        simulatedSendId: undefined,
        sentAt: undefined,
      };
      state.interactions.push(replacement);
      return replacement;
    });
  }

  async requestExpert(id: string, reason: string): Promise<Interaction | undefined> {
    return this.mutate((state) => {
      const interaction = state.interactions.find((entry) => entry.id === id);
      if (!interaction || interaction.approvalOutcome !== 'pending') return undefined;
      state.consecutiveApprovals[interaction.category] = 0;
      interaction.approvalOutcome = 'needs_expert';
      interaction.correctionReason = reason;
      interaction.qualifyingApprovals = 0;
      interaction.autonomyEligible = false;
      return interaction;
    });
  }

  async setAutonomy(category: EmailCategory, enabled: boolean): Promise<{ enabled: boolean; eligible: boolean }> {
    return this.mutate((state) => {
      const count = state.consecutiveApprovals[category];
      const eligible = count >= 20 && autonomyCategories.has(category);
      const allowed = eligible && !isAutonomyProtected(category, 'normal');
      state.autonomyEnabled[category] = enabled && allowed;
      return { enabled: state.autonomyEnabled[category], eligible };
    });
  }

  async summary(): Promise<{
    totals: Record<ApprovalOutcome, number>;
    consecutiveApprovals: Record<EmailCategory, number>;
    autonomyEnabled: Record<EmailCategory, boolean>;
    eligibleCategories: EmailCategory[];
  }> {
    const state = await this.readState();
    const totals = Object.fromEntries(['pending', 'approved', 'edited', 'rejected', 'needs_expert'].map((status) => [
      status,
      state.interactions.filter((interaction) => interaction.approvalOutcome === status).length,
    ])) as Record<ApprovalOutcome, number>;
    return {
      totals,
      consecutiveApprovals: state.consecutiveApprovals,
      autonomyEnabled: state.autonomyEnabled,
      eligibleCategories: emailCategories.filter((category) => state.consecutiveApprovals[category] >= 20 && autonomyCategories.has(category)),
    };
  }

  async feedbackSummary(): Promise<Array<{
    category: EmailCategory;
    generated: number;
    edited: number;
    rejected: number;
    expertEscalated: number;
    recentCorrections: string[];
  }>> {
    const interactions = (await this.readState()).interactions;
    return emailCategories.map((category) => {
      const categoryInteractions = interactions.filter((interaction) => interaction.category === category);
      return {
        category,
        generated: categoryInteractions.length,
        edited: categoryInteractions.filter((interaction) => interaction.wasEdited === true).length,
        rejected: categoryInteractions.filter((interaction) => interaction.approvalOutcome === 'rejected').length,
        expertEscalated: categoryInteractions.filter((interaction) => interaction.approvalOutcome === 'needs_expert').length,
        recentCorrections: categoryInteractions
          .filter((interaction) => Boolean(interaction.correctionReason)
            && (interaction.approvalOutcome === 'rejected' || interaction.approvalOutcome === 'needs_expert'))
          .slice(-5)
          .map((interaction) => interaction.correctionReason!),
      };
    });
  }

  private async readState(): Promise<InboxState> {
    try {
      const parsed = JSON.parse(await readFile(this.statePath, 'utf8')) as Partial<InboxState>;
      const defaults = defaultState();
      return {
        ...defaults,
        ...parsed,
        interactions: Array.isArray(parsed.interactions) ? parsed.interactions : [],
        consecutiveApprovals: { ...defaults.consecutiveApprovals, ...parsed.consecutiveApprovals },
        autonomyEnabled: { ...defaults.autonomyEnabled, ...parsed.autonomyEnabled },
      };
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') return defaultState();
      throw error;
    }
  }

  private async mutate<T>(operation: (state: InboxState) => T): Promise<T> {
    const pending = this.writeQueue.then(async () => {
      const state = await this.readState();
      const result = operation(state);
      await mkdir(path.dirname(this.statePath), { recursive: true });
      const temporaryPath = `${this.statePath}.${randomUUID()}.tmp`;
      await writeFile(temporaryPath, JSON.stringify(state, null, 2), 'utf8');
      await rename(temporaryPath, this.statePath);
      return result;
    });
    this.writeQueue = pending.then(() => undefined, () => undefined);
    return pending;
  }
}

