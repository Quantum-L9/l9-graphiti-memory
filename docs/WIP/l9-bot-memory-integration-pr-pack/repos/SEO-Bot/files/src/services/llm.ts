/* L9_META
 * layer: module
 * role: seo_bot_engine
 * status: active
 * version: 3.0.0
 */
import {
  L9LLMRouter,
  TaskType,
  TaskComplexity,
  type TaskDescriptor,
  type LLMResponse,
  type BudgetConfig,
  type RoutingDecision,
  BudgetExhaustedError,
} from '@quantum-l9/llm-router';
import type { FullSiteQAConfig, VisualQATask } from '@quantum-l9/llm-router/vision';
import { getConfig } from '../core/config.js';
import { createModuleLogger } from '../core/logger.js';
import { getDb, schema } from '../core/database/index.js';
import { parseJsonFromLlm, parseScore } from './llm-parse.js';
import type { ModuleName } from '../types/index.js';
import { hydrateSeoContext } from './memory.js';

const logger = createModuleLogger('llm');

export class DailyBudgetExhaustedError extends Error {
  constructor(message: string) { super(message); this.name = 'DailyBudgetExhaustedError'; }
}

type LegacyTier = 'fast' | 'strategic';
function tierToComplexity(tier: LegacyTier): TaskComplexity {
  return tier === 'fast' ? TaskComplexity.LOW : TaskComplexity.HIGH;
}

export class LlmService {
  private readonly router: L9LLMRouter;

  constructor() {
    const config = getConfig();
    const budget: BudgetConfig = {
      monthlyBudgetPerClient: config.DEFAULT_CLIENT_MONTHLY_BUDGET,
      weeklyTarget: config.DEFAULT_CLIENT_WEEKLY_TARGET,
      weeklyHardCeiling: config.DEFAULT_CLIENT_WEEKLY_CEILING,
      globalMonthlyHardCeiling: config.GLOBAL_MONTHLY_HARD_CEILING,
      surgeThreshold: config.SURGE_THRESHOLD,
    };
    this.router = new L9LLMRouter({
      perplexityApiKey: config.PERPLEXITY_API_KEY,
      openrouterApiKey: config.OPENROUTER_API_KEY,
      appName: 'L9-SEO-Bot',
      budget,
    });
    logger.info('LLM Service initialized; cognitive memory is delegated to l9-graphiti-memory');
  }

  getRouter(): L9LLMRouter { return this.router; }
  recoverExpiredBudgetReservations(): Promise<number> { return Promise.resolve(0); }

  async execute(
    task: TaskDescriptor,
    systemPrompt: string,
    userPrompt: string,
    options?: { images?: string[]; assistantContext?: string; consensus?: boolean },
  ): Promise<LLMResponse> {
    if (!task.clientId) throw new Error('LLM task clientId is required');
    await this.enforceDailyCap(task);
    try {
      const memoryContext = await hydrateSeoContext(
        task.clientId,
        task.type,
        task.description ?? 'SEO task',
        [this.extractModule(task.description), task.type],
      );
      const response = await this.router.execute(
        task,
        `${systemPrompt}${memoryContext}`,
        userPrompt,
        options,
      );
      await this.logUsage(task, response);
      return response;
    } catch (error: any) {
      if (error instanceof BudgetExhaustedError) {
        logger.warn({ clientId: task.clientId, taskType: task.type, complexity: task.complexity, reason: error.message }, 'Task deferred by budget engine');
      } else {
        logger.error({ error: error.message, task: task.description }, 'LLM execution failed');
      }
      throw error;
    }
  }

  async classify(prompt: string, clientId: string, module: ModuleName, purpose: string): Promise<string> {
    const response = await this.execute(
      { clientId, type: TaskType.CLASSIFICATION, complexity: TaskComplexity.LOW, expectedOutputTokens: 100, description: `[${module}] ${purpose}` },
      'You are a precise classifier. Respond with only the classification label, no explanation.',
      prompt,
    );
    return response.content.trim();
  }

  async extractJson<T>(prompt: string, clientId: string, module: ModuleName, purpose: string, complexity: TaskComplexity = TaskComplexity.LOW): Promise<T> {
    const response = await this.execute(
      { clientId, type: TaskType.EXTRACTION, complexity, expectedOutputTokens: 1000, description: `[${module}] ${purpose}` },
      'You are a precise data extractor. Always respond with valid JSON only. No markdown fences.',
      prompt,
    );
    return parseJsonFromLlm<T>(response.content);
  }

  async score(prompt: string, clientId: string, module: ModuleName, purpose: string): Promise<number> {
    const response = await this.execute(
      { clientId, type: TaskType.SCORING, complexity: TaskComplexity.LOW, expectedOutputTokens: 50, description: `[${module}] ${purpose}` },
      'You are a precise scorer. Respond with only a number between 0 and 100, no explanation.',
      prompt,
    );
    return parseScore(response.content);
  }

  async generateContent(
    systemPrompt: string,
    userPrompt: string,
    clientId: string,
    module: ModuleName,
    purpose: string,
    complexity: TaskComplexity = TaskComplexity.MEDIUM,
  ): Promise<string> {
    const response = await this.execute(
      { clientId, type: TaskType.CONTENT_GENERATION, complexity, expectedOutputTokens: 3000, description: `[${module}] ${purpose}` },
      systemPrompt,
      userPrompt,
    );
    return response.content;
  }

  async strategize(
    systemPrompt: string,
    userPrompt: string,
    clientId: string,
    module: ModuleName,
    purpose: string,
    complexity: TaskComplexity = TaskComplexity.HIGH,
  ): Promise<string> {
    const response = await this.execute(
      { clientId, type: TaskType.STRATEGIC_REASONING, complexity, expectedOutputTokens: 4000, requiresReasoning: true, description: `[${module}] ${purpose}` },
      systemPrompt,
      userPrompt,
    );
    return response.content;
  }

  async research(
    prompt: string,
    clientId: string,
    module: ModuleName,
    purpose: string,
    taskType: TaskType = TaskType.COMPETITOR_RESEARCH,
    complexity: TaskComplexity = TaskComplexity.MEDIUM,
    options?: { domainFilter?: string[]; consensus?: boolean },
  ): Promise<LLMResponse> {
    return this.execute(
      { clientId, type: taskType, complexity, requiresSearch: true, domainFilter: options?.domainFilter, description: `[${module}] ${purpose}` },
      'You are an expert SEO researcher. Provide factual, citation-backed answers.',
      prompt,
      { consensus: options?.consensus },
    );
  }

  async checkCitation(query: string, clientId: string, targetDomain: string): Promise<LLMResponse> {
    return this.execute(
      { clientId, type: TaskType.CITATION_CHECK, complexity: TaskComplexity.MEDIUM, requiresSearch: true, description: `[aeo-geo] Citation check: "${query}" -> ${targetDomain}` },
      'Answer the following question naturally and thoroughly. Cite your sources.',
      query,
    );
  }

  async analyzeScreenshot(
    prompt: string,
    imageUrls: string[],
    clientId: string,
    module: ModuleName,
    purpose: string,
    complexity: TaskComplexity = TaskComplexity.MEDIUM,
  ): Promise<string> {
    const response = await this.execute(
      { clientId, type: TaskType.LAYOUT_VALIDATION, complexity, images: imageUrls, description: `[${module}] ${purpose}` },
      'You are a professional web designer and UX expert. Analyze the screenshot for layout issues, misalignment, broken elements, and visual quality.',
      prompt,
      { images: imageUrls },
    );
    return response.content;
  }

  planVisualQA(config: FullSiteQAConfig): VisualQATask[] { return this.router.planVisualQA(config); }

  async call(request: {
    tier: LegacyTier;
    systemPrompt: string;
    userPrompt: string;
    clientId: string;
    module: ModuleName;
    purpose: string;
    maxTokens?: number;
    temperature?: number;
    responseFormat?: 'text' | 'json';
  }): Promise<{ content: string; inputTokens: number; outputTokens: number; cost: number; model: string }> {
    const response = await this.execute(
      {
        clientId: request.clientId,
        type: request.responseFormat === 'json' ? TaskType.EXTRACTION : TaskType.CONTENT_GENERATION,
        complexity: tierToComplexity(request.tier),
        expectedOutputTokens: request.maxTokens,
        description: `[${request.module}] ${request.purpose}`,
      },
      request.systemPrompt,
      request.userPrompt,
    );
    return { content: response.content, inputTokens: response.inputTokens, outputTokens: response.outputTokens, cost: response.cost, model: response.model };
  }

  async initClient(clientId: string, budgetOverrides?: Partial<BudgetConfig>): Promise<void> {
    await this.router.initClient(clientId, budgetOverrides);
    logger.info({ clientId, overrides: budgetOverrides }, 'Client initialized in persistent LLM budget ledger');
  }

  getClientBudgetReport(clientId: string) { return this.router.getClientBudgetReportAsync(clientId); }
  getAllBudgetReports() { return this.router.getAllBudgetReportsAsync(); }
  getGlobalSpend() { return this.router.getGlobalSpendAsync(); }

  private async enforceDailyCap(task: TaskDescriptor): Promise<void> {
    const cap = getConfig().DAILY_SPEND_CAP;
    if (!cap || cap <= 0) return;
    const spent = await this.getDailySpend();
    if (spent >= cap) {
      logger.warn({ clientId: task.clientId, spent, cap }, 'Daily LLM spend cap reached; deferring task');
      throw new DailyBudgetExhaustedError(`Daily LLM spend cap reached ($${spent.toFixed(2)} >= $${cap.toFixed(2)})`);
    }
  }

  async getDailySpend(): Promise<number> {
    try {
      const { gte, sql } = await import('drizzle-orm');
      const db = getDb();
      const todayStart = new Date();
      todayStart.setUTCHours(0, 0, 0, 0);
      const result = await db
        .select({ totalCost: sql<number>`COALESCE(SUM(${schema.llmUsage.cost}), 0)` })
        .from(schema.llmUsage)
        .where(gte(schema.llmUsage.timestamp, todayStart));
      return Number(result[0]?.totalCost ?? 0);
    } catch (error: any) {
      logger.warn({ error: error.message }, 'getDailySpend DB query failed, falling back to in-memory call log');
      const today = new Date().toISOString().slice(0, 10);
      return this.router.getCallLog(Number.MAX_SAFE_INTEGER)
        .filter(entry => {
          const date = new Date(entry.timestamp);
          return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === today;
        })
        .reduce((sum, entry) => sum + (entry.actualCost ?? 0), 0);
    }
  }

  getCallLog(limit = 100): RoutingDecision[] { return this.router.getCallLog(limit); }
  getCallLogByClient(clientId: string, limit = 50): RoutingDecision[] { return this.router.getCallLogByClient(clientId, limit); }

  private async logUsage(task: TaskDescriptor, response: LLMResponse): Promise<void> {
    try {
      await getDb().insert(schema.llmUsage).values({
        clientId: task.clientId,
        module: this.extractModule(task.description),
        tier: this.inferTier(task.complexity),
        purpose: task.description ?? 'unspecified',
        inputTokens: response.inputTokens,
        outputTokens: response.outputTokens,
        cost: response.cost,
      });
    } catch (error: any) {
      logger.warn({ error: error.message }, 'Failed to log LLM usage to database');
    }
  }

  private extractModule(description?: string): string {
    if (!description) return 'unknown';
    return description.match(/\[([^\]]+)\]/)?.[1] ?? 'unknown';
  }

  private inferTier(complexity: TaskComplexity): string {
    if (complexity === TaskComplexity.TRIVIAL || complexity === TaskComplexity.LOW) return 'fast';
    if (complexity === TaskComplexity.MEDIUM) return 'standard';
    return 'strategic';
  }
}

let _llmService: LlmService | null = null;
export function getLlmService(): LlmService {
  if (!_llmService) _llmService = new LlmService();
  return _llmService;
}

export { TaskType, TaskComplexity, BudgetExhaustedError } from '@quantum-l9/llm-router';
export type { TaskDescriptor, LLMResponse, RoutingDecision } from '@quantum-l9/llm-router';
export type { FullSiteQAConfig, VisualQATask } from '@quantum-l9/llm-router/vision';
