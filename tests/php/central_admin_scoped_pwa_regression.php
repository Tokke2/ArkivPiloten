<?php
declare(strict_types=1);

define('TADEGA_PWA_APP', 'invoice');

$sourceFile = __DIR__ . '/../../includes/central_admin_auth.php';
$invoiceAuthSource = __DIR__ . '/../../includes/invoice_auth.php';
$protocolAuthSource = __DIR__ . '/../../includes/protocol_auth.php';
$sandbox = __DIR__ . '/.central-admin-pwa-sandbox';
$storageDir = $sandbox . '/storage';
$includeDir = $sandbox . '/includes';
$sessionDir = $sandbox . '/sessions';

$removeTree = static function (string $path) use (&$removeTree): void {
    if (is_link($path) || is_file($path)) {
        @unlink($path);
        return;
    }
    if (!is_dir($path)) {
        return;
    }
    $items = @scandir($path);
    if (is_array($items)) {
        foreach ($items as $item) {
            if ($item !== '.' && $item !== '..') {
                $removeTree($path . DIRECTORY_SEPARATOR . $item);
            }
        }
    }
    @rmdir($path);
};

$removeTree($sandbox);
if (!@mkdir($storageDir, 0700, true) || !@mkdir($includeDir, 0700, true) || !@mkdir($sessionDir, 0700, true)) {
    throw new RuntimeException('Could not prepare isolated scoped-PWA test directories.');
}
if (
    @file_put_contents($storageDir . '/.htaccess', "Require all denied\n") === false ||
    !@copy($invoiceAuthSource, $includeDir . '/invoice_auth.php') ||
    !@copy($protocolAuthSource, $includeDir . '/protocol_auth.php') ||
    !@copy($sourceFile, $includeDir . '/central_admin_auth.php')
) {
    $removeTree($sandbox);
    throw new RuntimeException('Could not prepare isolated scoped-PWA test files.');
}

function save_data(string $file, mixed $data, bool $append = false): bool
{
    if (is_link($file) || is_link($file . '.lock')) {
        return false;
    }
    try {
        $json = json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
    } catch (JsonException) {
        return false;
    }
    $temp = $file . '.test-tmp';
    if (@file_put_contents($temp, $json . PHP_EOL, LOCK_EX) === false) {
        return false;
    }
    @chmod($temp, 0600);
    if (!@rename($temp, $file)) {
        @unlink($temp);
        return false;
    }
    @chmod($file, 0600);
    return true;
}

function load_data(string $file, mixed $default = []): array
{
    if (is_link($file) || !is_file($file) || !is_readable($file)) {
        return is_array($default) ? $default : [];
    }
    $content = @file_get_contents($file);
    if (!is_string($content) || $content === '') {
        return is_array($default) ? $default : [];
    }
    try {
        $data = json_decode($content, true, 512, JSON_THROW_ON_ERROR);
    } catch (JsonException) {
        return is_array($default) ? $default : [];
    }
    return is_array($data) ? $data : (is_array($default) ? $default : []);
}

require $includeDir . '/invoice_auth.php';
require $includeDir . '/protocol_auth.php';
require $includeDir . '/central_admin_auth.php';

$checks = 0;
$assert = static function (bool $condition, string $message) use (&$checks): void {
    $checks++;
    if (!$condition) {
        throw new RuntimeException($message);
    }
};

try {
    $_SERVER['SCRIPT_NAME'] = '/dokument/pwa-underlag.php';
    $_SERVER['REMOTE_ADDR'] = '127.0.0.1';
    ini_set('session.use_strict_mode', '1');
    session_save_path($sessionDir);
    session_name('PHPSESSID');
    session_id('CentralAdminPwaTestSession0000000001');
    if (!@session_start()) {
        throw new RuntimeException('Could not start isolated primary session.');
    }

    $pin = '735190!@';
    $hash = portal_central_admin_auth_hash_pin($pin);
    if (!is_string($hash)) {
        throw new RuntimeException('Could not hash the scoped-PWA test PIN.');
    }
    $credentialId = '1234567890abcdef1234567890abcdef';
    $now = time();
    $config = [
        'schema_version' => 1,
        'pin_policy_version' => 2,
        'pin_hash' => $hash,
        'credential_id' => $credentialId,
        'created_at' => $now,
        'pin_changed_at' => $now,
    ];
    if (!save_data(portal_central_admin_auth_config_file(), $config)) {
        throw new RuntimeException('Could not prepare scoped-PWA test credential.');
    }
    if (!portal_central_admin_auth_open_session($credentialId)) {
        throw new RuntimeException('Could not prepare isolated central admin session.');
    }

    $assert(portal_central_admin_auth_is_scoped_pwa(), 'The invoice PWA should be identified as a scoped route.');
    $assert(portal_central_admin_auth_current_user() === null, 'A scoped customer PWA must not recognize the central admin session.');
    $assert(portal_central_admin_auth_portal_user() === null, 'A central admin session must not grant staff-portal rights inside a customer PWA.');
    $assert(!portal_central_admin_auth_can_access_personal_portal(), 'A scoped customer PWA must not accept central cross-portal access.');
    $assert(portal_invoice_auth_current_user() === null, 'The central admin cookie must not become an invoice user in a customer PWA.');
    $assert(portal_protocol_auth_current_user() === null, 'The central admin cookie must not become a protocol user in a customer PWA.');
    $assert(!portal_invoice_auth_is_admin(), 'Scoped customer PWA requests must not pass existing invoice-admin checks.');
    $assert((portal_central_admin_auth_login($pin)['code'] ?? '') === 'forbidden', 'Central admin PIN login must be rejected on a scoped PWA route.');
    $assert((portal_central_admin_auth_enroll($pin)['code'] ?? '') === 'forbidden', 'Central PIN setup must be rejected on a scoped PWA route.');
    $assert((portal_central_admin_auth_change_pin($pin, $pin)['code'] ?? '') === 'forbidden', 'Central PIN changes must be rejected on a scoped PWA route.');
    $assert((portal_central_admin_auth_verify_current_pin($pin)['code'] ?? '') === 'forbidden', 'Central re-verification must be rejected on a scoped PWA route.');

    echo 'PASS: ' . $checks . ' scoped customer-PWA isolation checks.' . PHP_EOL;
} finally {
    if (session_status() === PHP_SESSION_ACTIVE) {
        @session_write_close();
    }
    $removeTree($sandbox);
}
