import type { ApplyQueueItem, MappedField } from '@/types/apply'
import { scoreColor } from '@/lib/scoreColor'
import { getSkillVariant } from '@/components/experience/skillTagHelper'
import { CompanyLogo } from '@/components/common/CompanyLogo'
import { sourceLabel } from '@/lib/sources'

function hasUnresolvedKnockouts(fields: MappedField[]): boolean {
  return fields.some(f => f.field.is_knockout && f.value === null)
}

interface FieldMapReviewProps {
  item: ApplyQueueItem
  onApprove: () => void
  onSkip: () => void
  isApproving: boolean
}

export function FieldMapReview({ item, onApprove, onSkip, isApproving }: FieldMapReviewProps) {
  const { job, field_map, application } = item
  const confidence = field_map?.overall_confidence ?? application.apply_confidence

  const titleSkills = job.title
    .split(/[\s,/&]+/)
    .filter(w => w.length > 2)
    .slice(0, 4)

  const blocked = field_map !== null && hasUnresolvedKnockouts(field_map.fields)
  const canApprove = !blocked && !isApproving

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden h-full flex flex-col">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border flex items-start gap-3">
        <CompanyLogo company={job.company} size="md" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-foreground">{job.company}</span>
            <span className="source-pill">{sourceLabel(job.source)}</span>
            <span className={`chip ${scoreColor(confidence)}`}>
              {Math.round(confidence * 100)}%
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">{job.title}</p>
          <div className="flex flex-wrap gap-1 mt-1.5">
            {titleSkills.map(skill => (
              <span key={skill} className={`skill-tag ${getSkillVariant(skill)}`}>
                {skill}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Field list */}
      <div className="flex-1 overflow-y-auto p-4 space-y-1.5">
        {field_map === null ? (
          <p className="text-sm text-muted-foreground text-center py-8">No field map yet</p>
        ) : (
          <>
            <p className="text-xs text-muted-foreground font-medium mb-2">
              What we&apos;ll submit — confirm the amber fields
            </p>
            {field_map.fields.map(mf => {
              const isKnockout = mf.field.is_knockout
              const isMissing = mf.value === null

              if (isKnockout) {
                return (
                  <div
                    key={mf.field.name}
                    className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-semibold text-amber-700">
                          {mf.field.label} ⚲
                        </p>
                        <p className="text-sm text-foreground mt-0.5">
                          {isMissing
                            ? <span className="text-amber-600 italic">needs your input</span>
                            : mf.value}
                        </p>
                        <p className="text-xs text-amber-600 mt-0.5">
                          Knockout — pinned, never auto-guessed
                        </p>
                      </div>
                      {!isMissing && (
                        <span className={`chip ${scoreColor(mf.confidence)} shrink-0`}>
                          {Math.round(mf.confidence * 100)}%
                        </span>
                      )}
                    </div>
                  </div>
                )
              }

              return (
                <div
                  key={mf.field.name}
                  className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg hover:bg-muted"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-muted-foreground">{mf.field.label}</p>
                    <p className="text-sm text-foreground">
                      {mf.value ?? <span className="text-muted-foreground">—</span>}
                    </p>
                  </div>
                  <span className={`chip ${scoreColor(mf.confidence)} shrink-0`}>
                    {Math.round(mf.confidence * 100)}%
                  </span>
                </div>
              )
            })}
          </>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-border flex items-center justify-between gap-2">
        <button className="btn btn-ghost text-xs" onClick={onSkip} disabled={isApproving}>
          Skip
        </button>
        <div className="flex items-center gap-2">
          {blocked && (
            <span className="text-xs text-amber-600">Resolve knockout fields to approve</span>
          )}
          <button
            className="btn btn-primary text-xs"
            onClick={onApprove}
            disabled={!canApprove}
          >
            {isApproving ? 'Approving…' : 'Approve & submit'}
          </button>
        </div>
      </div>
    </div>
  )
}
