const { test, expect } = require('@playwright/test');
const path = require('node:path');

const signaturePadScript = path.resolve(__dirname, '../../assets/signature_pad.js');
const viewportSizes = [
    { width: 360, height: 780, label: 'mobile' },
    { width: 768, height: 1024, label: 'tablet' },
    { width: 1280, height: 900, label: 'desktop' },
];

const signaturePage = `<!doctype html>
<html lang="sv">
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    html, body { margin: 0; padding: 0; }
    .frame { width: min(100%, 920px); margin: 0 auto; }
    #pad { display: block; box-sizing: border-box; width: 100%; height: 138px; border: 1px solid #cbd5e1; }
  </style>
</head>
<body>
  <div class="frame"><canvas id="pad" width="1000" height="220" aria-label="Signaturfält"></canvas></div>
</body>
</html>`;

test('signaturpennan ritar med penna och finger i responsiva storlekar', async ({ page }) => {
    for (const viewport of viewportSizes) {
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
        await page.setContent(signaturePage);
        await page.addScriptTag({ path: signaturePadScript });

        const result = await page.evaluate(async () => {
            const canvas = document.querySelector('#pad');
            const pad = window.TadegaSignaturePad.attach(canvas, {
                background: '#fff',
                color: '#18385f',
            });
            const rect = canvas.getBoundingClientRect();
            const display = {
                attached: !!pad,
                displayRatio: rect.width / rect.height,
                backingRatio: canvas.width / canvas.height,
                width: canvas.width,
                height: canvas.height,
            };
            const strokes = [];

            for (const kind of ['pen', 'touch']) {
                const points = [
                    [0.12, 0.66],
                    [0.28, 0.40],
                    [0.45, 0.61],
                    [0.62, 0.43],
                    [0.80, 0.56],
                    [0.88, 0.37],
                ];
                const eventOptions = (x, y, pressure) => ({
                    bubbles: true,
                    cancelable: true,
                    pointerId: 7,
                    pointerType: kind,
                    isPrimary: true,
                    button: 0,
                    clientX: rect.left + rect.width * x,
                    clientY: rect.top + rect.height * y,
                    pressure,
                    tiltX: kind === 'pen' ? 24 : 0,
                    tiltY: kind === 'pen' ? -18 : 0,
                    twist: kind === 'pen' ? 30 : 0,
                });
                const dispatch = (type, point, pressure) => canvas.dispatchEvent(
                    new PointerEvent(type, eventOptions(point[0], point[1], pressure))
                );

                dispatch('pointerdown', points[0], kind === 'pen' ? 0.24 : 0.5);
                for (let index = 1; index < points.length - 1; index += 1) {
                    dispatch('pointermove', points[index], kind === 'pen' ? 0.35 + index * 0.1 : 0.5);
                }
                dispatch('pointerup', points[points.length - 1], kind === 'pen' ? 0.58 : 0.5);

                const png = pad.serializeCropped();
                const image = new Image();
                const imageReady = new Promise((resolve, reject) => {
                    image.onload = resolve;
                    image.onerror = reject;
                });
                image.src = png;
                await imageReady;

                const stroke = {
                    pointerType: kind,
                    hasInk: pad.hasInk,
                    pngPrefix: png.slice(0, 22),
                    imageWidth: image.naturalWidth,
                    imageHeight: image.naturalHeight,
                    canvasWidth: canvas.width,
                    canvasHeight: canvas.height,
                };
                pad.clear();
                stroke.cleared = !pad.hasInk;
                strokes.push(stroke);
            }
            return { display, strokes };
        });

        expect(result.display.attached, `${viewport.label}: signaturmotorn ska ansluta`).toBe(true);
        expect(
            Math.abs(result.display.displayRatio / result.display.backingRatio - 1),
            `${viewport.label}: canvasens bildförhållande ska följa visningsytan`
        ).toBeLessThan(0.025);

        for (const stroke of result.strokes) {
            const context = `${viewport.label}/${stroke.pointerType}`;
            expect(stroke.hasInk, `${context}: stroke should be recorded`).toBe(true);
            expect(stroke.pngPrefix, `${context}: export should be a PNG`).toBe('data:image/png;base64,');
            expect(stroke.imageWidth, `${context}: exported PNG should have width`).toBeGreaterThan(0);
            expect(stroke.imageHeight, `${context}: exported PNG should have height`).toBeGreaterThan(0);
            expect(stroke.imageWidth, `${context}: drawn line should be compactly cropped`).toBeLessThan(stroke.canvasWidth);
            expect(stroke.imageHeight, `${context}: drawn line should be compactly cropped`).toBeLessThan(stroke.canvasHeight);
            expect(stroke.cleared, `${context}: clear should remove the signature`).toBe(true);
        }
    }
});

test('långsamma korta drag och små prickar behåller synligt bläck', async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 780 });
    await page.setContent(signaturePage);
    await page.addScriptTag({ path: signaturePadScript });

    const marks = await page.evaluate(async () => {
        const canvas = document.querySelector('#pad');
        const pad = window.TadegaSignaturePad.attach(canvas, {
            background: '#fff',
            color: '#18385f',
        });
        const rect = canvas.getBoundingClientRect();
        const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
        const dispatch = (type, x, y) => canvas.dispatchEvent(new PointerEvent(type, {
            bubbles: true,
            cancelable: true,
            pointerId: 9,
            pointerType: 'pen',
            isPrimary: true,
            button: 0,
            clientX: x,
            clientY: y,
            pressure: 0.42,
            tiltX: 0,
            tiltY: 0,
        }));
        const exportMark = async () => {
            const png = pad.serializeCropped();
            const image = new Image();
            const imageReady = new Promise((resolve, reject) => {
                image.onload = resolve;
                image.onerror = reject;
            });
            image.src = png;
            await imageReady;
            const mark = {
                hasInk: pad.hasInk,
                pngPrefix: png.slice(0, 22),
                width: image.naturalWidth,
                height: image.naturalHeight,
                canvasWidth: canvas.width,
                canvasHeight: canvas.height,
            };
            pad.clear();
            return mark;
        };

        const startX = rect.left + rect.width * 0.5;
        const startY = rect.top + rect.height * 0.5;
        dispatch('pointerdown', startX, startY);
        await wait(24);
        dispatch('pointermove', startX + 0.5, startY + 0.2);
        await wait(24);
        dispatch('pointerup', startX + 0.9, startY + 0.3);
        const slowShortStroke = await exportMark();

        dispatch('pointerdown', startX, startY);
        dispatch('pointerup', startX, startY);
        const tap = await exportMark();
        return { slowShortStroke, tap };
    });

    for (const [name, mark] of Object.entries(marks)) {
        expect(mark.hasInk, `${name}: mark should contain ink`).toBe(true);
        expect(mark.pngPrefix, `${name}: export should be a PNG`).toBe('data:image/png;base64,');
        expect(mark.width, `${name}: exported mark should have width`).toBeGreaterThan(0);
        expect(mark.height, `${name}: exported mark should have height`).toBeGreaterThan(0);
        expect(mark.width, `${name}: mark should be cropped`).toBeLessThan(mark.canvasWidth);
        expect(mark.height, `${name}: mark should be cropped`).toBeLessThan(mark.canvasHeight);
    }
});

test('tryckdiagnostik skiljer jämnt och varierande penntryck', async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 780 });
    await page.setContent(signaturePage);
    await page.addScriptTag({ path: signaturePadScript });

    const results = await page.evaluate(async () => {
        const canvas = document.querySelector('#pad');
        const pad = window.TadegaSignaturePad.attach(canvas, { background: null });
        const rect = canvas.getBoundingClientRect();
        const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
        const dispatch = (type, pointerId, x, y, pressure) => canvas.dispatchEvent(new PointerEvent(type, {
            bubbles: true,
            cancelable: true,
            pointerId,
            pointerType: 'pen',
            isPrimary: true,
            button: 0,
            clientX: rect.left + rect.width * x,
            clientY: rect.top + rect.height * y,
            pressure,
        }));
        const draw = async (pressures, pointerId) => {
            dispatch('pointerdown', pointerId, 0.18, 0.52, pressures[0]);
            for (let index = 1; index < pressures.length; index += 1) {
                await wait(8);
                dispatch('pointermove', pointerId, 0.18 + index * 0.11, 0.52 + (index % 2) * 0.06, pressures[index]);
            }
            await wait(8);
            dispatch('pointerup', pointerId, 0.70, 0.52, 0);
            const png = pad.serializeCropped();
            const result = {
                diagnostics: pad.getLastStrokeDiagnostics(),
                crop: pad.getLastCropMetrics(),
                pngPrefix: png.slice(0, 22),
            };
            pad.clear();
            return result;
        };
        return {
            fixed: await draw([0.5, 0.5, 0.5, 0.5], 11),
            variable: await draw([0.15, 0.34, 0.58, 0.82], 12),
        };
    });

    expect(results.fixed.diagnostics.pressureMode).toBe('flat');
    expect(results.fixed.diagnostics.pressureRange).toBe(0);
    expect(results.fixed.diagnostics.pressureSamples).toBe(4);
    expect(results.variable.diagnostics.pressureMode).toBe('variable');
    expect(results.variable.diagnostics.pressureRange).toBeGreaterThan(0.5);
    expect(results.variable.diagnostics.approximateHz).toBeGreaterThan(0);
    expect(results.variable.diagnostics.eventSamples).toBeGreaterThanOrEqual(5);
    expect(results.variable.pngPrefix).toBe('data:image/png;base64,');
    expect(results.variable.crop.padLeftPx).toBeGreaterThan(0);
});

test('långa inmatningsglapp bryter genvägsstreck och tappad pekarfångst avslutar säkert', async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 780 });
    await page.setContent(signaturePage);
    await page.addScriptTag({ path: signaturePadScript });

    const result = await page.evaluate(async () => {
        const canvas = document.querySelector('#pad');
        const pad = window.TadegaSignaturePad.attach(canvas, { background: null });
        const rect = canvas.getBoundingClientRect();
        const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
        const dispatch = (type, pointerId, x, y) => canvas.dispatchEvent(new PointerEvent(type, {
            bubbles: true,
            cancelable: true,
            pointerId,
            pointerType: 'pen',
            isPrimary: true,
            button: 0,
            clientX: rect.left + rect.width * x,
            clientY: rect.top + rect.height * y,
            pressure: 0.42,
        }));

        dispatch('pointerdown', 21, 0.10, 0.50);
        await wait(125);
        dispatch('pointermove', 21, 0.90, 0.50);
        dispatch('pointerup', 21, 0.92, 0.50);
        pad.serialize();
        const middleAlpha = pad.context.getImageData(Math.floor(canvas.width * 0.5), Math.floor(canvas.height * 0.5), 1, 1).data[3];
        const gapDiagnostics = pad.getLastStrokeDiagnostics();

        pad.clear();
        dispatch('pointerdown', 22, 0.40, 0.50);
        canvas.dispatchEvent(new PointerEvent('lostpointercapture', {
            bubbles: true,
            cancelable: false,
            pointerId: 22,
            pointerType: 'pen',
            isPrimary: true,
        }));
        return { middleAlpha, gapDiagnostics, captureDiagnostics: pad.getLastStrokeDiagnostics() };
    });

    expect(result.gapDiagnostics.longGapCount).toBeGreaterThan(0);
    expect(result.gapDiagnostics.maxGapMs).toBeGreaterThan(100);
    expect(result.middleAlpha).toBe(0);
    expect(result.captureDiagnostics.pointerCaptureLost).toBe(true);
});

test('stor handflatekontakt ersätts av pennan och PNG-bakgrunden är transparent', async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 780 });
    await page.setContent(signaturePage);
    await page.addScriptTag({ path: signaturePadScript });

    const result = await page.evaluate(async () => {
        const canvas = document.querySelector('#pad');
        let starts = 0;
        const pad = window.TadegaSignaturePad.attach(canvas, {
            background: null,
            onStart: () => { starts += 1; },
        });
        const rect = canvas.getBoundingClientRect();
        const dispatch = (type, pointerId, pointerType, x, y, extra) => canvas.dispatchEvent(new PointerEvent(type, {
            bubbles: true,
            cancelable: true,
            pointerId,
            pointerType,
            isPrimary: pointerType !== 'pen',
            button: 0,
            clientX: rect.left + rect.width * x,
            clientY: rect.top + rect.height * y,
            pressure: 0.45,
            ...(extra || {}),
        }));

        dispatch('pointerdown', 31, 'touch', 0.20, 0.50, { width: 60, height: 55 });
        dispatch('pointerdown', 32, 'pen', 0.80, 0.50, { width: 1, height: 1, isPrimary: false });
        dispatch('pointerup', 32, 'pen', 0.82, 0.50, { pressure: 0.5 });

        pad.serialize();
        const touchX = Math.floor(canvas.width * 0.20);
        const centerY = Math.floor(canvas.height * 0.50);
        const rejectedPalmAlpha = pad.context.getImageData(touchX, centerY, 1, 1).data[3];
        const png = pad.serializeCropped();
        const crop = pad.getLastCropMetrics();
        const image = new Image();
        const imageReady = new Promise((resolve, reject) => {
            image.onload = resolve;
            image.onerror = reject;
        });
        image.src = png;
        await imageReady;
        const probe = document.createElement('canvas');
        probe.width = image.naturalWidth;
        probe.height = image.naturalHeight;
        const probeContext = probe.getContext('2d');
        probeContext.drawImage(image, 0, 0);
        const cornerAlpha = probeContext.getImageData(0, 0, 1, 1).data[3];
        return {
            starts,
            diagnostics: pad.getLastStrokeDiagnostics(),
            rejectedPalmAlpha,
            cornerAlpha,
            crop,
            pngPrefix: png.slice(0, 22),
        };
    });

    expect(result.starts).toBe(2);
    expect(result.diagnostics.pointerType).toBe('pen');
    expect(result.diagnostics.palmStrokeDiscarded).toBe(true);
    expect(result.rejectedPalmAlpha).toBe(0);
    expect(result.cornerAlpha).toBe(0);
    expect(result.crop.padLeftPx).toBeGreaterThan(0);
    expect(result.pngPrefix).toBe('data:image/png;base64,');
});
