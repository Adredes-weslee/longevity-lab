export interface HealthRecommendationCitation {
  title: string
  url: string
}

export interface HealthRecommendation {
  recommendation: string
  title: string
  citations: HealthRecommendationCitation[]
}

export const healthRecommendations: Partial<Record<string, HealthRecommendation>> = {
  heart_disease: {
    title: 'General public-health guidance',
    recommendation:
      'CDC guidance points to practical prevention steps: move regularly, avoid smoking, keep weight in a healthy range when possible, and limit alcohol. These are general population-health steps, not personal treatment instructions.',
    citations: [
      {
        title: 'CDC: Preventing Heart Disease',
        url: 'https://www.cdc.gov/heart-disease/prevention/index.html',
      },
    ],
  },
  chronic_lung_disease: {
    title: 'General public-health guidance',
    recommendation:
      'CDC states that avoiding tobacco smoke is the most important prevention step for COPD. If someone smokes, quitting and reducing secondhand-smoke exposure are general risk-reduction steps.',
    citations: [
      {
        title: 'CDC: Health Effects of Cigarettes - COPD',
        url: 'https://www.cdc.gov/tobacco/about/cigarettes-and-copd.html',
      },
    ],
  },
  stroke: {
    title: 'General public-health guidance',
    recommendation:
      'CDC highlights everyday prevention steps for stroke risk: healthy eating, regular activity, not smoking, weight management when possible, and limiting alcohol.',
    citations: [
      {
        title: 'CDC: Preventing Stroke',
        url: 'https://www.cdc.gov/stroke/prevention/index.html',
      },
      {
        title: 'CDC: Moderate Alcohol Use',
        url: 'https://www.cdc.gov/alcohol/about-alcohol-use/moderate-alcohol-use.html',
      },
    ],
  },
  depression: {
    title: 'General public-health guidance',
    recommendation:
      'CDC emotional well-being guidance emphasizes stress management, self-care, social support, and getting help when stress, sadness, or depressed mood becomes hard to manage.',
    citations: [
      {
        title: 'CDC: Managing Stress',
        url: 'https://www.cdc.gov/mental-health/living-with/index.html',
      },
      {
        title: 'CDC: Tips to Improve Emotional Well-Being',
        url: 'https://www.cdc.gov/howrightnow/wellbeing/index.html',
      },
    ],
  },
  diabetes: {
    title: 'General public-health guidance',
    recommendation:
      'CDC states that type 2 diabetes can often be delayed or prevented through realistic lifestyle changes, including healthier eating, more activity, and modest weight loss for people who would benefit from it.',
    citations: [
      {
        title: 'CDC: Preventing Type 2 Diabetes',
        url: 'https://www.cdc.gov/diabetes/prevention-type-2/index.html',
      },
      {
        title: 'CDC: On Your Way to Preventing Type 2 Diabetes',
        url: 'https://www.cdc.gov/diabetes/prevention-type-2/type-2-diabetes-prevention-guide.html',
      },
    ],
  },
  asthma: {
    title: 'General public-health guidance',
    recommendation:
      'CDC asthma guidance emphasizes knowing personal triggers, reducing smoke exposure, and following a clinician-provided asthma action plan. This app only communicates modeled risk patterns.',
    citations: [
      {
        title: 'CDC: Asthma',
        url: 'https://www.cdc.gov/asthma/',
      },
    ],
  },
  kidney_disease: {
    title: 'General public-health guidance',
    recommendation:
      'CDC kidney disease guidance emphasizes managing diabetes and blood pressure risks, not smoking, and discussing kidney testing with a clinician when risk is elevated.',
    citations: [
      {
        title: 'CDC: Chronic Kidney Disease',
        url: 'https://www.cdc.gov/kidney-disease/',
      },
    ],
  },
  arthritis: {
    title: 'General public-health guidance',
    recommendation:
      'CDC arthritis guidance highlights physical activity, weight management where appropriate, self-management education, and joint-injury prevention as general public-health steps.',
    citations: [
      {
        title: 'CDC: Arthritis',
        url: 'https://www.cdc.gov/arthritis/',
      },
    ],
  },
}
