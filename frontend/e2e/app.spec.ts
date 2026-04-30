import { expect, test } from '@playwright/test'

test('loads the app and renders scenario compare output', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { name: 'Longevity Lab' })).toBeVisible()

  await expect(page.getByTestId('scenario-form')).toBeVisible()
  await expect(page.getByTestId('live-update-status')).toContainText('Live preview')
  await expect(page.getByTestId('explorer-disclaimer')).toBeVisible()
  await expect(page.getByTestId('explorer-disclaimer')).toContainText(
    'Educational use only',
  )
  await expect(page.getByTestId('contract-metadata')).toContainText('API v2')
  await expect(page.getByTestId('contract-metadata')).toContainText('explanations:')
  await expect(page.getByTestId('pipeline-status')).toHaveCount(0)

  await expect(page.getByTestId('overview-whatif')).toBeVisible()
  await expect(
    page.getByTestId('overview-whatif').locator('.metric-value'),
  ).toHaveText(/\d/)
  await expect(page.getByTestId('overview-regions')).toBeVisible()
  await expect(page.getByTestId('overview-changes')).toBeVisible()
  await expect(page.getByTestId('heatmap-mode-baseline')).toContainText('Current')
  await expect(page.getByTestId('heatmap-mode-scenario')).toContainText('What-if')
  await expect(page.getByTestId('heatmap-mode-delta')).toContainText('Change vs current')
  await expect(page.getByTestId('changed-input-smoker')).toContainText('Changed:')
  await expect(page.getByText('Blue: improves')).toBeVisible()

  await page.getByTestId('organ-callout-heart').click()
  await expect(page.getByTestId('condition-heart_disease')).toBeVisible()
  await expect(page.getByText('Improves vs current')).toBeVisible()
  await expect(page.getByText('Model explanation caveats')).toBeVisible()
  await expect(page.getByText(/Demo-mode heuristic contribution/i).first()).toBeVisible()

  await page.getByTestId('organ-callout-brain').focus()
  await page.keyboard.press('Enter')
  await expect(page.getByTestId('condition-stroke')).toBeVisible()

  await page.getByTestId('heatmap-mode-baseline').click()
  await expect(page.getByText('Lower current risk')).toBeVisible()

  await page.getByTestId('heatmap-mode-scenario').click()
  await expect(page.getByText('Lower what-if risk')).toBeVisible()

  await page.getByTestId('heatmap-mode-delta').click()
  await expect(page.getByText('Relative change scale')).toBeVisible()
  await expect(
    page.getByText('Blue means improved and orange means worsened relative to current'),
  ).toBeVisible()

  await page.getByRole('button', { name: 'Data evidence' }).click()
  await expect(page.getByTestId('data-evidence-page')).toBeVisible()
  await expect(page.getByTestId('pipeline-status')).toBeVisible()
  await expect(
    page.locator('[data-testid="pipeline-status"] .pipeline-status-list li').first(),
  ).toBeVisible()

  await page.getByRole('button', { name: 'Model cards' }).click()
  await expect(page.getByTestId('model-cards-page')).toBeVisible()
  await expect(page.getByText('Active scoring contract')).toBeVisible()

  await page.getByRole('button', { name: 'Scenario lab' }).click()
  await expect(page.getByTestId('scenario-lab-page')).toBeVisible()
  await expect(page.getByText('Current what-if comparison')).toBeVisible()
})

test('clamps invalid numeric input to the supported feature range', async ({ page }) => {
  await page.goto('/')

  const ageInput = page.getByLabel('What-if Age number input')
  await ageInput.fill('150')
  await ageInput.blur()

  await expect(ageInput).toHaveValue('100')
})

test('updates results live when the what-if profile changes', async ({ page }) => {
  await page.goto('/')

  const scenarioScore = await page
    .getByTestId('overview-whatif')
    .locator('.metric-value')
    .textContent()

  const ageInput = page.getByLabel('What-if Age number input')
  await ageInput.fill('80')
  await ageInput.blur()

  await expect(page.getByTestId('overview-whatif').locator('.metric-value')).not.toHaveText(
    scenarioScore ?? '',
  )
})

test('keeps the last good results visible when a live comparison fails', async ({ page }) => {
  await page.goto('/')

  await expect(
    page.getByTestId('overview-whatif').locator('.metric-value'),
  ).toHaveText(/\d/, { timeout: 15000 })

  const previousScore =
    (await page.getByTestId('overview-whatif').locator('.metric-value').textContent()) ?? ''

  await page.route('**/api/scenario/compare', async (route) => {
    await route.fulfill({
      status: 500,
      body: 'forced failure',
      contentType: 'text/plain',
    })
  })

  const ageInput = page.getByLabel('What-if Age number input')
  await ageInput.fill('80')
  await ageInput.blur()

  await expect(page.locator('.error-banner')).toBeVisible()
  await expect(page.getByTestId('overview-whatif').locator('.metric-value')).toHaveText(
    previousScore,
  )
})

test('shows CDC-backed guidance when a selected organ is in the high-risk band', async ({ page }) => {
  await page.route('**/api/scenario/compare', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        baseline: {
          summary_score: 32.4,
          organs: [
            { organ_id: 'heart', label: 'Heart', score: 0.386, band: 'red', top_conditions: ['Heart disease'] },
            { organ_id: 'lungs', label: 'Lungs', score: 0.479, band: 'red', top_conditions: ['Chronic lung disease'] },
            { organ_id: 'brain', label: 'Brain', score: 0.211, band: 'amber', top_conditions: ['Stroke', 'Depression'] },
            { organ_id: 'pancreas', label: 'Pancreas', score: 0.220, band: 'amber', top_conditions: ['Diabetes'] },
          ],
          conditions: [
            { condition_id: 'heart_disease', label: 'Heart disease', organ_id: 'heart', probability: 0.386, band: 'red', key_drivers: ['Smoking'] },
            { condition_id: 'chronic_lung_disease', label: 'Chronic lung disease', organ_id: 'lungs', probability: 0.479, band: 'red', key_drivers: ['Smoking', 'Air quality'] },
            { condition_id: 'stroke', label: 'Stroke', organ_id: 'brain', probability: 0.24, band: 'amber', key_drivers: ['Age profile'] },
            { condition_id: 'depression', label: 'Depression', organ_id: 'brain', probability: 0.182, band: 'amber', key_drivers: ['Low exercise'] },
            { condition_id: 'diabetes', label: 'Diabetes', organ_id: 'pancreas', probability: 0.22, band: 'amber', key_drivers: ['BMI'] },
          ],
        },
        candidate: {
          summary_score: 44.1,
          organs: [
            { organ_id: 'heart', label: 'Heart', score: 0.491, band: 'red', top_conditions: ['Heart disease'] },
            { organ_id: 'lungs', label: 'Lungs', score: 0.641, band: 'red', top_conditions: ['Chronic lung disease'] },
            { organ_id: 'brain', label: 'Brain', score: 0.361, band: 'red', top_conditions: ['Stroke', 'Depression'] },
            { organ_id: 'pancreas', label: 'Pancreas', score: 0.533, band: 'red', top_conditions: ['Diabetes'] },
          ],
          conditions: [
            { condition_id: 'heart_disease', label: 'Heart disease', organ_id: 'heart', probability: 0.491, band: 'red', key_drivers: ['Smoking'] },
            { condition_id: 'chronic_lung_disease', label: 'Chronic lung disease', organ_id: 'lungs', probability: 0.641, band: 'red', key_drivers: ['Smoking', 'Air quality'] },
            { condition_id: 'stroke', label: 'Stroke', organ_id: 'brain', probability: 0.414, band: 'red', key_drivers: ['Age profile'] },
            { condition_id: 'depression', label: 'Depression', organ_id: 'brain', probability: 0.307, band: 'amber', key_drivers: ['Low exercise'] },
            { condition_id: 'diabetes', label: 'Diabetes', organ_id: 'pancreas', probability: 0.533, band: 'red', key_drivers: ['BMI'] },
          ],
        },
        organ_deltas: [
          { organ_id: 'heart', label: 'Heart', baseline_score: 0.386, candidate_score: 0.491, score_delta: 0.105, band: 'red', top_conditions: ['Heart disease'] },
          { organ_id: 'lungs', label: 'Lungs', baseline_score: 0.479, candidate_score: 0.641, score_delta: 0.162, band: 'red', top_conditions: ['Chronic lung disease'] },
          { organ_id: 'brain', label: 'Brain', baseline_score: 0.211, candidate_score: 0.361, score_delta: 0.15, band: 'red', top_conditions: ['Stroke', 'Depression'] },
          { organ_id: 'pancreas', label: 'Pancreas', baseline_score: 0.22, candidate_score: 0.533, score_delta: 0.313, band: 'red', top_conditions: ['Diabetes'] },
        ],
      }),
    })
  })

  await page.goto('/')
  await expect(
    page.getByTestId('overview-whatif').locator('.metric-value'),
  ).toHaveText(/\d/, { timeout: 15000 })
  await expect(page.getByTestId('overview-whatif').locator('.metric-value')).toHaveText(
    '44.1',
    { timeout: 15000 },
  )

  await page.getByTestId('organ-callout-lungs').click()
  await expect(page.getByTestId('health-guidance')).toBeVisible()
  await expect(page.getByText('What may help')).toBeVisible()
  await expect(page.getByText('Guidance for current and what-if risk')).toBeVisible()
  await expect(page.getByRole('link', { name: /CDC: Health Effects of Cigarettes - COPD/i })).toBeVisible()
})

test('shows guidance when only the current profile remains high-risk', async ({ page }) => {
  await page.route('**/api/scenario/compare', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        baseline: {
          summary_score: 32.4,
          organs: [
            { organ_id: 'heart', label: 'Heart', score: 0.417, band: 'red', top_conditions: ['Heart disease'] },
            { organ_id: 'lungs', label: 'Lungs', score: 0.19, band: 'amber', top_conditions: ['Chronic lung disease'] },
            { organ_id: 'brain', label: 'Brain', score: 0.18, band: 'amber', top_conditions: ['Stroke', 'Depression'] },
            { organ_id: 'pancreas', label: 'Pancreas', score: 0.21, band: 'amber', top_conditions: ['Diabetes'] },
          ],
          conditions: [
            { condition_id: 'heart_disease', label: 'Heart disease', organ_id: 'heart', probability: 0.417, band: 'red', key_drivers: ['Smoking'] },
            { condition_id: 'chronic_lung_disease', label: 'Chronic lung disease', organ_id: 'lungs', probability: 0.19, band: 'amber', key_drivers: ['Air quality'] },
            { condition_id: 'stroke', label: 'Stroke', organ_id: 'brain', probability: 0.16, band: 'amber', key_drivers: ['Age profile'] },
            { condition_id: 'depression', label: 'Depression', organ_id: 'brain', probability: 0.20, band: 'amber', key_drivers: ['Low exercise'] },
            { condition_id: 'diabetes', label: 'Diabetes', organ_id: 'pancreas', probability: 0.21, band: 'amber', key_drivers: ['BMI'] },
          ],
        },
        candidate: {
          summary_score: 18.8,
          organs: [
            { organ_id: 'heart', label: 'Heart', score: 0.22, band: 'amber', top_conditions: ['Heart disease'] },
            { organ_id: 'lungs', label: 'Lungs', score: 0.12, band: 'green', top_conditions: ['Chronic lung disease'] },
            { organ_id: 'brain', label: 'Brain', score: 0.11, band: 'green', top_conditions: ['Stroke', 'Depression'] },
            { organ_id: 'pancreas', label: 'Pancreas', score: 0.19, band: 'amber', top_conditions: ['Diabetes'] },
          ],
          conditions: [
            { condition_id: 'heart_disease', label: 'Heart disease', organ_id: 'heart', probability: 0.22, band: 'amber', key_drivers: ['BMI'] },
            { condition_id: 'chronic_lung_disease', label: 'Chronic lung disease', organ_id: 'lungs', probability: 0.12, band: 'green', key_drivers: ['Air quality'] },
            { condition_id: 'stroke', label: 'Stroke', organ_id: 'brain', probability: 0.1, band: 'green', key_drivers: ['Age profile'] },
            { condition_id: 'depression', label: 'Depression', organ_id: 'brain', probability: 0.12, band: 'green', key_drivers: ['Low exercise'] },
            { condition_id: 'diabetes', label: 'Diabetes', organ_id: 'pancreas', probability: 0.19, band: 'amber', key_drivers: ['BMI'] },
          ],
        },
        organ_deltas: [
          { organ_id: 'heart', label: 'Heart', baseline_score: 0.417, candidate_score: 0.22, score_delta: -0.197, band: 'amber', top_conditions: ['Heart disease'] },
          { organ_id: 'lungs', label: 'Lungs', baseline_score: 0.19, candidate_score: 0.12, score_delta: -0.07, band: 'green', top_conditions: ['Chronic lung disease'] },
          { organ_id: 'brain', label: 'Brain', baseline_score: 0.18, candidate_score: 0.11, score_delta: -0.07, band: 'green', top_conditions: ['Stroke', 'Depression'] },
          { organ_id: 'pancreas', label: 'Pancreas', baseline_score: 0.21, candidate_score: 0.19, score_delta: -0.02, band: 'amber', top_conditions: ['Diabetes'] },
        ],
      }),
    })
  })

  await page.goto('/')
  await page.getByTestId('organ-callout-heart').click()
  await expect(page.getByTestId('health-guidance')).toBeVisible()
  await expect(page.getByText('Guidance for current risk')).toBeVisible()
  await expect(page.getByText('Current profile is high-risk; this scenario improves it.')).toBeVisible()
  await expect(page.getByText('Current 41.7%')).toBeVisible()
})

test('keeps drill-down content aligned with the selected heatmap mode', async ({ page }) => {
  await page.route('**/api/scenario/compare', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        baseline: {
          summary_score: 32.4,
          organs: [
            { organ_id: 'heart', label: 'Heart', score: 0.386, band: 'red', top_conditions: ['Heart disease'] },
            { organ_id: 'lungs', label: 'Lungs', score: 0.479, band: 'red', top_conditions: ['Chronic lung disease'] },
            { organ_id: 'brain', label: 'Brain', score: 0.211, band: 'amber', top_conditions: ['Stroke', 'Depression'] },
            { organ_id: 'pancreas', label: 'Pancreas', score: 0.22, band: 'amber', top_conditions: ['Diabetes'] },
          ],
          conditions: [
            { condition_id: 'heart_disease', label: 'Heart disease', organ_id: 'heart', probability: 0.386, band: 'red', key_drivers: ['Smoking'] },
            { condition_id: 'chronic_lung_disease', label: 'Chronic lung disease', organ_id: 'lungs', probability: 0.479, band: 'red', key_drivers: ['Smoking', 'Air quality'] },
            { condition_id: 'stroke', label: 'Stroke', organ_id: 'brain', probability: 0.24, band: 'amber', key_drivers: ['Age profile'] },
            { condition_id: 'depression', label: 'Depression', organ_id: 'brain', probability: 0.182, band: 'amber', key_drivers: ['Low exercise'] },
            { condition_id: 'diabetes', label: 'Diabetes', organ_id: 'pancreas', probability: 0.22, band: 'amber', key_drivers: ['BMI'] },
          ],
        },
        candidate: {
          summary_score: 44.1,
          organs: [
            { organ_id: 'heart', label: 'Heart', score: 0.491, band: 'red', top_conditions: ['Heart disease'] },
            { organ_id: 'lungs', label: 'Lungs', score: 0.641, band: 'red', top_conditions: ['Chronic lung disease'] },
            { organ_id: 'brain', label: 'Brain', score: 0.361, band: 'red', top_conditions: ['Stroke', 'Depression'] },
            { organ_id: 'pancreas', label: 'Pancreas', score: 0.533, band: 'red', top_conditions: ['Diabetes'] },
          ],
          conditions: [
            { condition_id: 'heart_disease', label: 'Heart disease', organ_id: 'heart', probability: 0.491, band: 'red', key_drivers: ['Smoking'] },
            { condition_id: 'chronic_lung_disease', label: 'Chronic lung disease', organ_id: 'lungs', probability: 0.641, band: 'red', key_drivers: ['Smoking', 'Air quality'] },
            { condition_id: 'stroke', label: 'Stroke', organ_id: 'brain', probability: 0.414, band: 'red', key_drivers: ['Age profile'] },
            { condition_id: 'depression', label: 'Depression', organ_id: 'brain', probability: 0.307, band: 'amber', key_drivers: ['Low exercise'] },
            { condition_id: 'diabetes', label: 'Diabetes', organ_id: 'pancreas', probability: 0.533, band: 'red', key_drivers: ['BMI'] },
          ],
        },
        organ_deltas: [
          { organ_id: 'heart', label: 'Heart', baseline_score: 0.386, candidate_score: 0.491, score_delta: 0.105, band: 'red', top_conditions: ['Heart disease'] },
          { organ_id: 'lungs', label: 'Lungs', baseline_score: 0.479, candidate_score: 0.641, score_delta: 0.162, band: 'red', top_conditions: ['Chronic lung disease'] },
          { organ_id: 'brain', label: 'Brain', baseline_score: 0.211, candidate_score: 0.361, score_delta: 0.15, band: 'red', top_conditions: ['Stroke', 'Depression'] },
          { organ_id: 'pancreas', label: 'Pancreas', baseline_score: 0.22, candidate_score: 0.533, score_delta: 0.313, band: 'red', top_conditions: ['Diabetes'] },
        ],
      }),
    })
  })

  await page.goto('/')
  await expect(page.getByTestId('overview-whatif').locator('.metric-value')).toHaveText(
    '44.1',
    { timeout: 15000 },
  )

  await page.getByTestId('heatmap-mode-baseline').click()
  await page.getByTestId('organ-callout-brain').click()

  await expect(page.getByTestId('condition-inspector')).toContainText('Current risk')
  await expect(page.getByTestId('condition-stroke')).toContainText('24.0%')
  await expect(page.getByTestId('condition-depression')).toContainText('18.2%')
  await expect(page.getByTestId('health-guidance')).toBeVisible()
  await expect(page.getByText('Guidance for what-if risk')).toBeVisible()
})
