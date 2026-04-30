import type { JSX } from 'react'

import type { ScenarioEvaluationResponse } from '../types'

interface SummaryCardProps {
  title: string
  evaluation: ScenarioEvaluationResponse | null
  testId?: string
}

export function SummaryCard({
  title,
  evaluation,
  testId,
}: SummaryCardProps): JSX.Element {
  return (
    <section className="panel summary-panel" data-testid={testId}>
      <div className="panel-header">
        <h2>{title}</h2>
        <p>Average organ-risk score across the current condition set.</p>
      </div>
      {evaluation ? (
        <>
          <strong className="summary-score">{evaluation.summary_score.toFixed(1)}</strong>
          <ul className="mini-list">
            {evaluation.organs.map((organ) => (
              <li key={organ.organ_id}>
                <span>{organ.label}</span>
                <span>{(organ.score * 100).toFixed(1)}%</span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="muted">No evaluation loaded yet.</p>
      )}
    </section>
  )
}
