<?php
declare(strict_types=1);

require_once __DIR__ . '/../../includes/release_updater.php';

$checks = 0;
$assert = static function (bool $condition, string $message) use (&$checks): void {
    $checks++;
    if (!$condition) {
        throw new RuntimeException($message);
    }
};

// This fixture key is test-only. Its private half is intentionally not stored
// in the project and is not a release trust key for the deployed portal.
$manifestJson = '{"schema":1,"version":"1.0.0","files":[{"path":"assets/new.svg","sha256":"cd1fafe3cc7f06f55ead3f0dce39300aca7a8911793e76fcdd327799c0709ac2","size":7},{"path":"includes/nested/release.php","sha256":"5a72ec6a6ee7359595e6f3d1ca22d3b9a714e72047c88028fd91b529cc08f2b6","size":11},{"path":"index.php","sha256":"037871a818fb15a2bf2063d460cdf8f1fe3e35974da69791ccd10dae6e1c8515","size":10},{"path":"tabs/admin.php","sha256":"3242b2a1f65331b5e4c194be6eb9d055cd2d5e229838ff687845747bd4062712","size":11}]}';
$publicKeyPem = <<<'PEM'
-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA5Ba093QC7MfSBXEjZzA7
u7mWiAt84doNoOg90dTnd/XgNOvTCpErLkLFAadFfYMP/L7TpoHhHNfOW+JsmRIZ
6vzP0xHsP0fIpMysDyOwnbCGfDunUzIqIFjFoUeCIT9Qm6LU+H9aqyryiV+MO8He
6piFbbS4GIcoEmt3XD+T74TA5Q/empOk0DhdWAQUlUFFeqcPyieGjcPId+QkU/76
IEi5OWanUCwIYAwkWqLRFJi4G4qXrnRz4N+hfyk6l0TiY+rPgpQTRux7EUZIXb/9
vBhROexUOyNgbDbFrjevoJHVTsLPjsRuLz3iM/0vTsqJGdly1xDCDafJ2ngRsy1Q
QQIDAQAB
-----END PUBLIC KEY-----
PEM;
$signatureBase64 = 'FGhwyZd5pzawPTq+P1vRAVnysrMmE59oZEHcyNvy/fkXaAINISSzq2lqajHxbEX4cc85rjhOVSrepjNT+V3OlUpByjHUilyr0VJkDDXsvixWeyJ8OUYn9qEfUiQTD+uAOF+Ix8Sy5EFp6YI0nvoAuAdsmDhiLB2zhvm6QGarQyGAJGIcSbpiDtlKq2smyOy0m6ARCJqpSow3BHa7x9vdbNd2UeXrePUh8R5HbczVc6SdZ0D9HEaqvEI4Sy9m/rUmpwDpwRyH3ACBke4oKs4xuxkE9bQ08rhQBsbBzHbw6/yFS79eo5rW+cc6pHou1+Apvn80Qz7YtBI2KI8jIASJhg==';

$verification = portal_release_verify_manifest($manifestJson, $signatureBase64, $publicKeyPem);
$assert(($verification['ok'] ?? false) === true, 'A valid SHA-256-signed manifest should verify.');
$assert(($verification['manifest']['version'] ?? '') === '1.0.0', 'The verified release version should be returned.');
$assert(count($verification['manifest']['files'] ?? []) === 4, 'Only validated manifest entries should be returned.');
$assert(!portal_release_path_is_allowed('storage/private.json'), 'storage/ paths must be excluded from manifests.');
$assert(!portal_release_path_is_allowed('tabs/../../storage/private.json'), 'Path traversal must be rejected.');
$assert(!portal_release_path_is_allowed('/index.php'), 'Absolute paths must be rejected.');
$assert(!portal_release_path_is_allowed('index.php\\storage\\private.json'), 'Backslash paths must be rejected.');
$assert(!portal_release_path_is_allowed('includes/.htaccess'), 'Hidden access-control files must never be replaced.');
$assert(!portal_release_path_is_allowed('includes/release_config.php'), 'Local GitHub trust configuration must not be replaced by an update.');
$assert(portal_release_path_is_allowed('includes/release_updater.php'), 'Portal code under includes/ may be updated.');
$assert(portal_release_directory_is_allowed('assets', []), 'An allowlisted asset directory is valid.');
$assert(!portal_release_directory_is_allowed('storage', []), 'storage/ may not be a ZIP directory.');
$assert(portal_release_directory_is_allowed('tabs', ['tabs/admin.php']), 'A manifest-listed parent directory is valid.');
$assert(!portal_release_directory_is_allowed('other', []), 'Unknown directories must be rejected.');
$assert(($verification['ok'] ?? false) === true, 'Path policy checks do not mutate the verified manifest.');

$tamperedManifest = portal_release_verify_manifest($manifestJson . ' ', $signatureBase64, $publicKeyPem);
$assert(($tamperedManifest['ok'] ?? true) === false, 'Changing signed manifest bytes must invalidate the signature.');
$tamperedSignature = portal_release_verify_manifest($manifestJson, $signatureBase64 . 'A', $publicKeyPem);
$assert(($tamperedSignature['ok'] ?? true) === false, 'An altered signature must be rejected.');
$invalidSignatureText = portal_release_verify_manifest($manifestJson, 'not base64 !!!', $publicKeyPem);
$assert(($invalidSignatureText['ok'] ?? true) === false, 'Malformed signature text must be rejected.');
$config = portal_release_configuration();
$assert(($config['ok'] ?? true) === false && ($config['code'] ?? '') === 'configuration_incomplete', 'Blank repository/key settings must keep the release checker disabled.');
$disabledCheck = portal_release_check_latest(sys_get_temp_dir());
$assert(($disabledCheck['ok'] ?? true) === false && ($disabledCheck['code'] ?? '') === 'configuration_incomplete', 'A release check with blank configuration must return before making any network request.');

$base = rtrim(sys_get_temp_dir(), DIRECTORY_SEPARATOR) . DIRECTORY_SEPARATOR . 'tadega-release-regression-' . bin2hex(random_bytes(8));
$appRoot = $base . DIRECTORY_SEPARATOR . 'app';
$zipPath = $base . DIRECTORY_SEPARATOR . 'valid-release.zip';
$badZipPath = $base . DIRECTORY_SEPARATOR . 'tampered-release.zip';
$extraZipPath = $base . DIRECTORY_SEPARATOR . 'extra-storage-release.zip';
$writeFixture = static function (string $root, string $relativePath, string $contents): void {
    $path = $root . DIRECTORY_SEPARATOR . str_replace('/', DIRECTORY_SEPARATOR, $relativePath);
    $directory = dirname($path);
    if (!is_dir($directory) && !@mkdir($directory, 0700, true) && !is_dir($directory)) {
        throw new RuntimeException('Could not create isolated test fixture directory.');
    }
    if (file_put_contents($path, $contents) === false) {
        throw new RuntimeException('Could not write isolated test fixture file.');
    }
};
$makeZip = static function (string $path, array $files) use ($manifestJson, $signatureBase64): void {
    $zip = new ZipArchive();
    if ($zip->open($path, ZipArchive::CREATE | ZipArchive::OVERWRITE) !== true) {
        throw new RuntimeException('Could not create an isolated ZIP fixture.');
    }
    $ok = $zip->addFromString('manifest.json', $manifestJson)
        && $zip->addFromString('manifest.sig', $signatureBase64);
    foreach ($files as $name => $content) {
        $ok = $zip->addFromString($name, $content) && $ok;
    }
    $closed = $zip->close();
    if (!$ok || !$closed) {
        throw new RuntimeException('Could not complete an isolated ZIP fixture.');
    }
};
$removeTree = static function (string $path) use (&$removeTree): void {
    if (is_link($path) || is_file($path)) {
        @unlink($path);
        return;
    }
    if (!is_dir($path)) {
        return;
    }
    foreach (scandir($path) ?: [] as $entry) {
        if ($entry !== '.' && $entry !== '..') {
            $removeTree($path . DIRECTORY_SEPARATOR . $entry);
        }
    }
    @rmdir($path);
};

try {
    if (!class_exists(ZipArchive::class)) {
        throw new RuntimeException('ZipArchive is required for release integration tests.');
    }
    if (!@mkdir($appRoot . '/assets', 0700, true) || !@mkdir($appRoot . '/includes/nested', 0700, true) || !@mkdir($appRoot . '/tabs', 0700, true)) {
        throw new RuntimeException('Could not create application test directories.');
    }
    if (!@mkdir($appRoot . '/storage', 0700, true)) {
        throw new RuntimeException('Could not create the untouched storage test directory.');
    }
    $writeFixture($appRoot, '.htaccess', "Options -Indexes\n# release-lock-anchor\n");
    $writeFixture($appRoot, 'index.php', "old-index\n");
    $writeFixture($appRoot, 'includes/nested/release.php', "old-nested\n");
    $writeFixture($appRoot, 'tabs/admin.php', "same-admin\n");
    $writeFixture($appRoot, 'storage/keep.json', "private-data\n");
    $writeFixture($appRoot, 'settings.json', "legacy-settings\n");

    $validFiles = [
        'assets/new.svg' => "<svg/>\n",
        'includes/nested/release.php' => "new-nested\n",
        'index.php' => "new-index\n",
        'tabs/admin.php' => "same-admin\n",
    ];
    $makeZip($zipPath, $validFiles);
    $comparison = portal_release_compare_zip_files($appRoot, $zipPath, $publicKeyPem);
    $assert(($comparison['ok'] ?? false) === true, 'A ZIP matching its signed manifest must compare successfully.');
    $assert(($comparison['version'] ?? '') === '1.0.0', 'The ZIP comparison should return the signed version.');
    $assert(($comparison['manifest_sha256'] ?? '') === hash('sha256', $manifestJson), 'Approval must bind to the exact signed manifest digest.');
    $assert(($comparison['changed'] ?? []) === ['assets/new.svg', 'includes/nested/release.php', 'index.php'], 'Only changed or new files should appear in the plan, including changed files in nested directories.');
    $assert(($comparison['unchanged'] ?? []) === ['tabs/admin.php'], 'Identical files should not be included in the write list.');
    $assert(array_key_exists('assets/new.svg', $comparison['before'] ?? []) && $comparison['before']['assets/new.svg'] === null, 'The plan should record new targets as absent.');
    $assert(($comparison['before']['index.php'] ?? '') === hash('sha256', "old-index\n"), 'The plan should bind changed files to their pre-check hashes.');
    $assert(file_get_contents($appRoot . '/index.php') === "old-index\n", 'Comparison must not write application files.');
    $assert(file_get_contents($appRoot . '/storage/keep.json') === "private-data\n", 'Comparison must leave storage/ untouched.');
    $assert(file_get_contents($appRoot . '/settings.json') === "legacy-settings\n", 'Non-allowlisted legacy data files must remain untouched.');

    $wrongVersion = portal_release_install_package($appRoot, $zipPath, $publicKeyPem, 'v1.0.0', '2.0.0', hash('sha256', $manifestJson));
    $assert(($wrongVersion['ok'] ?? true) === false && ($wrongVersion['code'] ?? '') === 'approval_mismatch', 'An admin approval for a different version must fail closed.');
    $assert(file_get_contents($appRoot . '/index.php') === "old-index\n", 'A mismatched approval must not write files.');
    $wrongDigest = portal_release_install_package($appRoot, $zipPath, $publicKeyPem, 'v1.0.0', '1.0.0', str_repeat('0', 64));
    $assert(($wrongDigest['ok'] ?? true) === false && ($wrongDigest['code'] ?? '') === 'approval_mismatch', 'An admin approval for a different manifest digest must fail closed.');
    $assert(file_get_contents($appRoot . '/storage/keep.json') === "private-data\n", 'Rejected approvals must not touch storage/.');

    $install = portal_release_install_package($appRoot, $zipPath, $publicKeyPem, 'v1.0.0', '1.0.0', hash('sha256', $manifestJson));
    $assert(($install['ok'] ?? false) === true && ($install['code'] ?? '') === 'installed', 'A matching explicit approval should install the verified release.');
    $assert(($install['changed'] ?? []) === ['assets/new.svg', 'includes/nested/release.php', 'index.php'], 'Installer must report changed files in both root and nested directories.');
    $assert(file_get_contents($appRoot . '/index.php') === "new-index\n", 'The approved changed file should be replaced.');
    $assert(file_get_contents($appRoot . '/includes/nested/release.php') === "new-nested\n", 'A changed nested file should be staged, backed up, and installed.');
    $assert(file_get_contents($appRoot . '/assets/new.svg') === "<svg/>\n", 'The approved new file should be added.');
    $assert(file_get_contents($appRoot . '/tabs/admin.php') === "same-admin\n", 'An identical file should not be rewritten.');
    $assert(file_get_contents($appRoot . '/storage/keep.json') === "private-data\n", 'Installation must leave storage/ untouched.');
    $assert(file_get_contents($appRoot . '/settings.json') === "legacy-settings\n", 'Installation must not replace data outside the code allowlist.');
    $assert(file_get_contents($appRoot . '/.htaccess') === "Options -Indexes\n# release-lock-anchor\n", 'The lock anchor must not be modified.');

    $makeZip($badZipPath, [
        'assets/new.svg' => "<svg/>\n",
        'includes/nested/release.php' => "new-nested\n",
        'index.php' => "tampered-index\n",
        'tabs/admin.php' => "same-admin\n",
    ]);
    $badComparison = portal_release_compare_zip_files($appRoot, $badZipPath, $publicKeyPem);
    $assert(($badComparison['ok'] ?? true) === false && ($badComparison['code'] ?? '') === 'zip_file_hash_mismatch', 'A package file not matching its signed SHA-256 must be rejected; got ' . (string) ($badComparison['code'] ?? 'no-code') . '.');
    $assert(file_get_contents($appRoot . '/index.php') === "new-index\n", 'A tampered package must not modify installed code.');
    $assert(file_get_contents($appRoot . '/storage/keep.json') === "private-data\n", 'A tampered package must leave storage/ untouched.');

    $makeZip($extraZipPath, $validFiles + ['storage/private.json' => "must-not-be-read-or-written\n"]);
    $extraComparison = portal_release_compare_zip_files($appRoot, $extraZipPath, $publicKeyPem);
    $assert(($extraComparison['ok'] ?? true) === false, 'An archive containing storage/ entries must be rejected.');
    $assert(file_get_contents($appRoot . '/storage/keep.json') === "private-data\n", 'A forbidden archive entry must not alter storage/.');

    $rollbackRoot = $base . DIRECTORY_SEPARATOR . 'rollback-app';
    $rollbackTransaction = $base . DIRECTORY_SEPARATOR . 'rollback-transaction';
    foreach ([$rollbackRoot . '/assets', $rollbackRoot . '/includes/nested', $rollbackRoot . '/storage', $rollbackTransaction . '/backup'] as $directory) {
        if (!@mkdir($directory, 0700, true) && !is_dir($directory)) {
            throw new RuntimeException('Could not create isolated rollback fixture directories.');
        }
    }
    $writeFixture($rollbackRoot, 'index.php', "new-index\n");
    $writeFixture($rollbackRoot, 'includes/nested/release.php', "new-nested\n");
    $writeFixture($rollbackRoot, 'assets/new.svg', "<svg/>\n");
    $writeFixture($rollbackRoot, 'storage/keep.json', "private-data\n");
    $writeFixture($rollbackTransaction, 'backup/index.php', "old-index\n");
    $writeFixture($rollbackTransaction, 'backup/includes/nested/release.php', "old-nested\n");
    $oldPermissions = fileperms($rollbackRoot . '/index.php');
    $existingFileState = [
        'path' => 'index.php',
        'target' => $rollbackRoot . '/index.php',
        'existed' => true,
        'mode' => is_int($oldPermissions) ? ($oldPermissions & 0777) : 0644,
        'owner' => is_int(fileowner($rollbackRoot . '/index.php')) ? fileowner($rollbackRoot . '/index.php') : null,
        'group' => is_int(filegroup($rollbackRoot . '/index.php')) ? filegroup($rollbackRoot . '/index.php') : null,
        'before_hash' => hash('sha256', "old-index\n"),
    ];
    $nestedTarget = $rollbackRoot . '/includes/nested/release.php';
    $nestedPermissions = fileperms($nestedTarget);
    $nestedOwner = fileowner($nestedTarget);
    $nestedGroup = filegroup($nestedTarget);
    $nestedFileState = [
        'path' => 'includes/nested/release.php',
        'target' => $nestedTarget,
        'existed' => true,
        'mode' => is_int($nestedPermissions) ? ($nestedPermissions & 0777) : 0644,
        'owner' => is_int($nestedOwner) ? $nestedOwner : null,
        'group' => is_int($nestedGroup) ? $nestedGroup : null,
        'before_hash' => hash('sha256', "old-nested\n"),
    ];
    $newFileState = [
        'path' => 'assets/new.svg',
        'target' => $rollbackRoot . '/assets/new.svg',
        'existed' => false,
        'mode' => 0644,
        'owner' => null,
        'group' => null,
        'before_hash' => null,
    ];
    $rollbackOk = portal_release_rollback_targets([$existingFileState, $nestedFileState, $newFileState], $rollbackTransaction);
    $assert($rollbackOk, 'Rollback should restore modified files in root and nested directories and remove newly added files.');
    $assert(file_get_contents($rollbackRoot . '/index.php') === "old-index\n", 'Rollback should restore the byte-identical previous root file.');
    $assert(file_get_contents($rollbackRoot . '/includes/nested/release.php') === "old-nested\n", 'Rollback should restore a byte-identical nested file from its mirrored backup path.');
    $assert(!file_exists($rollbackRoot . '/assets/new.svg'), 'Rollback should remove a file that did not exist before installation.');
    $assert(file_get_contents($rollbackRoot . '/storage/keep.json') === "private-data\n", 'Rollback should leave storage/ untouched.');
} finally {
    $removeTree($base);
}

fwrite(STDOUT, 'PASS: ' . $checks . ' GitHub release updater checks.' . PHP_EOL);
