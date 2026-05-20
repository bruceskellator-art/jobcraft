const ML_KEYWORDS = ['python', 'ml', 'llm', 'rag', 'ai', 'qdrant', 'evals', 'torch', 'tensorflow', 'nlp', 'data', 'bert', 'gpt']
const FE_KEYWORDS = ['typescript', 'javascript', 'react', 'vue', 'angular', 'next', 'css', 'html', 'tailwind', 'frontend', 'ui']
const BE_KEYWORDS = ['fastapi', 'django', 'flask', 'node', 'go', 'rust', 'java', 'spring', 'postgresql', 'mysql', 'redis', 'asyncio', 'api', 'backend', 'graphql', 'grpc', 'sql']
const INFRA_KEYWORDS = ['kubernetes', 'docker', 'aws', 'gcp', 'azure', 'terraform', 'ci', 'cd', 'devops', 'k8s', 'helm', 'nginx', 'linux', 'infra', 'cloud']

export type SkillVariant = 'skill-ml' | 'skill-fe' | 'skill-be' | 'skill-infra' | 'skill-gen'

export function getSkillVariant(tag: string): SkillVariant {
  const lower = tag.toLowerCase()
  if (ML_KEYWORDS.some(kw => lower.includes(kw))) return 'skill-ml'
  if (FE_KEYWORDS.some(kw => lower.includes(kw))) return 'skill-fe'
  if (BE_KEYWORDS.some(kw => lower.includes(kw))) return 'skill-be'
  if (INFRA_KEYWORDS.some(kw => lower.includes(kw))) return 'skill-infra'
  return 'skill-gen'
}
