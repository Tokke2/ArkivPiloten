<?php
declare(strict_types=1);
/**
 * Tadega Portal — refreshed application shell and request controller.
 * Access control is expected to be enforced by the hosting/proxy layer, as
 * selected for this deployment. Protect the complete /dokument path, including
 * static files, not just this PHP entry point.
 */
error_reporting(E_ALL);
ini_set('display_errors', '0');
ini_set('log_errors', '1');
require_once __DIR__ . '/includes/logger.php';
TadegaPrivacyLogger::registerErrorHandlers();

// Tabs retain their POST handlers for backward compatibility. Buffer the shell
// so tab-level redirects still set HTTP headers before any markup is sent.
if (ob_get_level() === 0 && !headers_sent()) {
    ob_start();
}

if (!headers_sent()) {
    header('X-Content-Type-Options: nosniff');
    header('X-Frame-Options: SAMEORIGIN');
    header('Referrer-Policy: strict-origin-when-cross-origin');
    // Permit only this same-origin portal to initiate camera capture for a service-protocol photo.
    header('Permissions-Policy: camera=(self), microphone=(), geolocation=()');
    header('Cache-Control: no-store, private, max-age=0, must-revalidate');
    header('Pragma: no-cache');
    header("Content-Security-Policy: default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'");
}

// A scoped PWA entry point pins this request to its own form area. The wrapper
// routes preserve query parameters needed for that area, but cannot be switched
// to another portal tab by changing ?tab= in the address bar or a POST URL.
$portalPwaConfig = [
    'protocol' => ['tab' => 'protocol', 'entry' => 'pwa-protokoll.php', 'manifest' => 'manifest-protokoll.webmanifest'],
    'invoice' => ['tab' => 'invoice', 'entry' => 'pwa-underlag.php', 'manifest' => 'manifest-underlag.webmanifest'],
    'skadeblankett' => ['tab' => 'skadeblankett', 'entry' => 'skadeblankett-kund.php', 'manifest' => 'manifest-skadeblankett.webmanifest'],
];
$portalPwaApp = defined('TADEGA_PWA_APP') && is_string(TADEGA_PWA_APP) && isset($portalPwaConfig[TADEGA_PWA_APP])
    ? TADEGA_PWA_APP
    : '';
$portalIsScopedPwa = $portalPwaApp !== '';
$portalPwaEntry = $portalIsScopedPwa ? $portalPwaConfig[$portalPwaApp]['entry'] : '';
$portalPwaManifest = $portalIsScopedPwa ? $portalPwaConfig[$portalPwaApp]['manifest'] : '';
if ($portalIsScopedPwa) {
    $_GET['tab'] = $portalPwaConfig[$portalPwaApp]['tab'];
}

// The protocol tab uses its own session cookie after invoice auth is configured.
// Search keeps the invoice session active and reads the optional protocol session
// separately; the customer register continues to share the invoice PIN session.
// During first-admin setup, keep the default portal session for its CSRF token.
$requestedSessionTab = isset($_GET['tab']) && is_string($_GET['tab']) ? $_GET['tab'] : 'protocol';
if (!in_array($requestedSessionTab, ['protocol', 'search', 'invoice', 'skadeblankett', 'files', 'archive', 'customers', 'settings', 'admin'], true)) {
    $requestedSessionTab = 'protocol';
}
$useProtocolSession = false;
$invoiceUsersPathForSession = __DIR__ . '/storage/invoice_users.json';
$storagePathForSession = __DIR__ . '/storage';
if (
    $requestedSessionTab === 'protocol' && !is_link($storagePathForSession) &&
    !is_link($invoiceUsersPathForSession) && is_file($invoiceUsersPathForSession) && is_readable($invoiceUsersPathForSession)
) {
    $invoiceUsersRawForSession = @file_get_contents($invoiceUsersPathForSession);
    if (is_string($invoiceUsersRawForSession)) {
        try {
            $invoiceUsersForSession = json_decode($invoiceUsersRawForSession, true, 512, JSON_THROW_ON_ERROR);
            $useProtocolSession = is_array($invoiceUsersForSession) && $invoiceUsersForSession !== [];
        } catch (JsonException) {
            $useProtocolSession = false;
        }
    }
}
if ($useProtocolSession && session_status() !== PHP_SESSION_ACTIVE && !headers_sent()) {
    session_name('TADEGA_PROTOCOL_SESSID');
}

if (session_status() !== PHP_SESSION_ACTIVE && !headers_sent()) {
    ini_set('session.use_strict_mode', '1');

    // Keep PHP session files inside the portal's private, web-denied storage
    // directory. Do not silently fall back to the host's external temp path.
    $storageDir = __DIR__ . '/storage';
    $storageGuard = $storageDir . '/.htaccess';
    $sessionDir = $storageDir . '/sessions';
    if (is_link($storageDir) || is_link($storageGuard) || is_link($sessionDir) || !is_file($storageGuard)) {
        http_response_code(503);
        exit('Portalen kan inte starta en skyddad session. Kontrollera den privata storage-mappen.');
    }
    if (!is_dir($sessionDir)) {
        $oldUmask = umask(0077);
        $created = @mkdir($sessionDir, 0700, true);
        umask($oldUmask);
        if (!$created && !is_dir($sessionDir)) {
            http_response_code(503);
            exit('Portalen kan inte skapa sin privata sessionsmapp. Kontrollera rättigheterna för storage.');
        }
    }
    $realStorageDir = realpath($storageDir);
    $realSessionDir = realpath($sessionDir);
    if (
        $realStorageDir === false || $realSessionDir === false ||
        dirname($realSessionDir) !== $realStorageDir || !is_dir($realSessionDir) || !is_writable($realSessionDir)
    ) {
        http_response_code(503);
        exit('Portalen kan inte använda sin privata sessionsmapp. Kontrollera rättigheterna för storage/sessions.');
    }
    @chmod($realSessionDir, 0700);
    @session_save_path($realSessionDir);
    if (session_save_path() !== $realSessionDir) {
        http_response_code(503);
        exit('Portalen kan inte placera sessioner i den privata sessionsmappen.');
    }

    $cookiePath = rtrim(dirname($_SERVER['SCRIPT_NAME'] ?? '/'), '/') . '/';
    if ($cookiePath === '//') {
        $cookiePath = '/';
    }
    session_set_cookie_params([
        'lifetime' => 0,
        'path' => $cookiePath,
        'secure' => true,
        'httponly' => true,
        'samesite' => 'Strict',
    ]);
    if (!@session_start() && session_status() !== PHP_SESSION_ACTIVE) {
        http_response_code(503);
        exit('Portalen kunde inte starta en privat session.');
    }
}

require_once __DIR__ . '/functions.php';
require_once __DIR__ . '/includes/ui_components.php';
require_once __DIR__ . '/includes/invoice_auth.php';
require_once __DIR__ . '/includes/protocol_auth.php';
require_once __DIR__ . '/includes/central_admin_auth.php';
require_once __DIR__ . '/includes/autosaved_drafts.php';
require_once __DIR__ . '/includes/email_status.php';
require_once __DIR__ . '/includes/send_protocol_email.php';
require_once __DIR__ . '/includes/invoice_catalog.php';
require_once __DIR__ . '/includes/protocol_catalog.php';
require_once __DIR__ . '/includes/portal_search.php';
require_once __DIR__ . '/includes/release_updater.php';

/** Read the separate protocol login while preserving the active invoice session. */
function portal_search_protocol_auth_user(): ?array
{
    if (session_status() !== PHP_SESSION_ACTIVE) {
        return null;
    }
    if (function_exists('portal_central_admin_auth_portal_user')) {
        $centralAdmin = portal_central_admin_auth_portal_user();
        if (is_array($centralAdmin)) {
            return $centralAdmin;
        }
    }
    $protocolSessionName = portal_protocol_auth_session_name();
    if (session_name() === $protocolSessionName) {
        return portal_protocol_auth_current_user();
    }
    $protocolSessionId = $_COOKIE[$protocolSessionName] ?? null;
    if (!is_string($protocolSessionId) || !preg_match('/\\A[A-Za-z0-9,-]{16,128}\\z/D', $protocolSessionId)) {
        return null;
    }

    $primarySessionName = session_name();
    $primarySessionId = session_id();
    if (
        $primarySessionName === '' || $primarySessionId === '' ||
        !@session_write_close() || session_status() === PHP_SESSION_ACTIVE
    ) {
        return null;
    }

    $_SESSION = [];
    $protocolUser = null;
    try {
        session_name($protocolSessionName);
        session_id($protocolSessionId);
        if (@session_start() && session_name() === $protocolSessionName) {
            $protocolUser = portal_protocol_auth_current_user();
        }
    } finally {
        if (session_status() === PHP_SESSION_ACTIVE) {
            @session_write_close();
        }
        $_SESSION = [];
        session_name($primarySessionName);
        session_id($primarySessionId);
        if (!@session_start() || session_name() !== $primarySessionName || session_status() !== PHP_SESSION_ACTIVE) {
            http_response_code(503);
            exit('Portalen kunde inte återuppta den ordinarie sessionen.');
        }
    }

    return is_array($protocolUser) ? $protocolUser : null;
}

$portalTabs = [
    'protocol' => ['Serviceprotokoll', 'Skapa och spara verkstadsprotokoll.'],
    'search' => ['Sök', 'Sök i de dokument och register du har behörighet att se.'],
    'invoice' => ['Fakturaunderlag', 'Samla arbetstid, material och belopp.'],
    'skadeblankett' => ['Skadeblankett', 'Fyll i skadeunderlag och skapa PDF.'],
    'files' => ['PDF-arkiv', 'Hitta och hantera arkiverade dokument.'],
    'archive' => ['Historik', 'Överblick över sparade dokument och filer.'],
    'customers' => ['Kundregister', 'Hitta och hantera kunduppgifter.'],
    'settings' => ['Inställningar', 'E-post och företagsinställningar.'],
    'admin' => ['Adminpanel', 'Central behörighet och åtkomst till portalens personalsidor.'],
];

$activeTab = isset($_GET['tab']) && is_string($_GET['tab']) ? $_GET['tab'] : 'protocol';
if (!isset($portalTabs[$activeTab])) {
    $activeTab = 'protocol';
}

// Existing invoice/protocol accounts remain intact. The separate central admin
// credential adds cross-portal administrator access without replacing either account store.
$invoiceSetupState = portal_invoice_auth_setup_state();
$centralAdminSetupState = portal_central_admin_auth_setup_state();
$centralAdminUser = !$portalIsScopedPwa ? portal_central_admin_auth_current_user() : null;
$centralAdminNeedsPinChange = is_array($centralAdminUser) && ($centralAdminUser['must_change_pin'] ?? false) === true;
$centralAdminCanAccess = !$portalIsScopedPwa && portal_central_admin_auth_can_access_personal_portal();
if ($invoiceSetupState === 'unconfigured' && !$portalIsScopedPwa && $activeTab !== 'admin' && !$centralAdminCanAccess) {
    $activeTab = 'invoice';
}
if (!$portalIsScopedPwa && $activeTab === 'admin' && $centralAdminSetupState === 'unconfigured') {
    // After the existing invoice admin signs in, return here to finish the
    // one-time central-admin enrollment (also across first invoice setup).
    $_SESSION['portal_invoice_login_return_tab'] = 'admin';
}
$isSkadeCustomerMode = $activeTab === 'skadeblankett'
    && isset($_GET['mode']) && is_string($_GET['mode']) && $_GET['mode'] === 'customer'
    && basename($_SERVER['SCRIPT_NAME'] ?? '') === 'skadeblankett-kund.php';
TadegaPrivacyLogger::cleanupDiagnostics(30);
$protocolAuthUser = ($invoiceSetupState === 'configured' || $centralAdminCanAccess)
    ? ($activeTab === 'protocol'
        ? portal_protocol_auth_current_user()
        : ($activeTab === 'search' ? portal_search_protocol_auth_user() : null))
    : null;
$invoiceAuthUser = in_array($activeTab, ['invoice', 'customers', 'search', 'admin'], true)
    && ($invoiceSetupState !== 'unconfigured' || $centralAdminCanAccess)
    ? portal_invoice_auth_current_user()
    : null;

function portal_redirect(string $tab, string $message = '', array $context = []): never
{
    $allowed = ['protocol', 'search', 'invoice', 'skadeblankett', 'files', 'archive', 'customers', 'settings', 'admin'];
    if (!in_array($tab, $allowed, true)) {
        $tab = 'protocol';
    }
    $requestedInvoiceView = isset($_GET['invoice_view']) && is_string($_GET['invoice_view']) ? $_GET['invoice_view'] : '';
    $viewSuffix = $tab === 'invoice' && in_array($requestedInvoiceView, ['admin', 'email', 'debug', 'articles', 'customers', 'processing', 'invoice_history'], true)
        ? '&invoice_view=' . rawurlencode($requestedInvoiceView)
        : '';
    $contextSuffix = '';
    if ($tab === 'invoice') {
        foreach (['draft_id', 'edit_id', 'copy_id'] as $contextKey) {
            $contextValue = isset($_GET[$contextKey]) && is_string($_GET[$contextKey]) ? $_GET[$contextKey] : '';
            if ($contextValue !== '' && preg_match('/\A[A-Za-z0-9_-]{1,128}\z/D', $contextValue)) {
                $contextSuffix .= '&' . rawurlencode($contextKey) . '=' . rawurlencode($contextValue);
            }
        }
    }
    if ($tab === 'protocol') {
        foreach (['view_id', 'edit_id', 'draft_id'] as $contextKey) {
            $contextValue = isset($context[$contextKey]) && is_string($context[$contextKey])
                ? $context[$contextKey]
                : (isset($_GET[$contextKey]) && is_string($_GET[$contextKey]) ? $_GET[$contextKey] : '');
            if ($contextValue !== '' && preg_match('/\\A[A-Za-z0-9_-]{1,128}\\z/D', $contextValue)) {
                $contextSuffix .= '&' . rawurlencode($contextKey) . '=' . rawurlencode($contextValue);
            }
        }
    }
    $suffix = $message !== '' ? '&msg=' . rawurlencode($message) : '';
    if (ob_get_level() > 0 && !headers_sent()) {
        ob_clean();
    }
    header('Location: ?tab=' . rawurlencode($tab) . $viewSuffix . $contextSuffix . $suffix, true, 303);
    exit;
}

if ($centralAdminNeedsPinChange && !$portalIsScopedPwa && $activeTab !== 'admin') {
    portal_redirect('admin', 'central_admin_pin_expired');
}

if ($activeTab === 'customers' && !is_array($invoiceAuthUser)) {
    if ($invoiceSetupState === 'configured') {
        $_SESSION['portal_invoice_login_return_tab'] = 'customers';
        portal_redirect('invoice', 'invoice_login_required');
    }
    portal_redirect('invoice', $invoiceSetupState === 'error' ? 'invoice_setup_storage_error' : 'invoice_login_required');
}

function portal_post_text(array $source, string $key, int $maxLength): ?string
{
    $value = $source[$key] ?? '';
    if (!is_string($value)) {
        return null;
    }
    $value = str_replace(["\r\n", "\r"], "\n", $value);
    $value = trim($value);
    if (preg_match('//u', $value) !== 1 || preg_match('/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/u', $value)) {
        return null;
    }
    $length = function_exists('mb_strlen') ? mb_strlen($value, 'UTF-8') : strlen($value);
    if ($length > $maxLength) {
        return null;
    }
    return $value;
}

function portal_valid_iso_date(string $value): bool
{
    if (!preg_match('/\A(\d{4})-(\d{2})-(\d{2})\z/', $value, $parts)) {
        return false;
    }
    return checkdate((int) $parts[2], (int) $parts[3], (int) $parts[1]);
}

function portal_random_id(): string
{
    return bin2hex(random_bytes(16));
}

function portal_json_response(array $payload, int $status = 200): never
{
    http_response_code($status);
    header('Content-Type: application/json; charset=UTF-8');
    header('Cache-Control: no-store, private, max-age=0, must-revalidate');
    echo json_encode($payload, JSON_INVALID_UTF8_SUBSTITUTE);
    exit;
}

function portal_process_items(mixed $rawItems, string $kind): ?array
{
    if (!is_array($rawItems) || count($rawItems) > 100) {
        return null;
    }
    $items = [];
    foreach ($rawItems as $row) {
        if (!is_array($row)) {
            return null;
        }
        if ($kind === 'invoice') {
            $name = portal_post_text($row, 'art', 200);
            $unit = portal_post_text($row, 'unit', 12);
            $qtyRaw = $row['qty'] ?? '';
            $priceRaw = $row['price'] ?? '';
            if ($name === null || $unit === null || (!is_string($qtyRaw) && !is_numeric($qtyRaw)) || (!is_string($priceRaw) && !is_numeric($priceRaw))) {
                return null;
            }
            $unit = trim($unit);
            if ($unit === '') {
                $unit = 'st';
            }
            $qtyRaw = trim((string) $qtyRaw);
            $priceRaw = trim((string) $priceRaw);
            if ($name === '' && $qtyRaw === '' && $priceRaw === '') {
                continue;
            }
            if (!is_numeric($qtyRaw) || !is_numeric($priceRaw)) {
                return null;
            }
            $qty = (float) $qtyRaw;
            $price = (float) $priceRaw;
            if (!is_finite($qty) || !is_finite($price) || $qty < 0 || $qty > 100000 || $price < 0 || $price > 10000000) {
                return null;
            }
            if ($name === '' || !in_array($unit, array_keys(portal_invoice_catalog_units()), true)) {
                return null;
            }
            $items[] = ['art' => $name, 'unit' => $unit, 'qty' => $qty, 'price' => $price];
        } else {
            $name = portal_post_text($row, 'art', 200);
            $qtyRaw = $row['qty'] ?? '';
            $spec = portal_post_text($row, 'spec', 300);
            if ($name === null || $spec === null || (!is_string($qtyRaw) && !is_numeric($qtyRaw))) {
                return null;
            }
            $qtyRaw = trim((string) $qtyRaw);
            if ($name === '' && $qtyRaw === '' && $spec === '') {
                continue;
            }
            if ($qtyRaw !== '' && (!is_numeric($qtyRaw) || !is_finite((float) $qtyRaw) || (float) $qtyRaw < 0 || (float) $qtyRaw > 100000)) {
                return null;
            }
            $items[] = ['art' => $name, 'qty' => $qtyRaw === '' ? '' : (float) $qtyRaw, 'spec' => $spec];
        }
    }
    return $items;
}

function portal_protocol_content_hash(array $protocol): string
{
    $text = static function (mixed $value): string {
        if (!is_scalar($value)) {
            return '';
        }
        return trim(str_replace(["\r\n", "\r"], "\n", (string) $value));
    };
    $registration = strtoupper(preg_replace('/[^A-Z0-9 -]/i', '', $text($protocol['reg'] ?? $protocol['regnr'] ?? '')) ?? '');
    $mileage = preg_replace('/[\\s\\x{00A0}\\x{202F}\\x{2009}\\x{2007}]+/u', '', $text($protocol['km'] ?? ''));
    $items = portal_process_items($protocol['items'] ?? [], 'protocol');
    $normalized = [
        'reg' => $registration,
        'date' => $text($protocol['date'] ?? ''),
        'km' => is_string($mileage) ? $mileage : '',
        'customer' => $text($protocol['customer'] ?? ''),
        'tech' => $text($protocol['tech'] ?? ''),
        'description' => $text($protocol['description'] ?? ''),
        'items' => $items ?? ['invalid_saved_items'],
        'meter_photo_file' => $text($protocol['meter_photo_file'] ?? ''),
    ];
    $encoded = json_encode($normalized, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);
    return hash('sha256', is_string($encoded) ? $encoded : 'invalid-protocol-content');
}

function portal_protocol_media_directory(): string|false
{
    $uploadsDirectory = __DIR__ . '/uploads';
    $mediaDirectory = $uploadsDirectory . '/protocols';
    if (is_link($uploadsDirectory) || is_link($mediaDirectory) || !is_dir($uploadsDirectory)) {
        return false;
    }
    if (!is_dir($mediaDirectory)) {
        $oldUmask = umask(0077);
        $created = @mkdir($mediaDirectory, 0700);
        umask($oldUmask);
        if (!$created && !is_dir($mediaDirectory)) {
            return false;
        }
    }
    if (is_link($mediaDirectory)) {
        return false;
    }
    $realUploadsDirectory = realpath($uploadsDirectory);
    $realMediaDirectory = realpath($mediaDirectory);
    if (
        $realUploadsDirectory === false || $realMediaDirectory === false ||
        dirname($realMediaDirectory) !== $realUploadsDirectory || !is_dir($realMediaDirectory) || !is_writable($realMediaDirectory)
    ) {
        return false;
    }
    return $realMediaDirectory;
}

function portal_protocol_media_file(mixed $relativeFile, string $mediaDirectory): string
{
    if (!is_string($relativeFile) || !preg_match('/\\Auploads\\/protocols\\/[a-f0-9]{32}\\.(?:png|jpe?g)\\z/i', $relativeFile)) {
        return '';
    }
    $candidate = __DIR__ . DIRECTORY_SEPARATOR . str_replace('/', DIRECTORY_SEPARATOR, $relativeFile);
    $realCandidate = realpath($candidate);
    if (
        $realCandidate === false || is_link($candidate) || dirname($realCandidate) !== $mediaDirectory || !is_file($realCandidate)
    ) {
        return '';
    }
    return $relativeFile;
}

function portal_protocol_prepare_meter_photo_upload(mixed $upload): array|false|null
{
    if ($upload === null) {
        return null;
    }
    if (!is_array($upload) || is_array($upload['error'] ?? null)) {
        return false;
    }
    $error = $upload['error'] ?? UPLOAD_ERR_NO_FILE;
    if (!is_int($error)) {
        return false;
    }
    if ($error === UPLOAD_ERR_NO_FILE) {
        return null;
    }
    if ($error !== UPLOAD_ERR_OK) {
        return false;
    }
    $temporaryFile = $upload['tmp_name'] ?? null;
    if (!is_string($temporaryFile) || $temporaryFile === '' || !is_uploaded_file($temporaryFile)) {
        return false;
    }
    $size = @filesize($temporaryFile);
    if (!is_int($size) || $size < 1 || $size > 12582912) {
        return false;
    }
    $image = @getimagesize($temporaryFile);
    if (!is_array($image)) {
        return false;
    }
    $mime = (string) ($image['mime'] ?? '');
    $extension = match ($mime) {
        'image/jpeg' => 'jpg',
        'image/png' => 'png',
        default => '',
    };
    $width = (int) ($image[0] ?? 0);
    $height = (int) ($image[1] ?? 0);
    if ($extension === '' || $width < 1 || $height < 1 || $width > 12000 || $height > 12000 || $width * $height > 60000000) {
        return false;
    }
    $bytes = @file_get_contents($temporaryFile);
    if (!is_string($bytes) || strlen($bytes) !== $size) {
        return false;
    }
    return ['bytes' => $bytes, 'extension' => $extension];
}

function portal_protocol_signature_bytes(mixed $dataUri): string|false|null
{
    if ($dataUri === null || $dataUri === '') {
        return null;
    }
    if (!is_string($dataUri) || strlen($dataUri) > 1400000 || !preg_match('/\\Adata:image\\/png;base64,([A-Za-z0-9+\\/]+={0,2})\\z/', $dataUri, $matches)) {
        return false;
    }
    $bytes = base64_decode($matches[1], true);
    if (!is_string($bytes) || strlen($bytes) < 100 || strlen($bytes) > 1048576) {
        return false;
    }
    $image = @getimagesizefromstring($bytes);
    if (!is_array($image) || (int) ($image[0] ?? 0) !== 1000 || (int) ($image[1] ?? 0) !== 220 || ($image['mime'] ?? '') !== 'image/png') {
        return false;
    }
    if (function_exists('imagecreatefromstring')) {
        $bitmap = @imagecreatefromstring($bytes);
        if ($bitmap === false) {
            return false;
        }
        $hasInk = false;
        for ($y = 0; $y < 220 && !$hasInk; $y += 2) {
            for ($x = 0; $x < 1000; $x += 2) {
                $rgba = imagecolorat($bitmap, $x, $y);
                if (imageistruecolor($bitmap)) {
                    $alpha = ($rgba >> 24) & 0x7f;
                    $red = ($rgba >> 16) & 0xff;
                    $green = ($rgba >> 8) & 0xff;
                    $blue = $rgba & 0xff;
                } else {
                    $color = imagecolorsforindex($bitmap, $rgba);
                    $alpha = (int) ($color['alpha'] ?? 0);
                    $red = (int) ($color['red'] ?? 255);
                    $green = (int) ($color['green'] ?? 255);
                    $blue = (int) ($color['blue'] ?? 255);
                }
                if ($alpha < 120 && ($red < 235 || $green < 235 || $blue < 235)) {
                    $hasInk = true;
                    break;
                }
            }
        }
        imagedestroy($bitmap);
        if (!$hasInk) {
            return false;
        }
    }
    return $bytes;
}

function portal_protocol_store_media(string $bytes, string $extension, string $mediaDirectory): array|false
{
    if ($bytes === '' || strlen($bytes) > 12582912 || !in_array($extension, ['png', 'jpg'], true)) {
        return false;
    }
    $filename = portal_random_id() . '.' . $extension;
    $absoluteFile = $mediaDirectory . DIRECTORY_SEPARATOR . $filename;
    if (file_exists($absoluteFile) || is_link($absoluteFile)) {
        return false;
    }
    $oldUmask = umask(0077);
    $handle = @fopen($absoluteFile, 'xb');
    umask($oldUmask);
    if (!is_resource($handle)) {
        return false;
    }
    $length = strlen($bytes);
    $written = 0;
    while ($written < $length) {
        $count = @fwrite($handle, substr($bytes, $written));
        if (!is_int($count) || $count < 1) {
            break;
        }
        $written += $count;
    }
    $flushed = @fflush($handle);
    fclose($handle);
    if ($written !== $length || !$flushed || !@chmod($absoluteFile, 0600)) {
        @unlink($absoluteFile);
        return false;
    }
    return [
        'relative' => 'uploads/protocols/' . $filename,
        'absolute' => $absoluteFile,
    ];
}

function portal_protocol_delete_media(mixed $relativeFile, string $mediaDirectory): void
{
    $safeRelative = portal_protocol_media_file($relativeFile, $mediaDirectory);
    if ($safeRelative === '') {
        return;
    }
    $absoluteFile = __DIR__ . DIRECTORY_SEPARATOR . str_replace('/', DIRECTORY_SEPARATOR, $safeRelative);
    @unlink($absoluteFile);
}

function portal_save_protocol(): string|false
{
    unset($_SESSION['portal_protocol_save_failure']);
    $protocolUser = portal_protocol_auth_current_user();
    if (!is_array($protocolUser)) {
        return false;
    }
    $p = $_POST['p'] ?? null;
    if (!is_array($p)) {
        return false;
    }
    $fields = [
        'reg' => portal_post_text($p, 'reg', 20),
        'date' => portal_post_text($p, 'date', 10),
        'km' => portal_post_text($p, 'km', 20),
        'customer' => portal_post_text($p, 'customer', 180),
        'tech' => portal_post_text($p, 'tech', 120),
        'description' => portal_post_text($p, 'description', 5000),
        'id' => portal_post_text($p, 'id', 128),
    ];
    foreach ($fields as $value) {
        if ($value === null) {
            return false;
        }
    }
    $reg = strtoupper(preg_replace('/[^A-Z0-9 -]/i', '', $fields['reg']));
    if ($reg === '' || strlen($reg) > 12) {
        return false;
    }
    if ($fields['date'] !== '' && !portal_valid_iso_date($fields['date'])) {
        return false;
    }
    $km = preg_replace('/[\\s\\x{00A0}\\x{202F}\\x{2009}\\x{2007}]+/u', '', $fields['km']);
    if (!is_string($km) || ($km !== '' && (!preg_match('/\\A\\d+\\z/', $km) || (float) $km > 99999999))) {
        return false;
    }
    $items = portal_process_items($_POST['items'] ?? [], 'protocol');
    if ($items === null) {
        return false;
    }

    $photoUpload = portal_protocol_prepare_meter_photo_upload($_FILES['protocol_meter_photo'] ?? null);
    if ($photoUpload === false) {
        return false;
    }
    $signatureValue = $p['signature_png'] ?? '';
    if (!is_string($signatureValue)) {
        return false;
    }
    $signatureBytes = portal_protocol_signature_bytes($signatureValue);
    if ($signatureBytes === false) {
        return false;
    }
    $removeSignatureValue = $p['signature_remove'] ?? '0';
    if ((!is_string($removeSignatureValue) && !is_int($removeSignatureValue)) || !in_array((string) $removeSignatureValue, ['', '0', '1'], true)) {
        return false;
    }
    $removeSignature = (string) $removeSignatureValue === '1';

    $records = load_data(PROTOCOLS_FILE, []);
    if (!is_array($records)) {
        return false;
    }
    $editIndex = null;
    if ($fields['id'] !== '') {
        foreach ($records as $index => $record) {
            if (is_array($record) && (string) ($record['id'] ?? '') === $fields['id']) {
                $editIndex = $index;
                break;
            }
        }
        if ($editIndex === null) {
            return false;
        }
    }
    $old = $editIndex !== null ? $records[$editIndex] : [];
    $mediaDirectory = portal_protocol_media_directory();
    if ($mediaDirectory === false) {
        return false;
    }
    $oldPhotoFile = portal_protocol_media_file($old['meter_photo_file'] ?? null, $mediaDirectory);
    $oldSignatureFile = portal_protocol_media_file($old['signature_file'] ?? null, $mediaDirectory);
    $nextPhotoFile = $oldPhotoFile;
    $nextSignatureFile = $signatureBytes !== null ? '' : ($removeSignature ? '' : $oldSignatureFile);
    $contentChanged = false;
    if ($editIndex !== null) {
        $oldContent = $old;
        $oldContent['meter_photo_file'] = $oldPhotoFile;
        $newContent = [
            'reg' => $reg,
            'date' => $fields['date'] !== '' ? $fields['date'] : date('Y-m-d'),
            'km' => $km,
            'customer' => $fields['customer'],
            'tech' => $fields['tech'],
            'description' => $fields['description'],
            'items' => $items,
            'meter_photo_file' => is_array($photoUpload) ? '__new_uploaded_photo__' : $oldPhotoFile,
        ];
        $contentChanged = portal_protocol_content_hash($oldContent) !== portal_protocol_content_hash($newContent);
    }
    if ($signatureBytes === null && ($nextSignatureFile === '' || $contentChanged)) {
        $_SESSION['portal_protocol_save_failure'] = 'signature_required';
        return false;
    }

    $newPhoto = null;
    $newSignature = null;
    if (is_array($photoUpload)) {
        $newPhoto = portal_protocol_store_media($photoUpload['bytes'], $photoUpload['extension'], $mediaDirectory);
        if ($newPhoto === false) {
            return false;
        }
        $nextPhotoFile = $newPhoto['relative'];
    }
    if ($signatureBytes !== null) {
        $newSignature = portal_protocol_store_media($signatureBytes, 'png', $mediaDirectory);
        if ($newSignature === false) {
            if (is_array($newPhoto)) {
                portal_protocol_delete_media($newPhoto['relative'], $mediaDirectory);
            }
            return false;
        }
        $nextSignatureFile = $newSignature['relative'];
    }
    $now = gmdate('Y-m-d\TH:i:s\Z');
    $actor = [
        'id' => (string) ($protocolUser['id'] ?? ''),
        'username' => (string) ($protocolUser['username'] ?? ''),
        'name' => (string) ($protocolUser['name'] ?? $protocolUser['username'] ?? ''),
    ];
    $history = $editIndex !== null && is_array($old['history'] ?? null)
        ? array_values(array_filter($old['history'], 'is_array'))
        : [];
    $history[] = [
        'action' => $editIndex === null ? 'created' : 'updated',
        'at' => $now,
        'actor' => $actor,
    ];
    $record = [
        'id' => $fields['id'] !== '' ? $fields['id'] : portal_random_id(),
        'nummer' => (string) ($old['nummer'] ?? get_next_protocol_number()),
        'reg' => $reg,
        'date' => $fields['date'] !== '' ? $fields['date'] : date('Y-m-d'),
        'km' => $km,
        'customer' => $fields['customer'],
        'tech' => $fields['tech'],
        'description' => $fields['description'],
        'items' => $items,
        'meter_photo_file' => $nextPhotoFile,
        'signature_file' => $nextSignatureFile,
        'updated_at' => $now,
        'updated_by' => $actor,
        'history' => $history,
    ];
    $previousEmailStatus = $editIndex !== null && is_array($old['internal_email_status'] ?? null) ? $old['internal_email_status'] : [];
    $previousEmailAttempts = is_numeric($previousEmailStatus['attempts'] ?? null) ? (int) $previousEmailStatus['attempts'] : 0;
    $record['internal_email_status'] = [
        'result' => 'pending',
        'transport' => 'none',
        'code' => 'pending',
        'attempts' => min(1000000, max(0, $previousEmailAttempts)),
        'last_attempt_at' => $now,
    ];
    if ($editIndex === null) {
        $record['created_at'] = $now;
        $record['created_by'] = $actor;
        $records[] = $record;
        $event = 'protocol.created';
    } else {
        if (isset($old['created_at']) && is_string($old['created_at'])) {
            $record['created_at'] = $old['created_at'];
        }
        if (isset($old['created_by']) && is_array($old['created_by'])) {
            $record['created_by'] = $old['created_by'];
        }
        $records[$editIndex] = $record;
        $event = 'protocol.updated';
    }
    if (!save_data(PROTOCOLS_FILE, array_values($records))) {
        if (is_array($newPhoto)) {
            portal_protocol_delete_media($newPhoto['relative'], $mediaDirectory);
        }
        if (is_array($newSignature)) {
            portal_protocol_delete_media($newSignature['relative'], $mediaDirectory);
        }
        return false;
    }
    if (is_array($newPhoto) && $oldPhotoFile !== '') {
        portal_protocol_delete_media($oldPhotoFile, $mediaDirectory);
    }
    if (is_array($newSignature) && $oldSignatureFile !== '') {
        portal_protocol_delete_media($oldSignatureFile, $mediaDirectory);
    }
    TadegaPrivacyLogger::event($event);
    return (string) $record['id'];
}

function portal_protocol_find_saved(string $protocolId): ?array
{
    if (!preg_match('/\\A[a-f0-9]{32}\\z/i', $protocolId)) {
        return null;
    }
    $records = load_data(PROTOCOLS_FILE, []);
    if (!is_array($records)) {
        return null;
    }
    foreach ($records as $record) {
        if (is_array($record) && (string) ($record['id'] ?? '') === $protocolId) {
            return $record;
        }
    }
    return null;
}

function portal_protocol_email_status_update(string $protocolId, array $delivery): bool
{
    if (!preg_match('/\\A[a-f0-9]{32}\\z/i', $protocolId)) {
        return false;
    }
    $result = in_array($delivery['result'] ?? '', ['accepted', 'failed', 'not_configured'], true)
        ? (string) $delivery['result']
        : 'failed';
    $transport = in_array($delivery['transport'] ?? '', ['smtp', 'php_mail', 'none', 'unavailable'], true)
        ? (string) $delivery['transport']
        : 'none';
    $rawCode = is_string($delivery['code'] ?? null) ? $delivery['code'] : 'unknown';
    $code = preg_match('/\\A[a-z0-9_]{1,64}\\z/i', $rawCode) ? $rawCode : 'unknown';
    $records = load_data(PROTOCOLS_FILE, []);
    if (!is_array($records)) {
        return false;
    }
    foreach ($records as $index => $record) {
        if (!is_array($record) || (string) ($record['id'] ?? '') !== $protocolId) {
            continue;
        }
        $previous = is_array($record['internal_email_status'] ?? null) ? $record['internal_email_status'] : [];
        $attempts = is_numeric($previous['attempts'] ?? null) ? (int) $previous['attempts'] : 0;
        $record['internal_email_status'] = [
            'result' => $result,
            'transport' => $transport,
            'code' => $code,
            'attempts' => min(1000000, max(0, $attempts) + 1),
            'last_attempt_at' => gmdate('Y-m-d\\TH:i:s\\Z'),
        ];
        $records[$index] = $record;
        return save_data(PROTOCOLS_FILE, array_values($records));
    }
    return false;
}

/** @return array{accepted:bool,result:string,transport:string,code:string} */
function portal_send_invoice_saved_email(array $invoice, string $kind = 'invoice_saved'): array
{
    if (!in_array($kind, ['invoice_saved', 'invoice_retry'], true)) {
        $kind = 'invoice_saved';
    }
    $settings = load_settings();
    $recipient = $settings['notification_email'] ?? '';
    if (!is_string($recipient) || !filter_var($recipient, FILTER_VALIDATE_EMAIL)) {
        portal_email_status_record('invoice', 'not_configured', $kind, 'none', 'recipient_not_configured');
        return ['accepted' => false, 'result' => 'not_configured', 'transport' => 'none', 'code' => 'recipient_not_configured'];
    }

    // Send to the configured primary internal recipient only. Never copy the
    // customer or the portal's additional notification recipients.
    $number = trim(preg_replace('/[\r\n\x00-\x1F\x7F]+/u', ' ', (string) ($invoice['nummer'] ?? '')) ?? '');
    $number = function_exists('mb_substr') ? mb_substr($number, 0, 100, 'UTF-8') : substr($number, 0, 100);
    $rawSubject = 'Tadega Portal – fakturaunderlag sparat' . ($number !== '' ? ' – ' . $number : '');
    $subject = function_exists('mb_encode_mimeheader')
        ? mb_encode_mimeheader($rawSubject, 'UTF-8', 'B', "\r\n")
        : '=?UTF-8?B?' . base64_encode($rawSubject) . '?=';

    $plainLine = static function (mixed $value, int $limit = 5000): string {
        $text = is_scalar($value) ? (string) $value : '';
        $text = str_replace(["\r\n", "\r"], "\n", $text);
        $text = preg_replace('/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/u', '', $text) ?? '';
        return function_exists('mb_substr') ? mb_substr($text, 0, $limit, 'UTF-8') : substr($text, 0, $limit);
    };
    $singleLine = static function (mixed $value, int $limit = 200): string {
        $text = is_scalar($value) ? (string) $value : '';
        $text = preg_replace('/[\r\n\x00-\x1F\x7F]+/u', ' ', $text) ?? '';
        $text = trim($text);
        return function_exists('mb_substr') ? mb_substr($text, 0, $limit, 'UTF-8') : substr($text, 0, $limit);
    };

    $body = [
        'Ett fakturaunderlag har sparats i Tadega Portal.',
        'Detta är en intern avisering; ingen kundkopia skickas.',
        '',
        'Underlagsnummer: ' . $number,
        'Fortnox fakturanummer: ' . $singleLine($invoice['fortnox_invoice_number'] ?? '', 80),
        'Fortnox fakturadatum: ' . $singleLine($invoice['fortnox_invoice_date'] ?? '', 10),
        'Underlagsdatum: ' . $singleLine($invoice['date'] ?? '', 10),
        'Kund/företag: ' . $singleLine($invoice['customer'] ?? '', 180),
        'Kundens referens: ' . $singleLine($invoice['ref'] ?? '', 160),
        '',
        'Vad underlaget gäller:',
        $plainLine($invoice['description'] ?? ''),
        '',
        'Moms: ' . (($invoice['vat_mode'] ?? 'ex') === 'inc' ? 'inkl. moms' : 'exkl. moms'),
        '',
        'Rader (antal och enhet × à-pris):',
    ];
    $invoiceUnitLabels = portal_invoice_catalog_units();
    foreach (is_array($invoice['items'] ?? null) ? $invoice['items'] : [] as $item) {
        if (!is_array($item)) {
            continue;
        }
        $quantity = is_numeric($item['qty'] ?? null) ? (float) $item['qty'] : 0.0;
        $price = is_numeric($item['price'] ?? null) ? (float) $item['price'] : 0.0;
        $lineTotal = round($quantity * $price, 2);
        $unit = is_scalar($item['unit'] ?? null) ? (string) $item['unit'] : 'st';
        if (!array_key_exists($unit, $invoiceUnitLabels)) {
            $unit = 'st';
        }
        $body[] = '- ' . $singleLine($item['art'] ?? '', 200)
            . ' — ' . number_format($quantity, 2, ',', ' ') . ' ' . $invoiceUnitLabels[$unit]
            . ' × ' . number_format($price, 2, ',', ' ') . ' kr'
            . ' = ' . number_format($lineTotal, 2, ',', ' ') . ' kr';
    }
    $body[] = '';
    $body[] = 'Fakturaunderlaget är inte en faktura och förs inte automatiskt över till det separata fakturasystemet.';
    $body[] = 'Separat fakturasystem: https://tadega.com/faktura/';
    $body[] = '';
    $body[] = 'Tadega Portal';

    $headers = "From: Tadega Portal <noreply@tadega.com>\r\n";
    $headers .= "MIME-Version: 1.0\r\nContent-Type: text/plain; charset=UTF-8\r\n";
    $delivery = portal_email_transport_send($recipient, $subject, implode("\r\n", $body), $headers);
    $accepted = ($delivery['accepted'] ?? false) === true;
    $transport = is_string($delivery['transport'] ?? null) && in_array($delivery['transport'], ['smtp', 'php_mail'], true) ? $delivery['transport'] : 'none';
    $result = $accepted ? 'accepted' : 'failed';
    $code = is_string($delivery['code'] ?? null) ? $delivery['code'] : 'unknown';
    portal_email_status_record('invoice', $result, $kind, $transport, $code);
    return ['accepted' => $accepted, 'result' => $result, 'transport' => $transport, 'code' => $code];
}

function portal_invoice_email_status_update(string $invoiceId, array $emailResult, array $actor): bool
{
    if (!preg_match('/\A[a-f0-9]{32}\z/i', $invoiceId)) {
        return false;
    }
    $result = is_string($emailResult['result'] ?? null) && in_array($emailResult['result'], ['accepted', 'failed', 'not_configured'], true)
        ? $emailResult['result']
        : 'failed';
    $transport = is_string($emailResult['transport'] ?? null) && in_array($emailResult['transport'], ['smtp', 'php_mail', 'none'], true)
        ? $emailResult['transport']
        : 'none';
    $code = is_string($emailResult['code'] ?? null) && in_array($emailResult['code'], portal_email_status_known_codes(), true)
        ? $emailResult['code']
        : 'unknown';
    $records = load_data(INVOICES_FILE, []);
    foreach ($records as $index => $record) {
        if (!is_array($record) || (string) ($record['id'] ?? '') !== $invoiceId) {
            continue;
        }
        $previousStatus = is_array($record['internal_email_status'] ?? null) ? $record['internal_email_status'] : [];
        $safeActor = [
            'id' => (string) ($actor['id'] ?? ''),
            'username' => (string) ($actor['username'] ?? ''),
            'name' => (string) ($actor['name'] ?? $actor['username'] ?? ''),
        ];
        $record['internal_email_status'] = [
            'result' => $result,
            'attempts' => max(0, (int) ($previousStatus['attempts'] ?? 0)) + 1,
            'transport' => $transport,
            'code' => $code,
            'last_attempt_at' => gmdate('Y-m-d\TH:i:s\Z'),
            'last_attempt_by' => $safeActor,
        ];
        $records[$index] = $record;
        return save_data(INVOICES_FILE, array_values($records));
    }
    return false;
}

function portal_save_invoice(): bool
{
    $_SESSION['portal_invoice_email_sent'] = false;
    $_SESSION['portal_invoice_email_status_saved'] = false;
    $invoiceUser = portal_invoice_auth_current_user();
    if (!is_array($invoiceUser)) {
        return false;
    }
    $isInvoiceAdmin = ($invoiceUser['role'] ?? '') === 'admin';
    $i = $_POST['i'] ?? null;
    if (!is_array($i)) {
        return false;
    }
    $fields = [
        'id' => portal_post_text($i, 'id', 128),
        'vat_mode' => portal_post_text($i, 'vat_mode', 8),
        'date' => portal_post_text($i, 'date', 10),
        'ref' => portal_post_text($i, 'ref', 160),
        'customer' => portal_post_text($i, 'customer', 180),
        'description' => portal_post_text($i, 'description', 5000),
    ];
    foreach ($fields as $value) {
        if ($value === null) {
            return false;
        }
    }
    $fortnoxNumber = null;
    $fortnoxDate = null;
    if ($isInvoiceAdmin) {
        $fortnoxNumber = portal_post_text($i, 'fortnox_invoice_number', 80);
        $fortnoxDate = portal_post_text($i, 'fortnox_invoice_date', 10);
        if (
            $fortnoxNumber === null || $fortnoxDate === null ||
            ($fortnoxNumber !== '' && !preg_match('/\A[\pL\pN][\pL\pN .\/_-]{0,79}\z/u', $fortnoxNumber))
        ) {
            return false;
        }
        if ($fortnoxNumber === '') {
            $fortnoxDate = '';
        } elseif (!portal_valid_iso_date($fortnoxDate)) {
            return false;
        }
    }
    if (!in_array($fields['vat_mode'], ['ex', 'inc'], true)) {
        return false;
    }
    if ($fields['date'] !== '' && !preg_match('/\A\d{4}-\d{2}-\d{2}\z/', $fields['date'])) {
        return false;
    }
    $items = portal_process_items($_POST['items'] ?? [], 'invoice');
    if ($items === null) {
        return false;
    }

    $lineTotal = 0.0;
    foreach ($items as $item) {
        $lineTotal += round($item['qty'] * $item['price'], 2);
    }
    if (!is_finite($lineTotal) || $lineTotal > 1000000000) {
        return false;
    }
    // VAT mode is descriptive only: keep the raw sum of entered line amounts,
    // and do not derive net, VAT, or gross totals in the portal.
    $lineTotal = round($lineTotal, 2);

    $records = load_data(INVOICES_FILE, []);
    $editIndex = null;
    if ($fields['id'] !== '') {
        foreach ($records as $index => $record) {
            if (is_array($record) && (string) ($record['id'] ?? '') === $fields['id']) {
                $editIndex = $index;
                break;
            }
        }
        if ($editIndex === null) {
            return false;
        }
    }
    $old = $editIndex !== null ? $records[$editIndex] : [];
    $now = gmdate('Y-m-d\TH:i:s\Z');
    $actor = [
        'id' => (string) ($invoiceUser['id'] ?? ''),
        'username' => (string) ($invoiceUser['username'] ?? ''),
        'name' => (string) ($invoiceUser['name'] ?? $invoiceUser['username'] ?? ''),
    ];
    $history = $editIndex !== null && is_array($old['history'] ?? null)
        ? array_values(array_filter($old['history'], 'is_array'))
        : [];
    $history[] = [
        'action' => $editIndex === null ? 'created' : 'updated',
        'at' => $now,
        'actor' => $actor,
    ];
    $invoice = [
        'id' => $fields['id'] !== '' ? $fields['id'] : portal_random_id(),
        'nummer' => $old['nummer'] ?? get_next_invoice_number(),
        'fortnox_invoice_number' => $isInvoiceAdmin ? $fortnoxNumber : (string) ($old['fortnox_invoice_number'] ?? ''),
        'fortnox_invoice_date' => $isInvoiceAdmin ? $fortnoxDate : (string) ($old['fortnox_invoice_date'] ?? ''),
        'date' => $fields['date'] !== '' ? $fields['date'] : date('Y-m-d'),
        'ref' => $fields['ref'],
        'customer' => $fields['customer'],
        'description' => $fields['description'],
        'vat_mode' => $fields['vat_mode'],
        'items' => $items,
        'total_sum' => $lineTotal,
        'updated_at' => $now,
        'updated_by' => $actor,
        'history' => $history,
    ];
    if ($editIndex !== null && is_array($old['internal_email_status'] ?? null)) {
        $invoice['internal_email_status'] = $old['internal_email_status'];
    }
    if ($editIndex === null) {
        $invoice['created_at'] = $now;
        $invoice['created_by'] = $actor;
        $records[] = $invoice;
        $event = 'invoice.created';
    } else {
        if (isset($old['created_at']) && is_string($old['created_at'])) {
            $invoice['created_at'] = $old['created_at'];
        }
        if (isset($old['created_by']) && is_array($old['created_by'])) {
            $invoice['created_by'] = $old['created_by'];
        }
        $records[$editIndex] = $invoice;
        $event = 'invoice.updated';
    }
    if (!save_data(INVOICES_FILE, array_values($records))) {
        return false;
    }
    TadegaPrivacyLogger::event($event);
    $emailResult = portal_send_invoice_saved_email($invoice);
    $_SESSION['portal_invoice_email_sent'] = $emailResult['accepted'] === true;
    $_SESSION['portal_invoice_email_status_saved'] = portal_invoice_email_status_update($invoice['id'], $emailResult, $actor);
    return true;
}

function portal_sanitize_svg(string $xml): ?string
{
    if (!class_exists('DOMDocument') || strlen($xml) > 524288 || preg_match('/<!DOCTYPE|<!ENTITY/i', $xml)) {
        return null;
    }
    $previous = libxml_use_internal_errors(true);
    $dom = new DOMDocument('1.0', 'UTF-8');
    $dom->resolveExternals = false;
    $dom->substituteEntities = false;
    $ok = $dom->loadXML($xml, LIBXML_NONET | LIBXML_NOBLANKS);
    libxml_clear_errors();
    libxml_use_internal_errors($previous);
    if (!$ok || !$dom->documentElement || strtolower($dom->documentElement->localName) !== 'svg' || !empty($dom->documentElement->prefix)) {
        return null;
    }
    if ($dom->documentElement->namespaceURI && $dom->documentElement->namespaceURI !== 'http://www.w3.org/2000/svg') {
        return null;
    }
    if (!$dom->documentElement->hasAttribute('xmlns')) {
        $dom->documentElement->setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    }
    $allowedElements = ['svg', 'g', 'path', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon', 'title', 'desc'];
    $allowedAttributes = ['xmlns', 'viewbox', 'width', 'height', 'fill', 'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin', 'fill-rule', 'clip-rule', 'opacity', 'fill-opacity', 'stroke-opacity', 'transform', 'd', 'points', 'cx', 'cy', 'r', 'rx', 'ry', 'x', 'y', 'x1', 'x2', 'y1', 'y2'];

    $cleanNode = static function (DOMNode $node) use (&$cleanNode, $allowedElements, $allowedAttributes): void {
        if (!$node->childNodes) {
            return;
        }
        for ($index = $node->childNodes->length - 1; $index >= 0; $index--) {
            $child = $node->childNodes->item($index);
            if ($child->nodeType === XML_ELEMENT_NODE) {
                if (!empty($child->prefix) || ($child->namespaceURI && $child->namespaceURI !== 'http://www.w3.org/2000/svg') || !in_array(strtolower($child->localName), $allowedElements, true)) {
                    $node->removeChild($child);
                    continue;
                }
                if ($child->hasAttributes()) {
                    for ($attrIndex = $child->attributes->length - 1; $attrIndex >= 0; $attrIndex--) {
                        $attribute = $child->attributes->item($attrIndex);
                        $name = strtolower($attribute->nodeName);
                        $value = (string) $attribute->nodeValue;
                        $standardSvgNamespace = $name === 'xmlns' && $value === 'http://www.w3.org/2000/svg';
                        if (!in_array($name, $allowedAttributes, true) || ($name === 'xmlns' && !$standardSvgNamespace) || (!$standardSvgNamespace && preg_match('/url\s*\(|javascript:|https?:|data:/i', $value))) {
                            $child->removeAttributeNode($attribute);
                        }
                    }
                }
                $cleanNode($child);
            } elseif (!in_array($child->nodeType, [XML_TEXT_NODE, XML_CDATA_SECTION_NODE], true)) {
                $node->removeChild($child);
            }
        }
    };
    $cleanNode($dom->documentElement);
    $result = $dom->saveXML($dom->documentElement);
    return is_string($result) && strpos($result, '<svg') !== false ? $result : null;
}

function portal_handle_svg_upload(): bool
{
    $file = $_FILES['logo_file'] ?? null;
    $tmpName = is_array($file) ? ($file['tmp_name'] ?? null) : null;
    $size = is_array($file) ? ($file['size'] ?? null) : null;
    if (!is_array($file) || ($file['error'] ?? UPLOAD_ERR_NO_FILE) !== UPLOAD_ERR_OK || !is_string($tmpName) || !is_uploaded_file($tmpName) || !is_numeric($size)) {
        return false;
    }
    if ((float) $size <= 0 || (float) $size > 524288) {
        return false;
    }
    $originalName = is_string($file['name'] ?? null) ? $file['name'] : '';
    if (strtolower(pathinfo($originalName, PATHINFO_EXTENSION)) !== 'svg') {
        return false;
    }
    $contents = @file_get_contents($file['tmp_name']);
    if (!is_string($contents)) {
        return false;
    }
    $safeSvg = portal_sanitize_svg($contents);
    if ($safeSvg === null) {
        return false;
    }
    $dir = __DIR__ . '/svg';
    if (is_link($dir) || (!is_dir($dir) && !@mkdir($dir, 0750, true))) {
        return false;
    }
    try {
        $name = 'logo-' . bin2hex(random_bytes(8)) . '.svg';
    } catch (Throwable $e) {
        return false;
    }
    $path = $dir . '/' . $name;
    $oldUmask = umask(0027);
    $written = @file_put_contents($path, $safeSvg, LOCK_EX);
    umask($oldUmask);
    if ($written === false) {
        return false;
    }
    @chmod($path, 0640);
    TadegaPrivacyLogger::event('file.uploaded');
    return true;
}

function portal_skade_new_action_token(string $purpose, string $recordId = ''): string
{
    if (session_status() !== PHP_SESSION_ACTIVE || !in_array($purpose, ['submission', 'email_retry', 'edit'], true)) {
        return '';
    }
    if (in_array($purpose, ['email_retry', 'edit'], true) && !preg_match('/\\A[a-f0-9]{32}\\z/', $recordId)) {
        return '';
    }

    $key = 'tadega_skade_action_tokens_v1';
    $tokens = $_SESSION[$key] ?? [];
    if (!is_array($tokens)) {
        $tokens = [];
    }
    $now = time();
    foreach ($tokens as $existingToken => $entry) {
        if (!is_array($entry) || !isset($entry['created_at']) || (int) $entry['created_at'] < $now - 86400) {
            unset($tokens[$existingToken]);
        }
    }
    try {
        $token = bin2hex(random_bytes(32));
    } catch (Throwable $e) {
        return '';
    }
    $tokens[$token] = [
        'purpose' => $purpose,
        'status' => 'pending',
        'created_at' => $now,
    ];
    if (in_array($purpose, ['email_retry', 'edit'], true)) {
        $tokens[$token]['record_id'] = $recordId;
    }
    if (count($tokens) > 48) {
        uasort($tokens, static fn (array $a, array $b): int => ((int) ($a['created_at'] ?? 0)) <=> ((int) ($b['created_at'] ?? 0)));
        while (count($tokens) > 48) {
            $oldestToken = array_key_first($tokens);
            if (!is_string($oldestToken)) {
                break;
            }
            unset($tokens[$oldestToken]);
        }
    }
    $_SESSION[$key] = $tokens;
    return $token;
}

function portal_skade_get_action_token(string $token, string $purpose): ?array
{
    if (session_status() !== PHP_SESSION_ACTIVE || !preg_match('/\\A[a-f0-9]{64}\\z/', $token)) {
        return null;
    }
    $entry = $_SESSION['tadega_skade_action_tokens_v1'][$token] ?? null;
    if (!is_array($entry) || ($entry['purpose'] ?? '') !== $purpose || (int) ($entry['created_at'] ?? 0) < time() - 86400) {
        return null;
    }
    return $entry;
}

function portal_skade_update_action_token(string $token, array $changes): bool
{
    if (session_status() !== PHP_SESSION_ACTIVE || !preg_match('/\\A[a-f0-9]{64}\\z/', $token)) {
        return false;
    }
    $key = 'tadega_skade_action_tokens_v1';
    $tokens = $_SESSION[$key] ?? null;
    if (!is_array($tokens) || !isset($tokens[$token]) || !is_array($tokens[$token])) {
        return false;
    }
    $_SESSION[$key][$token] = array_merge($tokens[$token], $changes, ['updated_at' => time()]);
    return true;
}

function portal_skade_set_action_token_processing(string $token, string $purpose = 'submission'): bool
{
    if (!in_array($purpose, ['submission', 'edit'], true)) {
        return false;
    }
    $entry = portal_skade_get_action_token($token, $purpose);
    if (!is_array($entry) || ($entry['status'] ?? '') !== 'pending') {
        return false;
    }
    return portal_skade_update_action_token($token, ['status' => 'processing']);
}

function portal_skade_is_customer_route(): bool
{
    return ($_GET['mode'] ?? '') === 'customer' && basename($_SERVER['SCRIPT_NAME'] ?? '') === 'skadeblankett-kund.php';
}

/** Only an authenticated central admin or existing invoice-admin may omit the date internally. */
function portal_skade_admin_can_omit_accident_date(): bool
{
    if (portal_skade_is_customer_route()) {
        return false;
    }
    $invoiceUser = portal_invoice_auth_current_user();
    return is_array($invoiceUser) && ($invoiceUser['role'] ?? '') === 'admin';
}

function portal_skade_submission_required_fields(bool $legacySubmission, bool $adminCanOmitAccidentDate): array
{
    $requiredFields = $legacySubmission
        ? ['namn_adress']
        : ['namn_adress', 'person_orgnr', 'modell', 'forsakringsbolag'];
    if (!$adminCanOmitAccidentDate) {
        $requiredFields[] = 'skadedatum';
    }
    return $requiredFields;
}

function portal_skade_redirect_submission_result(array $entry): never
{
    $mailStatus = in_array($entry['mail_status'] ?? '', ['sent', 'failed', 'pending'], true) ? $entry['mail_status'] : 'pending';
    if (portal_skade_is_customer_route()) {
        $url = 'skadeblankett-kund.php?done=1';
        if (in_array($mailStatus, ['sent', 'failed'], true)) {
            $url .= '&mail=' . $mailStatus;
        }
        if (!empty($entry['text_fit_warning'])) {
            $url .= '&text_fit_warning=1';
        }
        header('Location: ' . $url, true, 303);
        exit;
    }

    $relativeFile = $entry['file'] ?? '';
    if (!is_string($relativeFile) || !preg_match('~\\Apdf/[A-Z0-9-]{2,12}/Skadeblankett-Bilglas-[A-Z0-9-]{2,12}-\\d{8}-\\d{6}-[a-f0-9]{6}\\.pdf\\z~D', $relativeFile)) {
        portal_redirect('skadeblankett', 'skade_submit_error');
    }
    $signatureStatus = in_array($entry['signature_status'] ?? '', ['drawn', 'missing'], true) ? $entry['signature_status'] : 'missing';
    $url = '?tab=skadeblankett&pdf=' . rawurlencode($relativeFile) . '&mail=' . rawurlencode($mailStatus) . '&sig=' . $signatureStatus;
    if (!empty($entry['updated'])) {
        $url .= '&updated=1';
    }
    if (!empty($entry['text_fit_warning'])) {
        $url .= '&text_fit_warning=1';
    }
    header('Location: ' . $url, true, 303);
    exit;
}

function portal_update_skade_records(callable $mutator): array|false
{
    $storageDir = __DIR__ . '/storage';
    if (is_link($storageDir) || !is_dir($storageDir)) {
        return false;
    }
    $storageRoot = realpath($storageDir);
    if ($storageRoot === false) {
        return false;
    }
    $lockPath = $storageRoot . DIRECTORY_SEPARATOR . 'skade_records_update.lock';
    if (is_link($lockPath)) {
        return false;
    }
    $oldUmask = umask(0077);
    $lock = @fopen($lockPath, 'c+');
    umask($oldUmask);
    if (!is_resource($lock)) {
        return false;
    }
    @chmod($lockPath, 0600);
    if (!@flock($lock, LOCK_EX)) {
        fclose($lock);
        return false;
    }
    try {
        $recordsPath = app_safe_data_path(SKADE_FILE);
        if ($recordsPath === null || is_link($recordsPath)) {
            return false;
        }
        $records = [];
        if (is_file($recordsPath)) {
            $json = @file_get_contents($recordsPath);
            if (!is_string($json) || trim($json) === '') {
                return false;
            }
            try {
                $decoded = json_decode($json, true, 512, JSON_THROW_ON_ERROR);
            } catch (JsonException) {
                return false;
            }
            if (!is_array($decoded)) {
                return false;
            }
            $records = $decoded;
        }
        $updated = $mutator($records);
        if (!is_array($updated) || !save_data(SKADE_FILE, $updated)) {
            return false;
        }
        return $updated;
    } finally {
        @flock($lock, LOCK_UN);
        fclose($lock);
    }
}

function portal_skade_run_retention_cleanup(): void
{
    $now = time();
    $status = load_json('skade_retention_status.json');
    $lastRunAt = is_array($status) ? (int) ($status['last_run_at'] ?? 0) : 0;
    if ($lastRunAt > 0 && $now - $lastRunAt < 86400) {
        return;
    }

    $cutoff = skade_private_data_cutoff_timestamp($now);
    $recordsOk = true;
    $recordsPath = app_safe_data_path(SKADE_FILE);
    $records = [];
    if ($recordsPath === null || is_link($recordsPath)) {
        $recordsOk = false;
    } elseif (is_file($recordsPath)) {
        $recordsJson = @file_get_contents($recordsPath);
        if (!is_string($recordsJson) || trim($recordsJson) === '') {
            $recordsOk = false;
        } else {
            try {
                $decodedRecords = json_decode($recordsJson, true, 512, JSON_THROW_ON_ERROR);
                if (!is_array($decodedRecords)) {
                    $recordsOk = false;
                } else {
                    $records = $decodedRecords;
                }
            } catch (JsonException) {
                $recordsOk = false;
            }
        }
    }

    $purgeResult = skade_purge_expired_private_data($records, $cutoff, $now);
    if ($recordsOk && (int) ($purgeResult['purged_count'] ?? 0) > 0) {
        $updatedRecords = portal_update_skade_records(static function (array $currentRecords) use ($cutoff, $now): array {
            $currentPurgeResult = skade_purge_expired_private_data($currentRecords, $cutoff, $now);
            return $currentPurgeResult['records'];
        });
        $recordsOk = $updatedRecords !== false;
    }

    $backupsOk = skade_purge_backup_archives($cutoff, $now);
    if ($recordsOk && $backupsOk) {
        save_json('skade_retention_status.json', ['last_run_at' => $now]);
    }
}

portal_skade_run_retention_cleanup();

function portal_skade_record_file_path(array $record): ?string
{
    $regnr = isset($record['regnr']) && is_string($record['regnr']) ? strtoupper($record['regnr']) : '';
    $relativeFile = isset($record['file']) && is_string($record['file']) ? $record['file'] : '';
    if (!preg_match('/\\A[A-Z0-9-]{2,12}\\z/', $regnr) || !preg_match('~\\Apdf/([A-Z0-9-]{2,12})/Skadeblankett-Bilglas-\\1-\\d{8}-\\d{6}-[a-f0-9]{6}\\.pdf\\z~D', $relativeFile, $matches) || ($matches[1] ?? '') !== $regnr) {
        return null;
    }
    $pdfPath = __DIR__ . '/pdf';
    $pdfRoot = realpath($pdfPath);
    $fullPath = __DIR__ . '/' . $relativeFile;
    if ($pdfRoot === false || is_link($pdfPath) || is_link(dirname($fullPath)) || is_link($fullPath)) {
        return null;
    }
    $expectedDir = $pdfRoot . DIRECTORY_SEPARATOR . $regnr;
    $realDir = realpath(dirname($fullPath));
    $realFile = realpath($fullPath);
    $prefix = rtrim($pdfRoot, DIRECTORY_SEPARATOR) . DIRECTORY_SEPARATOR;
    if ($realDir !== $expectedDir || $realFile === false || strpos($realFile, $prefix) !== 0 || !is_file($realFile)) {
        return null;
    }
    $size = @filesize($realFile);
    if (!is_int($size) || $size < 1000 || $size > 52428800) {
        return null;
    }
    return $realFile;
}

function portal_skade_editable_record_by_id(string $recordId): ?array
{
    if (!preg_match('/\\A[a-f0-9]{32}\\z/', $recordId)) {
        return null;
    }
    foreach (load_skadeblanketter() as $record) {
        if (!is_array($record) || ($record['id'] ?? '') !== $recordId) {
            continue;
        }
        if (!is_array($record['form_data'] ?? null) || portal_skade_record_file_path($record) === null) {
            return null;
        }
        return $record;
    }
    return null;
}

function portal_skade_signature_data_uri_from_record(array $record): ?string
{
    $encoded = $record['signature_png_base64'] ?? '';
    if (!is_string($encoded)) {
        return null;
    }
    if ($encoded === '') {
        return '';
    }
    if (strlen($encoded) > 540000 || (strlen($encoded) % 4) !== 0 || !function_exists('getimagesizefromstring')) {
        return null;
    }
    $bytes = base64_decode($encoded, true);
    if (!is_string($bytes) || strlen($bytes) < 100 || strlen($bytes) > 400000 || substr($bytes, 0, 8) !== "\x89PNG\r\n\x1a\n") {
        return null;
    }
    $info = @getimagesizefromstring($bytes);
    if (
        !is_array($info) || ($info['mime'] ?? '') !== 'image/png' ||
        (int) ($info[0] ?? 0) < 25 || (int) ($info[0] ?? 0) > 1600 ||
        (int) ($info[1] ?? 0) < 20 || (int) ($info[1] ?? 0) > 800 ||
        (int) $info[0] * (int) $info[1] > 1200000
    ) {
        return null;
    }
    return 'data:image/png;base64,' . base64_encode($bytes);
}

function portal_skade_redirect_email_retry_result(string $relativeFile, string $mailStatus, string $retryResult = ''): never
{
    if (!preg_match('~\\Apdf/[A-Z0-9-]{2,12}/Skadeblankett-Bilglas-[A-Z0-9-]{2,12}-\\d{8}-\\d{6}-[a-f0-9]{6}\\.pdf\\z~D', $relativeFile) || !in_array($mailStatus, ['sent', 'failed', 'pending'], true)) {
        portal_redirect('skadeblankett', 'skade_email_retry_error');
    }
    $url = '?tab=skadeblankett&pdf=' . rawurlencode($relativeFile) . '&mail=' . rawurlencode($mailStatus);
    if (in_array($retryResult, ['sent', 'failed', 'pending'], true)) {
        $url .= '&email_retry=' . rawurlencode($retryResult);
    }
    header('Location: ' . $url, true, 303);
    exit;
}

function portal_handle_skade_email_retry(): never
{
    global $activeTab, $isSkadeCustomerMode;

    if ($isSkadeCustomerMode || portal_skade_is_customer_route()) {
        header('Location: skadeblankett-kund.php', true, 303);
        exit;
    }
    if ($activeTab !== 'skadeblankett') {
        portal_redirect('skadeblankett', 'skade_email_retry_error');
    }
    $recordId = isset($_POST['record_id']) && is_string($_POST['record_id']) ? $_POST['record_id'] : '';
    $retryToken = isset($_POST['retry_token']) && is_string($_POST['retry_token']) ? $_POST['retry_token'] : '';
    $tokenEntry = portal_skade_get_action_token($retryToken, 'email_retry');
    if (!preg_match('/\\A[a-f0-9]{32}\\z/', $recordId) || !is_array($tokenEntry) || ($tokenEntry['record_id'] ?? '') !== $recordId) {
        portal_redirect('skadeblankett', 'skade_email_retry_error');
    }
    if (($tokenEntry['status'] ?? '') === 'completed') {
        $file = isset($tokenEntry['file']) && is_string($tokenEntry['file']) ? $tokenEntry['file'] : '';
        $status = in_array($tokenEntry['mail_status'] ?? '', ['sent', 'failed', 'pending'], true) ? $tokenEntry['mail_status'] : 'pending';
        $retryResult = in_array($tokenEntry['retry_result'] ?? '', ['sent', 'failed', 'pending'], true) ? $tokenEntry['retry_result'] : $status;
        portal_skade_redirect_email_retry_result($file, $status, $retryResult);
    }
    if (($tokenEntry['status'] ?? '') !== 'pending') {
        portal_redirect('skadeblankett', 'skade_email_retry_error');
    }
    if (!portal_skade_update_action_token($retryToken, ['status' => 'processing'])) {
        portal_redirect('skadeblankett', 'skade_email_retry_error');
    }

    $claimStatus = 'missing';
    $retryRecord = null;
    $updatedRecords = portal_update_skade_records(static function (array $currentRecords) use (&$claimStatus, &$retryRecord, $recordId): array|false {
        foreach ($currentRecords as &$record) {
            if (!is_array($record) || ($record['id'] ?? '') !== $recordId) {
                continue;
            }
            $retryRecord = $record;
            if (portal_skade_record_file_path($record) === null) {
                $claimStatus = 'invalid_file';
                unset($record);
                return false;
            }
            if (!empty($record['email_accepted']) || !empty($record['email_sent']) || in_array($record['email_status'] ?? '', ['accepted', 'sent'], true)) {
                $claimStatus = 'sent';
                unset($record);
                return false;
            }
            if (!empty($record['email_retry_pending']) || in_array($record['email_status'] ?? '', ['sending', 'retrying'], true)) {
                $claimStatus = 'pending';
                unset($record);
                return false;
            }
            $record['email_retry_pending'] = true;
            $record['email_status'] = 'retrying';
            $record['email_attempts'] = max(1, (int) ($record['email_attempts'] ?? 1)) + 1;
            $record['email_last_attempt_at'] = gmdate('Y-m-d\TH:i:s\Z');
            $retryRecord = $record;
            $claimStatus = 'claimed';
            unset($record);
            return $currentRecords;
        }
        unset($record);
        return false;
    });

    if (!is_array($retryRecord)) {
        portal_skade_update_action_token($retryToken, ['status' => 'completed', 'mail_status' => 'pending', 'retry_result' => 'pending']);
        portal_redirect('skadeblankett', 'skade_email_retry_error');
    }
    $relativeFile = isset($retryRecord['file']) && is_string($retryRecord['file']) ? $retryRecord['file'] : '';
    if ($claimStatus === 'sent') {
        portal_skade_update_action_token($retryToken, ['status' => 'completed', 'file' => $relativeFile, 'mail_status' => 'sent', 'retry_result' => 'sent']);
        portal_skade_redirect_email_retry_result($relativeFile, 'sent', 'sent');
    }
    if ($claimStatus === 'pending') {
        portal_skade_update_action_token($retryToken, ['status' => 'completed', 'file' => $relativeFile, 'mail_status' => 'pending', 'retry_result' => 'pending']);
        portal_skade_redirect_email_retry_result($relativeFile, 'pending', 'pending');
    }
    if ($claimStatus !== 'claimed' || !is_array($updatedRecords)) {
        portal_skade_update_action_token($retryToken, ['status' => 'completed', 'file' => $relativeFile, 'mail_status' => 'pending', 'retry_result' => 'pending']);
        portal_skade_redirect_email_retry_result($relativeFile, 'pending', 'pending');
    }

    $pdfPath = portal_skade_record_file_path($retryRecord);
    if ($pdfPath === null) {
        portal_skade_update_action_token($retryToken, ['status' => 'completed', 'file' => $relativeFile, 'mail_status' => 'pending', 'retry_result' => 'pending']);
        portal_skade_redirect_email_retry_result($relativeFile, 'pending', 'pending');
    }
    require_once __DIR__ . '/includes/send_skade_email.php';
    $regnr = isset($retryRecord['regnr']) && is_string($retryRecord['regnr']) ? strtoupper($retryRecord['regnr']) : '';
    $sent = send_skadeblankett_email($pdfPath, [
        'retry_attempt' => true,
        'pdf_text_fit_warning' => !empty($retryRecord['pdf_text_fit_warning']),
    ], $regnr);
    $emailAccepted = is_array($sent) && ($sent['accepted'] ?? false) === true;
    $emailTransport = is_array($sent) && is_string($sent['transport'] ?? null) && in_array($sent['transport'], ['smtp', 'php_mail'], true) ? $sent['transport'] : 'none';
    $emailCode = is_array($sent) && is_string($sent['code'] ?? null) ? $sent['code'] : 'preparation_failed';
    portal_email_status_record('skadeblankett', $emailAccepted ? 'accepted' : 'failed', 'skade_retry', $emailTransport, $emailCode);
    $emailStatus = $emailAccepted ? 'sent' : 'failed';
    $attemptAt = gmdate('Y-m-d\TH:i:s\Z');
    $finalRecords = portal_update_skade_records(static function (array $currentRecords) use ($recordId, $emailAccepted, $attemptAt): array|false {
        foreach ($currentRecords as &$record) {
            if (is_array($record) && ($record['id'] ?? '') === $recordId) {
                $record['email_accepted'] = $emailAccepted;
                $record['email_sent'] = $emailAccepted; // Backward-compatible alias; the transport accepted it, not confirmed delivered.
                $record['email_status'] = $emailAccepted ? 'accepted' : 'failed';
                $record['email_retry_pending'] = false;
                $record['email_last_attempt_at'] = $attemptAt;
                unset($record);
                return $currentRecords;
            }
        }
        unset($record);
        return false;
    });
    if (!is_array($finalRecords)) {
        $emailStatus = 'pending';
        TadegaPrivacyLogger::event('skade.email_status_save_failed');
    }
    portal_skade_update_action_token($retryToken, [
        'status' => 'completed',
        'file' => $relativeFile,
        'mail_status' => $emailStatus,
        'retry_result' => $emailStatus,
    ]);
    TadegaPrivacyLogger::event($emailAccepted ? 'skade.email_retry_accepted' : 'skade.email_retry_failed');
    portal_skade_redirect_email_retry_result($relativeFile, $emailStatus, $emailStatus);
}

function portal_handle_skade_submission(): bool
{
    global $portalPostError, $portalSkadeTextFitConfirmationRequired, $portalSkadeTextFitMessage;

    $reject = static function (string $message, string $diagnosticCode = '', array $fieldKeys = [], ?Throwable $exception = null) use (&$portalPostError): bool {
        if ($diagnosticCode !== '') {
            TadegaPrivacyLogger::applicationError($diagnosticCode, $fieldKeys, $exception);
        }
        $portalPostError = $message;
        return false;
    };
    $data = $_POST['s'] ?? null;
    if (!is_array($data)) {
        return $reject('Formuläret saknar uppgifter. Ladda om sidan och försök igen.', 'skade.form_missing');
    }
    $editId = isset($_POST['edit_id']) && is_string($_POST['edit_id']) ? trim($_POST['edit_id']) : '';
    $editSourceFile = isset($_POST['edit_source_file']) && is_string($_POST['edit_source_file']) ? $_POST['edit_source_file'] : '';
    $isEdit = $editId !== '';
    if ($isEdit && (portal_skade_is_customer_route() || !preg_match('/\\A[a-f0-9]{32}\\z/', $editId))) {
        return $reject('Redigeringslänken kunde inte verifieras. Öppna skadeblanketten igen från Historik.', 'skade.edit_id_invalid');
    }
    $tokenPurpose = $isEdit ? 'edit' : 'submission';
    $submissionToken = isset($_POST['skade_submission_token']) && is_string($_POST['skade_submission_token']) ? $_POST['skade_submission_token'] : '';
    $tokenEntry = portal_skade_get_action_token($submissionToken, $tokenPurpose);
    if (!is_array($tokenEntry) || ($isEdit && ($tokenEntry['record_id'] ?? '') !== $editId)) {
        return $reject('Säkerhetskontrollen har gått ut eller kunde inte verifieras. Öppna blanketten igen och försök.', 'skade.token_invalid');
    }
    if (($tokenEntry['status'] ?? '') === 'completed') {
        portal_skade_redirect_submission_result($tokenEntry);
    }
    if (($tokenEntry['status'] ?? '') === 'processing') {
        return $reject($isEdit ? 'Redigeringen pågår redan. Skicka inte igen; kontrollera den aktuella posten i Historik.' : 'Den här blanketten har redan påbörjats. Skicka inte in den igen; be personalen kontrollera statusen.', 'skade.duplicate_submission');
    }
    if (($tokenEntry['status'] ?? '') !== 'pending') {
        return $reject('Blanketten kunde inte verifieras. Öppna den igen och försök.', 'skade.token_state_invalid');
    }
    $editRecord = null;
    if ($isEdit) {
        $editRecord = portal_skade_editable_record_by_id($editId);
        if (!is_array($editRecord)) {
            return $reject('Den här historikposten saknar redigerbara formuläruppgifter eller PDF-filen finns inte längre. Äldre poster kan öppnas som PDF, men kan inte fyllas i automatiskt.', 'skade.edit_record_unavailable');
        }
        $currentFile = isset($editRecord['file']) && is_string($editRecord['file']) ? $editRecord['file'] : '';
        if ($editSourceFile === '' || !hash_equals($currentFile, $editSourceFile)) {
            return $reject('Posten har ändrats sedan du öppnade den. Öppna den på nytt från Historik innan du sparar.', 'skade.edit_stale');
        }
    }

    $versionValue = isset($_POST['form_version']) && is_string($_POST['form_version']) ? $_POST['form_version'] : '';
    $formVersion = in_array($versionValue, ['skade-customer-v2', 'skade-customer-v3-signature'], true);
    $digitalSignature = $versionValue === 'skade-customer-v3-signature';
    if ($isEdit && !$digitalSignature) {
        return $reject('Redigeringsformuläret är gammalt eller ogiltigt. Öppna posten igen från Historik.', 'skade.edit_form_version_invalid');
    }
    $legacySubmission = !$formVersion && !array_key_exists('damage_cause', $data) && !array_key_exists('payment_method', $data) && !array_key_exists('consent', $data);
    $limits = [
        'inbokad' => $legacySubmission ? 80 : 20, 'namn_adress' => $legacySubmission ? 500 : 250, 'person_orgnr' => 40,
        'telefon' => 40, 'epost' => 254, 'regnr' => 16, 'modell' => $legacySubmission ? 100 : 70,
        'matarstallning' => 20, 'forsakringsbolag' => $legacySubmission ? 100 : 70, 'skadedatum' => 32,
        'skadeplats' => $legacySubmission ? 120 : 80, 'skadenummer' => $legacySubmission ? 100 : 80, 'other_cause' => 45,
        'stone_count' => 4, 'mount_time' => 20, 'glass_price' => 20,
        'notes' => 250, 'wiper_price' => 20, 'washer_liters' => 20,
        'solar_price' => 20, 'payment_amount' => 20, 'signature_date' => 10,
        'replacement_date' => 10,
    ];
    $clean = [];
    foreach ($limits as $key => $limit) {
        $value = portal_post_text($data, $key, $limit);
        if ($value === null) {
            return $reject('En uppgift är för lång eller har ett ogiltigt format. Kontrollera de markerade fälten och försök igen.', 'skade.field_invalid', [$key]);
        }
        $clean[$key] = $value;
    }

    $signatureRequired = portal_skade_is_customer_route();
    if ($signatureRequired && !$digitalSignature) {
        return $reject('Kundläget kräver en ritad signatur och bekräftelse. Ladda om kundformuläret och försök igen.', 'skade.signature_required', ['signature_png', 'signature_confirmed']);
    }
    if ($digitalSignature) {
        $signatureDataUrl = $data['signature_png'] ?? '';
        $signatureConfirmation = $data['signature_confirmed'] ?? '';
        $prefix = 'data:image/png;base64,';
        if (!is_string($signatureDataUrl)) {
            return $reject('Signaturbilden kunde inte läsas. Rita om signaturen och försök igen.', 'skade.signature_data_invalid', ['signature_png']);
        }
        if ($signatureDataUrl === '') {
            if ($signatureRequired) {
                return $reject('Rita signaturen och kryssa i bekräftelserutan innan du skickar.', 'skade.signature_required', ['signature_png', 'signature_confirmed']);
            }
        } else {
            if (strlen($signatureDataUrl) > 550000 || strpos($signatureDataUrl, $prefix) !== 0) {
                return $reject('Signaturbilden kunde inte läsas. Rita om signaturen och försök igen.', 'skade.signature_data_invalid', ['signature_png']);
            }
            if (!is_string($signatureConfirmation) || $signatureConfirmation !== '1') {
                return $reject('Bekräfta att uppgifterna stämmer och att den ritade signaturen tillhör kunden.', 'skade.signature_required', ['signature_confirmed']);
            }
            if (!function_exists('getimagesizefromstring')) {
                return $reject('Servern kan inte kontrollera signaturbilden just nu. Be personalen kontrollera PHP-bildstödet.', 'skade.signature_processor_unavailable', ['signature_png']);
            }
            $encodedSignature = substr($signatureDataUrl, strlen($prefix));
            if ($encodedSignature === '' || (strlen($encodedSignature) % 4) !== 0) {
                return $reject('Signaturen kunde inte läsas. Rita om signaturen och försök igen.', 'skade.signature_data_invalid', ['signature_png']);
            }
            $signatureBytes = base64_decode($encodedSignature, true);
            if (!is_string($signatureBytes) || strlen($signatureBytes) < 100 || strlen($signatureBytes) > 400000 || substr($signatureBytes, 0, 8) !== "\x89PNG\r\n\x1a\n") {
                return $reject('Signaturbilden kunde inte läsas. Rensa rutan, rita om signaturen och försök igen.', 'skade.signature_data_invalid', ['signature_png']);
            }
            $signatureInfo = @getimagesizefromstring($signatureBytes);
            if (
                !is_array($signatureInfo) || ($signatureInfo['mime'] ?? '') !== 'image/png' ||
                (int) ($signatureInfo[0] ?? 0) < 25 || (int) ($signatureInfo[0] ?? 0) > 1600 ||
                (int) ($signatureInfo[1] ?? 0) < 20 || (int) ($signatureInfo[1] ?? 0) > 800 ||
                (int) $signatureInfo[0] * (int) $signatureInfo[1] > 1200000
            ) {
                return $reject('Signaturbildens format eller storlek är ogiltig. Rensa rutan och rita en ny signatur.', 'skade.signature_image_invalid', ['signature_png']);
            }
            $clean['signature_png_bytes'] = $signatureBytes;
        }
    }

    $clean['regnr'] = strtoupper(preg_replace('/[^A-Z0-9-]/i', '', $clean['regnr']));
    if (strlen($clean['regnr']) < 2 || strlen($clean['regnr']) > 12) {
        return $reject('Ange ett giltigt registreringsnummer med 2–12 bokstäver, siffror eller bindestreck.', 'skade.registration_invalid', ['regnr']);
    }
    $skadeAdminCanOmitAccidentDate = portal_skade_admin_can_omit_accident_date();
    $requiredFields = portal_skade_submission_required_fields($legacySubmission, $skadeAdminCanOmitAccidentDate);
    if (!$legacySubmission && portal_skade_is_customer_route()) {
        $requiredFields[] = 'telefon';
    }
    $requiredLabels = [
        'namn_adress' => 'namn och adress', 'person_orgnr' => 'person-/organisationsnummer',
        'telefon' => 'telefonnummer', 'modell' => 'fabrikat och modell', 'forsakringsbolag' => 'försäkringsbolag',
        'skadedatum' => 'skadedatum',
    ];
    $missingRequired = [];
    $missingRequiredFields = [];
    foreach ($requiredFields as $required) {
        if ($clean[$required] === '') {
            $missingRequired[] = $requiredLabels[$required] ?? 'obligatoriska uppgifter';
            $missingRequiredFields[] = $required;
        }
    }
    if ($missingRequired !== []) {
        return $reject('Fyll i obligatoriska fält: ' . implode(', ', $missingRequired) . '.', 'skade.required_fields_missing', $missingRequiredFields);
    }
    if ($clean['epost'] !== '' && filter_var($clean['epost'], FILTER_VALIDATE_EMAIL) === false) {
        return $reject('E-postadressen är frivillig, men måste ha ett giltigt format om du fyller i den. Rätta adressen eller lämna fältet tomt.', 'skade.email_invalid', ['epost']);
    }
    if ($clean['telefon'] !== '' && strlen((string) preg_replace('/\D+/', '', $clean['telefon'])) < 5) {
        return $reject('Telefonnumret är frivilligt, men måste innehålla minst fem siffror om du fyller i det. Rätta numret eller lämna fältet tomt.', 'skade.phone_invalid', ['telefon']);
    }

    $normalizeSkadeDate = static function (string $value): string {
        $value = trim($value);
        if ($value === '') {
            return '';
        }
        $year = $month = $day = 0;
        if (preg_match('/\A(\d{4})[.\s\/-](\d{1,2})[.\s\/-](\d{1,2})\z/', $value, $parts)) {
            $year = (int) $parts[1];
            $month = (int) $parts[2];
            $day = (int) $parts[3];
        } elseif (preg_match('/\A(\d{1,2})[.\s\/-](\d{1,2})[.\s\/-](\d{4})\z/', $value, $parts)) {
            $day = (int) $parts[1];
            $month = (int) $parts[2];
            $year = (int) $parts[3];
        } elseif (preg_match('/\A\d{6}\z/', $value)) {
            $shortYear = (int) substr($value, 0, 2);
            $year = $shortYear <= 49 ? 2000 + $shortYear : 1900 + $shortYear;
            $month = (int) substr($value, 2, 2);
            $day = (int) substr($value, 4, 2);
        } elseif (preg_match('/\A\d{8}\z/', $value)) {
            $compactYear = (int) substr($value, 0, 4);
            $compactMonth = (int) substr($value, 4, 2);
            $compactDay = (int) substr($value, 6, 2);
            if ($compactYear >= 1000 && checkdate($compactMonth, $compactDay, $compactYear)) {
                $year = $compactYear;
                $month = $compactMonth;
                $day = $compactDay;
            } else {
                $day = (int) substr($value, 0, 2);
                $month = (int) substr($value, 2, 2);
                $year = (int) substr($value, 4, 4);
            }
        } else {
            return $value;
        }
        if ($year < 1 || $year > 9999 || !checkdate($month, $day, $year)) {
            return $value;
        }
        return sprintf('%04d-%02d-%02d', $year, $month, $day);
    };
    $clean['skadedatum'] = $normalizeSkadeDate($clean['skadedatum']);

    $validDate = static function (string $value): bool {
        if (!preg_match('/\A\d{4}-\d{2}-\d{2}\z/', $value)) {
            return false;
        }
        $parts = explode('-', $value);
        return count($parts) === 3 && checkdate((int) $parts[1], (int) $parts[2], (int) $parts[0]);
    };
    if ($clean['skadedatum'] !== '' && !$validDate($clean['skadedatum'])) {
        return $reject('Ange ett giltigt skadedatum.', 'skade.accident_date_invalid', ['skadedatum']);
    }
    if ($clean['signature_date'] !== '' && !$validDate($clean['signature_date'])) {
        return $reject('Ange ett giltigt signaturdatum eller lämna fältet tomt.', 'skade.signature_date_invalid', ['signature_date']);
    }
    if ($clean['replacement_date'] !== '' && !$validDate($clean['replacement_date'])) {
        return $reject('Ange ett giltigt bytesdatum eller lämna fältet tomt.', 'skade.replacement_date_invalid', ['replacement_date']);
    }
    if (!$legacySubmission && $clean['inbokad'] !== '') {
        $appointment = explode('T', $clean['inbokad']);
        if (count($appointment) !== 2 || !$validDate($appointment[0]) || !preg_match('/\A(?:[01]\d|2[0-3]):[0-5]\d\z/', $appointment[1])) {
            return $reject('Kontrollera datum och tid för den inbokade tiden, eller lämna fältet tomt.', 'skade.appointment_invalid', ['inbokad']);
        }
    }

    $parseNumber = static function (string $value, int $maxIntegerDigits = 8): ?string {
        $value = str_replace(',', '.', trim($value));
        if ($value === '') {
            return '';
        }
        if (!preg_match('/\A\d{1,' . $maxIntegerDigits . '}(?:\.\d{1,2})?\z/', $value)) {
            return null;
        }
        $number = (float) $value;
        return is_finite($number) && $number >= 0 ? rtrim(rtrim(number_format($number, 2, '.', ''), '0'), '.') : null;
    };
    $numberRules = [
        'matarstallning' => 8, 'stone_count' => 2, 'mount_time' => 5,
        'glass_price' => 8, 'wiper_price' => 8, 'washer_liters' => 4,
        'solar_price' => 8, 'payment_amount' => 8,
    ];
    foreach ($numberRules as $key => $maxDigits) {
        if ($legacySubmission && $key === 'matarstallning') {
            continue;
        }
        $parsed = $parseNumber($clean[$key], $maxDigits);
        if ($parsed === null) {
            return $reject('Kontrollera att antal, tider, priser och belopp bara innehåller giltiga positiva tal.', 'skade.numeric_invalid', [$key]);
        }
        $clean[$key] = $parsed;
    }
    foreach (['matarstallning', 'stone_count'] as $integerField) {
        if (!$legacySubmission && $clean[$integerField] !== '' && strpos($clean[$integerField], '.') !== false) {
            return $reject('Mätarställning och antal stenskott måste anges som heltal.', 'skade.integer_invalid', [$integerField]);
        }
    }

    $readChoice = static function (string $key, array $allowed) use ($data): ?string {
        $value = $data[$key] ?? '';
        if (!is_string($value)) {
            return null;
        }
        return $value === '' || in_array($value, $allowed, true) ? $value : null;
    };
    $readSet = static function (string $key, array $allowed) use ($data): ?array {
        $values = $data[$key] ?? [];
        if ($values === '') {
            return [];
        }
        if (!is_array($values) || count($values) > count($allowed)) {
            return null;
        }
        $result = [];
        foreach ($values as $value) {
            if (!is_string($value) || !in_array($value, $allowed, true)) {
                return null;
            }
            $result[] = $value;
        }
        return array_values(array_unique($result));
    };
    $damageCause = $readChoice('damage_cause', ['stone_chip', 'other']);
    $paymentMethod = $readChoice('payment_method', ['pickup', 'izettle', 'invoice', 'swish', 'cash']);
    $glassLocations = $readSet('glass_locations', ['windshield', 'side', 'rear']);
    $actions = $readSet('actions', ['replacement', 'repair']);
    $equipment = $readSet('equipment', ['head_up', 'rain_sensor', 'mirror_mount', 'camera', 'electric', 'static_calibration', 'im_sensor', 'dynamic_calibration']);
    if ($damageCause === null || $paymentMethod === null || $glassLocations === null || $actions === null || $equipment === null) {
        $invalidChoiceFields = [];
        foreach (['damage_cause' => $damageCause, 'payment_method' => $paymentMethod, 'glass_locations' => $glassLocations, 'actions' => $actions, 'equipment' => $equipment] as $fieldKey => $fieldValue) {
            if ($fieldValue === null) {
                $invalidChoiceFields[] = $fieldKey;
            }
        }
        return $reject('Ett val i formuläret kunde inte läsas. Kontrollera valen och försök igen.', 'skade.choice_invalid', $invalidChoiceFields);
    }
    if ($paymentMethod === '') {
        $paymentMethod = 'pickup';
    }
    if ($damageCause === 'other' && $clean['other_cause'] === '') {
        return $reject('Beskriv skadan när alternativet ”Annat” är valt.', 'skade.damage_description_missing', ['other_cause']);
    }

    $readCheck = static function (string $key) use ($data): ?bool {
        $value = $data[$key] ?? '';
        if ($value === '') {
            return false;
        }
        return is_string($value) && $value === '1' ? true : null;
    };
    $company = $readCheck('foretag');
    $orderedWipers = $readCheck('nya_torkarblad_bestalls');
    $wiperService = $readCheck('wiper_service');
    $solarFilm = $readCheck('solar_film');
    $consentSupplied = array_key_exists('consent', $data);
    $consent = $consentSupplied ? $readCheck('consent') : null;
    $consentRequired = !$legacySubmission && !$formVersion;
    if ($company === null || $orderedWipers === null || $wiperService === null || $solarFilm === null) {
        $invalidCheckboxFields = [];
        foreach (['foretag' => $company, 'nya_torkarblad_bestalls' => $orderedWipers, 'wiper_service' => $wiperService, 'solar_film' => $solarFilm] as $fieldKey => $fieldValue) {
            if ($fieldValue === null) {
                $invalidCheckboxFields[] = $fieldKey;
            }
        }
        return $reject('En kryssruta kunde inte läsas. Kontrollera markeringarna och försök igen.', 'skade.checkbox_invalid', $invalidCheckboxFields);
    }
    if (($consentRequired && $consent !== true) || ($consentSupplied && $consent !== true)) {
        return $reject('Bekräfta intygandet genom att kryssa i rutan innan du skickar.', 'skade.declaration_unconfirmed', ['consent']);
    }

    $clean['foretag'] = $company ? '1' : '';
    $clean['nya_torkarblad_bestalls'] = $orderedWipers ? '1' : '';
    $clean['company'] = $company;
    $clean['glass_locations'] = $glassLocations;
    $clean['damage_cause'] = $damageCause;
    $clean['actions'] = $actions;
    $clean['equipment'] = $equipment;
    $clean['wiper_service'] = $wiperService;
    $clean['solar_film'] = $solarFilm;
    $clean['payment_method'] = $paymentMethod;
    $clean['payment_amount'] = $paymentMethod === 'pickup' || $paymentMethod === 'invoice' ? '' : $clean['payment_amount'];
    if (isset($clean['signature_png_bytes']) && $clean['signature_date'] === '') {
        $clean['signature_date'] = (new DateTimeImmutable('now', new DateTimeZone('Europe/Stockholm')))->format('Y-m-d');
    }

    $appRoot = realpath(__DIR__);
    $templatePath = '';
    if ($appRoot !== false) {
        foreach ([$appRoot . '/pdf/Bilrutan Skadeblankett.pdf', $appRoot . '/pdf/Bilrutan_Skadeblankett.pdf'] as $candidate) {
            if (is_file($candidate) && !is_link($candidate) && @filesize($candidate) > 1000) {
                $templatePath = $candidate;
                break;
            }
        }
        if ($templatePath === '') {
            foreach ([$appRoot . '/png/blankett.png', $appRoot . '/png/Bilrutan_Skadeblankett.png'] as $candidate) {
                if (is_file($candidate) && !is_link($candidate) && @filesize($candidate) > 10000) {
                    $templatePath = $candidate;
                    break;
                }
            }
        }
    }
    if ($appRoot === false || $templatePath === '') {
        TadegaPrivacyLogger::event('skade.pdf_failed');
        return $reject('PDF-mallen saknas eller kan inte läsas. Inga uppgifter sparades; be personalen kontrollera PDF- och PNG-mallarna.', 'skade.template_missing');
    }

    $outputDir = $appRoot . '/pdf/' . $clean['regnr'];
    if (is_link($appRoot . '/pdf') || is_link($outputDir)) {
        TadegaPrivacyLogger::event('skade.pdf_failed');
        return $reject('PDF-arkivets sökväg kan inte användas säkert. Inga uppgifter sparades; be personalen kontrollera lagringen.', 'skade.archive_path_invalid');
    }
    if (!is_dir($outputDir) && !@mkdir($outputDir, 0750, true)) {
        TadegaPrivacyLogger::event('skade.pdf_failed');
        return $reject('Appen saknar skrivbehörighet i PDF-arkivet. Inga uppgifter sparades; be personalen kontrollera mappbehörigheterna.', 'skade.pdf_directory_create_failed');
    }
    if (!is_writable($outputDir)) {
        TadegaPrivacyLogger::event('skade.pdf_failed');
        return $reject('Appen kan inte skriva i PDF-arkivet. Inga uppgifter sparades; be personalen kontrollera mappbehörigheterna.', 'skade.pdf_directory_unwritable');
    }
    try {
        $fileName = 'Skadeblankett-Bilglas-' . $clean['regnr'] . '-' . gmdate('Ymd-His') . '-' . bin2hex(random_bytes(3)) . '.pdf';
    } catch (Throwable $e) {
        return $reject('Ett säkert PDF-filnamn kunde inte skapas. Försök igen; om felet kvarstår, be personalen kontrollera servern.', 'skade.secure_filename_failed', [], $e);
    }
    $outputPath = $outputDir . '/' . $fileName;
    if (!portal_skade_set_action_token_processing($submissionToken, $tokenPurpose)) {
        return $reject('Säkerhetskontrollen har gått ut. Öppna blanketten igen och försök.', 'skade.token_processing_failed');
    }

    require_once __DIR__ . '/includes/skadeblankett_logger.php';
    require_once __DIR__ . '/includes/skadeblankett_pdf.php';
    $signatureDrawn = isset($clean['signature_png_bytes']);
    $signatureBase64 = $signatureDrawn ? base64_encode($clean['signature_png_bytes']) : '';
    $formData = $clean;
    unset($formData['signature_png_bytes']);
    $pdfException = null;
    try {
        $result = create_skadeblankett_pdf_php($clean, $templatePath, $outputPath, 'pdf');
    } catch (Throwable $exception) {
        $result = null;
        $pdfException = $exception;
    }
    unset($clean['signature_png_bytes']);
    $pdfFailureCode = 'skade.pdf_generation_failed';
    $pdfFailureFields = [];
    $pdfTextFitWarning = false;
    if (is_array($result)) {
        $pdfTextFitWarning = is_array($result[2] ?? null) && (int) ($result[2]['below_5pt_fields'] ?? 0) > 0;
        if (is_string($result[2] ?? null)) {
            $pdfFailureCode = $result[2];
        }
        if (($result[3] ?? null) instanceof Throwable) {
            $pdfException = $result[3];
        }
        if (is_array($result[4] ?? null)) {
            $pdfFailureFields = $result[4];
        }
    }
    if (!is_array($result) || empty($result[0]) || !is_file($outputPath) || filesize($outputPath) < 1000) {
        @unlink($outputPath);
        portal_skade_update_action_token($submissionToken, ['status' => 'pending']);
        TadegaPrivacyLogger::event('skade.pdf_failed');
        $pdfFailureMessage = $pdfFailureCode === 'skade.pdf_text_unfit'
            ? 'Ett eller flera fält innehåller text som inte ryms i PDF-mallen utan att kapas. Ingen PDF har sparats eller skickats. Förkorta texten eller lägg in mellanslag där långa ord kan delas, och försök igen.'
            : 'PDF-filen kunde inte skapas. Inga uppgifter sparades; be personalen kontrollera PDF-mall och skrivbehörighet.';
        return $reject($pdfFailureMessage, $pdfFailureCode, $pdfFailureFields, $pdfException);
    }

    $confirmSmallText = isset($_POST['confirm_small_text']) && is_string($_POST['confirm_small_text']) && $_POST['confirm_small_text'] === '1';
    if ($pdfTextFitWarning && !$confirmSmallText) {
        @unlink($outputPath);
        portal_skade_update_action_token($submissionToken, ['status' => 'pending']);
        $warningStats = is_array($result[2] ?? null) ? $result[2] : [];
        $smallFieldCount = max(1, (int) ($warningStats['below_5pt_fields'] ?? 1));
        $smallestFontPt = is_numeric($warningStats['minimum_font_pt'] ?? null) ? number_format((float) $warningStats['minimum_font_pt'], 1, ',', '') : '';
        $fontDetail = $smallestFontPt !== '' ? ' Minsta storlek är ' . $smallestFontPt . ' pt.' : '';
        $portalSkadeTextFitMessage = 'PDF-förhandskontrollen visar att ' . $smallFieldCount . ' textfält behöver mindre än 5 pt.' . $fontDetail . ' Ingen PDF har sparats eller skickats. Granska uppgifterna och välj sedan uttryckligen om du vill fortsätta.';
        $portalSkadeTextFitConfirmationRequired = true;
        TadegaPrivacyLogger::event('skade.pdf_text_fit_confirmation_required');
        return false;
    }

    $relativeFile = 'pdf/' . $clean['regnr'] . '/' . $fileName;
    if ($isEdit) {
        $recordId = $editId;
    } else {
        try {
            $recordId = portal_random_id();
        } catch (Throwable $e) {
            @unlink($outputPath);
            portal_skade_update_action_token($submissionToken, ['status' => 'pending']);
            TadegaPrivacyLogger::event('skade.pdf_failed');
            return $reject('PDF-filen kunde inte registreras säkert och har tagits bort. Inga uppgifter sparades; be personalen kontrollera lagringen.', 'skade.record_id_failed', [], $e);
        }
    }
    $createdAt = gmdate('Y-m-d\TH:i:s\Z');
    $initialRecord = [
        'id' => $recordId,
        'regnr' => $clean['regnr'],
        'file' => $relativeFile,
        'created_at' => $createdAt,
        'email_accepted' => false,
        'email_sent' => false,
        'email_status' => 'sending',
        'email_retry_pending' => true,
        'email_attempts' => 1,
        'email_last_attempt_at' => $createdAt,
        'signature_drawn' => $signatureDrawn,
        'pdf_text_fit_warning' => $pdfTextFitWarning,
        'form_data' => $formData,
        'signature_png_base64' => $signatureBase64,
        'history' => [['action' => 'created', 'at' => $createdAt]],
        'versions' => [],
    ];
    $records = portal_update_skade_records(static function (array $currentRecords) use ($initialRecord, $isEdit, $editId, $editSourceFile, $relativeFile, $clean, $formData, $signatureBase64, $signatureDrawn, $pdfTextFitWarning, $createdAt): array|false {
        if (!$isEdit) {
            $currentRecords[] = $initialRecord;
            return $currentRecords;
        }
        foreach ($currentRecords as &$record) {
            if (!is_array($record) || ($record['id'] ?? '') !== $editId) {
                continue;
            }
            $currentFile = isset($record['file']) && is_string($record['file']) ? $record['file'] : '';
            if (
                !is_array($record['form_data'] ?? null) || $currentFile === '' ||
                !hash_equals($currentFile, $editSourceFile) || portal_skade_record_file_path($record) === null
            ) {
                unset($record);
                return false;
            }
            $currentRegnr = isset($record['regnr']) && is_string($record['regnr']) ? $record['regnr'] : '';
            $currentVersionDate = (string) ($record['updated_at'] ?? $record['created_at'] ?? $createdAt);
            $versions = is_array($record['versions'] ?? null) ? array_values(array_filter($record['versions'], 'is_array')) : [];
            $versions[] = [
                'file' => $currentFile,
                'regnr' => $currentRegnr,
                'created_at' => $currentVersionDate,
                'archived_at' => $createdAt,
            ];
            $record['versions'] = array_slice($versions, -100);
            $history = is_array($record['history'] ?? null) ? array_values(array_filter($record['history'], 'is_array')) : [];
            $history[] = ['action' => 'updated', 'at' => $createdAt];
            $record['history'] = array_slice($history, -100);
            $record['regnr'] = $clean['regnr'];
            $record['file'] = $relativeFile;
            $record['updated_at'] = $createdAt;
            $record['form_data'] = $formData;
            $record['signature_png_base64'] = $signatureBase64;
            $record['signature_drawn'] = $signatureDrawn;
            $record['pdf_text_fit_warning'] = $pdfTextFitWarning;
            unset($record['private_data_purged_at']);
            $record['email_accepted'] = false;
            $record['email_sent'] = false;
            $record['email_status'] = 'sending';
            $record['email_retry_pending'] = true;
            $record['email_attempts'] = max(0, (int) ($record['email_attempts'] ?? 0)) + 1;
            $record['email_last_attempt_at'] = $createdAt;
            unset($record);
            return $currentRecords;
        }
        unset($record);
        return false;
    });
    if (!is_array($records)) {
        @unlink($outputPath);
        portal_skade_update_action_token($submissionToken, ['status' => 'pending']);
        TadegaPrivacyLogger::event('skade.pdf_failed');
        return $reject(
            $isEdit
                ? 'Ändringen kunde inte sparas. Den tidigare PDF:en finns kvar; ladda om posten från Historik och försök igen.'
                : 'PDF-arkivet kunde inte spara posten. PDF-filen har tagits bort; inga uppgifter sparades. Be personalen kontrollera privat lagring.',
            'skade.record_save_failed'
        );
    }

    $signatureStatus = $signatureDrawn ? 'drawn' : 'missing';
    portal_skade_update_action_token($submissionToken, [
        'status' => 'completed',
        'file' => $relativeFile,
        'mail_status' => 'pending',
        'signature_status' => $signatureStatus,
        'record_id' => $recordId,
        'updated' => $isEdit,
        'text_fit_warning' => $pdfTextFitWarning,
    ]);

    require_once __DIR__ . '/includes/send_skade_email.php';
    $emailData = $clean;
    $emailData['signature_drawn'] = $signatureDrawn;
    $emailData['pdf_text_fit_warning'] = $pdfTextFitWarning;
    $sent = send_skadeblankett_email($outputPath, $emailData, $clean['regnr']);
    $emailAccepted = is_array($sent) && ($sent['accepted'] ?? false) === true;
    $emailTransport = is_array($sent) && is_string($sent['transport'] ?? null) && in_array($sent['transport'], ['smtp', 'php_mail'], true) ? $sent['transport'] : 'none';
    $emailCode = is_array($sent) && is_string($sent['code'] ?? null) ? $sent['code'] : 'preparation_failed';
    portal_email_status_record('skadeblankett', $emailAccepted ? 'accepted' : 'failed', 'skade_submission', $emailTransport, $emailCode);
    $emailStatus = $emailAccepted ? 'sent' : 'failed';
    $attemptAt = gmdate('Y-m-d\TH:i:s\Z');
    $statusSaved = portal_update_skade_records(static function (array $currentRecords) use ($recordId, $relativeFile, $emailAccepted, $attemptAt): array|false {
        foreach ($currentRecords as &$record) {
            if (is_array($record) && ($record['id'] ?? '') === $recordId && ($record['file'] ?? '') === $relativeFile) {
                $record['email_accepted'] = $emailAccepted;
                $record['email_sent'] = $emailAccepted; // Backward-compatible alias; the transport accepted it, not confirmed delivered.
                $record['email_status'] = $emailAccepted ? 'accepted' : 'failed';
                $record['email_retry_pending'] = false;
                $record['email_last_attempt_at'] = $attemptAt;
                unset($record);
                return $currentRecords;
            }
        }
        unset($record);
        return false;
    });
    if (!is_array($statusSaved)) {
        $emailStatus = 'pending';
        TadegaPrivacyLogger::event('skade.email_status_save_failed');
    }
    portal_skade_update_action_token($submissionToken, [
        'status' => 'completed',
        'file' => $relativeFile,
        'mail_status' => $emailStatus,
        'signature_status' => $signatureStatus,
        'record_id' => $recordId,
        'updated' => $isEdit,
        'text_fit_warning' => $pdfTextFitWarning,
    ]);

    if ($digitalSignature) {
        TadegaPrivacyLogger::event('skade.signature_drawn');
    }
    TadegaPrivacyLogger::event('skade.pdf_generated');
    TadegaPrivacyLogger::event($emailAccepted ? 'skade.email_accepted' : 'skade.email_failed');
    portal_skade_redirect_submission_result([
        'file' => $relativeFile,
        'mail_status' => $emailStatus,
        'signature_status' => $signatureStatus,
        'updated' => $isEdit,
        'text_fit_warning' => $pdfTextFitWarning,
    ]);
}
function portal_serve_asset_route(): void
{
    global $activeTab, $portalIsScopedPwa, $portalPwaApp, $protocolAuthUser;

    $download = isset($_GET['download_file']);
    $key = $download ? 'download_file' : 'view_file';
    if (!isset($_GET[$key])) {
        return;
    }
    $relative = $_GET[$key];
    if (!is_string($relative) || $relative === '' || strlen($relative) > 600 || strpos($relative, chr(0)) !== false) {
        http_response_code(404);
        exit;
    }
    $segments = explode('/', $relative);
    $baseName = array_shift($segments);
    if (!in_array($baseName, ['pdf', 'png', 'svg', 'uploads', 'assets'], true) || !$segments) {
        http_response_code(404);
        exit;
    }
    if ($portalIsScopedPwa) {
        $pwaAssetBases = match ($portalPwaApp) {
            'protocol' => ['assets', 'uploads'],
            'invoice' => ['assets'],
            'skadeblankett' => ['assets', 'pdf'],
            default => [],
        };
        if (!in_array($baseName, $pwaAssetBases, true)) {
            http_response_code(404);
            exit;
        }
        if ($portalPwaApp === 'protocol' && $baseName === 'uploads') {
            if (
                ($segments[0] ?? '') !== 'protocols' || count($segments) !== 2 ||
                !preg_match('/\\A[a-f0-9]{32}\\.(?:png|jpe?g)\\z/i', (string) ($segments[1] ?? ''))
            ) {
                http_response_code(404);
                exit;
            }
        }
        if ($portalPwaApp === 'skadeblankett' && $baseName === 'pdf') {
            $isPublicTemplate = count($segments) === 1
                && in_array($segments[0], ['Bilrutan Skadeblankett.pdf', 'Bilrutan_Skadeblankett.pdf'], true);
            $isScopedSkadePdf = preg_match(
                '~\\Apdf/([A-Z0-9-]{2,12})/Skadeblankett-Bilglas-\\1-\\d{8}-\\d{6}-[a-f0-9]{6}\\.pdf\\z~D',
                $relative
            ) === 1;
            if (!$isPublicTemplate && $isScopedSkadePdf) {
                // Customer PWA sessions may see only a PDF generated by their
                // own, still-valid submission token; never enumerate the archive.
                $isScopedSkadePdf = false;
                $tokenStore = $_SESSION['tadega_skade_action_tokens_v1'] ?? [];
                if (is_array($tokenStore)) {
                    foreach ($tokenStore as $tokenEntry) {
                        if (
                            is_array($tokenEntry) &&
                            in_array($tokenEntry['purpose'] ?? '', ['submission', 'edit'], true) &&
                            ($tokenEntry['status'] ?? '') === 'completed' &&
                            is_string($tokenEntry['file'] ?? null) &&
                            hash_equals($tokenEntry['file'], $relative) &&
                            (int) ($tokenEntry['created_at'] ?? 0) >= time() - 86400
                        ) {
                            $isScopedSkadePdf = true;
                            break;
                        }
                    }
                }
            }
            if (!$isPublicTemplate && !$isScopedSkadePdf) {
                http_response_code(404);
                exit;
            }
        }
    }
    if ($baseName === 'uploads' && ($segments[0] ?? '') === 'protocols') {
        if (
            ($activeTab ?? '') !== 'protocol' || !is_array($protocolAuthUser ?? null) || count($segments) !== 2 ||
            !preg_match('/\\A[a-f0-9]{32}\\.(?:png|jpe?g)\\z/i', (string) ($segments[1] ?? ''))
        ) {
            http_response_code(404);
            exit;
        }
    }
    $basePath = realpath(__DIR__ . DIRECTORY_SEPARATOR . $baseName);
    if ($basePath === false || is_link(__DIR__ . DIRECTORY_SEPARATOR . $baseName)) {
        http_response_code(404);
        exit;
    }
    $candidate = __DIR__ . DIRECTORY_SEPARATOR . $baseName;
    foreach ($segments as $segment) {
        if ($segment === '' || $segment === '.' || $segment === '..' || $segment[0] === '.' || preg_match('/[\\x00-\\x1f\\x7f]/u', $segment) || !preg_match('/\\A[\\pL\\pN _().-]{1,180}\\z/u', $segment)) {
            http_response_code(404);
            exit;
        }
        $candidate .= DIRECTORY_SEPARATOR . $segment;
        if (is_link($candidate)) {
            http_response_code(404);
            exit;
        }
    }
    $real = realpath($candidate);
    $prefix = rtrim($basePath, DIRECTORY_SEPARATOR) . DIRECTORY_SEPARATOR;
    if ($real === false || strpos($real, $prefix) !== 0 || !is_file($real)) {
        http_response_code(404);
        exit;
    }
    $extension = strtolower(pathinfo($real, PATHINFO_EXTENSION));
    $allowed = [
        'pdf' => ['pdf'],
        'png' => ['png'],
        'svg' => ['svg'],
        'uploads' => ['pdf', 'png', 'jpg', 'jpeg'],
        'assets' => ['png', 'css', 'js', 'svg'],
    ];
    if (!in_array($extension, $allowed[$baseName], true)) {
        http_response_code(404);
        exit;
    }
    if (
        $baseName === 'assets' &&
        (($extension === 'css' && basename($real) !== 'portal.css') ||
            ($extension === 'js' && basename($real) !== 'signature_pad.js') ||
            ($extension === 'svg' && !in_array(basename($real), ['tadega-icon.svg', 'tadega-logo.svg'], true)))
    ) {
        http_response_code(404);
        exit;
    }
    if (
        $baseName === 'assets' &&
        (basename($real) === 'tadega-logo-fpdf.png' || ($download && basename($real) === 'tadega-logo.svg'))
    ) {
        http_response_code(404);
        exit;
    }
    $size = filesize($real);
    $maxSize = $extension === 'js' ? 262144 : ($extension === 'css' ? 1048576 : ($extension === 'svg' ? 524288 : ($extension === 'pdf' ? 52428800 : 12582912)));
    if (!is_int($size) || $size <= 0 || $size > $maxSize) {
        http_response_code(404);
        exit;
    }
    if ($extension === 'svg') {
        $raw = @file_get_contents($real);
        $safe = is_string($raw) ? portal_sanitize_svg($raw) : null;
        if ($safe === null) {
            http_response_code(404);
            exit;
        }
        $payload = $safe;
        $mime = 'image/svg+xml';
    } elseif ($extension === 'js') {
        $payload = null;
        $mime = 'application/javascript; charset=UTF-8';
    } elseif ($extension === 'css') {
        $payload = null;
        $mime = 'text/css; charset=UTF-8';
    } elseif ($extension === 'pdf') {
        $handle = @fopen($real, 'rb');
        $signature = is_resource($handle) ? fread($handle, 5) : false;
        if (is_resource($handle)) {
            fclose($handle);
        }
        if ($signature !== '%PDF-') {
            http_response_code(404);
            exit;
        }
        $payload = null;
        $mime = 'application/pdf';
    } else {
        $image = @getimagesize($real);
        $expectedMime = $extension === 'png' ? 'image/png' : 'image/jpeg';
        if (!is_array($image) || ($image['mime'] ?? '') !== $expectedMime || (int) ($image[0] ?? 0) < 1 || (int) ($image[1] ?? 0) < 1 || (int) $image[0] > 12000 || (int) $image[1] > 12000 || (int) $image[0] * (int) $image[1] > 60000000) {
            http_response_code(404);
            exit;
        }
        $payload = null;
        $mime = $expectedMime;
    }
    $filename = basename($real);
    $safeFilename = preg_replace('/[^A-Za-z0-9._-]/', '_', $filename);
    header('Content-Type: ' . $mime);
    header('X-Content-Type-Options: nosniff');
    header($baseName === 'assets' ? 'Cache-Control: private, max-age=86400' : 'Cache-Control: private, no-store, max-age=0');
    header('Content-Length: ' . ($payload === null ? $size : strlen($payload)));
    header('Content-Disposition: ' . ($download ? 'attachment' : 'inline') . '; filename="' . $safeFilename . '"');
    if ($extension === 'svg') {
        header("Content-Security-Policy: default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; object-src 'none'; base-uri 'none'");
        if (($_SERVER['REQUEST_METHOD'] ?? 'GET') !== 'HEAD') {
            echo $payload;
        }
    } elseif (($_SERVER['REQUEST_METHOD'] ?? 'GET') !== 'HEAD') {
        readfile($real);
    }
    exit;
}

portal_serve_asset_route();

// Backups belong to portal administration, not any isolated form PWA.
if ($portalIsScopedPwa && isset($_GET['download_backup'])) {
    http_response_code(404);
    exit;
}

// Download private application-generated backups through this controller only.
if (isset($_GET['download_backup']) && is_string($_GET['download_backup'])) {
    $name = $_GET['download_backup'];
    if (!preg_match('/\Atadega-backup-\d{8}-\d{6}-[a-f0-9]{8}\.zip\z/', $name)) {
        http_response_code(404);
        exit;
    }
    $backupDir = realpath(__DIR__ . '/storage/backups');
    $backup = $backupDir !== false ? realpath($backupDir . DIRECTORY_SEPARATOR . $name) : false;
    if ($backupDir === false || $backup === false || strpos($backup, $backupDir . DIRECTORY_SEPARATOR) !== 0 || !is_file($backup)) {
        http_response_code(404);
        exit;
    }
    header('Content-Type: application/zip');
    header('Content-Length: ' . filesize($backup));
    header('Content-Disposition: attachment; filename="' . basename($backup) . '"');
    readfile($backup);
    exit;
}

$portalPostError = '';
$portalSkadeTextFitConfirmationRequired = false;
$portalSkadeTextFitMessage = '';
$portalCsrfFailed = false;
$portalReleaseResult = null;
if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST') {
    $action = isset($_POST['action']) && is_string($_POST['action']) ? $_POST['action'] : '';
    $pwaAllowedActions = match ($portalPwaApp) {
        'protocol' => ['client_diagnostic', 'autosave_draft', 'delete_autosaved_draft', 'protocol_pin_login', 'protocol_pin_logout', 'save_protocol', 'protocol_catalog_quick_save'],
        'invoice' => [
            'client_diagnostic', 'autosave_draft', 'delete_autosaved_draft', 'invoice_first_admin_setup',
            'invoice_pin_login', 'invoice_pin_logout', 'save_invoice', 'invoice_catalog_save_article',
            'invoice_catalog_delete_article', 'invoice_catalog_quick_save', 'retry_invoice_email',
            'invoice_admin_set_fortnox_number', 'invoice_admin_save_email_transport',
            'invoice_admin_lock_email_transport', 'invoice_admin_unlock_email_transport',
            'invoice_admin_test_email', 'invoice_admin_create_user', 'invoice_admin_reset_pin',
        ],
        'skadeblankett' => ['client_diagnostic', 'generate_skadeblankett'],
        default => [],
    };
    if (!csrf_is_valid()) {
        http_response_code(403);
        $portalCsrfFailed = true;
        TadegaPrivacyLogger::event('system.php_error');
        if (in_array($action, ['autosave_draft', 'client_diagnostic'], true)) {
            header('Content-Type: application/json; charset=UTF-8');
            header('Cache-Control: no-store, private, max-age=0, must-revalidate');
            echo json_encode(['ok' => false, 'code' => 'csrf_failed']);
            exit;
        }
    } elseif ($portalIsScopedPwa && !in_array($action, $pwaAllowedActions, true)) {
        http_response_code(404);
        $portalPostError = 'Åtgärden finns inte i den här fristående formulärappen.';
    } elseif ($centralAdminNeedsPinChange && !in_array($action, ['central_admin_change_pin', 'central_admin_logout'], true)) {
        portal_redirect('admin', 'central_admin_pin_expired');
    } elseif (
        $invoiceSetupState === 'unconfigured' && $action !== 'invoice_first_admin_setup' &&
        !$centralAdminCanAccess &&
        !in_array($action, ['central_admin_login', 'central_admin_logout', 'central_admin_enroll', 'central_admin_change_pin'], true)
    ) {
        portal_redirect('invoice');
    } else {
        if (in_array($action, ['portal_release_check', 'portal_release_install'], true)) {
            if ($activeTab !== 'admin' || $portalIsScopedPwa) {
                http_response_code(404);
                if (ob_get_level() > 0 && !headers_sent()) {
                    ob_clean();
                }
                exit;
            } elseif (!$centralAdminCanAccess || !is_array($centralAdminUser) || $centralAdminNeedsPinChange) {
                http_response_code(403);
                $portalPostError = 'Endast en aktiv central admin kan använda releasefunktionen.';
            } elseif ($action === 'portal_release_check') {
                if (function_exists('set_time_limit')) {
                    @set_time_limit(180);
                }
                $portalReleaseResult = portal_release_check_latest(__DIR__);
                $portalReleaseResult['action'] = 'check';
            } else {
                if (function_exists('set_time_limit')) {
                    @set_time_limit(180);
                }
                $approvedTag = portal_post_text($_POST, 'approved_tag', 120);
                $approvedVersion = portal_post_text($_POST, 'approved_version', 80);
                $approvedManifestSha256 = portal_post_text($_POST, 'approved_manifest_sha256', 64);
                $approvalConfirmed = isset($_POST['confirm_install']) && is_string($_POST['confirm_install']) && $_POST['confirm_install'] === '1';
                if (!$approvalConfirmed) {
                    $portalReleaseResult = ['ok' => false, 'code' => 'approval_required', 'action' => 'install'];
                } elseif ($approvedTag === null || $approvedVersion === null || $approvedManifestSha256 === null) {
                    $portalReleaseResult = ['ok' => false, 'code' => 'approval_invalid', 'action' => 'install'];
                } else {
                    $portalReleaseResult = portal_release_install_approved(
                        __DIR__,
                        $approvedTag,
                        $approvedVersion,
                        $approvedManifestSha256
                    );
                    $portalReleaseResult['action'] = 'install';
                    if (($portalReleaseResult['ok'] ?? false) === true) {
                        portal_redirect('admin', ($portalReleaseResult['code'] ?? '') === 'installed'
                            ? 'release_install_success'
                            : 'release_already_current');
                    }
                }
            }
        } elseif ($action === 'portal_search') {
            if ($activeTab !== 'search' || $portalIsScopedPwa) {
                http_response_code(404);
                $portalPostError = 'Sökningen finns bara i Dokumentportalens personalvy.';
            } elseif (!is_array($invoiceAuthUser) && !is_array($protocolAuthUser)) {
                http_response_code(403);
                $portalPostError = 'Logga in på ett behörigt personalområde innan du söker.';
                unset($_POST['q']);
            } elseif (!isset($_POST['q']) || !is_string($_POST['q'])) {
                http_response_code(400);
                $portalPostError = 'Ange en giltig sökfras.';
            } else {
                // Keep potentially identifying search terms in the POST body only.
                $_POST['q'] = portal_global_search_clean_text($_POST['q'], 120);
            }
        } elseif ($action === 'client_diagnostic') {
            $clientType = isset($_POST['diagnostic_type']) && is_string($_POST['diagnostic_type']) ? $_POST['diagnostic_type'] : '';
            if (!in_array($clientType, ['js_error', 'js_unhandled_rejection', 'client_validation'], true)) {
                http_response_code(400);
                header('Content-Type: application/json; charset=UTF-8');
                header('Cache-Control: no-store, private, max-age=0, must-revalidate');
                echo json_encode(['ok' => false, 'code' => 'invalid_type']);
                exit;
            }

            $rateKey = 'portal_client_diagnostic_rate';
            $now = time();
            $rate = is_array($_SESSION[$rateKey] ?? null) ? $_SESSION[$rateKey] : [];
            $windowStart = is_numeric($rate['started'] ?? null) ? (int) $rate['started'] : 0;
            $count = is_numeric($rate['count'] ?? null) ? (int) $rate['count'] : 0;
            if ($windowStart <= 0 || $now - $windowStart >= 60 || $windowStart > $now) {
                $windowStart = $now;
                $count = 0;
            }
            if ($count >= 20) {
                http_response_code(429);
                header('Content-Type: application/json; charset=UTF-8');
                header('Cache-Control: no-store, private, max-age=0, must-revalidate');
                echo json_encode(['ok' => false, 'code' => 'rate_limited']);
                exit;
            }
            $_SESSION[$rateKey] = ['started' => $windowStart, 'count' => $count + 1];

            if ($clientType === 'client_validation') {
                $clientCode = isset($_POST['diagnostic_code']) && is_string($_POST['diagnostic_code']) ? $_POST['diagnostic_code'] : '';
                if ($clientCode !== 'skade.client_validation_failed') {
                    http_response_code(400);
                    header('Content-Type: application/json; charset=UTF-8');
                    header('Cache-Control: no-store, private, max-age=0, must-revalidate');
                    echo json_encode(['ok' => false, 'code' => 'invalid_code']);
                    exit;
                }
                $rawFieldKeys = $_POST['diagnostic_fields'] ?? [];
                $clientFieldKeys = [];
                if (is_array($rawFieldKeys)) {
                    foreach (array_slice($rawFieldKeys, 0, 20) as $fieldKey) {
                        if (is_string($fieldKey) && strlen($fieldKey) <= 60) {
                            $clientFieldKeys[] = $fieldKey;
                        }
                    }
                }
                TadegaPrivacyLogger::applicationError($clientCode, array_values(array_unique($clientFieldKeys)));
                http_response_code(200);
                header('Content-Type: application/json; charset=UTF-8');
                header('Cache-Control: no-store, private, max-age=0, must-revalidate');
                echo json_encode(['ok' => true]);
                exit;
            }

            $rawFile = isset($_POST['diagnostic_file']) && is_string($_POST['diagnostic_file']) ? substr($_POST['diagnostic_file'], 0, 512) : '';
            $clientFile = basename(str_replace(chr(92), '/', $rawFile));
            $clientFile = preg_replace('/[^A-Za-z0-9._-]/', '_', $clientFile) ?? '';
            if ($clientFile === '') {
                $clientFile = 'inline';
            }
            $errorName = isset($_POST['diagnostic_error_name']) && is_string($_POST['diagnostic_error_name']) ? $_POST['diagnostic_error_name'] : '';
            $allowedErrorNames = ['Error', 'TypeError', 'ReferenceError', 'SyntaxError', 'RangeError', 'URIError', 'EvalError', 'AggregateError', 'UnhandledRejection', 'NetworkError', 'AbortError', 'DOMException'];
            if (!in_array($errorName, $allowedErrorNames, true)) {
                $errorName = 'Error';
            }
            $rawLine = isset($_POST['diagnostic_line']) && is_string($_POST['diagnostic_line']) ? $_POST['diagnostic_line'] : '';
            $rawColumn = isset($_POST['diagnostic_column']) && is_string($_POST['diagnostic_column']) ? $_POST['diagnostic_column'] : '';
            $line = ctype_digit($rawLine) ? max(0, min((int) $rawLine, 999999)) : 0;
            $column = ctype_digit($rawColumn) ? max(0, min((int) $rawColumn, 999999)) : 0;

            TadegaPrivacyLogger::diagnostic($clientType, null, $clientFile, $line, $errorName, $activeTab, $column);
            http_response_code(200);
            header('Content-Type: application/json; charset=UTF-8');
            header('Cache-Control: no-store, private, max-age=0, must-revalidate');
            echo json_encode(['ok' => true]);
            exit;
        }
        if ($action === 'autosave_draft') {
            if ($activeTab === 'invoice') {
                $draftUser = portal_invoice_auth_current_user();
                $draftType = 'invoice';
                $draftUserId = is_array($draftUser) ? (string) ($draftUser['id'] ?? '') : '';
                $draftIsAdmin = is_array($draftUser) && ($draftUser['role'] ?? '') === 'admin';
            } elseif ($activeTab === 'protocol') {
                $draftUser = portal_protocol_auth_current_user();
                $draftType = 'protocol';
                $draftUserId = is_array($draftUser) ? (string) ($draftUser['id'] ?? '') : '';
                $draftIsAdmin = false;
            } else {
                http_response_code(400);
                header('Content-Type: application/json; charset=UTF-8');
                echo json_encode(['ok' => false, 'code' => 'invalid_tab']);
                exit;
            }
            if (!is_array($draftUser) || $draftUserId === '') {
                http_response_code(401);
                header('Content-Type: application/json; charset=UTF-8');
                echo json_encode(['ok' => false, 'code' => 'login_required']);
                exit;
            }
            $draftId = isset($_POST['draft_id']) && is_string($_POST['draft_id']) ? $_POST['draft_id'] : '';
            $draftResult = portal_autosaved_drafts_save($draftType, $draftUserId, $draftId, $_POST, $draftIsAdmin);
            http_response_code(($draftResult['ok'] ?? false) === true ? 200 : (($draftResult['code'] ?? '') === 'storage_error' ? 503 : 400));
            header('Content-Type: application/json; charset=UTF-8');
            echo json_encode($draftResult, JSON_INVALID_UTF8_SUBSTITUTE);
            exit;
        }
        if ($action === 'delete_autosaved_draft') {
            if (!in_array($activeTab, ['invoice', 'protocol'], true)) {
                portal_redirect('protocol');
            }
            $draftType = $activeTab;
            $draftUser = $draftType === 'invoice' ? portal_invoice_auth_current_user() : portal_protocol_auth_current_user();
            if (!is_array($draftUser)) {
                portal_redirect($draftType, $draftType === 'invoice' ? 'invoice_login_required' : 'protocol_login_required');
            }
            $draftId = isset($_POST['draft_id']) && is_string($_POST['draft_id']) ? $_POST['draft_id'] : '';
            $deleted = portal_autosaved_drafts_delete($draftType, (string) ($draftUser['id'] ?? ''), $draftId);
            portal_redirect($draftType, ($deleted['ok'] ?? false) === true ? 'draft_deleted' : 'draft_delete_error');
        }
        $localActions = [
            'save_customer' => 'customers', 'delete_customer' => 'customers',
            'upload_pdf_file' => 'files',
        ];
        if ($action === 'invoice_first_admin_setup') {
            if ($activeTab !== 'invoice' || $invoiceSetupState !== 'unconfigured') {
                portal_redirect('invoice', $invoiceSetupState === 'error' ? 'invoice_setup_storage_error' : 'invoice_setup_closed');
            }
            $setupForm = is_array($_POST['admin'] ?? null) ? $_POST['admin'] : [];
            $setupUsername = isset($setupForm['username']) && is_string($setupForm['username']) ? $setupForm['username'] : '';
            $setupName = isset($setupForm['name']) && is_string($setupForm['name']) ? $setupForm['name'] : '';
            $setupPin = isset($setupForm['pin']) && is_string($setupForm['pin']) ? $setupForm['pin'] : '';
            $setupPinConfirm = isset($setupForm['pin_confirm']) && is_string($setupForm['pin_confirm']) ? $setupForm['pin_confirm'] : '';
            if ($setupPin !== $setupPinConfirm) {
                portal_redirect('invoice', 'invoice_setup_pin_mismatch');
            }
            $created = portal_invoice_auth_create_first_admin($setupUsername, $setupName, $setupPin);
            if (($created['ok'] ?? false) === true) {
                portal_redirect('invoice', 'invoice_setup_success');
            }
            $setupCode = (string) ($created['code'] ?? '');
            $setupNotice = in_array($setupCode, ['invalid_username', 'invalid_name', 'invalid_pin'], true)
                ? 'invoice_setup_error'
                : ($setupCode === 'setup_closed' ? 'invoice_setup_closed' : 'invoice_setup_storage_error');
            portal_redirect('invoice', $setupNotice);
        } elseif ($action === 'central_admin_enroll') {
            if ($activeTab !== 'admin' || $portalIsScopedPwa) {
                portal_redirect('admin');
            }
            $newPin = isset($_POST['new_pin']) && is_string($_POST['new_pin']) ? $_POST['new_pin'] : '';
            $confirmPin = isset($_POST['pin_confirm']) && is_string($_POST['pin_confirm']) ? $_POST['pin_confirm'] : '';
            if (!hash_equals($newPin, $confirmPin)) {
                portal_redirect('admin', 'central_admin_pin_mismatch');
            }
            $created = portal_central_admin_auth_enroll($newPin);
            if (($created['ok'] ?? false) === true) {
                portal_redirect('admin', 'central_admin_setup_success');
            }
            $enrollMessage = match ($created['code'] ?? '') {
                'invalid_pin' => 'central_admin_pin_policy_error',
                'already_configured' => 'central_admin_setup_closed',
                'forbidden' => 'central_admin_enroll_forbidden',
                'session_error' => 'central_admin_session_error',
                default => 'central_admin_storage_error',
            };
            portal_redirect('admin', $enrollMessage);
        } elseif ($action === 'central_admin_login') {
            if ($activeTab !== 'admin' || $portalIsScopedPwa) {
                portal_redirect('admin');
            }
            $centralPin = isset($_POST['central_pin']) && is_string($_POST['central_pin']) ? $_POST['central_pin'] : '';
            $login = portal_central_admin_auth_login($centralPin);
            if (($login['ok'] ?? false) === true) {
                portal_redirect('admin', ($login['must_change_pin'] ?? false) === true
                    ? 'central_admin_pin_expired'
                    : 'central_admin_login_success');
            }
            $loginMessage = match ($login['code'] ?? '') {
                'locked' => 'central_admin_login_locked',
                'storage_error' => 'central_admin_storage_error',
                'setup_required' => 'central_admin_setup_required',
                'forbidden' => 'central_admin_login_forbidden',
                default => 'central_admin_login_failed',
            };
            portal_redirect('admin', $loginMessage);
        } elseif ($action === 'central_admin_change_pin') {
            if ($activeTab !== 'admin' || $portalIsScopedPwa) {
                portal_redirect('admin');
            }
            $currentPin = isset($_POST['current_pin']) && is_string($_POST['current_pin']) ? $_POST['current_pin'] : '';
            $newPin = isset($_POST['new_pin']) && is_string($_POST['new_pin']) ? $_POST['new_pin'] : '';
            $confirmPin = isset($_POST['pin_confirm']) && is_string($_POST['pin_confirm']) ? $_POST['pin_confirm'] : '';
            if (!hash_equals($newPin, $confirmPin)) {
                portal_redirect('admin', 'central_admin_pin_mismatch');
            }
            $changed = portal_central_admin_auth_change_pin($currentPin, $newPin);
            $changeMessage = match ($changed['code'] ?? '') {
                'changed' => 'central_admin_pin_changed',
                'invalid_new_pin' => 'central_admin_pin_policy_error',
                'invalid_current_pin' => 'central_admin_current_pin_error',
                'same_pin' => 'central_admin_pin_same',
                'locked' => 'central_admin_login_locked',
                'session_expired', 'forbidden' => 'central_admin_session_expired',
                'session_error' => 'central_admin_session_error',
                default => 'central_admin_storage_error',
            };
            portal_redirect('admin', $changeMessage);
        } elseif ($action === 'central_admin_logout') {
            if ($activeTab !== 'admin' || $portalIsScopedPwa) {
                portal_redirect('admin');
            }
            portal_central_admin_auth_logout();
            portal_redirect('admin', 'central_admin_logout');
        } elseif ($action === 'protocol_pin_login') {
            if ($activeTab !== 'protocol') {
                portal_redirect('protocol');
            }
            $loginName = isset($_POST['username']) && is_string($_POST['username']) ? $_POST['username'] : '';
            $loginPin = isset($_POST['pin']) && is_string($_POST['pin']) ? $_POST['pin'] : '';
            $login = portal_protocol_auth_login($loginName, $loginPin);
            if (($login['ok'] ?? false) === true) {
                portal_redirect('protocol', 'protocol_login_success');
            }
            $loginCode = (string) ($login['code'] ?? '');
            portal_redirect('protocol', $loginCode === 'locked' ? 'protocol_login_locked' : ($loginCode === 'storage_error' ? 'protocol_auth_storage_error' : 'protocol_login_failed'));
        } elseif ($action === 'protocol_pin_logout') {
            if ($activeTab !== 'protocol') {
                portal_redirect('protocol');
            }
            portal_protocol_auth_logout();
            portal_redirect('protocol', 'protocol_logout');
        } elseif ($action === 'invoice_pin_login') {
            if ($activeTab !== 'invoice') {
                portal_redirect('invoice');
            }
            $loginName = isset($_POST['username']) && is_string($_POST['username']) ? $_POST['username'] : '';
            $loginPin = isset($_POST['pin']) && is_string($_POST['pin']) ? $_POST['pin'] : '';
            $rememberLogin = isset($_POST['remember_me']) && is_string($_POST['remember_me']) && $_POST['remember_me'] === '1';
            $login = portal_invoice_auth_login($loginName, $loginPin, $rememberLogin);
            if (($login['ok'] ?? false) === true) {
                $loginReturnTab = in_array($_SESSION['portal_invoice_login_return_tab'] ?? '', ['customers', 'search', 'admin'], true)
                    ? (string) $_SESSION['portal_invoice_login_return_tab']
                    : 'invoice';
                unset($_SESSION['portal_invoice_login_return_tab']);
                if ($rememberLogin && ($login['remember_saved'] ?? false) !== true) {
                    portal_redirect($loginReturnTab, 'invoice_login_remember_failed');
                }
                portal_redirect($loginReturnTab, $rememberLogin ? 'invoice_login_remembered' : 'invoice_login_success');
            }
            portal_redirect('invoice', ($login['code'] ?? '') === 'locked' ? 'invoice_login_locked' : 'invoice_login_failed');
        } elseif ($action === 'invoice_pin_logout') {
            if ($activeTab !== 'invoice') {
                portal_redirect('invoice');
            }
            portal_invoice_auth_logout();
            portal_redirect('invoice', 'invoice_logout');
        } elseif ($action === 'invoice_admin_save_email_transport') {
            if ($activeTab !== 'invoice' || !isset($_GET['invoice_view']) || $_GET['invoice_view'] !== 'email') {
                portal_redirect('invoice');
            }
            $mailAdmin = portal_invoice_auth_current_user();
            if (!is_array($mailAdmin) || ($mailAdmin['role'] ?? '') !== 'admin') {
                portal_redirect('invoice', 'invoice_admin_required');
            }
            $smtpInput = [];
            foreach (['smtp_host', 'smtp_profile', 'smtp_username', 'smtp_password', 'smtp_from_email', 'smtp_from_name'] as $field) {
                $smtpInput[$field] = isset($_POST[$field]) && is_string($_POST[$field]) ? $_POST[$field] : '';
            }
            $saveResult = portal_email_transport_save_settings($smtpInput);
            $saveMessage = match ($saveResult['code'] ?? '') {
                'saved' => 'email_transport_saved',
                'locked' => 'email_transport_locked',
                'config_invalid_values' => 'email_transport_validation_error',
                default => 'email_transport_storage_error',
            };
            portal_redirect('invoice', $saveMessage);
        } elseif ($action === 'invoice_admin_lock_email_transport') {
            if ($activeTab !== 'invoice' || !isset($_GET['invoice_view']) || $_GET['invoice_view'] !== 'email') {
                portal_redirect('invoice');
            }
            $mailAdmin = portal_invoice_auth_current_user();
            if (!is_array($mailAdmin) || ($mailAdmin['role'] ?? '') !== 'admin') {
                portal_redirect('invoice', 'invoice_admin_required');
            }
            $lockResult = portal_email_transport_set_locked(true);
            $lockMessage = match ($lockResult['code'] ?? '') {
                'locked' => 'email_transport_locked',
                'test_required' => 'email_transport_test_required',
                default => 'email_transport_storage_error',
            };
            portal_redirect('invoice', $lockMessage);
        } elseif ($action === 'invoice_admin_unlock_email_transport') {
            if ($activeTab !== 'invoice' || !isset($_GET['invoice_view']) || $_GET['invoice_view'] !== 'email') {
                portal_redirect('invoice');
            }
            $mailAdmin = portal_invoice_auth_current_user();
            if (!is_array($mailAdmin) || ($mailAdmin['role'] ?? '') !== 'admin') {
                portal_redirect('invoice', 'invoice_admin_required');
            }
            $unlockPin = isset($_POST['admin_pin']) && is_string($_POST['admin_pin']) ? $_POST['admin_pin'] : '';
            $pinCheck = portal_invoice_auth_verify_current_admin_pin($unlockPin);
            if (($pinCheck['ok'] ?? false) !== true) {
                portal_redirect('invoice', ($pinCheck['code'] ?? '') === 'locked' ? 'email_transport_unlock_rate_limited' : 'email_transport_unlock_pin_error');
            }
            $unlockResult = portal_email_transport_set_locked(false, true);
            portal_redirect('invoice', ($unlockResult['code'] ?? '') === 'unlocked' ? 'email_transport_unlocked' : 'email_transport_storage_error');
        } elseif ($action === 'invoice_admin_test_email') {
            if ($activeTab !== 'invoice' || !isset($_GET['invoice_view']) || $_GET['invoice_view'] !== 'email') {
                portal_redirect('invoice');
            }
            $mailAdmin = portal_invoice_auth_current_user();
            if (!is_array($mailAdmin) || ($mailAdmin['role'] ?? '') !== 'admin') {
                portal_redirect('invoice', 'invoice_admin_required');
            }
            $testResult = portal_email_send_test('invoice');
            $testMessage = match ($testResult['result'] ?? '') {
                'accepted' => 'email_test_invoice_accepted',
                'not_configured' => 'email_test_invoice_not_configured',
                default => 'email_test_invoice_failed',
            };
            portal_redirect('invoice', $testMessage);
        } elseif ($action === 'skade_admin_test_email') {
            if ($activeTab !== 'invoice' || !isset($_GET['invoice_view']) || $_GET['invoice_view'] !== 'email') {
                portal_redirect('invoice');
            }
            $mailAdmin = portal_invoice_auth_current_user();
            if (!is_array($mailAdmin) || ($mailAdmin['role'] ?? '') !== 'admin') {
                portal_redirect('invoice', 'invoice_admin_required');
            }
            $testResult = portal_email_send_test('skadeblankett');
            if (($testResult['result'] ?? '') === 'accepted' && ($testResult['transport'] ?? '') === 'smtp' && ($testResult['test_marked'] ?? false) !== true) {
                portal_redirect('invoice', 'email_test_skade_accepted_not_marked');
            }
            portal_redirect('invoice', ($testResult['result'] ?? '') === 'accepted' ? 'email_test_skade_accepted' : 'email_test_skade_failed');
        } elseif ($action === 'invoice_admin_set_fortnox_number') {
            if ($activeTab !== 'invoice' || !isset($_GET['invoice_view']) || $_GET['invoice_view'] !== 'processing') {
                portal_redirect('invoice');
            }
            $numberAdmin = portal_invoice_auth_current_user();
            if (!is_array($numberAdmin) || ($numberAdmin['role'] ?? '') !== 'admin') {
                portal_redirect('invoice', 'invoice_admin_required');
            }
            $targetInvoiceId = portal_post_text($_POST, 'invoice_id', 128);
            $fortnoxNumber = portal_post_text($_POST, 'fortnox_invoice_number', 80);
            $fortnoxDate = portal_post_text($_POST, 'fortnox_invoice_date', 10);
            if (
                $targetInvoiceId === null || $targetInvoiceId === '' || $fortnoxNumber === null || $fortnoxNumber === '' ||
                !preg_match('/\A[\pL\pN][\pL\pN .\/_-]{0,79}\z/u', $fortnoxNumber)
            ) {
                portal_redirect('invoice', 'invoice_number_error');
            }
            if ($fortnoxDate === null || !portal_valid_iso_date($fortnoxDate)) {
                portal_redirect('invoice', 'invoice_number_date_error');
            }
            $invoiceRecordsForNumber = load_data(INVOICES_FILE, []);
            $numberRecordIndex = null;
            foreach ($invoiceRecordsForNumber as $invoiceRecordIndex => $invoiceRecord) {
                if (is_array($invoiceRecord) && (string) ($invoiceRecord['id'] ?? '') === $targetInvoiceId) {
                    $numberRecordIndex = $invoiceRecordIndex;
                    break;
                }
            }
            if ($numberRecordIndex === null || !is_array($invoiceRecordsForNumber[$numberRecordIndex] ?? null)) {
                portal_redirect('invoice', 'invoice_number_not_found');
            }
            $targetInvoice = $invoiceRecordsForNumber[$numberRecordIndex];
            $existingFortnoxNumber = is_scalar($targetInvoice['fortnox_invoice_number'] ?? null) ? trim((string) $targetInvoice['fortnox_invoice_number']) : '';
            if ($existingFortnoxNumber !== '') {
                portal_redirect('invoice', 'invoice_number_already_set');
            }
            $numberNow = gmdate('Y-m-d\TH:i:s\Z');
            $numberActor = [
                'id' => (string) ($numberAdmin['id'] ?? ''),
                'username' => (string) ($numberAdmin['username'] ?? ''),
                'name' => (string) ($numberAdmin['name'] ?? $numberAdmin['username'] ?? ''),
            ];
            $numberHistory = is_array($targetInvoice['history'] ?? null)
                ? array_values(array_filter($targetInvoice['history'], 'is_array'))
                : [];
            $numberHistory[] = ['action' => 'updated', 'at' => $numberNow, 'actor' => $numberActor];
            $targetInvoice['fortnox_invoice_number'] = $fortnoxNumber;
            $targetInvoice['fortnox_invoice_date'] = $fortnoxDate;
            $targetInvoice['updated_at'] = $numberNow;
            $targetInvoice['updated_by'] = $numberActor;
            $targetInvoice['history'] = $numberHistory;
            $invoiceRecordsForNumber[$numberRecordIndex] = $targetInvoice;
            if (!save_data(INVOICES_FILE, array_values($invoiceRecordsForNumber))) {
                portal_redirect('invoice', 'invoice_number_storage_error');
            }
            TadegaPrivacyLogger::event('invoice.fortnox_number_set');
            portal_redirect('invoice', 'invoice_number_saved');
        } elseif ($action === 'invoice_catalog_quick_save') {
            if ($activeTab !== 'invoice') {
                portal_json_response(['ok' => false, 'code' => 'invalid_tab'], 404);
            }
            $quickCatalogUser = portal_invoice_auth_current_user();
            if (!is_array($quickCatalogUser)) {
                portal_json_response(['ok' => false, 'code' => 'login_required'], 401);
            }
            if (($quickCatalogUser['role'] ?? '') !== 'admin') {
                portal_json_response(['ok' => false, 'code' => 'admin_required'], 403);
            }
            $quickCatalogResult = portal_invoice_catalog_save($_POST);
            if (($quickCatalogResult['ok'] ?? false) === true) {
                portal_json_response(['ok' => true, 'code' => $quickCatalogResult['code'] ?? 'saved']);
            }
            $quickCatalogCode = (string) ($quickCatalogResult['code'] ?? 'save_error');
            portal_json_response(
                ['ok' => false, 'code' => $quickCatalogCode],
                $quickCatalogCode === 'storage_error' ? 503 : 422
            );
        } elseif ($action === 'protocol_catalog_quick_save') {
            if ($activeTab !== 'protocol') {
                portal_json_response(['ok' => false, 'code' => 'invalid_tab'], 404);
            }
            $quickProtocolUser = portal_protocol_auth_current_user();
            if (!is_array($quickProtocolUser)) {
                portal_json_response(['ok' => false, 'code' => 'login_required'], 401);
            }
            if (($quickProtocolUser['role'] ?? '') !== 'admin') {
                portal_json_response(['ok' => false, 'code' => 'admin_required'], 403);
            }
            $quickProtocolResult = portal_protocol_catalog_save($_POST);
            if (($quickProtocolResult['ok'] ?? false) === true) {
                portal_json_response(['ok' => true, 'code' => $quickProtocolResult['code'] ?? 'saved']);
            }
            $quickProtocolCode = (string) ($quickProtocolResult['code'] ?? 'save_error');
            portal_json_response(
                ['ok' => false, 'code' => $quickProtocolCode],
                $quickProtocolCode === 'storage_error' ? 503 : 422
            );
        } elseif ($action === 'invoice_catalog_save_article' || $action === 'invoice_catalog_delete_article') {
            if ($activeTab !== 'invoice' || !isset($_GET['invoice_view']) || $_GET['invoice_view'] !== 'articles') {
                portal_redirect('invoice');
            }
            $catalogUser = portal_invoice_auth_current_user();
            if (!is_array($catalogUser)) {
                portal_redirect('invoice', 'invoice_login_required');
            }
            if ($action === 'invoice_catalog_save_article') {
                $catalogResult = portal_invoice_catalog_save($_POST);
                if (($catalogResult['ok'] ?? false) === true) {
                    portal_redirect('invoice', 'invoice_article_saved');
                }
                $catalogMessage = match ($catalogResult['code'] ?? '') {
                    'storage_error' => 'invoice_catalog_storage_error',
                    'catalog_full' => 'invoice_catalog_full',
                    default => 'invoice_article_save_error',
                };
                portal_redirect('invoice', $catalogMessage);
            }
            $deleteArticleId = isset($_POST['article_id']) && is_string($_POST['article_id']) ? $_POST['article_id'] : '';
            $deleteArticleResult = portal_invoice_catalog_delete($deleteArticleId);
            if (($deleteArticleResult['ok'] ?? false) === true) {
                portal_redirect('invoice', 'invoice_article_deleted');
            }
            portal_redirect('invoice', ($deleteArticleResult['code'] ?? '') === 'storage_error' ? 'invoice_catalog_storage_error' : 'invoice_article_delete_error');
        } elseif ($action === 'invoice_admin_create_user') {
            if ($activeTab !== 'invoice') {
                portal_redirect('invoice');
            }
            $userForm = is_array($_POST['user'] ?? null) ? $_POST['user'] : [];
            $created = portal_invoice_auth_create_user(
                isset($userForm['username']) && is_string($userForm['username']) ? $userForm['username'] : '',
                isset($userForm['name']) && is_string($userForm['name']) ? $userForm['name'] : '',
                isset($userForm['pin']) && is_string($userForm['pin']) ? $userForm['pin'] : '',
                isset($userForm['role']) && is_string($userForm['role']) ? $userForm['role'] : 'staff'
            );
            if (($created['ok'] ?? false) === true) {
                portal_redirect('invoice', 'invoice_user_created');
            }
            portal_redirect('invoice', ($created['code'] ?? '') === 'forbidden' ? 'invoice_admin_required' : 'invoice_user_create_error');
        } elseif ($action === 'invoice_admin_reset_pin') {
            if ($activeTab !== 'invoice') {
                portal_redirect('invoice');
            }
            $userId = isset($_POST['user_id']) && is_string($_POST['user_id']) ? $_POST['user_id'] : '';
            $newPin = isset($_POST['new_pin']) && is_string($_POST['new_pin']) ? $_POST['new_pin'] : '';
            $reset = portal_invoice_auth_reset_pin($userId, $newPin);
            if (($reset['ok'] ?? false) === true) {
                portal_redirect('invoice', 'invoice_pin_reset');
            }
            portal_redirect('invoice', ($reset['code'] ?? '') === 'forbidden' ? 'invoice_admin_required' : 'invoice_pin_reset_error');
        } elseif ($action === 'protocol_admin_create_user') {
            if ($activeTab !== 'invoice' || !isset($_GET['invoice_view']) || $_GET['invoice_view'] !== 'admin') {
                portal_redirect('invoice');
            }
            $userForm = is_array($_POST['protocol_user'] ?? null) ? $_POST['protocol_user'] : [];
            $created = portal_protocol_auth_create_user(
                isset($userForm['username']) && is_string($userForm['username']) ? $userForm['username'] : '',
                isset($userForm['name']) && is_string($userForm['name']) ? $userForm['name'] : '',
                isset($userForm['pin']) && is_string($userForm['pin']) ? $userForm['pin'] : '',
                isset($userForm['role']) && is_string($userForm['role']) ? $userForm['role'] : 'staff'
            );
            if (($created['ok'] ?? false) === true) {
                portal_redirect('invoice', 'protocol_user_created');
            }
            portal_redirect('invoice', ($created['code'] ?? '') === 'forbidden' ? 'invoice_admin_required' : 'protocol_user_create_error');
        } elseif ($action === 'protocol_admin_reset_pin') {
            if ($activeTab !== 'invoice' || !isset($_GET['invoice_view']) || $_GET['invoice_view'] !== 'admin') {
                portal_redirect('invoice');
            }
            $userId = isset($_POST['protocol_user_id']) && is_string($_POST['protocol_user_id']) ? $_POST['protocol_user_id'] : '';
            $newPin = isset($_POST['protocol_new_pin']) && is_string($_POST['protocol_new_pin']) ? $_POST['protocol_new_pin'] : '';
            $reset = portal_protocol_auth_reset_pin($userId, $newPin);
            if (($reset['ok'] ?? false) === true) {
                portal_redirect('invoice', 'protocol_user_pin_reset');
            }
            portal_redirect('invoice', ($reset['code'] ?? '') === 'forbidden' ? 'invoice_admin_required' : 'protocol_user_pin_reset_error');
        } elseif ($action === 'protocol_admin_set_role') {
            if ($activeTab !== 'invoice' || !isset($_GET['invoice_view']) || $_GET['invoice_view'] !== 'admin' || $portalIsScopedPwa) {
                portal_redirect('invoice');
            }
            $protocolRoleUserId = isset($_POST['protocol_user_id']) && is_string($_POST['protocol_user_id']) ? $_POST['protocol_user_id'] : '';
            $protocolRole = isset($_POST['protocol_role']) && is_string($_POST['protocol_role']) ? $_POST['protocol_role'] : '';
            $roleUpdate = portal_protocol_auth_set_role($protocolRoleUserId, $protocolRole);
            if (($roleUpdate['ok'] ?? false) === true) {
                if (($roleUpdate['code'] ?? '') === 'role_updated') {
                    TadegaPrivacyLogger::event('protocol.user_role_updated');
                }
                portal_redirect('invoice', ($roleUpdate['code'] ?? '') === 'unchanged' ? 'protocol_user_role_unchanged' : 'protocol_user_role_updated');
            }
            $roleMessage = match ($roleUpdate['code'] ?? '') {
                'last_admin' => 'protocol_user_last_admin',
                default => 'protocol_user_role_error',
            };
            portal_redirect('invoice', $roleMessage);
        } elseif (isset($localActions[$action])) {
            if ($activeTab !== $localActions[$action]) {
                portal_redirect($localActions[$action], '');
            }
        } elseif ($action === 'save_settings') {
            $email = portal_post_text($_POST, 'notification_email', 254);
            if ($email === null || !filter_var($email, FILTER_VALIDATE_EMAIL)) {
                portal_redirect('settings', 'email_error');
            }
            if (!save_data(SETTINGS_FILE, array_merge(load_settings(), ['notification_email' => $email]))) {
                portal_redirect('settings', 'save_error');
            }
            TadegaPrivacyLogger::event('settings.updated');
            portal_redirect('settings', 'success');
        } elseif ($action === 'upload_logo') {
            portal_redirect('settings', portal_handle_svg_upload() ? 'logo_ok' : 'logo_error');
        } elseif ($action === 'trigger_backup') {
            $backup = create_backup();
            if (!is_string($backup) || !is_file($backup)) {
                portal_redirect('settings', 'backup_error');
            }
            $_SESSION['tadega_latest_backup'] = basename($backup);
            portal_redirect('settings', 'backup_ok');
        } elseif ($action === 'save_protocol') {
            if ($activeTab !== 'protocol') {
                portal_redirect('protocol');
            }
            $protocolSavingUser = portal_protocol_auth_current_user();
            if (!is_array($protocolSavingUser)) {
                portal_redirect('protocol', 'protocol_login_required');
            }
            $savedProtocolId = portal_save_protocol();
            if ($savedProtocolId === false) {
                $failureCode = is_string($_SESSION['portal_protocol_save_failure'] ?? null) ? $_SESSION['portal_protocol_save_failure'] : '';
                unset($_SESSION['portal_protocol_save_failure']);
                $context = [];
                $postedFields = is_array($_POST['p'] ?? null) ? $_POST['p'] : [];
                $postedId = isset($postedFields['id']) && is_string($postedFields['id']) ? $postedFields['id'] : '';
                $postedDraftId = isset($_POST['draft_id']) && is_string($_POST['draft_id']) ? $_POST['draft_id'] : '';
                if ($postedId !== '' && preg_match('/\\A[a-f0-9]{32}\\z/i', $postedId)) {
                    $context['edit_id'] = $postedId;
                }
                if ($postedDraftId !== '' && preg_match('/\\A[A-Za-z0-9_-]{1,128}\\z/D', $postedDraftId)) {
                    $context['draft_id'] = $postedDraftId;
                }
                if ($failureCode === 'signature_required') {
                    portal_redirect('protocol', 'protocol_signature_required', $context);
                }
                portal_redirect('protocol', 'save_error', $context);
            }

            $draftId = isset($_POST['draft_id']) && is_string($_POST['draft_id']) ? $_POST['draft_id'] : '';
            $draftCleanupOk = true;
            if ($draftId !== '') {
                $cleanup = portal_autosaved_drafts_delete('protocol', (string) ($protocolSavingUser['id'] ?? ''), $draftId);
                $draftCleanupOk = ($cleanup['ok'] ?? false) === true || ($cleanup['code'] ?? '') === 'not_found';
            }

            $savedProtocol = portal_protocol_find_saved($savedProtocolId);
            $emailDelivery = is_array($savedProtocol)
                ? portal_send_protocol_saved_email($savedProtocol)
                : ['accepted' => false, 'result' => 'failed', 'transport' => 'none', 'code' => 'protocol_not_found'];
            $emailStatusSaved = portal_protocol_email_status_update($savedProtocolId, $emailDelivery);
            if (($emailDelivery['result'] ?? '') === 'accepted') {
                TadegaPrivacyLogger::event('protocol.email_accepted');
            } elseif (($emailDelivery['result'] ?? '') === 'not_configured') {
                TadegaPrivacyLogger::event('protocol.email_not_configured');
            } else {
                TadegaPrivacyLogger::event('protocol.email_failed');
            }

            if (!$emailStatusSaved) {
                $notice = $draftCleanupOk ? 'protocol_email_status_storage_error' : 'protocol_email_status_storage_and_draft_cleanup_error';
            } elseif (($emailDelivery['result'] ?? '') === 'accepted') {
                $notice = $draftCleanupOk ? 'protocol_email_accepted' : 'protocol_email_accepted_draft_cleanup_error';
            } elseif (($emailDelivery['result'] ?? '') === 'not_configured') {
                $notice = $draftCleanupOk ? 'protocol_email_not_configured' : 'protocol_email_not_configured_draft_cleanup_error';
            } else {
                $notice = $draftCleanupOk ? 'protocol_email_failed' : 'protocol_email_failed_draft_cleanup_error';
            }
            portal_redirect('protocol', $notice, ['view_id' => $savedProtocolId]);
        } elseif ($action === 'save_invoice') {
            if ($activeTab !== 'invoice') {
                portal_redirect('invoice');
            }
            if (!is_array(portal_invoice_auth_current_user())) {
                portal_redirect('invoice', 'invoice_login_required');
            }
            if (!portal_save_invoice()) {
                portal_redirect('invoice', 'save_error');
            }
            $invoiceSavingUser = portal_invoice_auth_current_user();
            $draftCleanupOk = true;
            if (is_array($invoiceSavingUser) && isset($_POST['draft_id']) && is_string($_POST['draft_id']) && $_POST['draft_id'] !== '') {
                $cleanup = portal_autosaved_drafts_delete('invoice', (string) ($invoiceSavingUser['id'] ?? ''), $_POST['draft_id']);
                $draftCleanupOk = ($cleanup['ok'] ?? false) === true || ($cleanup['code'] ?? '') === 'not_found';
            }
            $mailSent = ($_SESSION['portal_invoice_email_sent'] ?? false) === true;
            $emailStatusSaved = ($_SESSION['portal_invoice_email_status_saved'] ?? false) === true;
            unset($_SESSION['portal_invoice_email_sent'], $_SESSION['portal_invoice_email_status_saved']);
            if (!$emailStatusSaved) {
                $invoiceNotice = $draftCleanupOk ? 'invoice_email_status_storage_error' : 'invoice_email_status_storage_and_draft_cleanup_error';
            } else {
                $invoiceNotice = $draftCleanupOk
                    ? ($mailSent ? 'saved_email_sent' : 'saved_email_failed')
                    : ($mailSent ? 'saved_email_sent_draft_cleanup_error' : 'saved_email_failed_draft_cleanup_error');
            }
            portal_redirect('invoice', $invoiceNotice);
        } elseif ($action === 'retry_invoice_email') {
            if ($activeTab !== 'invoice') {
                portal_redirect('invoice');
            }
            $retryingUser = portal_invoice_auth_current_user();
            if (!is_array($retryingUser) || ($retryingUser['role'] ?? '') !== 'admin') {
                portal_redirect('invoice', 'invoice_admin_required');
            }
            $invoiceId = portal_post_text($_POST, 'invoice_id', 128);
            if ($invoiceId === null || !preg_match('/\A[a-f0-9]{32}\z/i', $invoiceId)) {
                portal_redirect('invoice', 'invoice_email_retry_not_found');
            }
            $invoiceToRetry = null;
            foreach (load_data(INVOICES_FILE, []) as $invoiceRecord) {
                if (is_array($invoiceRecord) && (string) ($invoiceRecord['id'] ?? '') === $invoiceId) {
                    $invoiceToRetry = $invoiceRecord;
                    break;
                }
            }
            if (!is_array($invoiceToRetry)) {
                portal_redirect('invoice', 'invoice_email_retry_not_found');
            }
            $emailResult = portal_send_invoice_saved_email($invoiceToRetry, 'invoice_retry');
            if (!portal_invoice_email_status_update($invoiceId, $emailResult, $retryingUser)) {
                portal_redirect('invoice', 'invoice_email_status_storage_error');
            }
            TadegaPrivacyLogger::event('invoice.email_retry');
            portal_redirect('invoice', $emailResult['accepted'] === true ? 'invoice_email_retry_accepted' : 'invoice_email_retry_failed');
        } elseif ($action === 'generate_skadeblankett') {
            $ok = portal_handle_skade_submission();
            if (!$ok) {
                http_response_code(422);
                if ($portalPostError === '' && !$portalSkadeTextFitConfirmationRequired) {
                    $portalPostError = 'Blanketten kunde inte färdigställas. Kontrollera uppgifterna och försök igen. Om inga fält markeras, be personalen kontrollera PDF-mall och lagringsbehörigheter. Inga uppgifter har sparats.';
                }
            }
        } elseif ($action === 'retry_skade_email') {
            portal_handle_skade_email_retry();
        } else {
            http_response_code(400);
            $portalPostError = 'Kontrollera fält med felmarkering och försök igen. Om felet återkommer, kontakta administratören och ange flik och tidpunkt. Skicka inte en ny begäran om åtgärden redan verkar vara klar.';
        }
    }
}

$noticeMessages = [
    'success' => 'Inställningarna har sparats.',
    'release_install_success' => 'Den signerade GitHub-releasen installerades efter ditt godkännande. Endast ändrade tillåtna programfiler skrevs; storage/ lämnades orörd. Ta en ny webbhotellsbackup innan nästa release.',
    'release_already_current' => 'Den godkända GitHub-releasen matchade redan installerade filer. Ingen programfil skrevs.',
    'release_update_failed' => 'GitHub-uppdateringen stoppades. Läs felinformationen i Adminpanelen; ingen uppdatering bekräftades.',
    'release_changed_since_approval' => 'GitHub-releasen ändrades efter kontrollen. Ingen installation gjordes; kör kontrollen igen och granska den nya releasen.',
    'release_rollback_failed' => 'KRITISKT: återställningen kunde inte verifieras. Sluta använda portalen och återställ från webbhotellets manuella säkerhetskopia innan fortsatt drift.',
    'saved' => 'Underlaget har sparats.',
    'saved_draft_cleanup_error' => 'Underlaget har sparats, men det autosparade utkastet kunde inte tas bort. Ta bort det manuellt under Utkast.',
    'protocol_signature_required' => 'Protokollets innehåll har ändrats. Rita en ny teknikersignatur innan du sparar.',
    'protocol_email_accepted' => 'Serviceprotokollet har sparats. E-posttransporten accepterade PDF-mejlet till portalens primära interna mottagare; det bekräftar inte leverans till inkorgen. Ingen kundkopia skickades.',
    'protocol_email_failed' => 'Serviceprotokollet har sparats, men PDF-mejlet kunde inte accepteras. Kontrollera portalens primära mottagaradress och e-posttransport. Ingen kundkopia skickades.',
    'protocol_email_not_configured' => 'Serviceprotokollet har sparats, men ingen giltig primär intern mottagaradress är konfigurerad. Inget mejl skickades och ingen kundkopia skickades.',
    'protocol_email_accepted_draft_cleanup_error' => 'Serviceprotokollet har sparats och e-posttransporten accepterade PDF-mejlet, men det autosparade utkastet kunde inte tas bort. Leverans till inkorgen är inte bekräftad. Ingen kundkopia skickades.',
    'protocol_email_failed_draft_cleanup_error' => 'Serviceprotokollet har sparats, men PDF-mejlet kunde inte accepteras och det autosparade utkastet kunde inte tas bort. Kontrollera mottagaradress och transport. Ingen kundkopia skickades.',
    'protocol_email_not_configured_draft_cleanup_error' => 'Serviceprotokollet har sparats, men primär intern mottagare saknas och utkastet kunde inte tas bort. Inget mejl skickades och ingen kundkopia skickades.',
    'protocol_email_status_storage_error' => 'Serviceprotokollet har sparats, men mejlets status kunde inte sparas. Kontrollera om PDF-mejlet kom fram innan du försöker skicka igen. Protokollet är kvar i Historik.',
    'protocol_email_status_storage_and_draft_cleanup_error' => 'Serviceprotokollet har sparats, men mejlets status kunde inte sparas och det autosparade utkastet kunde inte tas bort. Kontrollera inkorgen innan nytt mejlförsök och ta vid behov bort utkastet manuellt.',
    'draft_deleted' => 'Utkastet har raderats.',
    'draft_delete_error' => 'Utkastet kunde inte raderas. Ladda om sidan och försök igen.',
    'saved_email_sent' => 'Underlaget har sparats och e-posttransporten accepterade den interna aviseringen till portalens primära mottagaradress. Det bekräftar inte leverans till mottagarens inkorg. Ingen kundkopia skickades.',
    'saved_email_failed' => 'Underlaget har sparats, men e-posttransporten kunde inte acceptera aviseringen. Kontrollera primär mottagaradress och webbhotellets e-postfunktion. Ingen kundkopia skickades.',
    'invoice_email_status_storage_error' => 'Underlaget sparades, men aviseringens status kunde inte sparas. Kontrollera om mejlet kom fram innan du försöker igen, så undviker du en eventuell dubbelavisering.',
    'invoice_email_status_storage_and_draft_cleanup_error' => 'Underlaget sparades, men aviseringens status kunde inte sparas och det autosparade utkastet kunde inte tas bort. Kontrollera mejlet innan nytt försök och ta vid behov bort utkastet manuellt.',
    'invoice_email_retry_accepted' => 'E-posttransporten accepterade ett nytt försök att skicka den interna aviseringen. Det bekräftar inte leverans till mottagarens inkorg. Ingen kundkopia skickades.',
    'invoice_email_retry_failed' => 'Det nya försöket kunde inte accepteras av e-posttransporten. Kontrollera primär mottagaradress och webbhotellets e-postfunktion. Ingen kundkopia skickades.',
    'invoice_email_retry_not_found' => 'Underlaget hittades inte. Ladda om vyn och försök igen.',
    'saved_email_sent_draft_cleanup_error' => 'Underlaget har sparats och e-posttransporten accepterade aviseringen, men autosparade utkastet kunde inte tas bort. Leverans till inkorgen är inte bekräftad. Ta bort utkastet manuellt.',
    'saved_email_failed_draft_cleanup_error' => 'Underlaget har sparats, men e-posttransporten kunde inte acceptera aviseringen och autosparade utkastet kunde inte tas bort. Kontrollera e-poststatus och ta bort utkastet manuellt.',
    'invoice_login_success' => 'Du är inloggad på fakturaunderlaget.',
    'invoice_login_remembered' => 'Du är inloggad. Den här enheten hålls inloggad tills du loggar ut.',
    'invoice_login_remember_failed' => 'Du är inloggad, men den beständiga inloggningen kunde inte sparas. Kontrollera privat lagring under storage; du kan behöva logga in igen när webbläsaren stängs.',
    'invoice_logout' => 'Du är utloggad från fakturaunderlaget.',
    'invoice_login_failed' => 'Fel användarnamn eller PIN. Kontrollera uppgifterna och försök igen.',
    'invoice_login_locked' => 'För många felaktiga försök. Inloggningen är tillfälligt spärrad; försök igen senare.',
    'invoice_setup_success' => 'Första adminkontot har skapats. Logga in med användarnamnet och PIN-koden du valde.',
    'invoice_setup_error' => 'Adminkontot kunde inte skapas. Kontrollera användarnamnet, visningsnamnet och att PIN-koden har sex siffror.',
    'invoice_setup_pin_mismatch' => 'PIN-koderna stämde inte överens. Försök igen.',
    'invoice_setup_closed' => 'Första adminkontot är redan skapat. Logga in med ditt konto.',
    'invoice_setup_storage_error' => 'Kontot kunde inte skapas eftersom privat lagring inte kunde läsas eller skrivas. Kontrollera filrättigheterna eller kontakta administratören.',
    'invoice_login_required' => 'Logga in med din personliga PIN för att använda fakturaunderlaget och Kundregistret.',
    'protocol_login_success' => 'Du är inloggad för serviceprotokoll.',
    'protocol_logout' => 'Du är utloggad från serviceprotokoll.',
    'protocol_login_failed' => 'Fel användarnamn eller PIN för serviceprotokoll. Kontrollera uppgifterna och försök igen.',
    'protocol_login_locked' => 'För många felaktiga försök. Protokollinloggningen är tillfälligt spärrad; försök igen senare.',
    'protocol_login_required' => 'Logga in med ditt personliga protokollkonto innan du sparar.',
    'protocol_auth_storage_error' => 'Protokollinloggningen kunde inte läsa privat kontolagring. Kontakta administratören.',
    'protocol_user_created' => 'Protokollkontot har skapats.',
    'protocol_user_create_error' => 'Protokollkontot kunde inte skapas. Kontrollera uppgifterna och att användarnamnet inte redan används.',
    'protocol_user_pin_reset' => 'Protokoll-PIN har återställts. Användarens tidigare protokollinloggningar har ogiltigförklarats.',
    'protocol_user_pin_reset_error' => 'Protokoll-PIN kunde inte återställas. Kontrollera att kontot finns och att den nya PIN-koden består av sex siffror.',
    'invoice_admin_required' => 'Den här åtgärden är endast tillgänglig för admin.',
    'central_admin_login_success' => 'Du är inloggad som central admin. Admin-PIN fungerar nu på personalsidorna; kund-PWA:erna förblir separata.',
    'central_admin_logout' => 'Du är utloggad från den centrala Adminpanelen.',
    'central_admin_setup_success' => 'Den centrala admin-PIN:en är skapad. Den ger åtkomst till personalsidorna utan att ändra de separata faktura- och protokollkontona.',
    'central_admin_pin_changed' => 'Den centrala admin-PIN:en har bytts. Övriga aktiva centrala admins-sessioner har ogiltigförklarats.',
    'central_admin_pin_expired' => 'Den centrala PIN-koden måste uppdateras innan adminåtkomsten kan fortsätta. Bekräfta den nuvarande koden och välj en ny enligt kraven på sidan.',
    'central_admin_login_failed' => 'Den centrala admin-PIN:en kunde inte verifieras. Kontrollera den och försök igen.',
    'central_admin_login_locked' => 'För många felaktiga försök. Central admininloggning är tillfälligt spärrad; försök igen senare.',
    'central_admin_storage_error' => 'Central adminautentisering kunde inte läsa eller spara sin privata lagring. Kontrollera storage-rättigheter via SFTP.',
    'central_admin_setup_required' => 'Den centrala admin-PIN:en är inte inställd. Logga in med ett befintligt Fakturaunderlag-admin för att välja den.',
    'central_admin_login_forbidden' => 'Central admininloggning är endast tillgänglig i den interna personalportalen.',
    'central_admin_pin_mismatch' => 'PIN-fälten stämde inte överens. Försök igen.',
    'central_admin_pin_policy_error' => 'PIN-koden ska innehålla 6–10 siffror och högst 2 valfria specialtecken ur !@#$%&*+-_=; bokstäver och mellanslag är inte tillåtna.',
    'central_admin_setup_closed' => 'En central admin-PIN finns redan. PIN-återställning görs via SFTP.',
    'central_admin_enroll_forbidden' => 'Första central admin-PIN:en får endast väljas efter inloggning med ett befintligt Fakturaunderlag-admin.',
    'central_admin_session_error' => 'PIN-ändringen kunde inte slutföras i den säkra sessionen. Logga in igen med den senast sparade PIN:en.',
    'central_admin_current_pin_error' => 'Nuvarande central admin-PIN stämde inte. Ingen PIN-ändring gjordes.',
    'central_admin_pin_same' => 'Den nya PIN:en måste skilja sig från den nuvarande.',
    'central_admin_session_expired' => 'Central admin-sessionen är inte längre giltig. Logga in igen.',
    'email_test_invoice_accepted' => 'E-posttransporten accepterade testutskicket till fakturaunderlagets konfigurerade mottagare. Det bekräftar inte leverans till inkorgen.',
    'email_test_invoice_failed' => 'E-posttransporten kunde inte acceptera testutskicket för fakturaunderlag. Kontrollera SMTP-konfigurationen eller webbhotellets mail()-fallback.',
    'email_test_invoice_not_configured' => 'Ingen giltig primär mottagaradress är konfigurerad. Inget utskick gjordes.',
    'email_test_skade_accepted' => 'E-posttransporten accepterade testutskicket för skadeblanketter till rl@tadega.com. Det bekräftar inte leverans till inkorgen.',
    'email_test_skade_failed' => 'E-posttransporten kunde inte acceptera testutskicket för skadeblanketter till rl@tadega.com. Kontrollera SMTP-konfigurationen eller webbhotellets mail()-fallback.',
    'email_test_skade_accepted_not_marked' => 'SMTP-servern accepterade testutskicket till rl@tadega.com, men teststatusen kunde inte sparas. Kontrollera privat lagring innan du låser inställningarna. Leverans till inkorgen är inte bekräftad.',
    'email_transport_saved' => 'SMTP-inställningarna har sparats i privat lagring. Lösenordet visas inte. Skicka ett testmejl till rl@tadega.com och kontrollera både status och inkorg innan du låser.',
    'email_transport_locked' => 'SMTP-inställningarna är låsta. Utskick kan fortsätta; ändring kräver adminens PIN.',
    'email_transport_unlocked' => 'SMTP-inställningarna är upplåsta med adminens PIN. Lås dem igen när ändring och kontroll är klar.',
    'email_transport_test_required' => 'Skicka ett SMTP-test till rl@tadega.com och lås först efter att transporten accepterat testet. Det bekräftar inte leverans till inkorgen.',
    'email_transport_validation_error' => 'SMTP-inställningarna är ogiltiga. Kontrollera servernamn, e-postadresser, lösenord och kombinationen 465/SSL eller 587/TLS.',
    'email_transport_storage_error' => 'SMTP-inställningarna kunde inte läsas eller sparas säkert. Kontrollera privat storage och filrättigheterna.',
    'email_transport_unlock_pin_error' => 'Admin-PIN kunde inte verifieras. Inställningarna förblir låsta.',
    'email_transport_unlock_rate_limited' => 'För många felaktiga PIN-försök. Vänta tills spärren löper ut innan du försöker igen.',
    'invoice_user_created' => 'Användarkontot har skapats.',
    'invoice_user_create_error' => 'Kontot kunde inte skapas. Kontrollera uppgifterna och att användarnamnet inte redan används.',
    'invoice_pin_reset' => 'PIN-koden har återställts. Användarens tidigare inloggningar har ogiltigförklarats.',
    'invoice_pin_reset_error' => 'PIN-koden kunde inte återställas. Kontrollera att kontot finns och att den nya PIN-koden består av sex siffror.',
    'invoice_number_saved' => 'Fortnox-fakturanummer och fakturadatum har sparats. Underlaget har flyttats till Historik.',
    'invoice_number_error' => 'Fakturanumret kunde inte sparas. Ange ett nummer med högst 80 tecken och tillåtna tecken.',
    'invoice_number_date_error' => 'Ange ett giltigt fakturadatum från Fortnox.',
    'invoice_number_storage_error' => 'Fakturanumret kunde inte sparas säkert. Kontrollera privat lagring och filrättigheter.',
    'invoice_number_not_found' => 'Underlaget hittades inte. Ladda om listan och försök igen.',
    'invoice_number_already_set' => 'Underlaget har redan ett Fortnox-fakturanummer och finns inte längre under Under behandling.',
    'invoice_article_saved' => 'Artikeln har sparats i artikelkatalogen.',
    'invoice_article_deleted' => 'Artikeln har tagits bort från artikelkatalogen.',
    'invoice_article_save_error' => 'Artikeln kunde inte sparas. Ange en beskrivning och ett giltigt pris mellan 0 och 10 000 000 kr.',
    'invoice_article_delete_error' => 'Artikeln kunde inte tas bort. Ladda om katalogen och försök igen.',
    'invoice_catalog_storage_error' => 'Artikelkatalogen kunde inte läsas eller sparas säkert. Kontrollera privat lagring och filrättigheter; inga ändringar har bekräftats.',
    'invoice_catalog_full' => 'Artikelkatalogen har nått gränsen på 500 artiklar.',
    'logo_ok' => 'Logotypen har laddats upp och sanerats.',

    'logo_error' => 'Logotypen kunde inte laddas upp. Kontrollera att det är en liten, giltig SVG-fil.',
    'backup_ok' => 'En privat säkerhetskopia har skapats.',
    'backup_error' => 'Säkerhetskopian kunde inte skapas. Kontrollera att den privata lagringen är skrivbar och att det finns ledigt utrymme; försök sedan igen.',
    'email_error' => 'Ange en giltig e-postadress, till exempel namn@foretag.se. Kontrollera att adressen inte innehåller mellanslag.',
    'save_error' => 'Uppgifterna kunde inte sparas. Kontrollera fält med felmarkering och försök igen. Om felet återkommer, ange flik och tidpunkt till administratören.',
    'submit_error' => 'Skadeblanketten kunde inte skapas. Kontrollera fält med felmarkering och försök igen. Om det fortsätter, ange flik och tidpunkt till administratören.',
    'skade_submit_error' => 'Skadeblanketten kunde inte visas. Öppna skadeblankettfliken igen. Om felet återkommer, ange flik och tidpunkt till administratören.',
    'skade_email_retry_error' => 'Mejlet kunde inte skickas om. Kontrollera att skadeblanketten finns kvar och att dess utskicksstatus inte är oklar.',
];
$msgKey = isset($_GET['msg']) && is_string($_GET['msg']) ? $_GET['msg'] : '';
$notice = $noticeMessages[$msgKey] ?? '';
if (str_starts_with($msgKey, 'release_') && ($activeTab !== 'admin' || !$centralAdminCanAccess)) {
    $notice = '';
}
$noticeTone = 'success';
if (in_array($msgKey, ['protocol_email_failed', 'protocol_email_not_configured', 'protocol_email_accepted_draft_cleanup_error', 'protocol_email_failed_draft_cleanup_error', 'protocol_email_not_configured_draft_cleanup_error', 'protocol_email_status_storage_error', 'protocol_email_status_storage_and_draft_cleanup_error', 'saved_email_failed', 'saved_draft_cleanup_error', 'saved_email_sent_draft_cleanup_error', 'saved_email_failed_draft_cleanup_error', 'invoice_email_status_storage_error', 'invoice_email_status_storage_and_draft_cleanup_error', 'invoice_email_retry_failed', 'email_test_invoice_failed', 'email_test_invoice_not_configured', 'email_test_skade_failed', 'email_test_skade_accepted_not_marked', 'email_transport_test_required', 'invoice_setup_closed', 'invoice_login_remember_failed', 'invoice_number_already_set', 'central_admin_pin_expired', 'central_admin_setup_closed', 'central_admin_session_expired', 'release_update_failed', 'release_changed_since_approval'], true)) {
    $noticeTone = 'warning';
} elseif (in_array($msgKey, [
    'logo_error', 'backup_error', 'email_error', 'save_error', 'protocol_signature_required', 'submit_error', 'draft_delete_error', 'skade_submit_error', 'skade_email_retry_error',
    'invoice_login_failed', 'invoice_login_locked', 'invoice_login_required',
    'protocol_login_failed', 'protocol_login_locked', 'protocol_login_required', 'protocol_auth_storage_error',
    'protocol_user_create_error', 'protocol_user_pin_reset_error',
    'invoice_admin_required', 'invoice_user_create_error', 'invoice_pin_reset_error',
    'invoice_article_save_error', 'invoice_article_delete_error', 'invoice_catalog_storage_error', 'invoice_catalog_full', 'invoice_email_retry_not_found',
    'invoice_number_error', 'invoice_number_date_error', 'invoice_number_storage_error', 'invoice_number_not_found',
    'email_transport_validation_error', 'email_transport_storage_error', 'email_transport_unlock_pin_error', 'email_transport_unlock_rate_limited',
    'invoice_setup_error', 'invoice_setup_pin_mismatch', 'invoice_setup_storage_error',
    'central_admin_login_failed', 'central_admin_login_locked', 'central_admin_storage_error', 'central_admin_setup_required',
    'central_admin_login_forbidden', 'central_admin_pin_mismatch', 'central_admin_pin_policy_error',
    'central_admin_enroll_forbidden', 'central_admin_session_error', 'central_admin_current_pin_error', 'central_admin_pin_same',
    'release_rollback_failed',
], true)) {
    $noticeTone = 'error';
}
if (in_array($activeTab, ['settings', 'files'], true)) {
    // These tabs render action-specific notices themselves.
    $notice = '';
}
$pageTitle = $portalTabs[$activeTab][0];
$pageSubtitle = $portalTabs[$activeTab][1];
if ($activeTab === 'invoice' && $invoiceSetupState === 'unconfigured' && !is_array($invoiceAuthUser) && (!$portalIsScopedPwa || $portalPwaApp === 'invoice')) {
    $pageTitle = 'Första adminkonto';
    $pageSubtitle = 'Skapa portalens första adminkonto för fakturaunderlaget.';
}
if ($isSkadeCustomerMode) {
    $pageTitle = 'Skadeblankett';
    $pageSubtitle = 'Fyll i uppgifterna och signera.';
}
$breadcrumbItems = [];
if (!$isSkadeCustomerMode) {
    if ($activeTab === 'protocol') {
        $protocolView = isset($_GET['protocol_view']) && is_string($_GET['protocol_view']) ? $_GET['protocol_view'] : '';
        if ($protocolView === 'records') {
            $breadcrumbItems = [
                ['label' => 'Serviceprotokoll', 'href' => '?tab=protocol'],
                ['label' => 'Sparade protokoll'],
            ];
        } else {
            $breadcrumbItems = [['label' => $pageTitle]];
        }
    } elseif ($activeTab === 'invoice' && $invoiceSetupState === 'configured' && is_array($invoiceAuthUser)) {
        $breadcrumbItems = [
            ['label' => 'Portal', 'href' => '?tab=protocol'],
            ['label' => $pageTitle, 'href' => '?tab=invoice'],
        ];
        $invoiceView = isset($_GET['invoice_view']) && is_string($_GET['invoice_view']) ? $_GET['invoice_view'] : 'form';
        $invoiceViewLabels = [
            'processing' => 'Under behandling',
            'invoice_history' => 'Historik',
            'articles' => 'Artikelkatalog',
            'customers' => 'Kunder',
            'admin' => 'Konton',
            'email' => 'E-poststatus',
            'debug' => 'Diagnostik',
        ];
        if (isset($invoiceViewLabels[$invoiceView])) {
            $breadcrumbItems[] = ['label' => $invoiceViewLabels[$invoiceView]];
        } else {
            $breadcrumbItems[1] = ['label' => $pageTitle];
        }
    } elseif ($activeTab === 'files' && isset($_GET['sub']) && $_GET['sub'] === 'skade') {
        $breadcrumbItems = [
            ['label' => 'Portal', 'href' => '?tab=protocol'],
            ['label' => $pageTitle, 'href' => '?tab=files'],
            ['label' => 'Skadeblanketter'],
        ];
    } else {
        $breadcrumbItems = [
            ['label' => 'Portal', 'href' => '?tab=protocol'],
            ['label' => $pageTitle],
        ];
    }
}
$csrfReady = csrf_token() !== '';
$portalPwaNames = [
    'protocol' => 'Serviceprotokoll',
    'invoice' => 'Fakturaunderlag',
    'skadeblankett' => 'Skadeblankett',
];
$portalPwaName = $portalIsScopedPwa ? ($portalPwaNames[$portalPwaApp] ?? 'Tadega Portal') : 'Tadega Portal';
$portalManifestHref = $portalIsScopedPwa
    ? './' . $portalPwaManifest
    : ($isSkadeCustomerMode ? './manifest-skadeblankett.webmanifest' : './manifest.webmanifest');
$portalAssetEntry = $portalIsScopedPwa ? './' . $portalPwaEntry : './index.php';
?>
<!doctype html>
<html lang="sv">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <meta name="color-scheme" content="light">
    <script>
    (function () {
        'use strict';
        var root = document.documentElement;
        var theme = 'system';
        var density = 'comfortable';
        try {
            var savedTheme = window.localStorage.getItem('tadega.portal.theme');
            var savedDensity = window.localStorage.getItem('tadega.portal.density');
            if (savedTheme === 'light' || savedTheme === 'dark' || savedTheme === 'system') theme = savedTheme;
            if (savedDensity === 'compact' || savedDensity === 'comfortable') density = savedDensity;
        } catch (ignore) {}
        var systemPrefersDark = false;
        try {
            systemPrefersDark = !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
        } catch (ignore) {}
        root.setAttribute('data-theme', theme === 'system' ? (systemPrefersDark ? 'dark' : 'light') : theme);
        root.setAttribute('data-density', density);
        root.setAttribute('data-theme-preference', theme);
    })();
    </script>
    <meta name="theme-color" content="#0b7a72">
    <meta name="description" content="<?= h($isSkadeCustomerMode ? 'Kundformulär för skadeblankett.' : ($portalIsScopedPwa ? 'Tadega ' . $portalPwaName . ' — separat formulärvy.' : 'Tadega Portal – verkstadsdokument och administration.')) ?>">
    <meta name="application-name" content="<?= h($isSkadeCustomerMode ? 'Tadega Skadeblankett' : ($portalIsScopedPwa ? 'Tadega ' . $portalPwaName : 'Tadega Dokumentportalen')) ?>">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="<?= h($isSkadeCustomerMode ? 'Skadeblankett' : ($portalIsScopedPwa ? $portalPwaName : 'Tadega Dokumentportalen')) ?>">
    <meta name="msapplication-TileColor" content="#07172d">
    <meta name="msapplication-TileImage" content="<?= h($portalAssetEntry . '?view_file=assets/pwa-icon-192.png') ?>">
    <meta name="msapplication-config" content="./browserconfig.xml">
    <title><?= h($isSkadeCustomerMode ? 'Skadeblankett · Tadega' : ($portalIsScopedPwa ? $portalPwaName . ' · Tadega' : $pageTitle . ' · Tadega Dokumentportalen')) ?></title>
    <link rel="manifest" href="<?= h($portalManifestHref) ?>">
    <link rel="icon" type="image/x-icon" href="./favicon.ico?v=<?= (string) (@filemtime(__DIR__ . '/favicon.ico') ?: '1') ?>">
    <link rel="icon" type="image/png" sizes="192x192" href="<?= h($portalAssetEntry . '?view_file=assets/pwa-icon-192.png') ?>">
    <link rel="shortcut icon" type="image/png" href="<?= h($portalAssetEntry . '?view_file=assets/pwa-icon-192.png') ?>">
    <link rel="apple-touch-icon" sizes="180x180" href="<?= h($portalAssetEntry . '?view_file=assets/apple-touch-icon.png&v=' . (string) (@filemtime(__DIR__ . '/assets/apple-touch-icon.png') ?: '1')) ?>">
    <link rel="stylesheet" href="<?= h($portalAssetEntry . '?view_file=assets/portal.css&v=' . (string) (@filemtime(__DIR__ . '/assets/portal.css') ?: '1')) ?>">
    <script>
    (function () {
        'use strict';
        var page = <?= json_encode($activeTab, JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT) ?>;
        var csrfToken = <?= json_encode(csrf_token(), JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT) ?>;
        var endpoint = window.location.pathname + '?tab=' + encodeURIComponent(page) + <?= json_encode($isSkadeCustomerMode ? '&mode=customer' : '') ?>;
        if (!csrfToken || typeof window.fetch !== 'function' || typeof window.URLSearchParams !== 'function') return;
        var sent = Object.create(null);
        var sentCount = 0;
        var allowedNames = ['Error', 'TypeError', 'ReferenceError', 'SyntaxError', 'RangeError', 'URIError', 'EvalError', 'AggregateError', 'UnhandledRejection', 'NetworkError', 'AbortError', 'DOMException'];
        function safeName(value) {
            return typeof value === 'string' && allowedNames.indexOf(value) !== -1 ? value : 'Error';
        }
        function safeFile(value) {
            if (typeof value !== 'string' || value === '') return 'inline';
            try {
                var parsed = new URL(value, window.location.href);
                if (parsed.origin !== window.location.origin) return 'external';
                var parts = parsed.pathname.split('/');
                return (parts[parts.length - 1] || 'inline').replace(/[^A-Za-z0-9._-]/g, '_').slice(0, 120) || 'inline';
            } catch (ignore) {
                return 'inline';
            }
        }
        function report(type, name, file, line, column) {
            if (sentCount >= 15) return;
            var safeSource = safeFile(file);
            var safeErrorName = safeName(name);
            var safeLine = Number.isFinite(Number(line)) ? Math.max(0, Math.min(999999, Math.floor(Number(line)))) : 0;
            var safeColumn = Number.isFinite(Number(column)) ? Math.max(0, Math.min(999999, Math.floor(Number(column)))) : 0;
            var key = [type, safeErrorName, safeSource, safeLine, safeColumn].join(':');
            if (sent[key]) return;
            sent[key] = true;
            sentCount += 1;
            var body = new URLSearchParams();
            body.set('action', 'client_diagnostic');
            body.set('csrf_token', csrfToken);
            body.set('diagnostic_type', type);
            body.set('diagnostic_error_name', safeErrorName);
            body.set('diagnostic_file', safeSource);
            body.set('diagnostic_line', String(safeLine));
            body.set('diagnostic_column', String(safeColumn));
            window.fetch(endpoint, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' },
                body: body.toString(),
                keepalive: true
            }).catch(function () {});
        }
        window.addEventListener('error', function (event) {
            if (event.target !== window) return;
            report('js_error', event.error && event.error.name, event.filename, event.lineno, event.colno);
        });
        window.addEventListener('unhandledrejection', function (event) {
            var reason = event.reason;
            var reasonName = reason && typeof reason.name === 'string' ? reason.name : 'UnhandledRejection';
            report('js_unhandled_rejection', reasonName, reason && (reason.fileName || reason.filename), reason && reason.lineNumber, reason && reason.columnNumber);
        });
    }());
    </script>
</head>
<body<?= $isSkadeCustomerMode ? ' class="skade-kiosk-mode"' : '' ?>>
<a class="skip-link" href="#main-content"><?= $isSkadeCustomerMode ? 'Hoppa till formuläret' : 'Hoppa till huvudinnehåll' ?></a>
<?php if (!$isSkadeCustomerMode): ?>
<header class="app-header">
    <div class="app-header-inner">
        <a class="brand" href="?tab=<?= h($activeTab) ?>" aria-label="<?= h($portalIsScopedPwa ? 'Tadega ' . $portalPwaName . ' startsida' : 'Tadega Dokumentportalen startsida') ?>">
            <img class="brand-icon" src="?view_file=assets/tadega-icon.svg&amp;v=<?= (string) (@filemtime(__DIR__ . '/assets/tadega-icon.svg') ?: '1') ?>" alt="" width="42" height="42">
            <span><span class="brand-name">TADEGA</span><span class="brand-caption"><?= h($portalIsScopedPwa ? $portalPwaName : 'Dokumentportalen') ?></span></span>
        </a>
        <div class="header-actions">
            <button class="btn pwa-install-btn" id="pwa-install-button" type="button" hidden>Installera app</button>
            <p class="pwa-install-help" id="pwa-install-help" role="status" aria-live="polite" hidden></p>
            <details class="ui-preferences" id="portal-ui-preferences">
                <summary class="btn ui-preferences-toggle" aria-label="Visningsinställningar" aria-controls="portal-ui-preferences-panel">
                    <svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-1.8 3.1-.2-.1a1.7 1.7 0 0 0-1.9.1l-.2.1h-3.6l-.1-.2a1.7 1.7 0 0 0-1.7-1l-.2.1-3.1-1.8.1-.2a1.7 1.7 0 0 0-.1-1.9L7 15v-3.6l.2-.1a1.7 1.7 0 0 0 1-1.7l-.1-.2 1.8-3.1.2.1a1.7 1.7 0 0 0 1.9-.1l.2-.1h3.6l.1.2a1.7 1.7 0 0 0 1.7 1l.2-.1 3.1 1.8-.1.2a1.7 1.7 0 0 0 .1 1.9l.1.2V15z"/></svg>
                    <span class="ui-preferences-label">Visning</span>
                </summary>
                <div class="ui-preferences-panel" id="portal-ui-preferences-panel">
                    <div>
                        <label for="portal-theme-select">Färgläge</label>
                        <select id="portal-theme-select" name="portal-theme-select">
                            <option value="system">Följ enhetens inställning</option>
                            <option value="light">Ljust</option>
                            <option value="dark">Mörkt</option>
                        </select>
                    </div>
                    <div>
                        <label for="portal-density-select">Visningstäthet</label>
                        <select id="portal-density-select" name="portal-density-select">
                            <option value="comfortable">Luftig</option>
                            <option value="compact">Kompakt</option>
                        </select>
                    </div>
                    <p class="ui-preferences-help">Valen sparas lokalt i den här webbläsaren. Inga formulär- eller kunduppgifter lagras här.</p>
                </div>
            </details>
            <div class="header-meta"><span class="header-pill">Tadega AB</span><span><?= h(date('Y-m-d')) ?></span></div>
        </div>
    </div>
</header>
<?php endif; ?>
<?php if (($invoiceSetupState !== 'unconfigured' || $activeTab === 'admin' || $centralAdminCanAccess) && !$isSkadeCustomerMode && !$portalIsScopedPwa): ?>
<nav class="tabs-wrap" aria-label="Huvudmeny">
    <button class="btn portal-nav-toggle" id="portal-nav-toggle" type="button" aria-expanded="false" aria-controls="portal-main-menu" aria-label="Öppna huvudmenyn">
        <span class="portal-nav-toggle-label"><svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M4 7h16M4 12h16M4 17h16"/></svg><span>Huvudmeny</span></span>
        <svg class="ui-icon portal-nav-toggle-chevron" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m6 9 6 6 6-6"/></svg>
    </button>
    <div class="tabs" id="portal-main-menu">
        <?php
        $tabIcons = [
            'protocol' => '<svg class="tab-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M7 3.5h7l4 4v13H7z"/><path d="M14 3.5v4h4M10 12h5M10 16h5"/></svg>',
            'search' => '<svg class="tab-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 4.2 4.2"/></svg>',
            'invoice' => '<svg class="tab-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M6 3.5h12v17l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6M9 12h6M9 16h3"/></svg>',
            'skadeblankett' => '<svg class="tab-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 3 5 6v5c0 4.6 2.8 7.7 7 10 4.2-2.3 7-5.4 7-10V6z"/><path d="M12 8v4M12 15h.01"/></svg>',
            'files' => '<svg class="tab-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M3.5 7.5h6l2 2h9v9h-17z"/><path d="M3.5 7.5v-2h6l2 2"/></svg>',
            'archive' => '<svg class="tab-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3 2"/></svg>',
            'customers' => '<svg class="tab-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="9" cy="8" r="3"/><path d="M3.5 20v-1.5a5.5 5.5 0 0 1 11 0V20M16 5.5a3 3 0 0 1 0 5.8M17 15.5a5 5 0 0 1 3.5 4.5"/></svg>',
            'settings' => '<svg class="tab-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-1.8 3.1-.2-.1a1.7 1.7 0 0 0-1.9.1l-.2.1h-3.6l-.1-.2a1.7 1.7 0 0 0-1.7-1l-.2.1-3.1-1.8.1-.2a1.7 1.7 0 0 0-.1-1.9L7 15v-3.6l.2-.1a1.7 1.7 0 0 0 1-1.7l-.1-.2 1.8-3.1.2.1a1.7 1.7 0 0 0 1.9-.1l.2-.1h3.6l.1.2a1.7 1.7 0 0 0 1.7 1l.2-.1 3.1 1.8-.1.2a1.7 1.7 0 0 0 .1 1.9l.1.2V15z"/></svg>',
            'admin' => '<svg class="tab-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 3 5 6v5c0 4.6 2.8 7.7 7 10 4.2-2.3 7-5.4 7-10V6z"/><path d="m9.2 12.2 1.8 1.8 3.9-4"/></svg>',
        ];
        foreach ($portalTabs as $key => $meta):
        ?>
            <a class="tab-btn <?= $activeTab === $key ? 'active' : '' ?>" href="?tab=<?= h($key) ?>" <?= $activeTab === $key ? 'aria-current="page"' : '' ?>>
                <span class="tab-icon-wrap" aria-hidden="true"><?= $tabIcons[$key] ?? '' ?></span><?= h($meta[0]) ?>
            </a>
        <?php endforeach; ?>
    </div>
</nav>
<?php endif; ?>
<div class="portal-network-status is-checking" id="portal-network-status" role="status" aria-live="polite" aria-atomic="true">
    <svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M5 9.5a11 11 0 0 1 14 0M8 12.5a6.5 6.5 0 0 1 8 0M10.7 15.5a2 2 0 0 1 2.6 0"/><circle cx="12" cy="19" r=".8"/></svg>
    <div><strong id="portal-network-title">Anslutningsstatus</strong> <span id="portal-network-detail">Formulär skickas när du sparar; inga formulär eller dokument köas för synk.</span></div>
</div>
<main id="main-content" class="page-shell" tabindex="-1">
    <?php if (in_array($activeTab, ['protocol', 'skadeblankett'], true)): ?>
        <script src="<?= h($portalAssetEntry . '?view_file=assets/signature_pad.js&v=' . (string) (@filemtime(__DIR__ . '/assets/signature_pad.js') ?: '1')) ?>"></script>
    <?php endif; ?>
    <?php if (!$isSkadeCustomerMode): ?>
        <?php if (!$portalIsScopedPwa): ?><?= portal_ui_breadcrumbs($breadcrumbItems) ?><?php endif; ?>
        <div class="page-heading">
            <div class="page-heading-main">
                <span class="page-heading-icon" aria-hidden="true"><?= $tabIcons[$activeTab] ?? '' ?></span>
                <div class="page-heading-copy">
                    <p class="page-eyebrow"><?= h($portalIsScopedPwa ? 'Tadega ' . $portalPwaName : 'Tadega Portal') ?></p>
                    <h1 class="page-title"><?= h($pageTitle) ?></h1>
                    <p class="page-subtitle"><?= h($pageSubtitle) ?></p>
                </div>
            </div>
        </div>
        <?php if ($notice !== ''): ?>
            <?= portal_ui_alert($notice, $noticeTone) ?>
        <?php endif; ?>
        <?php if ($portalPostError !== ''): ?>
            <?= portal_ui_alert($portalPostError, 'error', 'Åtgärden kunde inte genomföras') ?>
        <?php endif; ?>
        <?php if (!$csrfReady): ?>
            <?= portal_ui_alert('Säker session kunde inte startas. Kontrollera PHP-sessioner och HTTPS innan du använder portalen.', 'error', 'Portalen är inte redo') ?>
        <?php endif; ?>
    <?php endif; ?>
    <div class="page-content">
        <?php if ($portalCsrfFailed): ?>
            <?= portal_ui_alert('Gå tillbaka till formuläret, ladda om sidan och försök igen.', 'error', 'Begäran kunde inte verifieras') ?>
        <?php elseif ($activeTab === 'invoice' && $invoiceSetupState === 'unconfigured' && !is_array($invoiceAuthUser)): ?>
            <section class="invoice-auth-card" aria-labelledby="invoice-first-admin-title">
                <div class="invoice-auth-card-head">
                    <span class="invoice-auth-mark" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="9" cy="8" r="3"/><path d="M3.5 20v-1.5a5.5 5.5 0 0 1 11 0V20M17 8h4M19 6v4"/></svg></span>
                    <div>
                        <h2 id="invoice-first-admin-title">Skapa portalens första adminkonto</h2>
                        <p>Gör detta en gång innan du börjar använda portalen.</p>
                    </div>
                </div>
                <form class="invoice-auth-form" method="post" action="?tab=invoice" autocomplete="on">
                    <input type="hidden" name="action" value="invoice_first_admin_setup">
                    <?= csrf_field() ?>
                    <div>
                        <label for="invoice-first-admin-username">Användarnamn</label>
                        <input id="invoice-first-admin-username" name="admin[username]" type="text" maxlength="120" autocomplete="username" autocapitalize="none" spellcheck="false" required>
                    </div>
                    <div>
                        <label for="invoice-first-admin-name">Visningsnamn</label>
                        <input id="invoice-first-admin-name" name="admin[name]" type="text" maxlength="120" autocomplete="name" required>
                    </div>
                    <div>
                        <label for="invoice-first-admin-pin">Välj sexsiffrig PIN</label>
                        <input id="invoice-first-admin-pin" name="admin[pin]" type="password" inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" autocomplete="new-password" required>
                    </div>
                    <div>
                        <label for="invoice-first-admin-pin-confirm">Upprepa PIN</label>
                        <input id="invoice-first-admin-pin-confirm" name="admin[pin_confirm]" type="password" inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" autocomplete="new-password" required>
                    </div>
                    <button class="btn btn-main" type="submit" <?= !$csrfReady ? 'disabled' : '' ?>>Skapa första admin</button>
                </form>
                <p class="invoice-auth-help">Det här engångssteget visas bara när kontolistan är tom. Skydda katalogen med Websupports lösenordsskydd innan portalen görs tillgänglig. Efter att kontot skapats loggar du in med ditt nya användarnamn och PIN.</p>
            </section>
        <?php elseif ($activeTab === 'invoice' && $invoiceSetupState === 'error' && !is_array($invoiceAuthUser)): ?>
            <section class="invoice-auth-card" aria-labelledby="invoice-setup-error-title">
                <div class="invoice-auth-card-head">
                    <span class="invoice-auth-mark" aria-hidden="true">!</span>
                    <div>
                        <h2 id="invoice-setup-error-title">Kontoinställningen kunde inte läsas</h2>
                        <p>Portalen kan inte avgöra om ett adminkonto redan finns.</p>
                    </div>
                </div>
                <p class="invoice-auth-help">Av säkerhetsskäl är första-admin-formuläret stängt när den privata kontofilen saknas i läsbar form, är ogiltig eller är en länk. Kontrollera <code>storage/invoice_users.json</code> och katalogens filrättigheter på webbhotellet.</p>
            </section>
        <?php elseif ($activeTab === 'invoice' && !is_array($invoiceAuthUser)): ?>
            <section class="invoice-auth-card" aria-labelledby="invoice-login-title">
                <div class="invoice-auth-card-head">
                    <span class="invoice-auth-mark" aria-hidden="true"><svg viewBox="0 0 24 24"><rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/></svg></span>
                    <div>
                        <h2 id="invoice-login-title">Logga in på fakturaunderlaget</h2>
                        <p>Använd ditt personliga användarnamn och din sexsiffriga PIN.</p>
                    </div>
                </div>
                <form class="invoice-auth-form" method="post" action="?tab=invoice" autocomplete="on">
                    <input type="hidden" name="action" value="invoice_pin_login">
                    <?= csrf_field() ?>
                    <div>
                        <label for="invoice-login-username">Användarnamn</label>
                        <input id="invoice-login-username" name="username" type="text" maxlength="120" autocomplete="username" autocapitalize="none" spellcheck="false" required>
                    </div>
                    <div>
                        <label for="invoice-login-pin">Sexsiffrig PIN</label>
                        <input id="invoice-login-pin" name="pin" type="password" inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" autocomplete="current-password" aria-describedby="invoice-login-help" required>
                    </div>
                    <label class="invoice-remember" for="invoice-remember-me">
                        <input id="invoice-remember-me" name="remember_me" type="checkbox" value="1">
                        <span><strong>Håll mig inloggad tills jag loggar ut</strong><small>Välj bara detta på en privat och betrodd enhet.</small></span>
                    </label>
                    <button class="btn btn-main" type="submit" <?= !$csrfReady ? 'disabled' : '' ?>>Logga in</button>
                </form>
                <p class="invoice-auth-help" id="invoice-login-help">Den här sexsiffriga PIN-koden gäller fakturaunderlaget och Kundregistret. Central adminåtkomst till personalsidorna sköts separat via Adminpanelen, och webbhotellets/proxyns grundskydd ska vara kvar.</p>
            </section>
        <?php else: ?>
            <?php if (in_array($activeTab, ['invoice', 'customers', 'search'], true) && is_array($invoiceAuthUser)): ?>
                <div class="invoice-session-bar">
                    <div class="invoice-session-person">
                        <span>Inloggad som</span>
                        <strong><?= h($invoiceAuthUser['name'] ?? $invoiceAuthUser['username'] ?? 'Användare') ?></strong>
                        <?= portal_ui_badge(($invoiceAuthUser['role'] ?? '') === 'admin' ? 'Admin' : 'Personal', 'info') ?>
                    </div>
                    <?php if (($invoiceAuthUser['auth_source'] ?? '') === 'central_admin'): ?>
                        <a class="btn btn-outline" href="?tab=admin">Hantera central adminsession</a>
                    <?php else: ?>
                        <form class="invoice-session-form" method="post" action="?tab=invoice">
                            <input type="hidden" name="action" value="invoice_pin_logout">
                            <?= csrf_field() ?>
                            <button class="btn btn-outline" type="submit">Logga ut från fakturakontot</button>
                        </form>
                    <?php endif; ?>
                </div>
            <?php endif; ?>
            <?php
            $tabFile = __DIR__ . '/tabs/' . $activeTab . '.php';
            if (is_file($tabFile)) {
                include $tabFile;
            } else {
                http_response_code(404);
                echo portal_ui_alert('Kontrollera att sidan fortfarande är tillgänglig. Ladda om och försök igen.', 'error', 'Fliken kunde inte laddas');
            }
            ?>
        <?php endif; ?>
    </div>
    <?php if (!$isSkadeCustomerMode): ?>
        <footer class="app-footer">Tadega Portal · Intern verkstadsadministration · © Rickard Längkvist / Tadega AB</footer>
    <?php endif; ?>
</main>
<script>
(function () {
    'use strict';

    var installButton = document.getElementById('pwa-install-button');
    var installHelp = document.getElementById('pwa-install-help');
    var deferredInstallPrompt = null;
    var isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
    var isIOS = /iPad|iPhone|iPod/.test(window.navigator.userAgent)
        || (window.navigator.platform === 'MacIntel' && window.navigator.maxTouchPoints > 1);
    var scopedPwaApp = <?= json_encode($portalPwaApp, JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT) ?>;
    var scopedPwaEntry = <?= json_encode($portalPwaEntry, JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT) ?>;
    var serviceWorkerUrl = scopedPwaApp ? './service-worker.js?app=' + encodeURIComponent(scopedPwaApp) : './service-worker.js';
    var serviceWorkerScope = scopedPwaApp ? './' + scopedPwaEntry : './';

    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register(serviceWorkerUrl, { scope: serviceWorkerScope, updateViaCache: 'none' })
            .then(function () { return navigator.serviceWorker.ready; })
            .then(function (registration) {
                if (registration && registration.active) {
                    registration.active.postMessage({ type: 'TADEGA_DAILY_CACHE_MAINTENANCE' });
                }
            })
            .catch(function () {
                // The portal remains usable if service workers are blocked by the host.
            });
    }

    if (!installButton || isStandalone) return;
    if (isIOS) {
        installButton.hidden = false;
        installButton.textContent = 'Lägg till app';
    }

    window.addEventListener('beforeinstallprompt', function (event) {
        event.preventDefault();
        deferredInstallPrompt = event;
        installButton.hidden = false;
        installButton.textContent = 'Installera app';
    });

    installButton.addEventListener('click', function () {
        if (deferredInstallPrompt) {
            deferredInstallPrompt.prompt();
            deferredInstallPrompt.userChoice.finally(function () {
                deferredInstallPrompt = null;
                installButton.hidden = true;
            });
            return;
        }
        if (isIOS && installHelp) {
            installHelp.textContent = 'I Safari: tryck på Dela och välj ”Lägg till på hemskärmen”. Appens formulär och sparade uppgifter kräver fortfarande nätverksanslutning.';
            installHelp.hidden = false;
        }
    });

    window.addEventListener('appinstalled', function () {
        installButton.hidden = true;
        if (installHelp) installHelp.hidden = true;
    });
})();
</script>
<script>
(function () {
    'use strict';

    var root = document.documentElement;
    var preferences = document.getElementById('portal-ui-preferences');
    var themeSelect = document.getElementById('portal-theme-select');
    var densitySelect = document.getElementById('portal-density-select');
    var themeKey = 'tadega.portal.theme';
    var densityKey = 'tadega.portal.density';
    var themeQuery = null;

    function storedChoice(key, allowed, fallback) {
        try {
            var value = window.localStorage.getItem(key);
            return allowed.indexOf(value) !== -1 ? value : fallback;
        } catch (ignore) {
            return fallback;
        }
    }

    function saveChoice(key, value) {
        try {
            window.localStorage.setItem(key, value);
            return true;
        } catch (ignore) {
            return false;
        }
    }

    try {
        if (typeof window.matchMedia === 'function') themeQuery = window.matchMedia('(prefers-color-scheme: dark)');
    } catch (ignore) {}

    function applyTheme(preference) {
        var dark = preference === 'dark' || (preference === 'system' && themeQuery && themeQuery.matches);
        root.setAttribute('data-theme', dark ? 'dark' : 'light');
        root.setAttribute('data-theme-preference', preference);
        var themeColor = document.querySelector('meta[name="theme-color"]');
        if (themeColor) themeColor.setAttribute('content', dark ? '#101b1d' : '#0b7a72');
    }

    function applyDensity(density) {
        root.setAttribute('data-density', density);
    }

    var selectedTheme = storedChoice(themeKey, ['system', 'light', 'dark'], 'system');
    var selectedDensity = storedChoice(densityKey, ['comfortable', 'compact'], 'comfortable');
    if (themeSelect) {
        themeSelect.value = selectedTheme;
        themeSelect.addEventListener('change', function () {
            selectedTheme = ['system', 'light', 'dark'].indexOf(themeSelect.value) !== -1 ? themeSelect.value : 'system';
            applyTheme(selectedTheme);
            saveChoice(themeKey, selectedTheme);
        });
    }
    if (densitySelect) {
        densitySelect.value = selectedDensity;
        densitySelect.addEventListener('change', function () {
            selectedDensity = densitySelect.value === 'compact' ? 'compact' : 'comfortable';
            applyDensity(selectedDensity);
            saveChoice(densityKey, selectedDensity);
        });
    }
    applyTheme(selectedTheme);
    applyDensity(selectedDensity);
    if (themeQuery) {
        var onSystemThemeChange = function () {
            if (selectedTheme === 'system') applyTheme('system');
        };
        if (typeof themeQuery.addEventListener === 'function') themeQuery.addEventListener('change', onSystemThemeChange);
        else if (typeof themeQuery.addListener === 'function') themeQuery.addListener(onSystemThemeChange);
    }
    if (preferences) {
        document.addEventListener('click', function (event) {
            if (preferences.open && !preferences.contains(event.target)) preferences.open = false;
        });
        preferences.addEventListener('keydown', function (event) {
            if (event.key === 'Escape' && preferences.open) {
                preferences.open = false;
                var summary = preferences.querySelector('summary');
                if (summary) summary.focus();
            }
        });
    }

    var networkStatus = document.getElementById('portal-network-status');
    var networkTitle = document.getElementById('portal-network-title');
    var networkDetail = document.getElementById('portal-network-detail');
    function updateNetworkStatus() {
        if (!networkStatus) return;
        var isOnline = typeof navigator.onLine !== 'boolean' || navigator.onLine;
        networkStatus.classList.toggle('is-online', isOnline);
        networkStatus.classList.toggle('is-offline', !isOnline);
        networkStatus.classList.remove('is-checking');
        if (networkTitle) networkTitle.textContent = isOnline ? 'Nätverk rapporteras tillgängligt' : 'Offline';
        if (networkDetail) {
            networkDetail.textContent = isOnline
                ? 'Enheten rapporterar nätverksanslutning. Formulär skickas direkt när du sparar; ingen väntande synkkö.'
                : 'Ingen väntande synkkö: formulär och dokument sparas inte offline. Anslut igen innan du skickar.';
        }
    }
    updateNetworkStatus();
    window.addEventListener('online', updateNetworkStatus);
    window.addEventListener('offline', updateNetworkStatus);

    var nav = document.querySelector('.tabs-wrap');
    var navToggle = document.getElementById('portal-nav-toggle');
    var navMenu = document.getElementById('portal-main-menu');
    var navQuery = null;
    try {
        if (typeof window.matchMedia === 'function') navQuery = window.matchMedia('(max-width:720px)');
    } catch (ignore) {}
    function isNarrowNav() {
        return navQuery ? navQuery.matches : window.innerWidth <= 720;
    }
    function setNavOpen(open) {
        if (!nav || !navToggle) return;
        nav.classList.toggle('is-open', !!open && isNarrowNav());
        var expanded = !!open && isNarrowNav();
        navToggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        navToggle.setAttribute('aria-label', expanded ? 'Stäng huvudmenyn' : 'Öppna huvudmenyn');
    }
    function syncNavMode() {
        if (!isNarrowNav()) setNavOpen(false);
    }
    if (nav && navToggle && navMenu) {
        nav.classList.add('nav-responsive-ready');
        navToggle.addEventListener('click', function () {
            setNavOpen(navToggle.getAttribute('aria-expanded') !== 'true');
        });
        navMenu.addEventListener('click', function (event) {
            var link = event.target && event.target.closest ? event.target.closest('a[href]') : null;
            if (link && isNarrowNav()) setNavOpen(false);
        });
        nav.addEventListener('keydown', function (event) {
            if (event.key === 'Escape' && nav.classList.contains('is-open')) {
                setNavOpen(false);
                navToggle.focus();
            }
        });
        window.addEventListener('resize', syncNavMode, { passive: true });
        if (navQuery && typeof navQuery.addEventListener === 'function') navQuery.addEventListener('change', syncNavMode);
        else if (navQuery && typeof navQuery.addListener === 'function') navQuery.addListener(syncNavMode);
        syncNavMode();
    }
})();
</script>
<script>
(function () {
    'use strict';
    var tabList = document.querySelector('.tabs');
    var activeTab = tabList ? tabList.querySelector('.tab-btn.active') : null;

    function revealActiveTab() {
        if (!tabList || !activeTab) return;
        var listRect = tabList.getBoundingClientRect();
        var activeRect = activeTab.getBoundingClientRect();
        var leftGap = activeRect.left - listRect.left;
        var rightGap = activeRect.right - listRect.right;
        if (tabList.clientWidth <= 720) {
            var centeredScroll = tabList.scrollLeft + leftGap - Math.max(0, (tabList.clientWidth - activeRect.width) / 2);
            tabList.scrollLeft = Math.max(0, Math.min(tabList.scrollWidth - tabList.clientWidth, centeredScroll));
            return;
        }
        if (leftGap < 0) tabList.scrollLeft += leftGap - 12;
        else if (rightGap > 0) tabList.scrollLeft += rightGap + 12;
    }

    var menus = document.querySelectorAll('.tabs, .invoice-subtabs, .pro-subnav, .file-subtabs');
    Array.prototype.forEach.call(menus, function (menu) {
        menu.addEventListener('keydown', function (event) {
            var current = event.target && event.target.closest ? event.target.closest('a[href], button:not(:disabled)') : null;
            if (!current || !menu.contains(current)) return;
            var horizontal = event.key === 'ArrowLeft' || event.key === 'ArrowRight';
            var vertical = event.key === 'ArrowUp' || event.key === 'ArrowDown';
            if (!horizontal && !vertical && event.key !== 'Home' && event.key !== 'End') return;
            var items = Array.prototype.filter.call(menu.querySelectorAll('a[href], button:not(:disabled)'), function (item) {
                return !item.hidden && item.getAttribute('aria-disabled') !== 'true' && item.getClientRects().length > 0;
            });
            var currentIndex = items.indexOf(current);
            if (currentIndex < 0 || !items.length) return;
            var nextIndex = currentIndex;
            if (event.key === 'Home') nextIndex = 0;
            else if (event.key === 'End') nextIndex = items.length - 1;
            else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') nextIndex = (currentIndex - 1 + items.length) % items.length;
            else if (event.key === 'ArrowRight' || event.key === 'ArrowDown') nextIndex = (currentIndex + 1) % items.length;
            if (nextIndex === currentIndex) return;
            event.preventDefault();
            items[nextIndex].focus();
            if (typeof items[nextIndex].scrollIntoView === 'function') {
                try { items[nextIndex].scrollIntoView({ block: 'nearest', inline: 'nearest' }); } catch (ignore) {}
            }
        });
    });

    if (window.requestAnimationFrame) window.requestAnimationFrame(revealActiveTab);
    else revealActiveTab();
})();
</script>
<script>
(function () {
    'use strict';
    var docks = Array.prototype.slice.call(document.querySelectorAll('[data-mobile-action-dock]'));
    if (!docks.length) return;
    var mobileQuery = typeof window.matchMedia === 'function' ? window.matchMedia('(max-width:720px), (max-width:900px) and (max-height:560px) and (orientation:landscape)') : null;
    var animationFrame = 0;

    function isEditableControl(target) {
        if (!target || target.disabled || target.readOnly) return false;
        var tag = String(target.tagName || '').toLowerCase();
        if (tag === 'textarea' || tag === 'select') return true;
        if (tag !== 'input') return false;
        return ['button', 'submit', 'reset', 'checkbox', 'radio', 'file', 'hidden', 'image'].indexOf(String(target.type || 'text').toLowerCase()) === -1;
    }

    function keyboardIsOpen() {
        if (mobileQuery && !mobileQuery.matches) return false;
        var viewport = window.visualViewport;
        if (viewport && viewport.height > 0 && window.innerHeight > 0) {
            var heightLoss = window.innerHeight - viewport.height;
            return viewport.height < window.innerHeight * 0.72 || heightLoss > 150;
        }
        return isEditableControl(document.activeElement);
    }

    function keepActiveFieldVisible() {
        if (!keyboardIsOpen() || !isEditableControl(document.activeElement)) return;
        var viewport = window.visualViewport;
        var visibleTop = viewport ? viewport.offsetTop + 10 : 10;
        var visibleBottom = viewport ? viewport.offsetTop + viewport.height - 12 : window.innerHeight - 12;
        var dock = docks.find(function (item) { return !item.hidden && item.getClientRects().length > 0; });
        if (dock) {
            var dockRect = dock.getBoundingClientRect();
            if (dockRect.top > visibleTop && dockRect.top < visibleBottom) visibleBottom = dockRect.top - 10;
        }
        var activeRect = document.activeElement.getBoundingClientRect();
        var delta = activeRect.bottom > visibleBottom
            ? activeRect.bottom - visibleBottom + 12
            : (activeRect.top < visibleTop ? activeRect.top - visibleTop - 12 : 0);
        if (Math.abs(delta) > 2) window.scrollBy({ top: delta, left: 0, behavior: 'smooth' });
    }

    function syncDocks() {
        animationFrame = 0;
        var keyboardOpen = keyboardIsOpen();
        var keyboardInset = 0;
        var viewport = window.visualViewport;
        if (keyboardOpen && viewport) {
            keyboardInset = Math.max(0, window.innerHeight - viewport.offsetTop - viewport.height);
        }
        document.documentElement.style.setProperty('--portal-keyboard-inset', Math.round(keyboardInset) + 'px');
        docks.forEach(function (dock) {
            // Keep the save/continue control available: CSS lifts it above the
            // virtual keyboard instead of hiding it while the user is editing.
            dock.classList.toggle('mobile-action-dock-keyboard-open', keyboardOpen);
        });
        if (keyboardOpen) window.setTimeout(keepActiveFieldVisible, 80);
    }

    function scheduleSync() {
        if (animationFrame) return;
        if (typeof window.requestAnimationFrame === 'function') animationFrame = window.requestAnimationFrame(syncDocks);
        else animationFrame = window.setTimeout(syncDocks, 50);
    }

    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', scheduleSync);
        window.visualViewport.addEventListener('scroll', scheduleSync);
    }
    window.addEventListener('resize', scheduleSync, { passive: true });
    document.addEventListener('focusin', function () {
        scheduleSync();
        window.setTimeout(keepActiveFieldVisible, 120);
        window.setTimeout(keepActiveFieldVisible, 360);
    }, true);
    document.addEventListener('focusout', function () { window.setTimeout(scheduleSync, 120); }, true);
    if (mobileQuery && typeof mobileQuery.addEventListener === 'function') mobileQuery.addEventListener('change', scheduleSync);
    else if (mobileQuery && typeof mobileQuery.addListener === 'function') mobileQuery.addListener(scheduleSync);
    syncDocks();
})();
</script>
<script>
(function () {
    'use strict';

    var actionLabels = {
        save_invoice: 'Sparar underlaget…',
        save_protocol: 'Sparar serviceprotokollet…',
        save_customer: 'Sparar kunden…',
        delete_customer: 'Raderar kunden…',
        generate_skadeblankett: 'Skapar PDF…',
        retry_skade_email: 'Skickar om mejlet…',
        retry_invoice_email: 'Försöker skicka aviseringen igen…',
        save_settings: 'Sparar inställningarna…',
        upload_logo: 'Laddar upp logotypen…',
        upload_pdf_file: 'Laddar upp PDF…',
        trigger_backup: 'Skapar säkerhetskopia…',
        invoice_pin_login: 'Loggar in…',
        protocol_pin_login: 'Loggar in…',
        invoice_pin_logout: 'Loggar ut…',
        protocol_pin_logout: 'Loggar ut…',
        central_admin_login: 'Loggar in som admin…',
        central_admin_enroll: 'Skapar central admin…',
        central_admin_change_pin: 'Byter central admin-PIN…',
        central_admin_logout: 'Loggar ut…',
        invoice_admin_test_email: 'Skickar testmejl…',
        skade_admin_test_email: 'Skickar testmejl…'
    };

    function isForm(element) {
        return !!element && String(element.tagName || '').toLowerCase() === 'form';
    }

    function findSubmitter(form, event) {
        var candidate = event && event.submitter;
        if (candidate && candidate.form === form) return candidate;
        var controls = form.querySelectorAll('button[type="submit"],button:not([type]),input[type="submit"],input[type="image"]');
        for (var i = 0; i < controls.length; i++) {
            var visible = typeof controls[i].getClientRects !== 'function' || controls[i].getClientRects().length > 0;
            if (!controls[i].disabled && !controls[i].hidden && visible) return controls[i];
        }
        return null;
    }

    function getBusyLabel(form, submitter) {
        var actionField = form.querySelector('input[name="action"]');
        var action = actionField && typeof actionField.value === 'string' ? actionField.value : '';
        if (action === 'generate_skadeblankett') {
            var label = submitter ? (submitter.tagName === 'INPUT' ? submitter.value : submitter.textContent) : '';
            if (/skicka/i.test(String(label || ''))) return 'Skickar blanketten…';
            if (/utskrift/i.test(String(label || ''))) return 'Skapar PDF för utskrift…';
            return 'Skapar signerad PDF…';
        }
        if (Object.prototype.hasOwnProperty.call(actionLabels, action)) return actionLabels[action];
        if (/^(?:save|update|delete)_/.test(action)) return 'Sparar ändringen…';
        if (/^(?:upload|retry|send|generate)_/.test(action)) return 'Skickar…';
        return 'Bearbetar…';
    }

    function statusNode(form) {
        var node = form.querySelector('[data-portal-submit-status]');
        if (node) return node;
        node = document.createElement('span');
        node.className = 'portal-submit-sr-only';
        node.setAttribute('data-portal-submit-status', '');
        node.setAttribute('role', 'status');
        node.setAttribute('aria-live', 'polite');
        form.appendChild(node);
        return node;
    }

    function markBusy(form, message, submitter) {
        if (!isForm(form) || form.dataset.portalSubmitBusy === '1') return false;
        submitter = submitter || findSubmitter(form, null);
        message = typeof message === 'string' && message !== '' ? message : getBusyLabel(form, submitter);
        form.dataset.portalSubmitBusy = '1';
        if (!Object.prototype.hasOwnProperty.call(form, '__portalSubmitOriginalAriaBusy')) {
            form.__portalSubmitOriginalAriaBusy = form.getAttribute('aria-busy');
        }
        form.setAttribute('aria-busy', 'true');
        form.classList.add('portal-form-is-submitting');
        statusNode(form).textContent = message;

        if (submitter) {
            if (submitter.tagName === 'INPUT') {
                if (!Object.prototype.hasOwnProperty.call(submitter, '__portalSubmitOriginalAriaLabel')) {
                    submitter.__portalSubmitOriginalAriaLabel = submitter.getAttribute('aria-label');
                }
                submitter.setAttribute('aria-label', message);
            } else {
                if (!Object.prototype.hasOwnProperty.call(submitter, '__portalSubmitOriginalHTML')) {
                    submitter.__portalSubmitOriginalHTML = submitter.innerHTML;
                }
                submitter.textContent = message;
            }
            if (!Object.prototype.hasOwnProperty.call(submitter, '__portalSubmitOriginalAriaDisabled')) {
                submitter.__portalSubmitOriginalAriaDisabled = submitter.getAttribute('aria-disabled');
            }
            submitter.setAttribute('aria-disabled', 'true');
            submitter.classList.add('portal-submit-busy');
        }
        return true;
    }

    function resetBusyForm(form) {
        if (!isForm(form) || form.dataset.portalSubmitBusy !== '1') return;
        form.removeAttribute('data-portal-submit-busy');
        form.classList.remove('portal-form-is-submitting');
        if (form.__portalSubmitOriginalAriaBusy === null) form.removeAttribute('aria-busy');
        else if (typeof form.__portalSubmitOriginalAriaBusy === 'string') form.setAttribute('aria-busy', form.__portalSubmitOriginalAriaBusy);
        delete form.__portalSubmitOriginalAriaBusy;

        var controls = form.querySelectorAll('.portal-submit-busy');
        Array.prototype.forEach.call(controls, function (control) {
            if (Object.prototype.hasOwnProperty.call(control, '__portalSubmitOriginalHTML')) {
                control.innerHTML = control.__portalSubmitOriginalHTML;
                delete control.__portalSubmitOriginalHTML;
            }
            if (Object.prototype.hasOwnProperty.call(control, '__portalSubmitOriginalAriaLabel')) {
                if (control.__portalSubmitOriginalAriaLabel === null) control.removeAttribute('aria-label');
                else control.setAttribute('aria-label', control.__portalSubmitOriginalAriaLabel);
                delete control.__portalSubmitOriginalAriaLabel;
            }
            if (Object.prototype.hasOwnProperty.call(control, '__portalSubmitOriginalAriaDisabled')) {
                if (control.__portalSubmitOriginalAriaDisabled === null) control.removeAttribute('aria-disabled');
                else control.setAttribute('aria-disabled', control.__portalSubmitOriginalAriaDisabled);
                delete control.__portalSubmitOriginalAriaDisabled;
            }
            control.classList.remove('portal-submit-busy');
        });
        var status = form.querySelector('[data-portal-submit-status]');
        if (status) status.textContent = '';
    }

    document.addEventListener('submit', function (event) {
        var form = event.target;
        if (!isForm(form) || form.dataset.portalSubmitBusy !== '1') return;
        event.preventDefault();
        event.stopImmediatePropagation();
    }, true);

    document.addEventListener('submit', function (event) {
        var form = event.target;
        if (!isForm(form) || event.defaultPrevented || form.dataset.noSubmitState === 'true') return;
        if (String(form.method || 'get').toLowerCase() !== 'post') return;
        var submitter = findSubmitter(form, event);
        markBusy(form, getBusyLabel(form, submitter), submitter);
    });

    window.addEventListener('pageshow', function () {
        Array.prototype.forEach.call(document.querySelectorAll('form[data-portal-submit-busy="1"]'), resetBusyForm);
    });

    window.TadegaPortalSubmitState = {
        markBusy: markBusy,
        reset: resetBusyForm
    };
})();
</script>
</body>
</html>
