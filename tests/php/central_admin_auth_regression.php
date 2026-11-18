<?php
declare(strict_types=1);

/**
 * Isolated regression test for central-admin auth. The copied module uses a
 * temporary storage/session sandbox so this test never touches portal accounts.
 */
$sourceFile = __DIR__ . '/../../includes/central_admin_auth.php';
$invoiceAuthSource = __DIR__ . '/../../includes/invoice_auth.php';
$protocolAuthSource = __DIR__ . '/../../includes/protocol_auth.php';
$sandbox = __DIR__ . '/.central-admin-auth-sandbox';
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
    throw new RuntimeException('Could not prepare isolated central-admin test directories.');
}
if (
    @file_put_contents($storageDir . '/.htaccess', "Require all denied\n") === false ||
    !@copy($invoiceAuthSource, $includeDir . '/invoice_auth.php') ||
    !@copy($protocolAuthSource, $includeDir . '/protocol_auth.php') ||
    !@copy($sourceFile, $includeDir . '/central_admin_auth.php')
) {
    $removeTree($sandbox);
    throw new RuntimeException('Could not prepare isolated central-admin test files.');
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
    $_SERVER['SCRIPT_NAME'] = '/dokument/index.php';
    $_SERVER['REMOTE_ADDR'] = '127.0.0.1';
    ini_set('session.use_strict_mode', '1');
    session_save_path($sessionDir);
    session_name('PHPSESSID');
    session_id('CentralAdminTestSession00000000000001');
    if (!@session_start()) {
        throw new RuntimeException('Could not start isolated primary session.');
    }

    $pin = '735190!@';
    $newPin = '8492716#_';
    $nextPin = '40286135';
    $assert(portal_central_admin_auth_pin_is_valid($pin), 'A six-digit PIN with two allowed symbols should be accepted.');
    $assert(portal_central_admin_auth_pin_is_valid('123456'), 'A six-digit numeric PIN should be accepted with no optional symbols.');
    $assert(portal_central_admin_auth_pin_is_valid('123456-'), 'A PIN should accept symbols from the documented allowlist.');
    $assert(portal_central_admin_auth_pin_is_valid('1234567890!@'), 'Ten digits with two allowed symbols should be accepted at the maximum.');
    $assert(!portal_central_admin_auth_pin_is_valid('12345!'), 'A PIN with fewer than six digits must be rejected.');
    $assert(!portal_central_admin_auth_pin_is_valid('Central123456'), 'Letters must not be accepted in the central PIN.');
    $assert(!portal_central_admin_auth_pin_is_valid('123456!@#'), 'More than two optional symbols must be rejected.');
    $assert(!portal_central_admin_auth_pin_is_valid('12345678901'), 'More than ten digits must be rejected.');
    $assert(!portal_central_admin_auth_pin_is_valid('123456?'), 'Symbols outside the documented allowlist must be rejected.');
    $assert(portal_central_admin_auth_legacy_pin_is_valid('LegacyAdminPin2026!'), 'An existing legacy credential should remain verifiable for one-time migration.');
    $assert(!portal_central_admin_auth_pin_is_valid("123456\n"), 'Control characters must be rejected.');
    $assert(portal_central_admin_auth_setup_state() === 'unconfigured', 'The isolated auth store should begin unconfigured.');

    $invoicePinHash = password_hash('135790', PASSWORD_DEFAULT);
    $invoiceUser = [
        'id' => 'existing-invoice-admin',
        'username' => 'existing-admin',
        'name' => 'Existing invoice admin',
        'role' => 'admin',
        'pin_hash' => is_string($invoicePinHash) ? $invoicePinHash : '',
        'auth_version' => 1,
        'active' => true,
        'created_at' => gmdate('Y-m-d\\TH:i:s\\Z'),
    ];
    if (!is_string($invoicePinHash) || !save_data($storageDir . '/invoice_users.json', [$invoiceUser])) {
        throw new RuntimeException('Could not prepare isolated invoice-admin account.');
    }
    $_SESSION['portal_invoice_auth'] = [
        'user_id' => 'existing-invoice-admin',
        'auth_version' => 1,
        'authenticated_at' => time(),
    ];
    $enroll = portal_central_admin_auth_enroll($pin);
    $assert(($enroll['ok'] ?? false) === true, 'An existing invoice admin should be able to set up the central PIN.');
    $assert(portal_central_admin_auth_setup_state() === 'configured', 'Enrollment should create a valid private credential record.');
    $storedConfig = portal_central_admin_auth_read_config();
    $assert(is_array($storedConfig) && isset($storedConfig['pin_hash']), 'The central PIN should be stored as a one-way hash.');
    $assert(($storedConfig['pin_policy_version'] ?? null) === 2, 'New credentials should be marked as using the current PIN-only policy.');
    $storedText = @file_get_contents(portal_central_admin_auth_config_file());
    $assert(is_string($storedText) && !str_contains($storedText, $pin), 'Plaintext central PIN must not be written to storage.');
    $assert(is_array(portal_central_admin_auth_current_user()), 'Successful enrollment should establish a central session.');
    $assert(is_array(portal_central_admin_auth_portal_user()), 'An active central admin session should grant staff-portal access.');
    $invoiceCentralUser = portal_invoice_auth_current_user();
    $protocolCentralUser = portal_protocol_auth_current_user();
    $assert(($invoiceCentralUser['auth_source'] ?? '') === 'central_admin' && ($invoiceCentralUser['role'] ?? '') === 'admin', 'The central PIN should grant invoice-admin capability without replacing invoice accounts.');
    $assert(($protocolCentralUser['auth_source'] ?? '') === 'central_admin' && ($protocolCentralUser['role'] ?? '') === 'admin', 'The central PIN should grant protocol-admin capability across its separate session.');
    $assert(portal_invoice_auth_is_admin(), 'Central admin should pass existing shared admin checks.');

    $changed = portal_central_admin_auth_change_pin($pin, $newPin);
    $assert(($changed['code'] ?? '') === 'changed', 'The central PIN should be changeable after re-verification.');
    $assert(is_array(portal_central_admin_auth_current_user()) && !portal_central_admin_auth_current_user()['must_change_pin'], 'A successful PIN change should keep the new admin session active.');
    $wrongRecheck = portal_central_admin_auth_verify_current_pin($pin);
    $assert(($wrongRecheck['ok'] ?? false) !== true, 'The previous PIN must stop verifying after a change.');
    $rightRecheck = portal_central_admin_auth_verify_current_pin($newPin);
    $assert(($rightRecheck['ok'] ?? false) === true, 'The new PIN should verify for sensitive admin actions.');

    $aged = portal_central_admin_auth_with_config_lock(static function (string $state, ?array $config, string $path): array {
        if ($state !== 'configured' || !is_array($config)) {
            return ['ok' => false, 'code' => 'unexpected_state'];
        }
        $config['created_at'] = time() - 20 * 86400;
        $config['pin_changed_at'] = time() - 20 * 86400;
        return portal_central_admin_auth_write_config($path, $config)
            ? ['ok' => true, 'code' => 'aged']
            : ['ok' => false, 'code' => 'write_failed'];
    });
    portal_central_admin_auth_request_cache_clear();
    $agedUser = portal_central_admin_auth_current_user();
    $assert(($aged['ok'] ?? false) === true && is_array($agedUser) && ($agedUser['must_change_pin'] ?? false) === true, 'A PIN at the 20-day limit must require rotation.');
    $assert(!portal_central_admin_auth_can_access_personal_portal(), 'An overdue central PIN must not retain central cross-portal access.');

    $rotated = portal_central_admin_auth_change_pin($newPin, $nextPin);
    $assert(($rotated['code'] ?? '') === 'changed', 'An overdue PIN must be changeable after re-verification.');
    $assert(portal_central_admin_auth_can_access_personal_portal(), 'Changing an overdue PIN should restore central access.');

    for ($attempt = 0; $attempt < 5; $attempt++) {
        portal_central_admin_auth_login('wrong');
    }
    $rateState = portal_central_admin_auth_rate_state();
    $assert(($rateState['locked'] ?? false) === true, 'Five failed PIN attempts should trigger a temporary lockout.');
    $assert(portal_central_admin_auth_clear_failures(), 'The isolated rate-limit state should be clearable.');
    $assert((portal_central_admin_auth_rate_state()['locked'] ?? true) === false, 'Clearing failures should release the test lockout.');

    portal_central_admin_auth_logout();
    $assert(portal_central_admin_auth_current_user() === null, 'Logout should remove central admin access.');
    $login = portal_central_admin_auth_login($nextPin);
    $assert(($login['ok'] ?? false) === true && is_array(portal_central_admin_auth_current_user()), 'The rotated PIN should log back in successfully.');

    $oldCredential = (string) (portal_central_admin_auth_read_config()['credential_id'] ?? '');
    @unlink(portal_central_admin_auth_config_file());
    portal_central_admin_auth_request_cache_clear();
    $assert(portal_central_admin_auth_setup_state() === 'unconfigured', 'Removing the central credential by SFTP should reopen controlled enrollment.');
    $assert(portal_central_admin_auth_current_user() === null, 'Removing the config must invalidate previous central sessions.');
    $invoiceSurvivesReset = portal_invoice_auth_current_user();
    $assert(($invoiceSurvivesReset['id'] ?? '') === 'existing-invoice-admin' && ($invoiceSurvivesReset['auth_source'] ?? '') !== 'central_admin', 'SFTP reset must leave the existing invoice account and session intact.');
    $resetEnroll = portal_central_admin_auth_enroll($pin);
    $assert(($resetEnroll['ok'] ?? false) === true, 'The existing invoice admin should be able to re-enroll after SFTP reset.');
    $newCredential = (string) (portal_central_admin_auth_read_config()['credential_id'] ?? '');
    $assert($oldCredential !== '' && $newCredential !== '' && !hash_equals($oldCredential, $newCredential), 'SFTP re-enrollment must use a fresh credential generation.');

    $legacyPin = 'LegacyAdminPin2026!';
    $legacyConfig = portal_central_admin_auth_read_config();
    $legacyHash = password_hash(portal_central_admin_auth_hash_input($legacyPin), PASSWORD_DEFAULT);
    if (!is_array($legacyConfig) || !is_string($legacyHash)) {
        throw new RuntimeException('Could not prepare the legacy-PIN migration fixture.');
    }
    $legacyConfig['pin_hash'] = $legacyHash;
    unset($legacyConfig['pin_policy_version']);
    $legacySaved = portal_central_admin_auth_write_config(portal_central_admin_auth_config_file(), $legacyConfig);
    portal_central_admin_auth_request_cache_clear();
    $legacyExistingSession = portal_central_admin_auth_current_user();
    $assert($legacySaved && is_array($legacyExistingSession) && ($legacyExistingSession['must_change_pin'] ?? false) === true, 'Existing sessions using the former PIN policy must be forced to rotate their PIN.');
    $assert(!portal_central_admin_auth_can_access_personal_portal(), 'A legacy-policy session must not retain admin access before rotation.');
    portal_central_admin_auth_logout();
    $legacyLogin = portal_central_admin_auth_login($legacyPin);
    $assert(($legacyLogin['ok'] ?? false) === true && ($legacyLogin['must_change_pin'] ?? false) === true, 'A valid old PIN should allow one login only to complete the forced migration.');
    $legacySessionUser = portal_central_admin_auth_current_user();
    $assert(is_array($legacySessionUser) && ($legacySessionUser['must_change_pin'] ?? false) === true, 'The migration requirement must persist in the isolated central session.');
    $legacyRotation = portal_central_admin_auth_change_pin($legacyPin, $pin);
    $migratedConfig = portal_central_admin_auth_read_config();
    $assert(($legacyRotation['code'] ?? '') === 'changed' && portal_central_admin_auth_can_access_personal_portal(), 'A legacy PIN should be replaceable with a policy-compliant PIN.');
    $assert(($migratedConfig['pin_policy_version'] ?? null) === 2, 'PIN rotation should persist the current policy version.');
    $assert((portal_central_admin_auth_verify_current_pin($legacyPin)['ok'] ?? false) !== true, 'The old PIN must no longer verify after migration.');
    $assert((portal_central_admin_auth_verify_current_pin($pin)['ok'] ?? false) === true, 'The newly migrated PIN should verify for sensitive actions.');

    portal_central_admin_auth_logout();
    $invoiceUser['role'] = 'staff';
    if (!save_data($storageDir . '/invoice_users.json', [$invoiceUser])) {
        throw new RuntimeException('Could not prepare a staff-only invoice account.');
    }
    $staffInvoiceUser = portal_invoice_auth_current_user();
    $assert(($staffInvoiceUser['role'] ?? '') === 'staff', 'The existing invoice account layer should keep its ordinary staff role.');
    $staffEnroll = portal_central_admin_auth_enroll($nextPin);
    $assert(($staffEnroll['code'] ?? '') === 'forbidden', 'A non-admin invoice user must not enroll or reset the central PIN.');

    echo 'PASS: ' . $checks . ' central admin auth regression checks.' . PHP_EOL;
} finally {
    if (session_status() === PHP_SESSION_ACTIVE) {
        @session_write_close();
    }
    $removeTree($sandbox);
}
