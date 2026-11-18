<?php
declare(strict_types=1);

require_once __DIR__ . '/../../includes/release_updater.php';

function h(mixed $value): string
{
    return htmlspecialchars((string) $value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function csrf_field(): string
{
    return '<input type="hidden" name="csrf_token" value="test-token">';
}

function portal_central_admin_auth_setup_state(): string
{
    return 'unconfigured';
}

function portal_email_transport_status(): array
{
    return [
        'transport' => 'smtp',
        'configured' => true,
        'tested' => true,
        'host' => 'smtp-secret.example.test',
        'username' => 'private-user@example.test',
        'from_email' => 'private-sender@example.test',
        'password' => 'must-not-be-rendered',
    ];
}

function portal_email_status_read(): ?array
{
    return [
        'invoice' => ['events' => [['at' => '2026-10-06T12:00:00+02:00', 'kind' => 'test', 'result' => 'accepted', 'transport' => 'smtp', 'code' => 'accepted']]],
        'skadeblankett' => ['events' => []],
    ];
}

function render_admin_panel_for_test(string $setupState, ?array $centralUser, ?array $invoiceUser, string $invoiceSetupState, ?array $releaseResult = null): string
{
    $centralAdminSetupState = $setupState;
    $centralAdminUser = $centralUser;
    $invoiceAuthUser = $invoiceUser;
    $portalReleaseResult = $releaseResult;
    $csrfReady = true;
    ob_start();
    include __DIR__ . '/../../tabs/admin.php';
    return (string) ob_get_clean();
}

$checks = 0;
$assert = static function (bool $condition, string $message) use (&$checks): void {
    $checks++;
    if (!$condition) {
        throw new RuntimeException($message);
    }
};

$invoiceAdmin = [
    'id' => 'existing-invoice-admin',
    'username' => 'existing-admin',
    'name' => 'Existing admin',
    'role' => 'admin',
    'active' => true,
];
$invoiceStaff = [
    'id' => 'existing-invoice-staff',
    'username' => 'existing-staff',
    'name' => 'Existing staff',
    'role' => 'staff',
    'active' => true,
];

$firstSetup = render_admin_panel_for_test('unconfigured', null, $invoiceAdmin, 'configured');
$assert(str_contains($firstSetup, 'central_admin_enroll') && str_contains($firstSetup, 'Välj central admin-PIN'), 'Only the existing invoice admin should see the first central-PIN setup form.');

$staffSetup = render_admin_panel_for_test('unconfigured', null, $invoiceStaff, 'configured');
    $assert(!str_contains($staffSetup, 'central_admin_enroll') && str_contains($staffSetup, 'faktura-adminkonto'), 'Invoice staff must be guided to the existing admin and must not receive the setup form.');

$firstInvoiceAccount = render_admin_panel_for_test('unconfigured', null, null, 'unconfigured');
$assert(str_contains($firstInvoiceAccount, '?tab=invoice') && !str_contains($firstInvoiceAccount, 'central_admin_enroll'), 'First invoice-admin setup must precede central-PIN enrollment when no account exists.');

$login = render_admin_panel_for_test('configured', null, null, 'configured');
$assert(str_contains($login, 'central_admin_login') && str_contains($login, 'SFTP-återställning'), 'Configured central auth should show the central login and SFTP recovery instructions.');
$assert(str_contains($login, 'Central admin-PIN-kod') && str_contains($login, 'autocomplete="off"') && !str_contains($login, 'current-password'), 'The central login should be presented as a PIN-only field, not a browser password-manager field.');
$assert(str_contains($login, 'äldre PIN-kod') && str_contains($login, '6–10 siffror'), 'The login screen should explain the new PIN rule and one-time legacy migration.');
$assert(!str_contains($login, 'Driftshälsa'), 'The health check must not render before central-admin authentication.');
$assert(!str_contains($login, 'GitHub-releasekontroll') && !str_contains($login, 'portal_release_check'), 'Release status and actions must remain hidden before central-admin authentication.');

$activeUser = [
    'id' => 'central-admin',
    'username' => 'central-admin',
    'name' => 'Central administratör',
    'role' => 'admin',
    'active' => true,
    'auth_source' => 'central_admin',
    'must_change_pin' => false,
    'pin_changed_at' => time(),
];
$active = render_admin_panel_for_test('configured', $activeUser, null, 'configured');
$assert(str_contains($active, 'central_admin_change_pin') && str_contains($active, 'Global sökning') && str_contains($active, 'Kundregister'), 'An active central admin should see all staff-page links and the PIN-change control.');
$assert(str_contains($active, 'Driftshälsa') && str_contains($active, 'PDF-arkivets rot') && str_contains($active, 'E-postkonfiguration') && str_contains($active, 'Senaste e-posttest'), 'An authenticated central admin should see the PDF, storage, and email health checks.');
$assert(!str_contains($active, 'smtp-secret.example.test') && !str_contains($active, 'private-user@example.test') && !str_contains($active, 'private-sender@example.test') && !str_contains($active, 'must-not-be-rendered'), 'The health check must not render SMTP host, account, sender, or password values.');
$assert(!str_contains($active, dirname(__DIR__, 2)), 'The health check must not render absolute server filesystem paths.');
$assert(!str_contains($active, 'central_admin_login"'), 'An authenticated central admin should not be shown the login form.');
$assert(str_contains($active, '6–10 siffror') && str_contains($active, 'högst 2 valfria specialtecken') && str_contains($active, 'minlength="6" maxlength="12"'), 'PIN enrollment and rotation should explain and constrain the numeric PIN format.');
$assert(!str_contains($active, 'new-password') && !str_contains($active, 'current-password') && !str_contains($active, 'inga lösenord'), 'The central PIN interface must not be described or autofilled as a password.');
$assert(str_contains($active, 'GitHub-releasekontroll') && str_contains($active, 'Avstängd'), 'Only the authenticated Adminpanel should show the dormant GitHub release status.');
$assert(str_contains($active, 'includes/release_config.php') && str_contains($active, 'ingen GitHub-begäran'), 'The Adminpanel should explain that blank configuration performs no GitHub check.');
$assert(str_contains($active, 'Så fungerar releaseuppdateringen') && str_contains($active, 'Kontrollera') && str_contains($active, 'Granska') && str_contains($active, 'Godkänn och installera'), 'The release workflow should clearly show its three separate steps.');
$assert(!str_contains($active, 'name="action" value="portal_release_check"') && !str_contains($active, 'portal_release_install'), 'Unconfigured release checks and installation must not be offered.');
$review = render_admin_panel_for_test('configured', $activeUser, null, 'configured', [
    'ok' => true,
    'code' => 'release_checked',
    'action' => 'check',
    'tag' => 'v2.0.0',
    'version' => '2.0.0',
    'manifest_sha256' => str_repeat('a', 64),
    'changed' => ['includes/nested/release.php'],
    'unchanged' => [],
]);
$assert(str_contains($review, '1 fil avviker') && str_contains($review, 'includes/nested/release.php'), 'A release review should show a clear singular file count and its exact path.');
$assert(str_contains($review, 'Visa manifestets godkännandedigest') && str_contains($review, str_repeat('a', 64)), 'A release review should expose the exact approval digest on demand.');
$assert(!str_contains($review, 'name="action" value="portal_release_install"'), 'A release review must not offer installation while trust configuration is incomplete.');
$disabledCheck = render_admin_panel_for_test('configured', $activeUser, null, 'configured', ['ok' => false, 'code' => 'configuration_incomplete', 'action' => 'check']);
$assert(str_contains($disabledCheck, 'GitHub-repo') && !str_contains($disabledCheck, 'name="action" value="portal_release_install"'), 'An incomplete release configuration must show only a disabled explanation, not an install form.');

$controllerSource = file_get_contents(__DIR__ . '/../../index.php');
$csrfPosition = is_string($controllerSource) ? strpos($controllerSource, 'if (!csrf_is_valid())') : false;
$releaseActionPosition = is_string($controllerSource) ? strpos($controllerSource, "if (in_array(\$action, ['portal_release_check', 'portal_release_install'], true))") : false;
$releaseBranchEnd = is_string($controllerSource) && is_int($releaseActionPosition)
    ? strpos($controllerSource, "} elseif (\$action === 'portal_search')", $releaseActionPosition)
    : false;
$assert(is_string($controllerSource) && is_int($csrfPosition) && is_int($releaseActionPosition) && $csrfPosition < $releaseActionPosition, 'Release POST handlers must run only after the shared CSRF check.');
$releaseBranch = is_string($controllerSource) && is_int($releaseActionPosition) && is_int($releaseBranchEnd)
    ? substr($controllerSource, $releaseActionPosition, $releaseBranchEnd - $releaseActionPosition)
    : '';
$assert(str_contains($releaseBranch, "\$activeTab !== 'admin' || \$portalIsScopedPwa"), 'Release endpoints must be confined to the full Adminpanel route, not scoped PWAs.');
$assert(str_contains($releaseBranch, '!$centralAdminCanAccess') && str_contains($releaseBranch, 'is_array($centralAdminUser)'), 'Release endpoints must require an authenticated central admin.');
$assert(str_contains($releaseBranch, "\$_POST['confirm_install']") && str_contains($releaseBranch, 'portal_release_install_approved'), 'Installation must require server-verified explicit admin approval.');
$assert(str_contains($controllerSource, "str_starts_with(\$msgKey, 'release_') && (\$activeTab !== 'admin' || !\$centralAdminCanAccess)"), 'Release notices must be hidden outside the authenticated Adminpanel.');

$expiredUser = $activeUser;
$expiredUser['must_change_pin'] = true;
$expiredUser['pin_policy_update_required'] = false;
$expired = render_admin_panel_for_test('configured', $expiredUser, null, 'configured');
$assert(str_contains($expired, 'PIN-byte krävs') && str_contains($expired, 'central_admin_change_pin') && str_contains($expired, 'Det har gått 20 dagar'), 'An overdue central PIN should explain the age-based rotation requirement.');
$assert(!str_contains($expired, 'Driftshälsa'), 'The health check must remain hidden until an overdue admin PIN has been changed.');
$legacyPolicyUser = $expiredUser;
$legacyPolicyUser['pin_policy_update_required'] = true;
$policyUpdate = render_admin_panel_for_test('configured', $legacyPolicyUser, null, 'configured');
$assert(str_contains($policyUpdate, 'PIN-kod följer ett äldre format') && str_contains($policyUpdate, '6–10 siffror'), 'Legacy PIN users should be told why rotation is required and shown the new format.');

fwrite(STDOUT, 'PASS: ' . $checks . ' Adminpanel render checks.' . PHP_EOL);
