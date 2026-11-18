<?php
declare(strict_types=1);

// A clean customer-facing route for a shared tablet or phone. Keep the page
// pinned to customer mode; only forward public shell assets, the original PDF
// template, or a tightly-shaped generated PDF path. The shared file route still
// verifies that generated PDFs belong to this session's completed submission.
$customerDone = isset($_GET['done']) && is_string($_GET['done']) && $_GET['done'] === '1';
$customerMailStatus = isset($_GET['mail']) && is_string($_GET['mail']) && in_array($_GET['mail'], ['sent', 'failed'], true)
    ? $_GET['mail']
    : '';
$customerTextFitWarning = isset($_GET['text_fit_warning']) && is_string($_GET['text_fit_warning']) && $_GET['text_fit_warning'] === '1';
$customerFileRoutes = [];
$customerPublicAssets = [
    'assets/apple-touch-icon.png',
    'assets/pwa-icon-192.png',
    'assets/pwa-icon-512.png',
    'assets/portal.css',
    'assets/signature_pad.js',
];
$customerPublicTemplates = [
    'pdf/Bilrutan Skadeblankett.pdf',
    'pdf/Bilrutan_Skadeblankett.pdf',
];
foreach (['view_file', 'download_file'] as $customerFileKey) {
    $customerFile = isset($_GET[$customerFileKey]) && is_string($_GET[$customerFileKey])
        ? $_GET[$customerFileKey]
        : '';
    $isGeneratedCustomerPdf = preg_match(
        '~\\Apdf/([A-Z0-9-]{2,12})/Skadeblankett-Bilglas-\\1-\\d{8}-\\d{6}-[a-f0-9]{6}\\.pdf\\z~D',
        $customerFile
    ) === 1;
    if (
        in_array($customerFile, $customerPublicAssets, true) ||
        in_array($customerFile, $customerPublicTemplates, true) ||
        $isGeneratedCustomerPdf
    ) {
        $customerFileRoutes[$customerFileKey] = $customerFile;
    }
}
$_GET = [
    'tab' => 'skadeblankett',
    'mode' => 'customer',
];
if ($customerDone) {
    $_GET['done'] = '1';
}
if ($customerMailStatus !== '') {
    $_GET['mail'] = $customerMailStatus;
}
if ($customerTextFitWarning) {
    $_GET['text_fit_warning'] = '1';
}
foreach ($customerFileRoutes as $customerFileKey => $customerFile) {
    $_GET[$customerFileKey] = $customerFile;
}

// Installable customer PWA uses a route-scoped manifest/worker and can never
// switch this entry point to another portal area through query parameters.
define('TADEGA_PWA_APP', 'skadeblankett');
require __DIR__ . '/index.php';
