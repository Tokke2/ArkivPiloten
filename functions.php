<?php
declare(strict_types=1);
/**
 * Tadega Portal core helpers.
 * Data files remain JSON for compatibility; writes are locked and atomic.
 * PHP 8.5+. Strict types are enabled; JSON data keys remain backward-compatible.
 */

require_once __DIR__ . '/includes/logger.php';
require_once __DIR__ . '/includes/email_transport.php';

$__tadega_constants = [
    // Runtime data is kept in the private, web-denied storage subfolder.
    'SETTINGS_FILE' => __DIR__ . '/storage/settings.json',
    'PROTOCOLS_FILE' => __DIR__ . '/storage/saved_protocols.json',
    'INVOICES_FILE' => __DIR__ . '/storage/saved_invoices.json',
    'SKADE_FILE' => __DIR__ . '/storage/saved_skadeblanketter.json',
    'INVENTORY_FILE' => __DIR__ . '/storage/inventory.json',
    'CUSTOMERS_FILE' => __DIR__ . '/storage/customers.json',
];
foreach ($__tadega_constants as $__name => $__value) {
    if (!defined($__name)) {
        define($__name, $__value);
    }
}
unset($__tadega_constants, $__name, $__value);

function h(mixed $value): string
{
    if (!is_scalar($value) && $value !== null) {
        $value = '';
    }
    return htmlspecialchars((string) $value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function app_legacy_text(mixed $value): string
{
    if (!is_scalar($value) && $value !== null) {
        return '';
    }
    return html_entity_decode((string) $value, ENT_QUOTES | ENT_HTML5, 'UTF-8');
}

function app_safe_data_path(mixed $file): ?string
{
    if (!is_string($file) || $file === '') {
        return null;
    }
    if ($file[0] !== DIRECTORY_SEPARATOR && !preg_match('/\A[A-Za-z]:[\\\\\/]/', $file)) {
        $file = __DIR__ . DIRECTORY_SEPARATOR . $file;
    }

    $root = realpath(__DIR__);
    $dir = realpath(dirname($file));
    if ($root === false || $dir === false || is_link($file)) {
        return null;
    }

    // Keep data files inside the application tree. Active portal data paths
    // are defined under /storage; legacy, unreferenced modules may still use
    // root-level paths until they are migrated separately.
    $full = $dir . DIRECTORY_SEPARATOR . basename($file);
    $prefix = rtrim($root, DIRECTORY_SEPARATOR) . DIRECTORY_SEPARATOR;
    if ($full !== $root && strpos($full, $prefix) !== 0) {
        return null;
    }
    return $full;
}

function load_data(string $file, mixed $default = []): array
{
    $path = app_safe_data_path($file);
    if ($path === null || !is_file($path) || is_link($path)) {
        return is_array($default) ? $default : [];
    }

    $content = @file_get_contents($path);
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

function save_data(string $file, mixed $data, bool $append = false): bool
{
    $path = app_safe_data_path($file);
    if ($path === null || is_link($path)) {
        return false;
    }

    if ($append && is_file($path)) {
        $existing = load_data($path, []);
        $data = array_merge($existing, is_array($data) ? $data : [$data]);
    }

    try {
        $json = json_encode(
            $data,
            JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_INVALID_UTF8_SUBSTITUTE | JSON_THROW_ON_ERROR
        );
    } catch (JsonException) {
        return false;
    }

    $dir = dirname($path);
    $lockPath = $path . '.lock';
    if (is_link($lockPath)) {
        return false;
    }

    $oldUmask = umask(0077);
    $lock = @fopen($lockPath, 'c');
    umask($oldUmask);
    if (!is_resource($lock)) {
        return false;
    }
    @chmod($lockPath, 0600);

    if (!@flock($lock, LOCK_EX)) {
        fclose($lock);
        return false;
    }

    $temp = null;
    try {
        // Re-check after acquiring the lock.
        if (is_link($path)) {
            return false;
        }
        $temp = @tempnam($dir, '.tadega-data-');
        if (!is_string($temp) || $temp === '') {
            return false;
        }
        $written = @file_put_contents($temp, $json . PHP_EOL, LOCK_EX);
        if ($written === false || $written !== strlen($json . PHP_EOL)) {
            @unlink($temp);
            return false;
        }
        @chmod($temp, 0600);
        if (!@rename($temp, $path)) {
            @unlink($temp);
            return false;
        }
        @chmod($path, 0600);
        return true;
    } finally {
        if (is_string($temp) && is_file($temp)) {
            @unlink($temp);
        }
        @flock($lock, LOCK_UN);
        fclose($lock);
    }
}

function csrf_token(): string
{
    if (session_status() !== PHP_SESSION_ACTIVE) {
        return '';
    }
    $key = 'tadega_customers_csrf_v1';
    if (!isset($_SESSION[$key]) || !is_string($_SESSION[$key]) || !preg_match('/\A[a-f0-9]{64}\z/', $_SESSION[$key])) {
        try {
            $_SESSION[$key] = bin2hex(random_bytes(32));
        } catch (Throwable $e) {
            return '';
        }
    }
    return $_SESSION[$key];
}

function csrf_field(): string
{
    $token = csrf_token();
    if ($token === '') {
        return '';
    }
    return '<input type="hidden" name="csrf_token" value="' . h($token) . '">';
}

function csrf_is_valid(mixed $provided = null): bool
{
    $expected = csrf_token();
    if ($expected === '') {
        return false;
    }
    if ($provided === null) {
        $provided = $_POST['csrf_token'] ?? '';
    }
    return is_string($provided) && hash_equals($expected, $provided);
}

function portal_log(mixed $message, array $context = [], mixed $level = 'INFO'): void
{
    // Do not persist message/context: callers may pass personal or secret data.
    TadegaPrivacyLogger::event('portal.activity');
}

function load_settings(): array
{
    $defaults = [
        'notification_email' => 'rl@tadega.com',
        'admin_email' => 'rl@tadega.com',
        'additional_emails' => ['info@tadega.com'],
        'company_name' => 'Tadega AB',
        'low_stock_threshold' => 2,
        'quality_report_url' => '',
    ];
    $settings = load_data(SETTINGS_FILE, []);
    // The portal now relies on upstream authentication; never expose or reuse
    // the old plaintext settings password.
    unset($settings['password'], $settings['password_hash']);
    return array_merge($defaults, $settings);
}

function save_settings(array $new): array
{
    $current = load_settings();
    $allowed = ['notification_email', 'admin_email', 'additional_emails', 'company_name', 'low_stock_threshold', 'quality_report_url'];
    $safe = [];
    foreach ($allowed as $key) {
        if (array_key_exists($key, $new)) {
            $safe[$key] = $new[$key];
        }
    }
    $merged = array_merge($current, $safe);
    unset($merged['password'], $merged['password_hash']);
    if (!save_data(SETTINGS_FILE, $merged)) {
        TadegaPrivacyLogger::event('settings.save_failed');
        return $current;
    }
    TadegaPrivacyLogger::event('settings.updated');
    return $merged;
}

function send_notification(string $type, mixed $data, ?array $settings = null): bool
{
    $settings ??= load_settings();
    $toList = [];
    $primary = $settings['notification_email'] ?? $settings['admin_email'] ?? '';
    if (is_string($primary) && filter_var($primary, FILTER_VALIDATE_EMAIL)) {
        $toList[] = $primary;
    }
    $additional = $settings['additional_emails'] ?? [];
    if (is_array($additional)) {
        foreach ($additional as $email) {
            if (is_string($email) && filter_var($email, FILTER_VALIDATE_EMAIL)) {
                $toList[] = $email;
            }
        }
    }
    $toList = array_values(array_unique($toList));
    if (!$toList) {
        return false;
    }

    $safeType = trim(preg_replace('/[\r\n]+/', ' ', (string) $type));
    $safeType = substr($safeType, 0, 100);
    $subject = 'Tadega Portal: ' . $safeType;
    $body = '<!doctype html><html lang="sv"><meta charset="utf-8"><body style="font-family:system-ui,sans-serif;color:#172033">';
    $body .= '<h2>' . h($safeType) . '</h2><table style="border-collapse:collapse">';
    if (is_array($data)) {
        foreach ($data as $key => $value) {
            if (is_array($value)) {
                $value = implode(', ', array_map('strval', $value));
            }
            $body .= '<tr><th style="text-align:left;padding:4px 12px 4px 0">' . h($key) . '</th><td style="padding:4px">' . h($value) . '</td></tr>';
        }
    }
    $body .= '</table><p style="color:#667085;font-size:12px">Sparad: ' . h(date('Y-m-d H:i')) . '</p></body></html>';
    $headers = "MIME-Version: 1.0\r\nContent-Type: text/html; charset=UTF-8\r\nFrom: Tadega Portal <noreply@tadega.com>\r\n";

    $sent = false;
    foreach ($toList as $to) {
        $delivery = portal_email_transport_send($to, $subject, $body, $headers);
        $sent = (($delivery['accepted'] ?? false) === true) || $sent;
    }
    return $sent;
}

function update_stock(array $items, int|float $direction = -1): bool
{
    if ($items === []) {
        return false;
    }
    $inventory = load_data(INVENTORY_FILE, []);
    $changed = false;
    $direction = $direction < 0 ? -1 : 1;

    foreach ($items as $item) {
        if (!is_array($item)) {
            continue;
        }
        $name = trim((string) ($item['art'] ?? $item['name'] ?? $item['namn'] ?? ''));
        $qty = (float) ($item['qty'] ?? $item['antal'] ?? 0);
        if ($name === '' || $qty <= 0) {
            continue;
        }
        foreach ($inventory as &$row) {
            if (!is_array($row)) {
                continue;
            }
            $rowName = (string) ($row['name'] ?? $row['namn'] ?? $row['art'] ?? '');
            if (strcasecmp($rowName, $name) === 0) {
                $current = (float) ($row['stock'] ?? $row['lager'] ?? 0);
                $newStock = max(0, $current + ($direction * $qty));
                if (array_key_exists('stock', $row)) {
                    $row['stock'] = $newStock;
                } else {
                    $row['lager'] = $newStock;
                }
                $changed = true;
                break;
            }
        }
        unset($row);
    }
    return $changed ? save_data(INVENTORY_FILE, $inventory) : false;
}

function skade_private_data_cutoff_timestamp(int $now): int
{
    return (new DateTimeImmutable('@' . $now))->modify('-1 year')->getTimestamp();
}

function skade_purge_expired_private_data(array $records, int $cutoffTimestamp, int $purgedAt): array
{
    $purgedCount = 0;
    foreach ($records as $key => $record) {
        if (!is_array($record) || (!array_key_exists('form_data', $record) && !array_key_exists('signature_png_base64', $record))) {
            continue;
        }
        $recordTimestamp = null;
        foreach (['updated_at', 'created_at'] as $dateField) {
            $dateValue = $record[$dateField] ?? null;
            if (is_string($dateValue) && $dateValue !== '') {
                $parsedTimestamp = strtotime($dateValue);
                if ($parsedTimestamp !== false) {
                    $recordTimestamp = $parsedTimestamp;
                    break;
                }
            }
        }
        if ($recordTimestamp === null || $recordTimestamp > $cutoffTimestamp) {
            continue;
        }
        unset($record['form_data'], $record['signature_png_base64']);
        $record['private_data_purged_at'] = gmdate(DATE_ATOM, $purgedAt);
        $records[$key] = $record;
        $purgedCount++;
    }
    return ['records' => $records, 'purged_count' => $purgedCount];
}

function skade_purge_backup_archives(int $cutoffTimestamp, int $purgedAt): bool
{
    $storageDir = __DIR__ . '/storage';
    $backupDir = $storageDir . '/backups';
    if (is_link($storageDir) || is_link($backupDir)) {
        return false;
    }
    if (!is_dir($backupDir)) {
        return true;
    }
    $storageRoot = realpath($storageDir);
    $backupRoot = realpath($backupDir);
    if ($storageRoot === false || $backupRoot === false || dirname($backupRoot) !== $storageRoot) {
        return false;
    }
    $backupPaths = glob($backupRoot . '/tadega-backup-*.zip') ?: [];
    if ($backupPaths === []) {
        return true;
    }
    if (!class_exists('ZipArchive')) {
        return false;
    }

    foreach ($backupPaths as $path) {
        $name = basename($path);
        if (!preg_match('/\\Atadega-backup-\\d{8}-\\d{6}-[a-f0-9]{8}\\.zip\\z/', $name)) {
            continue;
        }
        if (is_link($path) || !is_file($path)) {
            return false;
        }
        $realPath = realpath($path);
        if ($realPath === false || dirname($realPath) !== $backupRoot) {
            return false;
        }
        $zip = new ZipArchive();
        if ($zip->open($realPath) !== true) {
            return false;
        }
        $entryName = 'storage/saved_skadeblanketter.json';
        $entryIndex = $zip->locateName($entryName);
        if ($entryIndex === false) {
            if (!$zip->close()) {
                return false;
            }
            continue;
        }
        $entryStat = $zip->statIndex($entryIndex);
        if (!is_array($entryStat) || (int) ($entryStat['size'] ?? 0) > 104857600) {
            $zip->close();
            return false;
        }
        $json = $zip->getFromIndex($entryIndex);
        if (!is_string($json)) {
            $zip->close();
            return false;
        }
        try {
            $records = json_decode($json, true, 512, JSON_THROW_ON_ERROR);
            if (!is_array($records)) {
                $zip->close();
                return false;
            }
            $purgeResult = skade_purge_expired_private_data($records, $cutoffTimestamp, $purgedAt);
            if ((int) ($purgeResult['purged_count'] ?? 0) === 0) {
                if (!$zip->close()) {
                    return false;
                }
                continue;
            }
            $redactedJson = json_encode(
                $purgeResult['records'],
                JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_INVALID_UTF8_SUBSTITUTE | JSON_THROW_ON_ERROR
            );
        } catch (JsonException) {
            $zip->close();
            return false;
        }
        if (!is_string($redactedJson) || !$zip->deleteIndex($entryIndex) || !$zip->addFromString($entryName, $redactedJson . PHP_EOL)) {
            $zip->unchangeAll();
            $zip->close();
            return false;
        }
        if (!$zip->close()) {
            return false;
        }
        @chmod($realPath, 0600);
    }
    return true;
}

function create_backup(): string|false
{
    if (!class_exists('ZipArchive')) {
        return false;
    }
    $backupDir = __DIR__ . '/storage/backups';
    if (is_link(__DIR__ . '/storage') || is_link($backupDir)) {
        return false;
    }
    if (!is_dir($backupDir) && !@mkdir($backupDir, 0700, true)) {
        return false;
    }
    @chmod($backupDir, 0700);

    try {
        $name = 'tadega-backup-' . gmdate('Ymd-His') . '-' . bin2hex(random_bytes(4)) . '.zip';
    } catch (Throwable $e) {
        return false;
    }
    $path = $backupDir . DIRECTORY_SEPARATOR . $name;
    $zip = new ZipArchive();
    if ($zip->open($path, ZipArchive::CREATE | ZipArchive::EXCL) !== true) {
        return false;
    }

    // Explicit data allowlist. Never add SMTP credentials, invoice/protocol/
    // central-admin auth or rate-limit files, session, remember-token, or diagnostic secret files to downloadable backups.
    // The skade record file is added separately below after applying its retention rule.
    $files = [
        'storage/customers.json', 'storage/inventory.json', 'storage/saved_protocols.json',
        'storage/saved_invoices.json',
        'workplaces.json', 'inventory_units.json', 'inventory_transactions.json', 'inventory_sessions.json', 'inventory_users.json',
    ];
    foreach ($files as $relative) {
        $full = __DIR__ . DIRECTORY_SEPARATOR . $relative;
        if (is_file($full) && !is_link($full)) {
            $zip->addFile($full, $relative);
        }
    }

    $skadeRecordsPath = app_safe_data_path(SKADE_FILE);
    if (is_link(SKADE_FILE)) {
        $zip->close();
        @unlink($path);
        return false;
    }
    if ($skadeRecordsPath !== null && is_file($skadeRecordsPath)) {
        $skadeJson = @file_get_contents($skadeRecordsPath);
        if (!is_string($skadeJson)) {
            $zip->close();
            @unlink($path);
            return false;
        }
        try {
            $skadeRecords = json_decode($skadeJson, true, 512, JSON_THROW_ON_ERROR);
            if (!is_array($skadeRecords)) {
                $zip->close();
                @unlink($path);
                return false;
            }
            $backupNow = time();
            $purgeResult = skade_purge_expired_private_data(
                $skadeRecords,
                skade_private_data_cutoff_timestamp($backupNow),
                $backupNow
            );
            $redactedSkadeJson = json_encode(
                $purgeResult['records'],
                JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_INVALID_UTF8_SUBSTITUTE | JSON_THROW_ON_ERROR
            );
        } catch (JsonException) {
            $zip->close();
            @unlink($path);
            return false;
        }
        if (!is_string($redactedSkadeJson) || !$zip->addFromString('storage/saved_skadeblanketter.json', $redactedSkadeJson . PHP_EOL)) {
            $zip->close();
            @unlink($path);
            return false;
        }
    }

    // Include a redacted settings snapshot; never copy legacy passwords.
    $settings = load_settings();
    $settingsJson = json_encode($settings, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    if (is_string($settingsJson)) {
        $zip->addFromString('settings.json', $settingsJson);
    }

    foreach (['pdf', 'svg', 'uploads'] as $folder) {
        $dir = __DIR__ . DIRECTORY_SEPARATOR . $folder;
        if (!is_dir($dir) || is_link($dir)) {
            continue;
        }
        $iterator = new RecursiveIteratorIterator(
            new RecursiveDirectoryIterator($dir, FilesystemIterator::SKIP_DOTS),
            RecursiveIteratorIterator::LEAVES_ONLY
        );
        foreach ($iterator as $entry) {
            if ($entry->isFile() && !$entry->isLink()) {
                $full = $entry->getPathname();
                $relative = str_replace(__DIR__ . DIRECTORY_SEPARATOR, '', $full);
                if ($relative !== '' && strpos($relative, '..') === false) {
                    $zip->addFile($full, $relative);
                }
            }
        }
    }
    $zip->close();
    @chmod($path, 0600);
    TadegaPrivacyLogger::event('backup.created');
    return is_file($path) ? $path : false;
}

function load_json(string $filename): array
{
    return load_data(__DIR__ . '/storage/' . basename($filename), []);
}

function save_json(string $filename, mixed $data): bool
{
    return save_data(__DIR__ . '/storage/' . basename($filename), $data);
}

function load_customers(): array { return load_data(CUSTOMERS_FILE, []); }
function load_inventory(): array { return load_data(INVENTORY_FILE, []); }
function load_protocols(): array { return load_data(PROTOCOLS_FILE, []); }
function load_invoices(): array { return load_data(INVOICES_FILE, []); }
function load_skadeblanketter(): array { return load_data(SKADE_FILE, []); }

function get_next_protocol_number(): string
{
    $max = 0;
    foreach (load_protocols() as $protocol) {
        if (!is_array($protocol)) {
            continue;
        }
        $number = (string) ($protocol['nummer'] ?? '');
        if (preg_match('/\A1000-(\d+)\z/', $number, $match)) {
            $max = max($max, (int) $match[1]);
        }
    }
    return '1000-' . str_pad((string) ($max + 1), 2, '0', STR_PAD_LEFT);
}

function get_next_invoice_number(): int
{
    $max = 2000;
    foreach (load_invoices() as $invoice) {
        if (!is_array($invoice)) {
            continue;
        }
        $number = $invoice['nummer'] ?? null;
        if (is_numeric($number)) {
            $max = max($max, (int) $number);
        }
    }
    return $max + 1;
}

function get_archive_files(): array
{
    $pdfDir = __DIR__ . '/pdf';
    if (!is_dir($pdfDir) || is_link($pdfDir)) {
        return [];
    }
    $files = [];
    try {
        $iterator = new RecursiveIteratorIterator(
            new RecursiveDirectoryIterator($pdfDir, FilesystemIterator::SKIP_DOTS),
            RecursiveIteratorIterator::LEAVES_ONLY
        );
        foreach ($iterator as $entry) {
            if (!$entry->isFile() || $entry->isLink()) {
                continue;
            }
            $extension = strtolower($entry->getExtension());
            if (!in_array($extension, ['pdf', 'png', 'jpg', 'jpeg'], true)) {
                continue;
            }
            $absolute = $entry->getPathname();
            $relative = str_replace(DIRECTORY_SEPARATOR, '/', substr($absolute, strlen($pdfDir) + 1));
            if ($relative === '' || strpos($relative, '..') !== false) {
                continue;
            }
            $files[] = [
                'rel' => $relative,
                'name' => $entry->getFilename(),
                'size' => round($entry->getSize() / 1024, 1),
                'date' => date('Y-m-d H:i', $entry->getMTime()),
                'time' => $entry->getMTime(),
            ];
            if (count($files) >= 2000) {
                break;
            }
        }
    } catch (Throwable $e) {
        return [];
    }
    usort($files, static function (array $a, array $b): int {
        return ($b['time'] ?? 0) <=> ($a['time'] ?? 0);
    });
    return $files;
}

function ensure_base_files(): void
{
    $files = [
        SETTINGS_FILE => [
            'notification_email' => 'rl@tadega.com',
            'admin_email' => 'rl@tadega.com',
            'additional_emails' => ['info@tadega.com'],
            'company_name' => 'Tadega AB',
            'low_stock_threshold' => 2,
        ],
        PROTOCOLS_FILE => [],
        INVOICES_FILE => [],
        SKADE_FILE => [],
        INVENTORY_FILE => [],
        CUSTOMERS_FILE => [],
    ];
    foreach ($files as $path => $default) {
        if (!is_file($path)) {
            save_data($path, $default);
        }
    }

    // Remove the old plaintext password from existing settings data.
    $rawSettings = load_data(SETTINGS_FILE, []);
    if (array_key_exists('password', $rawSettings) || array_key_exists('password_hash', $rawSettings)) {
        unset($rawSettings['password'], $rawSettings['password_hash']);
        save_data(SETTINGS_FILE, $rawSettings);
    }
}

ensure_base_files();
