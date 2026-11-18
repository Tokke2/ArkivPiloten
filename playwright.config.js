const { defineConfig, devices } = require('@playwright/test');

const httpUser = process.env.PORTAL_HTTP_USERNAME || '';
const httpPassword = process.env.PORTAL_HTTP_PASSWORD || '';
if ((httpUser === '') !== (httpPassword === '')) {
    throw new Error('Ange både PORTAL_HTTP_USERNAME och PORTAL_HTTP_PASSWORD, eller lämna båda tomma.');
}

const httpCredentials = httpUser !== ''
    ? { username: httpUser, password: httpPassword }
    : undefined;

module.exports = defineConfig({
    testDir: './tests/e2e',
    fullyParallel: false,
    workers: 1,
    timeout: 60_000,
    expect: { timeout: 12_000 },
    reporter: 'list',
    use: {
        baseURL: process.env.PORTAL_BASE_URL,
        httpCredentials,
        actionTimeout: 12_000,
        navigationTimeout: 30_000,
        trace: 'retain-on-failure',
        screenshot: 'only-on-failure',
        video: 'retain-on-failure',
    },
    projects: [
        { name: 'chromium-desktop', use: { ...devices['Desktop Chrome'] } },
        { name: 'chromium-mobile', use: { ...devices['Pixel 7'] } },
        { name: 'firefox-desktop', use: { ...devices['Desktop Firefox'] } },
        { name: 'webkit-desktop', use: { ...devices['Desktop Safari'] } },
        { name: 'webkit-mobile', use: { ...devices['iPhone 13'] } },
    ],
});
