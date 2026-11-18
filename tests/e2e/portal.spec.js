const { test, expect } = require('@playwright/test');

const invoiceUsername = process.env.PORTAL_TEST_USERNAME || '';
const invoicePin = process.env.PORTAL_TEST_PIN || '';
const protocolUsername = process.env.PORTAL_PROTOCOL_TEST_USERNAME || '';
const protocolPin = process.env.PORTAL_PROTOCOL_TEST_PIN || '';

function requireTarget() {
    test.skip(!process.env.PORTAL_BASE_URL, 'Ange PORTAL_BASE_URL till en skyddad test- eller stagingmiljö.');
}

async function loginInvoice(page) {
    test.skip(!invoiceUsername || !invoicePin, 'Ange PORTAL_TEST_USERNAME och PORTAL_TEST_PIN för fakturaflödena.');
    await page.goto('?tab=invoice');

    const firstAdmin = page.locator('#invoice-first-admin-title');
    if (await firstAdmin.isVisible().catch(() => false)) {
        throw new Error('Fakturakonton är inte konfigurerade i testmiljön. Skapa konton innan webbläsartester körs.');
    }

    const loginTitle = page.locator('#invoice-login-title');
    if (await loginTitle.isVisible().catch(() => false)) {
        await page.locator('#invoice-login-username').fill(invoiceUsername);
        await page.locator('#invoice-login-pin').fill(invoicePin);
        await page.locator('form:has(input[name="action"][value="invoice_pin_login"]) button[type="submit"]').click();
    }
    await expect(page.locator('#invoice-form')).toBeVisible();
}

async function loginProtocol(page) {
    test.skip(!protocolUsername || !protocolPin, 'Ange PORTAL_PROTOCOL_TEST_USERNAME och PORTAL_PROTOCOL_TEST_PIN för protokollflödena.');
    await page.goto('?tab=protocol');
    const loginTitle = page.locator('#protocol-auth-title');
    if (await loginTitle.isVisible().catch(() => false)) {
        await page.locator('#protocol-login-username').fill(protocolUsername);
        await page.locator('#protocol-login-pin').fill(protocolPin);
        await page.locator('form:has(input[name="action"][value="protocol_pin_login"]) button[type="submit"]').click();
    }
    await expect(page.locator('#protocol-form')).toBeVisible();
}

async function drawProtocolSignature(page) {
    const canvas = page.locator('#protocol-signature-canvas');
    await canvas.scrollIntoViewIfNeeded();
    const bounds = await canvas.boundingBox();
    expect(bounds).not.toBeNull();
    await page.evaluate(({ x1, y1, x2, y2 }) => {
        const pad = document.getElementById('protocol-signature-canvas');
        const send = (type, x, y, buttons) => pad.dispatchEvent(new PointerEvent(type, {
            bubbles: true,
            cancelable: true,
            pointerId: 17,
            pointerType: 'touch',
            isPrimary: true,
            clientX: x,
            clientY: y,
            button: 0,
            buttons,
        }));
        send('pointerdown', x1, y1, 1);
        send('pointermove', x2, y2, 1);
        send('pointerup', x2, y2, 0);
    }, {
        x1: bounds.x + bounds.width * 0.2,
        y1: bounds.y + bounds.height * 0.55,
        x2: bounds.x + bounds.width * 0.78,
        y2: bounds.y + bounds.height * 0.42,
    });
    await expect(page.locator('#protocol-signature-data')).toHaveValue(/^data:image\/png;base64,/);
}

test('mobil: fakturaguiden går vidare till granskning utan att spara', async ({ page }, testInfo) => {
    requireTarget();
    test.skip(!testInfo.project.name.includes('mobile'), 'Detta stegflöde körs i mobilprojekten.');
    await loginInvoice(page);

    await page.locator('#invoice-customer').fill('E2E Testkund');
    await page.locator('#invoice-reference').fill('E2E-REFERENS');
    await page.locator('#invoice-description').fill('Automatiskt webbläsartest – sparas inte.');
    await expect(page.locator('#invoice-step-status')).toContainText('Steg 1 av 3');

    await page.locator('#invoice-step-next').click();
    await expect(page.locator('#invoice-step-status')).toContainText('Steg 2 av 3');
    await page.locator('.invoice-item-name').first().fill('E2E testarbete');
    await page.locator('.invoice-item-qty').first().fill('1');
    await page.locator('.invoice-item-price').first().fill('100');

    await page.locator('#invoice-step-next').click();
    await expect(page.locator('#invoice-step-status')).toContainText('Steg 3 av 3');
    await expect(page.locator('#invoice-mobile-review-heading')).toBeVisible();
    await expect(page.locator('#invoice-review-customer')).toHaveText('E2E Testkund');
    await expect(page.locator('#invoice-review-items')).toContainText('E2E testarbete');
    await expect(page.locator('.invoice-disclaimer')).toContainText('inte en faktura');
    // Intentionally do not submit: the test creates no persistent customer document.
});

test('dator: utskriftsknappen anropar print och döljer kontroller i utskriftsläge', async ({ page }, testInfo) => {
    requireTarget();
    test.skip(testInfo.project.name.includes('mobile'), 'Detta utskriftstest körs i datorprojekten.');
    await loginInvoice(page);

    await page.evaluate(() => {
        window.__portalPrintCalls = 0;
        window.print = () => { window.__portalPrintCalls += 1; };
    });
    await page.locator('#invoice-print').click();
    expect(await page.evaluate(() => window.__portalPrintCalls)).toBe(1);

    await page.emulateMedia({ media: 'print' });
    await expect(page.locator('.invoice-actions')).toHaveCSS('display', 'none');
    await expect(page.locator('.page-heading')).toHaveCSS('display', 'none');
    const disclaimerDisplay = await page.locator('.invoice-disclaimer').evaluate((element) => getComputedStyle(element).display);
    expect(disclaimerDisplay).not.toBe('none');
    await page.emulateMedia({ media: 'screen' });
});

test('kundläge: signaturen kan ritas och rensas utan att blanketten skickas', async ({ page }) => {
    requireTarget();
    await page.goto('skadeblankett-kund.php');

    await expect(page.getByRole('heading', { name: 'Fyll i skadeblanketten' })).toBeVisible();
    await expect(page.locator('#skade-signature-pad')).toBeVisible();
    await expect(page.locator('#skade-signature-confirmed')).toHaveAttribute('required', '');
    await expect(page.locator('.tabs-wrap')).toHaveCount(0);
    await expect(page.locator('a[href*="view_file"]:visible, a[href*="download_file"]:visible, a[href*="archive"]:visible')).toHaveCount(0);
    await expect(page.locator('#skade-form')).toHaveAttribute('action', './skadeblankett-kund.php');

    const canvas = page.locator('#skade-signature-pad');
    await canvas.scrollIntoViewIfNeeded();
    const bounds = await canvas.boundingBox();
    expect(bounds).not.toBeNull();
    // Synthetic touch-pointer events exercise the same PointerEvent handlers
    // used by finger input while keeping the test safe (it never submits).
    await page.evaluate(({ x1, y1, x2, y2 }) => {
        const pad = document.getElementById('skade-signature-pad');
        const send = (type, x, y, buttons) => pad.dispatchEvent(new PointerEvent(type, {
            bubbles: true,
            cancelable: true,
            pointerId: 7,
            pointerType: 'touch',
            isPrimary: true,
            clientX: x,
            clientY: y,
            button: 0,
            buttons,
        }));
        send('pointerdown', x1, y1, 1);
        send('pointermove', x2, y2, 1);
        send('pointerup', x2, y2, 0);
    }, {
        x1: bounds.x + bounds.width * 0.2,
        y1: bounds.y + bounds.height * 0.55,
        x2: bounds.x + bounds.width * 0.78,
        y2: bounds.y + bounds.height * 0.42,
    });

    await expect(page.locator('#skade-signature-png')).toHaveValue(/^data:image\/png;base64,/);
    await expect(page.locator('#skade-signature-status')).toContainText('Signaturen är klar');
    await page.locator('#skade-signature-clear').click();
    await expect(page.locator('#skade-signature-png')).toHaveValue('');
    // Deliberately no submit: no PDF is created and no email is sent.
});

test('autosparning: fakturaunderlag kan återupptas och utkast raderas', async ({ page }, testInfo) => {
    requireTarget();
    test.skip(!['chromium-desktop', 'chromium-mobile'].includes(testInfo.project.name), 'Autosparflödet körs i Chromium på dator och mobil.');
    await loginInvoice(page);

    await page.locator('#invoice-customer').fill('E2E Autospar Testkund');
    await page.locator('#invoice-description').fill('Autosparningstest – inget underlag skickas till kunden.');
    if (testInfo.project.name.includes('mobile')) await page.locator('#invoice-step-next').click();
    await page.locator('.invoice-item-name').first().fill('Autospar testarbete');
    await page.locator('.invoice-item-qty').first().fill('1');
    await page.locator('.invoice-item-price').first().fill('12');
    await expect(page.locator('#invoice-autosave-message')).toHaveText('Utkastet har sparats automatiskt.', { timeout: 15_000 });

    const draftId = await page.locator('#invoice-form input[name="draft_id"]').inputValue();
    await page.goto(`?tab=invoice&draft_id=${encodeURIComponent(draftId)}`);
    await expect(page.locator('#invoice-customer')).toHaveValue('E2E Autospar Testkund');
    await expect(page.locator('.invoice-item-name').first()).toHaveValue('Autospar testarbete');

    await page.goto('?tab=invoice');
    const deleteForm = page.locator(`form:has(input[name="draft_id"][value="${draftId}"])`);
    await expect(deleteForm).toBeVisible();
    page.once('dialog', (dialog) => dialog.accept());
    await deleteForm.locator('button[type="submit"]').click();
    await expect(page).toHaveURL(/msg=draft_deleted/);
    await expect(page.getByText('Utkastet har raderats.')).toBeVisible();
});

test('autosparning: serviceprotokoll kan återupptas och utkast raderas', async ({ page }, testInfo) => {
    requireTarget();
    test.skip(!['chromium-desktop', 'chromium-mobile'].includes(testInfo.project.name), 'Autosparflödet körs i Chromium på dator och mobil.');
    await loginProtocol(page);

    await page.locator('#p-reg').fill('E2E AUTOSPAR');
    await page.locator('#p-customer').fill('Autospar Testkund');
    if (testInfo.project.name.includes('mobile')) await page.locator('#protocol-step-next').click();
    await page.locator('#p-description').fill('Autosparningstest – ingen slutlig protokollpost skapas.');
    await expect(page.locator('#protocol-autosave-message')).toHaveText('Utkastet har sparats automatiskt.', { timeout: 15_000 });

    const draftId = await page.locator('#protocol-form input[name="draft_id"]').inputValue();
    await page.goto(`?tab=protocol&draft_id=${encodeURIComponent(draftId)}`);
    await expect(page.locator('#p-reg')).toHaveValue('E2E AUTOSPAR');
    await expect(page.locator('#p-customer')).toHaveValue('Autospar Testkund');

    await page.goto('?tab=protocol');
    const deleteForm = page.locator(`form:has(input[name="draft_id"][value="${draftId}"])`);
    await expect(deleteForm).toBeVisible();
    page.once('dialog', (dialog) => dialog.accept());
    await deleteForm.locator('button[type="submit"]').click();
    await expect(page).toHaveURL(/msg=draft_deleted/);
    await expect(page.getByText('Utkastet har raderats.')).toBeVisible();
});

test('mobil: protokollguiden granskar och skriver ut hela protokollet', async ({ page }, testInfo) => {
    requireTarget();
    test.skip(!testInfo.project.name.includes('mobile'), 'Detta guideflöde körs i mobilprojekten.');
    await loginProtocol(page);
    await page.route('**/*', async (route) => {
        const request = route.request();
        if (request.method() === 'POST' && (request.postData() || '').includes('action=autosave_draft')) {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, deleted: true }) });
            return;
        }
        await route.continue();
    });

    await page.locator('#p-reg').fill('E2E 123');
    await expect(page.locator('#protocol-step-status')).toContainText('Steg 1 av 3');
    await page.locator('#protocol-step-next').click();
    await expect(page.locator('#protocol-step-status')).toContainText('Steg 2 av 3');
    await page.locator('#p-description').fill('Automatiskt webbläsartest – sparas inte.');
    await page.locator('.p-name').first().fill('E2E testmoment');
    await page.locator('.p-qty').first().fill('1');
    await page.locator('#protocol-step-next').click();
    await expect(page.locator('#protocol-step-status')).toContainText('Steg 3 av 3');
    await expect(page.locator('#protocol-review-title')).toBeVisible();
    await expect(page.locator('#protocol-review-reg')).toHaveText('E2E 123');
    await expect(page.locator('#protocol-review-items')).toContainText('E2E testmoment');

    await page.evaluate(() => {
        window.__portalPrintCalls = 0;
        window.print = () => { window.__portalPrintCalls += 1; };
    });
    await drawProtocolSignature(page);
    await page.locator('#protocol-step-back').click();
    await expect(page.locator('#protocol-step-status')).toContainText('Steg 2 av 3');
    await page.locator('#p-description').fill('Innehållet ändrades efter signering.');
    await expect(page.locator('#protocol-signature-data')).toHaveValue('');
    await page.locator('#protocol-step-next').click();
    await expect(page.locator('#protocol-step-status')).toContainText('Steg 3 av 3');
    await page.getByRole('button', { name: 'Skriv ut A4' }).click();
    await expect(page.locator('#protocol-signature-error')).toBeVisible();
    expect(await page.evaluate(() => window.__portalPrintCalls)).toBe(0);
    await drawProtocolSignature(page);
    await page.getByRole('button', { name: 'Skriv ut A4' }).click();
    expect(await page.evaluate(() => window.__portalPrintCalls)).toBe(1);
    await page.emulateMedia({ media: 'print' });
    await expect(page.locator('#protocol-wizard-nav')).toHaveCSS('display', 'none');
    await expect(page.locator('.invoice-session-bar')).toHaveCSS('display', 'none');
    await expect(page.locator('.pro-section[data-protocol-step="1"]')).toHaveCSS('display', 'block');
    await expect(page.locator('.pro-review')).toHaveCSS('display', 'none');
    await page.emulateMedia({ media: 'screen' });
    // Deliberately do not submit: the test creates no persistent protocol.
});
