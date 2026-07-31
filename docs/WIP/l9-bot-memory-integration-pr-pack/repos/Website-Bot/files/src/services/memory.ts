// L9_META: layer=service, role=governed_memory_adapter, status=active, version=1.0.0
import {
  GraphitiMemoryClient,
  renderHydration,
  type MemoryClass,
  type WriteReceipt,
} from '@quantum-l9/graphiti-memory-client';
import type { WebsiteFactoryHandoffV3 } from '@quantum-l9/bot-interop';
import { createModuleLogger } from '../core/logger.js';

const logger = createModuleLogger('service:memory');
type MemoryMode = 'disabled' | 'optional' | 'required';

let client: GraphitiMemoryClient | null | undefined;

function mode(): MemoryMode {
  const value = process.env.L9_MEMORY_MODE ?? 'optional';
  if (value === 'disabled' || value === 'optional' || value === 'required') return value;
  throw new Error('L9_MEMORY_MODE must be disabled, optional, or required');
}

function getClient(): GraphitiMemoryClient | null {
  if (client !== undefined) return client;
  if (mode() === 'disabled') return (client = null);
  const baseUrl = process.env.L9_MEMORY_URL;
  const bearerToken = process.env.L9_MEMORY_TOKEN;
  if (!baseUrl || !bearerToken) {
    if (mode() === 'required') throw new Error('L9_MEMORY_URL and L9_MEMORY_TOKEN are required');
    logger.warn('Governed memory is not configured; continuing without hydration or promotion');
    return (client = null);
  }
  client = new GraphitiMemoryClient({ baseUrl, bearerToken });
  return client;
}

async function guarded<T>(operation: string, fn: (memory: GraphitiMemoryClient) => Promise<T>): Promise<T | undefined> {
  const memory = getClient();
  if (!memory) return undefined;
  try {
    return await fn(memory);
  } catch (error) {
    if (mode() === 'required') throw error;
    logger.warn({ operation, error: error instanceof Error ? error.message : String(error) }, 'Governed memory operation failed');
    return undefined;
  }
}

export async function hydrateWebsiteContext(
  clientId: string,
  taskType: string,
  task: string,
  topics: string[] = [],
  memoryClasses?: MemoryClass[],
): Promise<string> {
  const result = await guarded('hydrate', memory => memory.hydrate({
    clientId,
    taskType,
    task,
    topics,
    memoryClasses,
    tokenBudget: Number(process.env.L9_MEMORY_TOKEN_BUDGET ?? 1_200),
    maxRecords: Number(process.env.L9_MEMORY_MAX_RECORDS ?? 40),
  }));
  return result ? renderHydration(result) : '';
}

export async function recordWebsiteRelease(
  contract: WebsiteFactoryHandoffV3,
  routes: Array<{ path: string; title: string }>,
): Promise<WriteReceipt | undefined> {
  return guarded('write-release', memory => memory.writeSemanticFact({
    clientId: contract.client.id,
    sourceId: `website-release:${contract.proof.receipt_id}`,
    idempotencyKey: `website-release:${contract.proof.receipt_id}`,
    content: JSON.stringify({
      kind: 'website_release',
      domain: contract.client.domain,
      repository: contract.site.repository.full_name,
      branch: contract.site.repository.branch,
      commit_sha: contract.site.repository.commit_sha,
      deployment_url: contract.site.deployment.deployment_url,
      source_digest: contract.proof.source_digest,
      dist_digest: contract.proof.dist_digest,
      routes,
    }),
    subject: contract.client.domain,
    predicate: 'deployed_release_commit',
    object: contract.site.repository.commit_sha,
    tags: ['website-bot', 'release', 'deployment', 'content-inventory'],
  }));
}
