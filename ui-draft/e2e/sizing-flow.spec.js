import { test, expect } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const fixturesDir = path.resolve(__dirname, '../../tests/fixtures/sizing');

test.describe('sizing upload flow', () => {
  test('shows parsed sizing preview for valid RKE2 contract', async ({ page }) => {
    await page.goto('/');

    await page.locator('#name').fill(`e2e-valid-${Date.now()}`);
    await page.locator('#targetDir').fill('/tmp');
    await page.locator('#description').fill('rke2 elastic observability deployment');
    await page.locator('#sizingFile').setInputFiles(path.join(fixturesDir, 'rke2-v1.json'));

    await expect(page.locator('#sizingPreviewPanel')).toBeVisible();
    await expect(page.locator('#sizingPreviewStatusText')).toHaveText('Ready');
    await expect(page.locator('#sizingPreviewMeta')).toContainText('schema=es-sizing-rke2.v1');
    await expect(page.locator('#sizingPreviewMeta')).toContainText('platform=rke2');
    await expect(page.locator('#sizingPreviewBody')).toContainText('hot_pool');
    await expect(page.locator('#sizingPreviewBody')).toContainText('kibana');
  });

  test('invalid sizing prompts and can continue without sizing', async ({ page }) => {
    await page.goto('/');

    await page.locator('#name').fill(`e2e-invalid-${Date.now()}`);
    await page.locator('#targetDir').fill('/tmp');
    await page.locator('#description').fill('rke2 elastic deployment');
    await page.locator('#sizingFile').setInputFiles(path.join(fixturesDir, 'invalid.json'));

    await expect(page.locator('#sizingPreviewPanel')).toBeVisible();
    await expect(page.locator('#sizingPreviewStatusText')).toHaveText('Needs attention');
    await expect(page.locator('#sizingPreviewWarnings')).toContainText('Invalid');

    page.once('dialog', async (dialog) => {
      expect(dialog.message()).toContain('Invalid');
      await dialog.accept();
    });

    await page.locator('#createBtn').click();

    await expect(page.locator('#resultStatus')).toBeVisible();
    await expect(page.locator('#resultStatusText')).toHaveText('Created');
    await expect(page.locator('#createLog')).toContainText('Project created successfully');
  });
});
