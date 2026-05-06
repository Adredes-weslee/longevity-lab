export interface DisclaimerCopy {
  title: string
  body: string
  bullets?: string[]
}

export const disclaimers = {
  prediction: {
    title: 'Educational use only',
    body:
      'Longevity Lab is a non-diagnostic risk-communication tool. Scores are model estimates for scenario comparison, not medical advice, diagnosis, screening, or treatment guidance.',
  },
  publicHealthGuidance: {
    title: 'Public-health guidance',
    body:
      'Linked guidance is general public-health information from cited sources. It is not personalized medical advice and should not replace a clinician or emergency care.',
  },
  context: {
    title: 'Context features',
    body:
      'Geography and environmental fields describe background state-year context where available. They are not personal behaviors and should not be interpreted as individual-level causal effects.',
  },
  uncertainty: {
    title: 'Model uncertainty',
    body:
      'Uncertainty summaries communicate model reliability limits for the active artifact. They are not clinical confidence intervals and may be unavailable for some conditions.',
  },
  causal: {
    title: 'Causal reports',
    body:
      'Causal workbench outputs are offline research artifacts with explicit assumptions and diagnostics. Explorer what-if deltas remain predictive comparisons, not causal claims.',
  },
  dataLimitations: {
    title: 'Data limitations',
    body:
      'Inputs and labels are derived from public survey, environmental, and contextual datasets. Self-reporting bias, missing data, aggregation, and subgroup coverage can affect estimates.',
  },
  intendedUse: {
    title: 'Intended use',
    body:
      'Use this app to inspect model provenance and compare broad risk patterns. Do not use it for clinical decisions, insurance/employment decisions, or individual eligibility decisions.',
  },
} satisfies Record<string, DisclaimerCopy>
