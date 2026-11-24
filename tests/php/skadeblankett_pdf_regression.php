<?php
declare(strict_types=1);

/**
 * Lightweight regression checks for the skadeblankett PDF text-fit rules.
 * Run with a PHP CLI that can read the repository files:
 *   php tests/php/skadeblankett_pdf_regression.php
 */

require_once __DIR__ . '/../../includes/fpdf/fpdf.php';
require_once __DIR__ . '/../../includes/skadeblankett_pdf.php';

// Minimal no-op timers keep this isolated regression test from writing to app logs.
if (!function_exists('skade_timer_start')) {
    function skade_timer_start(string $name = 'default'): void {}
}
if (!function_exists('skade_timer_end')) {
    function skade_timer_end(string $name = 'default', string $label = ''): float { return 0.0; }
}

final class SkadePdfRegressionCapture extends FPDF
{
    /** @var list<array{x:float,y:float,text:string}> */
    public array $writtenText = [];
    /** @var list<array{width:float,lineHeight:float,text:string}> */
    public array $multiCellCalls = [];
    /** @var array{x:float,y:float}|null */
    public ?array $lastSetXY = null;

    public function Text($x, $y, $txt)
    {
        $this->writtenText[] = ['x' => (float) $x, 'y' => (float) $y, 'text' => (string) $txt];
    }

    public function SetXY($x, $y)
    {
        $this->lastSetXY = ['x' => (float) $x, 'y' => (float) $y];
        parent::SetXY($x, $y);
    }

    public function MultiCell($w, $h, $txt, $border = 0, $align = 'J', $fill = false)
    {
        $this->multiCellCalls[] = ['width' => (float) $w, 'lineHeight' => (float) $h, 'text' => (string) $txt];
    }
}

$checks = 0;
$failures = [];
$check = static function (bool $condition, string $description) use (&$checks, &$failures): void {
    $checks++;
    if (!$condition) {
        $failures[] = $description;
    }
};

// Signature placement preserves aspect ratio and exposes crop padding in physical mm.
$signaturePlacement = skade_pdf_signature_placement(600, 100);
$check(is_array($signaturePlacement), 'A valid cropped PNG should receive a PDF placement.');
if (is_array($signaturePlacement)) {
    $check(abs(($signaturePlacement['width_mm'] / $signaturePlacement['height_mm']) - 6.0) < 0.0001, 'Signature placement must preserve the cropped PNG aspect ratio.');
    $measuredPadMm = 12 * $signaturePlacement['mm_per_px'];
    $check(abs($measuredPadMm - 1.2657) < 0.01, 'A 12 px crop inset must be measurable as about 1.27 mm at the actual PDF placement.');
    $maximumOverrunMm = max(
        $signaturePlacement['left_overrun_mm'],
        $signaturePlacement['right_overrun_mm'],
        $signaturePlacement['top_overrun_mm'],
        $signaturePlacement['bottom_overrun_mm']
    );
    $check($maximumOverrunMm <= 10.0, 'Signature placement must stay under the hard 10 mm overrun ceiling.');
}
$check(skade_pdf_signature_placement(0, 100) === null, 'Zero-sized signature images must not receive a PDF placement.');

$pdf = new SkadePdfRegressionCapture('P', 'mm', 'A4');
$pdf->AddPage();
$pdf->SetFont('Arial', '', 8.0);

// The line writer must preserve its 0.1 mm vertical inset and the full string.
$GLOBALS['skade_pdf_text_fit_stats'] = ['below_5pt_fields' => 0, 'minimum_font_pt' => null, 'unfit_fields' => 0];
$topPt = 200.0;
$heightPt = 40.0;
$fontSize = 8.0;
skade_pdf_write_line($pdf, 'Margin test 123', 100.0, $topPt, 100.0, $heightPt, $fontSize);
$check(count($pdf->writtenText) === 1, 'A fitting single-line field should be written once.');
if (count($pdf->writtenText) === 1) {
    $boxHeightMm = max(1.2, skade_pdf_mm($heightPt));
    $availableHeightMm = max(0.1, $boxHeightMm - 0.2);
    $fontHeightMm = skade_pdf_mm($fontSize);
    $lineBoxHeightMm = min($availableHeightMm, $fontHeightMm);
    $baselineOffsetMm = max(0.0, ($availableHeightMm - $lineBoxHeightMm) / 2.0) + ($lineBoxHeightMm * 0.78);
    $expectedY = skade_pdf_mm($topPt) + 0.1 + $baselineOffsetMm;
    $check(abs($pdf->writtenText[0]['y'] - $expectedY) < 0.0001, 'Single-line text must use a 0.1 mm vertical inset.');
    $check($pdf->writtenText[0]['text'] === 'Margin test 123', 'Single-line text must not be shortened or altered.');
}

// The multiline writer must begin exactly 0.1 mm below the field's top edge.
$pdf->multiCellCalls = [];
$pdf->lastSetXY = null;
$multiTopPt = 240.0;
skade_pdf_write_multiline($pdf, 'A few words', 100.0, $multiTopPt, 150.0, 40.0, 8.0, 4.0);
$check(count($pdf->multiCellCalls) === 1, 'A fitting multiline field should be written once.');
if ($pdf->lastSetXY !== null && count($pdf->multiCellCalls) === 1) {
    $check(abs($pdf->lastSetXY['y'] - (skade_pdf_mm($multiTopPt) + 0.1)) < 0.0001, 'Multiline text must use a 0.1 mm vertical inset.');
    $check($pdf->multiCellCalls[0]['text'] === 'A few words', 'Multiline text must remain complete.');
}

// Wrapping may break only between words: even an oversized word remains intact,
// and all supplied words remain represented in the returned lines.
$longWord = 'Supercalifragilisticexpialidocious1234567890';
$sourceText = 'Kort rad med ' . $longWord . ' sedan slut';
$complete = null;
$wrapped = skade_pdf_wrap_lines($pdf, $sourceText, 20.0, 80, $complete);
$check($complete === false, 'An oversized unbreakable word must be marked as not fitting.');
$check(in_array($longWord, $wrapped, true), 'An oversized word must remain whole rather than being split.');
$check(implode(' ', $wrapped) === $sourceText, 'Wrapping must preserve every character and word.');

// A line-count overflow must report incomplete, without discarding the tail.
$lineOverflowText = 'one two three four five six';
$overflowLines = skade_pdf_wrap_lines($pdf, $lineOverflowText, 14.0, 1, $complete);
$check($complete === false, 'A line-count overflow must be reported as incomplete.');
$check(implode(' ', $overflowLines) === $lineOverflowText, 'Line-count overflow must not truncate the remaining text.');

// Below-5-point tracking is strict: 5.0 pt itself is not a warning; anything
// smaller is counted and the minimum size is retained for the preflight.
$GLOBALS['skade_pdf_text_fit_stats'] = ['below_5pt_fields' => 0, 'minimum_font_pt' => null, 'unfit_fields' => 0];
skade_pdf_track_font_size(5.0);
skade_pdf_track_font_size(4.99);
$fontStats = $GLOBALS['skade_pdf_text_fit_stats'];
$check(($fontStats['below_5pt_fields'] ?? 0) === 1, 'Only font sizes below 5 pt should trigger the warning threshold.');
$check(abs((float) ($fontStats['minimum_font_pt'] ?? 0) - 4.99) < 0.0001, 'The smallest fitted font size should be retained.');

// Text that cannot fit even at the minimum font size must never be drawn or
// clipped; it is recorded as an unfit field so the PDF submission can be stopped.
$pdf->writtenText = [];
$GLOBALS['skade_pdf_text_fit_stats'] = ['below_5pt_fields' => 0, 'minimum_font_pt' => null, 'unfit_fields' => 0];
skade_pdf_write_line($pdf, str_repeat('W', 1200), 100.0, 200.0, 0.1, 40.0, 8.0);
skade_pdf_write_multiline($pdf, str_repeat('W', 6000), 100.0, 200.0, 7.0, 40.0, 8.0, 4.0);
$unfitStats = $GLOBALS['skade_pdf_text_fit_stats'];
$check($pdf->writtenText === [], 'Text too wide to fit must not be emitted partially or outside the field.');
$check(($unfitStats['unfit_fields'] ?? 0) === 2, 'Both unfit fields must be reported for a hard pre-save error.');

// Exercise the complete PDF generator: unfit input must fail before a PDF is saved.
$projectRoot = dirname(__DIR__, 2);
$templatePath = $projectRoot . '/pdf/Bilrutan Skadeblankett.pdf';
$outputPath = $projectRoot . '/pdf/.pdf-regression-' . bin2hex(random_bytes(6)) . '.pdf';
$generatorResult = create_skadeblankett_pdf_php(['notes' => str_repeat('W', 6000)], $templatePath, $outputPath, 'pdf');
$check(is_array($generatorResult) && ($generatorResult[0] ?? true) === false && ($generatorResult[2] ?? '') === 'skade.pdf_text_unfit', 'The PDF generator must refuse a field that cannot fit without clipping.');
$check(!file_exists($outputPath), 'An unfit submission must not leave a partial or misleading PDF.');

// A field that fits only below 5 pt should return warning metadata to the
// submission preflight, and the temporary test PDF must be removed afterwards.
$warningPath = $projectRoot . '/pdf/.pdf-regression-warning-' . bin2hex(random_bytes(6)) . '.pdf';
try {
    $warningResult = create_skadeblankett_pdf_php(['regnr' => str_repeat('W', 50)], $templatePath, $warningPath, 'pdf');
    $warningMeta = is_array($warningResult[2] ?? null) ? $warningResult[2] : [];
    $check(is_array($warningResult) && ($warningResult[0] ?? false) === true, 'Fitting small text should still produce a preview PDF.');
    $check((int) ($warningMeta['below_5pt_fields'] ?? 0) > 0, 'The PDF preflight must report fields rendered below 5 pt.');
    $check((float) ($warningMeta['minimum_font_pt'] ?? 5.0) < 5.0, 'The PDF preflight must report the actual smallest font size.');
} finally {
    if (is_file($warningPath)) {
        @unlink($warningPath);
    }
}

unset($GLOBALS['skade_pdf_text_fit_stats']);

if ($failures !== []) {
    fwrite(STDERR, "FAIL: " . implode("\nFAIL: ", $failures) . "\n");
    exit(1);
}

echo "PASS: {$checks} skadeblankett PDF regression checks.\n";
