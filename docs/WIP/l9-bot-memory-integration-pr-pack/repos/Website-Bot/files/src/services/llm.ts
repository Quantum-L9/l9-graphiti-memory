// L9_META: layer=service, role=llm_adapter, status=active, version=4.0.0
import {
  BudgetExhaustedError,
  L9LLMRouter,
  TaskComplexity,
  TaskType,
  type LLMResponse,
  type TaskDescriptor,
} from '@quantum-l9/llm-router';
import { createModuleLogger } from '../core/logger.js';
import { BuildError } from '../pipeline/BuildError.js';
import { hydrateWebsiteContext } from './memory.js';

const logger = createModuleLogger('service:llm');

interface UsageRecord {
  stage: string;
  taskType: string;
  model: string;
  inputTokens: number;
  outputTokens: number;
  costUsd: number;
  recordedAt: string;
}

export interface WebsiteFactoryLLM {
  generateContent(prompt: string, context?: string): Promise<string>;
  designReasoning(prompt: string): Promise<string>;
  generateSchema(prompt: string): Promise<string>;
  recordUsage(stage: string, taskType: string, inputTokens: number, outputTokens: number, costUsd: number, model: string): void;
  flushUsage(): UsageRecord[];
}

export function createWebsiteFactoryLLM(clientId: string): WebsiteFactoryLLM {
  let router: L9LLMRouter | null = null;
  let routerReady: Promise<void> | null = null;

  async function getRouter(): Promise<L9LLMRouter> {
    if (!router) {
      const openrouterApiKey = process.env.OPENROUTER_API_KEY;
      if (!openrouterApiKey) throw new BuildError('LLM_CALL_FAILED', 'OPENROUTER_API_KEY not set');
      router = new L9LLMRouter({
        openrouterApiKey,
        perplexityApiKey: process.env.PERPLEXITY_API_KEY ?? '',
        appName: 'L9-Website-Bot',
      });
      routerReady = router.initClient(clientId);
      logger.info({ clientId }, 'LLM service initialized with @quantum-l9/llm-router');
    }
    await routerReady;
    return router;
  }

  const usageBuffer: UsageRecord[] = [];
  const record = (stage: string, taskType: string, inputTokens: number, outputTokens: number, costUsd: number, model: string) => {
    usageBuffer.push({ stage, taskType, model, inputTokens, outputTokens, costUsd, recordedAt: new Date().toISOString() });
  };

  async function run(
    task: TaskDescriptor,
    systemPrompt: string,
    userPrompt: string,
    stage: string,
    usageTaskType: string,
  ): Promise<LLMResponse> {
    try {
      const memoryContext = await hydrateWebsiteContext(
        clientId,
        task.type,
        task.description ?? usageTaskType,
        [stage, usageTaskType],
      );
      const response = await (await getRouter()).execute(
        task,
        `${systemPrompt}${memoryContext}`,
        userPrompt,
      );
      record(stage, usageTaskType, response.inputTokens, response.outputTokens, response.cost, response.model);
      return response;
    } catch (error) {
      if (error instanceof BudgetExhaustedError) throw new BuildError('LLM_CALL_FAILED', `Budget exhausted for ${stage}: ${error.message}`);
      throw new BuildError('LLM_CALL_FAILED', `Router execute failed for ${stage}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  return {
    async generateContent(prompt, context) {
      const response = await run(
        { clientId, type: TaskType.CONTENT_GENERATION, complexity: TaskComplexity.MEDIUM, expectedOutputTokens: 3000, description: '[content-generation] page_copy' },
        'You are an expert conversion copywriter for local service businesses. Write compliance-literate, SEO-optimized copy. Be direct. Never make guarantee claims.',
        context ? `${context}\n\n${prompt}` : prompt,
        'content-generation',
        'page_copy',
      );
      return response.content;
    },
    async designReasoning(prompt) {
      const response = await run(
        { clientId, type: TaskType.STRATEGIC_REASONING, complexity: TaskComplexity.HIGH, requiresReasoning: true, expectedOutputTokens: 1000, description: '[design-intelligence] design_tokens' },
        'You are a senior brand designer. Output ONLY valid JSON. No prose, no markdown fences. Keys: primary, secondary, accent, font_heading, font_body.',
        prompt,
        'design-intelligence',
        'design_tokens',
      );
      return response.content;
    },
    async generateSchema(prompt) {
      const response = await run(
        { clientId, type: TaskType.CODE_GENERATION, complexity: TaskComplexity.LOW, expectedOutputTokens: 1500, description: '[schema-generator] json_ld' },
        'You are a structured data expert. Output ONLY valid JSON-LD as raw JSON. No prose or code fences.',
        prompt,
        'schema-generator',
        'json_ld',
      );
      return response.content;
    },
    recordUsage: record,
    flushUsage() {
      const output = [...usageBuffer];
      usageBuffer.length = 0;
      return output;
    },
  };
}
