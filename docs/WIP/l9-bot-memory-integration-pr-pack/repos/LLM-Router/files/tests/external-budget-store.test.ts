import { describe, expect, it } from 'vitest';
import {
  BudgetReservationError,
  L9LLMRouter,
  Provider,
  TaskComplexity,
  TaskType,
  ThrottleLevel,
  type BudgetState,
  type BudgetStore,
  type GeneralModelConfig,
  type LLMResponse,
  type PerplexityConfig,
  type TaskDescriptor,
  type VisionConfig,
} from '../src/index.js';

const response: LLMResponse = {
  content: 'ok', model: 'openai/gpt-4o-mini', provider: Provider.OPENROUTER,
  inputTokens: 1, outputTokens: 1, totalTokens: 2, cost: 0.1, latencyMs: 1, cached: false,
};

class RecordingStore implements BudgetStore {
  events: string[] = [];
  initialized = new Set<string>();
  async initClient(clientId: string) { this.events.push(`init:${clientId}`); this.initialized.add(clientId); }
  async reserveTask(clientId: string, _task: TaskDescriptor, estimatedCost: number, now = new Date(), idFactory = () => 'r') {
    if (!this.initialized.has(clientId)) throw new BudgetReservationError('not initialized');
    this.events.push(`reserve:${clientId}:${estimatedCost}`);
    return {
      decision: { level: ThrottleLevel.NONE, reason: 'ok', allowTask: true, forceDowngrade: false, maxModelTier: 'critical' as const },
      reservation: { id: idFactory(), clientId, estimatedCost, createdAt: now.toISOString() },
    };
  }
  async reconcile(id: string, cost: number) { this.events.push(`reconcile:${id}:${cost}`); }
  async release(id: string) { this.events.push(`release:${id}`); }
  async recordSpend() {}
  async resetDaily() {}
  async resetWeekly() {}
  async resetMonthly() {}
  async resetGlobalMonthly() {}
  async checkSurgeAllowance() { return false; }
  async getClientBudgetReport(clientId: string): Promise<BudgetState> {
    return { clientId, monthlyBudget: 1, monthSpend: 0, weekSpend: 0, weekTarget: 1, todaySpend: 0, weeklyHardCeiling: 1, surgeAllowance: false, remainingMonthly: 1, remainingWeekly: 1, throttleLevel: 'none', reservedSpend: 0, activeReservations: 0 };
  }
  async getAllBudgetReports() { return []; }
  async getGlobalSpend() { return { monthSpend: 0, reservedSpend: 0, ceiling: 1, utilization: 0 }; }
}

const fakeOpenRouter = {
  complete: async (_config: GeneralModelConfig) => response,
  completeWithVision: async (_config: VisionConfig) => response,
  completeWithFallback: async (_config: GeneralModelConfig) => response,
};
const fakePerplexity = {
  complete: async (_config: PerplexityConfig) => ({ ...response, provider: Provider.PERPLEXITY }),
  completeWithConsensus: async (_config: PerplexityConfig) => ({
    best: { ...response, provider: Provider.PERPLEXITY }, all: [], consensusScore: 1,
    aggregate: { inputTokens: 1, outputTokens: 1, totalTokens: 2, cost: 0.1, latencyMs: 1, citations: [] },
  }),
};

describe('external budget store', () => {
  it('awaits atomic reserve and reconcile around dispatch', async () => {
    const store = new RecordingStore();
    const router = new L9LLMRouter(
      { perplexityApiKey: 'p', openrouterApiKey: 'o' },
      { budgetStore: store, openrouterClient: fakeOpenRouter, perplexityClient: fakePerplexity, idFactory: () => 'reservation' },
    );
    await router.initClient('client');
    await router.execute({ clientId: 'client', type: TaskType.CLASSIFICATION, complexity: TaskComplexity.LOW }, 's', 'u');
    expect(store.events[0]).toBe('init:client');
    expect(store.events.some(event => event.startsWith('reserve:client:'))).toBe(true);
    expect(store.events).toContain('reconcile:reservation:0.1');
    await expect(router.getClientBudgetReportAsync('client')).resolves.toMatchObject({ clientId: 'client' });
    expect(() => router.getClientBudgetReport('client')).toThrow(/external BudgetStore/);
  });
});

describe('hard ceiling invariants', () => {
  it('never admits a task whose reservation crosses a hard ceiling', async () => {
    const { BudgetTracker } = await import('../src/index.js');
    const tracker = new BudgetTracker({ monthlyBudgetPerClient: 1, weeklyTarget: 0.5, weeklyHardCeiling: 1, globalMonthlyHardCeiling: 1 });
    tracker.initClient('client');
    tracker.recordSpend('client', 0.99);
    expect(() => tracker.reserveTask('client', { clientId: 'client', type: TaskType.STRATEGIC_REASONING, complexity: TaskComplexity.CRITICAL }, 0.02)).toThrow(BudgetReservationError);
  });
});

describe('reconciliation failure safety', () => {
  it('retains a billed reservation when durable reconciliation fails', async () => {
    class FailingReconcileStore extends RecordingStore {
      override async reconcile(id: string, cost: number) {
        this.events.push(`reconcile-failed:${id}:${cost}`);
        throw new Error('ledger unavailable');
      }
    }
    const store = new FailingReconcileStore();
    const router = new L9LLMRouter(
      { perplexityApiKey: 'p', openrouterApiKey: 'o' },
      { budgetStore: store, openrouterClient: fakeOpenRouter, perplexityClient: fakePerplexity, idFactory: () => 'reservation' },
    );
    await router.initClient('client');
    await expect(router.execute({ clientId: 'client', type: TaskType.CLASSIFICATION, complexity: TaskComplexity.LOW }, 's', 'u')).rejects.toThrow(/ledger unavailable/);
    expect(store.events).toContain('reconcile-failed:reservation:0.1');
    expect(store.events).not.toContain('release:reservation');
  });
});
