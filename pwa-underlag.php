<?php
declare(strict_types=1);

// Dedicated Fakturaunderlag PWA entry point. Query state is restricted to the
// invoice work area; other portal controllers cannot be reached through it.
$allowedQueryKeys = [
    'invoice_view', 'draft_id', 'edit_id', 'copy_id', 'customer_id',
    'customer_ref', 'edit_article', 'msg', 'view_file', 'download_file',
];
$forwardedQuery = [];
foreach ($allowedQueryKeys as $key) {
    if (isset($_GET[$key]) && is_string($_GET[$key])) {
        $forwardedQuery[$key] = $_GET[$key];
    }
}
$_GET = $forwardedQuery;
$_GET['tab'] = 'invoice';
define('TADEGA_PWA_APP', 'invoice');
require __DIR__ . '/index.php';
