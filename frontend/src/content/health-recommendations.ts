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
      'CDC guidance emphasizes regular physical activity, maintaining a healthy weight, quitting smoking, and drinking less alcohol to help lower heart disease risk.',
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
      'CDC states that the best way to prevent COPD is to never start smoking. If you smoke, quitting is the most important action you can take, and avoiding secondhand smoke also helps reduce risk.',
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
      'CDC recommends healthy eating, regular physical activity, quitting smoking, maintaining a healthy weight, and limiting alcohol intake to help reduce stroke risk.',
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
      'CDC guidance on emotional well-being highlights stress management, self-care, and seeking support when stress, sadness, or depressed mood become difficult to manage.',
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
      'CDC states that type 2 diabetes can often be prevented or delayed through achievable lifestyle changes such as modest weight loss, healthier eating, and more physical activity.',
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
}
