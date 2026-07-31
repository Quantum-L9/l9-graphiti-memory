// L9_META: layer=stage, role=handoff_emitter, stage_index=16, status=active, version=5.0.0
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';
import { stringify } from 'yaml';
import { createModuleLogger } from '../core/logger.js';
import { BuildError } from '../pipeline/BuildError.js';
import type { BuildContext } from '../pipeline/BuildContext.js';
import type { Stage } from '../pipeline/PipelineRunner.js';
import type { StageCheckpoint } from '../pipeline/StageCheckpoint.js';
import { validateSeoBotRegistrationAck, type SeoBotRegistrationAck } from '../contracts/SeoBotRegistrationAck.js';
import { buildWebsiteFactoryHandoffV3, type WebsiteFactoryHandoffV3 } from '../contracts/WebsiteFactoryHandoffV3.js';
import { recordWebsiteRelease } from '../services/memory.js';

const logger = createModuleLogger('stage:handoff-emitter');
const CONVENIENCE_OUTPUT_PATH = 'contracts/website_factory_integration.yaml';
const CONVENIENCE_ACK_PATH = 'contracts/website_factory_registration_ack.json';

function assertAcknowledgement(ack: SeoBotRegistrationAck, expected: WebsiteFactoryHandoffV3): void {
  validateSeoBotRegistrationAck(ack);
  if (ack.client_id !== expected.client.id) throw new Error('SEO-Bot acknowledged a different client');
  if (ack.contract_id !== expected.contract_id) throw new Error('SEO-Bot acknowledged a different contract_id');
  if (ack.contract_digest !== expected.integrity.payload_digest) throw new Error('SEO-Bot acknowledged a different contract digest');
  if (ack.release_receipt_id !== expected.proof.receipt_id) throw new Error('SEO-Bot acknowledged a different release receipt');
  if (ack.verified_repository !== expected.site.repository.full_name) throw new Error('SEO-Bot verified a different repository');
  if (ack.verified_branch !== expected.site.repository.branch) throw new Error('SEO-Bot verified a different branch');
  if (ack.verified_commit_sha !== expected.site.repository.commit_sha) throw new Error('SEO-Bot verified a different commit');
}

export class HandoffEmitterStage implements Stage {
  name = 'handoff-emitter';
  version = '5.0.0';
  evidence = {
    inputs: (_ctx: BuildContext) => ['assembly' as const, 'build' as const, 'publication' as const, 'deployment' as const, 'release' as const],
    outputs: (ctx: BuildContext) => ctx.autoRegisterSeoBot ? ['handoff' as const, 'registration_ack' as const] : ['handoff' as const],
    resumable: true,
    externalMutation: true,
  };

  constructor(
    private readonly fetchImpl: typeof fetch = fetch,
    private readonly outputPath = CONVENIENCE_OUTPUT_PATH,
    private readonly ackPath = CONVENIENCE_ACK_PATH,
  ) {}

  async canResume(ctx: BuildContext, _checkpoint: StageCheckpoint): Promise<boolean> {
    const handoff = await ctx.evidenceStore.readHandoff();
    if (!handoff) return false;
    const bundle = await ctx.evidenceStore.loadValidatedReleaseBundle({ requireStatus: 'succeeded', requireMode: 'end-to-end' });
    if (handoff.proof.receipt_id !== bundle.releaseReceipt.receipt_id || handoff.site.repository.commit_sha !== bundle.publicationEvidence?.commitSha) return false;
    if (!ctx.autoRegisterSeoBot) return true;
    const acknowledgement = await ctx.evidenceStore.readRegistrationAck();
    if (!acknowledgement) return false;
    try { assertAcknowledgement(acknowledgement, handoff); return true; } catch { return false; }
  }

  async run(ctx: BuildContext): Promise<void> {
    if (ctx.dryRun) {
      logger.info({ path: this.outputPath }, '[dry-run] Would emit a canonical v3 handoff from persisted release evidence');
      return;
    }
    if (ctx.mode !== 'end-to-end' || !ctx.deployTarget) {
      throw new BuildError('HANDOFF_EMIT_FAILED', 'Canonical v3 handoff requires end-to-end mode and a deploy target');
    }

    let bundle;
    try {
      bundle = await ctx.evidenceStore.loadValidatedReleaseBundle({ requireStatus: 'succeeded', requireMode: 'end-to-end' });
    } catch (error) {
      throw new BuildError('EVIDENCE_CHAIN_INVALID', `Handoff release bundle validation failed: ${error instanceof Error ? error.message : String(error)}`);
    }

    let contract: WebsiteFactoryHandoffV3;
    try {
      contract = buildWebsiteFactoryHandoffV3({
        domainSpec: ctx.domainSpec,
        clientId: ctx.clientId,
        buildId: ctx.buildId,
        releaseBundle: bundle,
        deployTarget: ctx.deployTarget,
        qualitySummary: { seoBaseline: bundle.releaseReceipt.qa.seo_baseline, visualQa: bundle.releaseReceipt.qa.visual_qa },
      });
    } catch (error) {
      throw new BuildError('HANDOFF_EMIT_FAILED', `Canonical v3 handoff could not be built: ${error instanceof Error ? error.message : String(error)}`);
    }

    const handoffRecord = await ctx.evidenceStore.writeHandoff(contract);
    mkdirSync(dirname(this.outputPath), { recursive: true });
    const header = `# Convenience copy only. Authoritative evidence: ${ctx.evidenceStore.rootDir}/${handoffRecord.relativePath}\n`;
    writeFileSync(this.outputPath, `${header}${stringify(contract)}`, 'utf-8');
    logger.info({ contractId: contract.contract_id, evidencePath: handoffRecord.relativePath }, 'Canonical v3 handoff persisted');

    await recordWebsiteRelease(
      contract,
      ctx.domainSpec.routes.map(route => ({ path: route.path, title: route.title })),
    );

    if (!ctx.autoRegisterSeoBot) {
      logger.info('SEO-Bot auto-registration disabled; handoff evidence emitted without activation');
      return;
    }

    const seoBotUrl = process.env.SEO_BOT_URL?.replace(/\/+$/, '');
    const seoBotKey = process.env.SEO_BOT_API_KEY;
    if (!seoBotUrl || !seoBotKey) {
      throw new BuildError('HANDOFF_EMIT_FAILED', 'SEO_BOT_URL and SEO_BOT_API_KEY are required when auto-registration is enabled');
    }

    let response: Response;
    try {
      response = await this.fetchImpl(`${seoBotUrl}/api/clients/register`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${seoBotKey}`, 'Content-Type': 'application/json', 'Idempotency-Key': contract.contract_id },
        body: JSON.stringify(contract),
        signal: AbortSignal.timeout(20_000),
      });
    } catch (error) {
      throw new BuildError('HANDOFF_EMIT_FAILED', `SEO-Bot registration request failed: ${error instanceof Error ? error.message : String(error)}`);
    }

    const raw = await response.text();
    if (!response.ok) throw new BuildError('HANDOFF_EMIT_FAILED', `SEO-Bot rejected canonical handoff (${response.status}): ${raw.slice(0, 2_000)}`);

    let acknowledgement: SeoBotRegistrationAck;
    try {
      acknowledgement = JSON.parse(raw) as SeoBotRegistrationAck;
      assertAcknowledgement(acknowledgement, contract);
    } catch (error) {
      throw new BuildError('HANDOFF_ACK_MISMATCH', `SEO-Bot acknowledgement validation failed: ${error instanceof Error ? error.message : String(error)}`);
    }

    const ackRecord = await ctx.evidenceStore.writeRegistrationAck(acknowledgement);
    mkdirSync(dirname(this.ackPath), { recursive: true });
    writeFileSync(this.ackPath, `${JSON.stringify({ authoritative_evidence: `${ctx.evidenceStore.rootDir}/${ackRecord.relativePath}`, ...acknowledgement }, null, 2)}\n`, 'utf-8');
    logger.info({ clientId: acknowledgement.client_id, contractId: acknowledgement.contract_id, commitSha: acknowledgement.verified_commit_sha }, 'SEO-Bot maintenance readiness confirmed');
  }
}
