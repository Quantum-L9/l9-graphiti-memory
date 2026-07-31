import { GraphitiMemoryClient, renderHydration, type MemoryClass } from '@quantum-l9/graphiti-memory-client';

export interface RouterMemoryConfig {
  client: GraphitiMemoryClient;
  mode?: 'optional' | 'required';
  tokenBudget?: number;
  maxRecords?: number;
  memoryClasses?: MemoryClass[];
}
export async function hydrateRouterPrompt(config: RouterMemoryConfig | undefined, clientId: string, taskType: string, userPrompt: string): Promise<string> {
  if (!config) return '';
  try {
    const result = await config.client.hydrate({ clientId, taskType, task:userPrompt, tokenBudget:config.tokenBudget, maxRecords:config.maxRecords, memoryClasses:config.memoryClasses });
    return renderHydration(result);
  } catch (error) {
    if ((config.mode ?? 'optional') === 'required') throw error;
    return '';
  }
}
