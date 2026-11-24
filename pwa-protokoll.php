<?php
declare(strict_types=1);

// Dedicated Serviceprotokoll PWA entry point. Only protocol-form query state
// and public/private protocol media routes are forwarded to the shared router.
$allowedQueryKeys = [
    'protocol_view', 'draft_id', 'view_id', 'edit_id', 'copy_id',
    'protocol_from', 'protocol_to', 'protocol_reg', 'msg',
    'view_file', 'download_file',
];
$forwardedQuery = [];
$protocolSearchKeys = ['protocol_from', 'protocol_to', 'protocol_reg'];
foreach ($allowedQueryKeys as $key) {
    if (!array_key_exists($key, $_GET)) {
        continue;
    }
    if (is_string($_GET[$key]) || in_array($key, $protocolSearchKeys, true)) {
        // Keep malformed search-filter shapes so the records view can reject
        // them instead of silently treating an invalid search as no filter.
        $forwardedQuery[$key] = $_GET[$key];
    }
}
$_GET = $forwardedQuery;
$_GET['tab'] = 'protocol';
define('TADEGA_PWA_APP', 'protocol');
require __DIR__ . '/index.php';
