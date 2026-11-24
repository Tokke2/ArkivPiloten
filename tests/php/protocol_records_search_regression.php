<?php
declare(strict_types=1);

function h(mixed $value): string
{
    if (!is_scalar($value) && $value !== null) {
        $value = '';
    }
    return htmlspecialchars((string) $value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function app_legacy_text(mixed $value): string
{
    return is_scalar($value) || $value === null
        ? html_entity_decode((string) $value, ENT_QUOTES | ENT_HTML5, 'UTF-8')
        : '';
}

function csrf_field(): string
{
    return '<input type="hidden" name="csrf_token" value="test-token">';
}

function portal_valid_iso_date(string $value): bool
{
    return preg_match('/\A(\d{4})-(\d{2})-(\d{2})\z/', $value, $parts) === 1
        && checkdate((int) $parts[2], (int) $parts[3], (int) $parts[1]);
}

function render_protocol_records_for_test(array $records, array $query): string
{
    $_GET = $query;
    $savedProtocols = $records;
    $protocolAuthUser = ['name' => 'Testtekniker', 'username' => 'test', 'role' => 'staff'];
    ob_start();
    include __DIR__ . '/../../tabs/protocol_records.php';
    return (string) ob_get_clean();
}

$checks = 0;
$assert = static function (bool $condition, string $message) use (&$checks): void {
    $checks++;
    if (!$condition) {
        throw new RuntimeException($message);
    }
};

$records = [
    [
        'id' => str_repeat('a', 32),
        'nummer' => 'SP-001',
        'reg' => 'ABC 123',
        'date' => '2026-02-14',
        'updated_at' => '2026-02-14T12:00:00+01:00',
        'customer' => '<script>alert(1)</script>',
    ],
    [
        'id' => str_repeat('b', 32),
        'nummer' => 'SP-002',
        'reg' => 'XYZ-987',
        'date' => '2026-03-02',
        'updated_at' => '2026-03-02T09:00:00+01:00',
        'customer' => 'Beta Bil',
    ],
    [
        'id' => str_repeat('c', 32),
        'nummer' => 'SP-003',
        'reg' => '',
        'regnr' => 'DEF 456',
        'date' => '2026-01-30',
        'updated_at' => '2026-01-30T08:00:00+01:00',
        'customer' => 'Gamma AB',
    ],
    [
        'id' => 'not-a-safe-id',
        'nummer' => 'SP-004',
        'reg' => 'ABC-999',
        'date' => '2026-02-20',
        'updated_at' => '2026-02-20T08:00:00+01:00',
        'customer' => 'Delta AB',
    ],
];

$all = render_protocol_records_for_test($records, ['protocol_view' => 'records']);
$assert(str_contains($all, 'Visar 4 av 4 protokoll.'), 'The unfiltered records view should show every saved protocol.');
$assert(strpos($all, 'SP-002') < strpos($all, 'SP-004') && strpos($all, 'SP-004') < strpos($all, 'SP-001'), 'Filtered results should remain ordered by service date, newest first.');
$assert(str_contains($all, 'action="?tab=protocol"') && !str_contains($all, 'name="tab"'), 'The search form should submit a single tab parameter without duplicate query keys.');
$assert(str_contains($all, 'mellanslag/bindestreck påverkar inte sökningen'), 'The form should explain that registration formatting is ignored.');

$partialReg = render_protocol_records_for_test($records, ['protocol_reg' => 'bC-12']);
$assert(str_contains($partialReg, 'Visar 1 av 4 protokoll.'), 'A partial case-insensitive registration query should match one protocol.');
$assert(str_contains($partialReg, 'SP-001') && !str_contains($partialReg, 'SP-002'), 'A registration query should exclude nonmatching records.');
$assert(str_contains($partialReg, '&lt;script&gt;alert(1)&lt;/script&gt;') && !str_contains($partialReg, '<script>alert(1)</script>'), 'Customer text returned by search must remain HTML-escaped.');

$legacyReg = render_protocol_records_for_test($records, ['protocol_reg' => 'def-4']);
$assert(str_contains($legacyReg, 'Visar 1 av 4 protokoll.') && str_contains($legacyReg, 'SP-003'), 'Search should fall back to the legacy regnr field when reg is blank.');

$dateFiltered = render_protocol_records_for_test($records, [
    'protocol_reg' => 'ABC',
    'protocol_from' => '2026-02-01',
    'protocol_to' => '2026-02-28',
]);
$assert(str_contains($dateFiltered, 'Visar 2 av 4 protokoll.') && str_contains($dateFiltered, 'SP-001') && str_contains($dateFiltered, 'SP-004'), 'Registration and date filters should combine with AND semantics.');

$malformedStoredDateRecords = $records;
$malformedStoredDateRecords[] = [
    'id' => str_repeat('d', 32),
    'nummer' => 'SP-005',
    'reg' => 'ABC-555',
    'date' => '2026-02-31',
    'updated_at' => '2026-02-31T08:00:00+01:00',
    'customer' => 'Epsilon AB',
];
$validDateRange = render_protocol_records_for_test($malformedStoredDateRecords, ['protocol_from' => '2026-02-01']);
$assert(str_contains($validDateRange, 'Visar 3 av 5 protokoll.') && !str_contains($validDateRange, 'SP-005'), 'Date filters must exclude stored records with impossible calendar dates.');

$boundaryRecords = [
    ['id' => str_repeat('e', 32), 'nummer' => 'SP-006', 'reg' => 'EDGE-001', 'date' => '2026-02-01', 'updated_at' => '2026-02-01T08:00:00+01:00', 'customer' => 'Edge One'],
    ['id' => str_repeat('f', 32), 'nummer' => 'SP-007', 'reg' => 'EDGE-002', 'date' => '2026-02-28', 'updated_at' => '2026-02-28T08:00:00+01:00', 'customer' => 'Edge Two'],
];
$inclusiveDateBoundaries = render_protocol_records_for_test($boundaryRecords, [
    'protocol_from' => '2026-02-01',
    'protocol_to' => '2026-02-28',
]);
$assert(str_contains($inclusiveDateBoundaries, 'Visar 2 av 2 protokoll.') && str_contains($inclusiveDateBoundaries, 'SP-006') && str_contains($inclusiveDateBoundaries, 'SP-007'), 'Date range endpoints must be inclusive.');

$punctuationOnly = render_protocol_records_for_test($records, ['protocol_reg' => '---']);
$assert(str_contains($punctuationOnly, 'Ange minst en bokstav eller siffra') && str_contains($punctuationOnly, 'Sökningen kunde inte köras.') && !str_contains($punctuationOnly, 'SP-001'), 'A punctuation-only query must report an error instead of silently showing every record.');

$invalidCharacters = render_protocol_records_for_test($records, ['protocol_reg' => 'ABC/123']);
$assert(str_contains($invalidCharacters, 'Registreringsnumret får innehålla') && !str_contains($invalidCharacters, 'SP-001'), 'Unsupported search characters should fail safely and preserve the no-results state.');

$xssSearch = render_protocol_records_for_test($records, ['protocol_reg' => '"<script>alert(1)</script>']);
$assert(str_contains($xssSearch, '&quot;&lt;script&gt;alert(1)&lt;/script&gt;') && !str_contains($xssSearch, '"<script>alert(1)</script>'), 'Untrusted search text must remain HTML-escaped in the search field.');

$overlongRegistration = render_protocol_records_for_test($records, ['protocol_reg' => str_repeat('A', 41)]);
$assert(str_contains($overlongRegistration, 'högst 40 tecken') && !str_contains($overlongRegistration, 'SP-001'), 'An overlong registration search should fail closed.');

$nonStringRegistration = render_protocol_records_for_test($records, ['protocol_reg' => ['ABC']]);
$assert(str_contains($nonStringRegistration, 'Registreringssökningen är ogiltig') && str_contains($nonStringRegistration, 'Sökningen kunde inte köras.') && !str_contains($nonStringRegistration, 'SP-001'), 'An array-valued registration query must fail closed without a type error or warning.');

$nullRegistration = render_protocol_records_for_test($records, ['protocol_reg' => null]);
$assert(str_contains($nullRegistration, 'Registreringssökningen är ogiltig') && !str_contains($nullRegistration, 'SP-001'), 'A present but null registration parameter must not silently become an unfiltered search.');

$invalidDate = render_protocol_records_for_test($records, ['protocol_from' => '2026-02-31']);
$assert(str_contains($invalidDate, 'Från-datumet är ogiltigt') && str_contains($invalidDate, 'Sökningen kunde inte köras.') && !str_contains($invalidDate, 'SP-001'), 'An invalid date must not be silently ignored.');

$nonStringDate = render_protocol_records_for_test($records, ['protocol_from' => ['2026-02-01']]);
$assert(str_contains($nonStringDate, 'Från-datumet är ogiltigt') && !str_contains($nonStringDate, 'SP-001'), 'An array-valued date query must fail closed.');

$overlongDate = render_protocol_records_for_test($records, ['protocol_to' => str_repeat('2', 11)]);
$assert(str_contains($overlongDate, 'Till-datumet är ogiltigt') && !str_contains($overlongDate, 'SP-001'), 'An overlong date search should fail closed.');

$reversedRange = render_protocol_records_for_test($records, [
    'protocol_from' => '2026-03-01',
    'protocol_to' => '2026-02-01',
]);
$assert(str_contains($reversedRange, 'Från-datum måste vara samma som eller tidigare än till-datum') && !str_contains($reversedRange, 'SP-001'), 'A reversed date range must not return unfiltered records.');

$noMatch = render_protocol_records_for_test($records, ['protocol_reg' => 'NO-SUCH-REG']);
$assert(str_contains($noMatch, 'Visar 0 av 4 protokoll.') && str_contains($noMatch, 'Inga protokoll matchar sökningen.'), 'A valid query with no matches should have a clear empty state.');

fwrite(STDOUT, 'PASS: ' . $checks . ' saved service-protocol registration search checks.' . PHP_EOL);
