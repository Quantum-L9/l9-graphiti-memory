// L9_META: layer=contract, role=website_factory_handoff_builder, status=active, version=4.0.0
import type { DeployTarget, DomainSpec, QualityEvidence } from '../pipeline/BuildContext.js';
import type { ValidatedReleaseBundle } from '../pipeline/evidence/ValidatedReleaseBundle.js';
import {
  DEFAULT_MANAGED_MANIFEST_PATH,
  DEFAULT_REQUIRED_PATHS,
  WEBSITE_FACTORY_HANDOFF_PROTOCOL,
  WEBSITE_FACTORY_HANDOFF_VERSION,
  assertWebsiteFactoryHandoffV3,
  canonicalJson,
  digestHandoffPayload,
  sealWebsiteFactoryHandoff,
  type KeywordPriority,
  type WebsiteFactoryHandoffPayload,
  type WebsiteFactoryHandoffV3,
} from '@quantum-l9/bot-interop';

export {
  DEFAULT_MANAGED_MANIFEST_PATH,
  DEFAULT_REQUIRED_PATHS,
  WEBSITE_FACTORY_HANDOFF_PROTOCOL,
  WEBSITE_FACTORY_HANDOFF_VERSION,
  assertWebsiteFactoryHandoffV3,
  canonicalJson,
  digestHandoffPayload,
  type KeywordPriority,
  type WebsiteFactoryHandoffV3,
};

export interface WebsiteFactoryHandoffBuildInput {
  domainSpec: DomainSpec;
  clientId: string;
  buildId: string;
  releaseBundle: ValidatedReleaseBundle;
  deployTarget: DeployTarget;
  qualitySummary: QualityEvidence;
  emittedAt?: string;
}

function hostnameOf(url: string): string {
  return new URL(url).hostname.replace(/^www\./, '').toLowerCase();
}

function keywordPriority(value: unknown): KeywordPriority {
  return value === 'critical' || value === 'high' || value === 'low' ? value : 'medium';
}

function buildTargetKeywords(spec: DomainSpec): Array<{ keyword: string; priority: KeywordPriority }> {
  const raw = (spec.seo_contract as { target_keywords?: unknown } | undefined)?.target_keywords;
  if (Array.isArray(raw)) {
    const values = raw.flatMap((item): Array<{ keyword: string; priority: KeywordPriority }> => {
      if (typeof item === 'string' && item.trim()) return [{ keyword: item.trim(), priority: 'medium' }];
      if (!item || typeof item !== 'object') return [];
      const keyword = (item as { keyword?: unknown }).keyword;
      if (typeof keyword !== 'string' || !keyword.trim()) return [];
      return [{ keyword: keyword.trim(), priority: keywordPriority((item as { priority?: unknown }).priority) }];
    });
    if (values.length > 0) return values;
  }
  return spec.routes.map(route => ({ keyword: `${route.title} ${spec.geography.primary_state}`.trim(), priority: 'medium' }));
}

function buildCompetitorUrls(spec: DomainSpec): string[] {
  const raw = (spec.seo_contract as { competitor_urls?: unknown } | undefined)?.competitor_urls;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((value): string[] => {
    if (typeof value !== 'string') return [];
    try { return [new URL(value).toString()]; } catch { return []; }
  });
}

function requiredString(value: string | undefined, field: string): string {
  if (!value?.trim()) throw new Error(`${field} is required for the v3 handoff`);
  return value.trim();
}

export function buildWebsiteFactoryHandoffV3(input: WebsiteFactoryHandoffBuildInput): WebsiteFactoryHandoffV3 {
  const {
    domainSpec,
    clientId,
    buildId,
    releaseBundle,
    deployTarget,
    qualitySummary,
    emittedAt = new Date().toISOString(),
  } = input;
  const buildProof = releaseBundle.buildProof;
  const publication = releaseBundle.publicationEvidence;
  const deployment = releaseBundle.deploymentEvidence;
  const receipt = releaseBundle.releaseReceipt;

  if (!releaseBundle.validation.valid) throw new Error('v3 handoff requires a valid release evidence bundle');
  if (releaseBundle.index.mode !== 'end-to-end') throw new Error('v3 handoff requires end-to-end evidence mode');
  if (!buildProof || !publication || !deployment) throw new Error('v3 handoff requires build, publication, and deployment evidence');
  if (receipt.status !== 'succeeded' || receipt.missing_gates.length > 0) throw new Error('release receipt is not complete');
  if (qualitySummary.visualQa !== 'passed' || receipt.qa.visual_qa !== 'passed') throw new Error('v3 handoff requires passed visual QA');
  if (clientId !== releaseBundle.index.client_id || buildId !== releaseBundle.index.build_id) throw new Error('handoff identity differs from the release bundle');
  if (domainSpec.client_id !== clientId) throw new Error('DomainSpec client identity differs from the release bundle');

  const githubCredentialRef = deployTarget.seoBotGithubCredentialRef
    ?? process.env.SEO_BOT_SITE_GITHUB_CREDENTIAL_REF
    ?? 'env://SEO_BOT_SITE_GITHUB_TOKEN';
  const deployHookRef = deployTarget.seoBotVercelDeployHookRef ?? process.env.SEO_BOT_SITE_VERCEL_HOOK_REF;
  const deploymentUrl = requiredString(deployment.deploymentUrl, 'deployment.deploymentUrl');
  const vercelProjectId = requiredString(deployment.projectId, 'deployment.projectId');
  const city = (domainSpec.seo_contract as { city?: unknown } | undefined)?.city;

  const payload: WebsiteFactoryHandoffPayload = {
    protocol: WEBSITE_FACTORY_HANDOFF_PROTOCOL,
    schema_version: WEBSITE_FACTORY_HANDOFF_VERSION,
    contract_id: `${clientId}:${buildId}:${publication.commitSha}`,
    emitted_at: emittedAt,
    client: {
      id: clientId,
      domain: hostnameOf(deploymentUrl),
      name: domainSpec.business_name,
      industry: domainSpec.vertical,
      ...(typeof city === 'string' && city.trim() ? { city: city.trim() } : {}),
      ...(domainSpec.geography.primary_state.length === 2 ? { state: domainSpec.geography.primary_state.toUpperCase() } : {}),
    },
    seo: {
      target_keywords: buildTargetKeywords(domainSpec),
      competitor_urls: buildCompetitorUrls(domainSpec),
    },
    site: {
      repository: {
        provider: 'github',
        full_name: publication.repository,
        ...(publication.repositoryId ? { repository_id: publication.repositoryId } : {}),
        branch: publication.branch,
        commit_sha: publication.commitSha,
        source_digest: publication.sourceDigest,
        managed_manifest_path: DEFAULT_MANAGED_MANIFEST_PATH,
        editable_root: 'src/pages',
        page_path_strategy: 'directory-index-astro',
      },
      deployment: {
        provider: 'vercel',
        project_id: vercelProjectId,
        deployment_id: deployment.deploymentId,
        deployment_url: deploymentUrl,
        state: 'READY',
        requested_commit_sha: deployment.requestedCommitSha,
        observed_commit_sha: deployment.observedCommitSha,
      },
      maintenance: {
        enabled: true,
        transport: 'github-contents-api',
        github_credential_ref: githubCredentialRef,
        ...(deployHookRef ? { vercel_deploy_hook_ref: deployHookRef } : {}),
        required_paths: [...DEFAULT_REQUIRED_PATHS],
      },
    },
    proof: {
      receipt_id: receipt.receipt_id,
      receipt_status: 'succeeded',
      source_digest: receipt.correlation.source_digest,
      dist_digest: requiredString(receipt.correlation.dist_digest, 'receipt.correlation.dist_digest'),
      local_build_status: 'passed',
      publication_status: 'passed',
      deployment_status: 'passed',
    },
  };
  return sealWebsiteFactoryHandoff(payload);
}
