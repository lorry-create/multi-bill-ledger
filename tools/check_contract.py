"""Basic document/contract checks only; this is not an application test suite."""
from pathlib import Path
import argparse
import copy
import json
import re


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_api(doc):
    require(doc.get('openapi') == '3.1.0', 'Unexpected OpenAPI version')
    require(re.fullmatch(r'\d+\.\d+\.\d+', doc['info']['version']) is not None, 'Expected semantic contract version')
    ids = []
    def walk(value):
        if isinstance(value, dict):
            if '$ref' in value:
                pointer = value['$ref']
                require(pointer.startswith('#/'), f'Only local refs supported: {pointer}')
                target = doc
                for part in pointer[2:].split('/'):
                    target = target[part.replace('~1', '/').replace('~0', '~')]
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(doc)
    for path, methods in doc['paths'].items():
        for method, operation in methods.items():
            require(method in {'get', 'post', 'put', 'patch', 'delete'}, f'Unexpected method {method}')
            ids.append(operation['operationId'])
            declared = {p['name'] for p in operation.get('parameters', []) if p['in'] == 'path' and p.get('required')}
            require(set(re.findall(r'\{([^}]+)\}', path)) == declared, f'Missing required path params: {path}')
            require(any(code.startswith('2') for code in operation['responses']), f'No success response: {path}')
    require(len(ids) == len(set(ids)), 'Duplicate operationId')
    for key in ('/api/imports/{id}/confirm', '/api/imports/{id}/original', '/api/imports/{id}/retry', '/api/exports/monthly.pdf'):
        require(key in doc['paths'], f'Missing critical route {key}')


def check_fixture(fixture, doc):
    require(fixture.get('synthetic') is True, 'Fixture must be explicitly synthetic')
    require(fixture['contract_version'] == doc['info']['version'], 'Fixture version mismatch')
    categories = doc['components']['schemas']['Category']['enum']
    rows = fixture['transactions']
    for row in rows:
        require(type(row['amount_fen']) is int and row['amount_fen'] > 0, 'Money must be positive integer fen')
        require(row['category'] in categories, 'Unknown category')
        require(row['flow_type'] in doc['components']['schemas']['FlowType']['enum'], 'Unknown flow')
        require(row['source'] in doc['components']['schemas']['Source']['enum'], 'Unknown source')
        require(row['occurred_at'].startswith(fixture['month']), 'Wrong fixture month')
    income = sum(r['amount_fen'] for r in rows if r['flow_type'] == 'income')
    expense = sum(r['amount_fen'] for r in rows if r['flow_type'] == 'expense')
    refund = sum(r['amount_fen'] for r in rows if r['flow_type'] == 'refund')
    totals = dict(income_fen=income, gross_expense_fen=expense, refund_fen=refund, net_expense_fen=expense-refund, balance_fen=income-expense+refund)
    require(totals == fixture['expected']['totals'], 'Synthetic expected totals do not reconcile')
    gross = {}
    for row in rows:
        if row['flow_type'] == 'expense':
            gross[row['category']] = gross.get(row['category'], 0) + row['amount_fen']
    require(gross == fixture['expected']['expense_by_category'], 'Synthetic category totals mismatch')
    budgets = []
    for budget in fixture['budgets']:
        category = budget['category']
        spent = sum(r['amount_fen'] * (1 if r['flow_type'] == 'expense' else -1 if r['flow_type'] == 'refund' else 0) for r in rows if r['category'] == category)
        amount = budget['amount_fen']
        budgets.append(dict(category=category, budget_fen=amount, spent_fen=spent, remaining_fen=amount-spent, over_fen=max(0, spent-amount)))
    require(budgets == fixture['expected']['budgets'], 'Synthetic budget expectations mismatch')
    case = fixture['feedback_case']
    require(case['new_transaction']['source_transaction_id'] not in {r['source_transaction_id'] for r in rows}, 'Feedback must use a new transaction')
    require(case['correction_category'] == case['expected_new_category'], 'Feedback example mismatch')


def check_links(root):
    for path in root.rglob('*.md'):
        if any(part in {'node_modules', 'dist', '.git', '.venv', 'venv'} for part in path.relative_to(root).parts):
            continue
        for link in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
            if re.match(r'^(https?://|#|[A-Za-z]:)', link):
                continue
            target = link.split('#')[0]
            if target:
                require((path.parent / target).exists(), f'Broken document link in {path}: {target}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    doc = json.loads((root / 'contracts/openapi.json').read_text(encoding='utf-8'))
    fixture = json.loads((root / 'fixtures/synthetic_ledger.json').read_text(encoding='utf-8'))
    check_api(doc)
    check_fixture(fixture, doc)
    check_links(root)
    if args.self_test:
        invalid = copy.deepcopy(fixture)
        invalid['expected']['totals']['net_expense_fen'] += 1
        try:
            check_fixture(invalid, doc)
        except ValueError:
            pass
        else:
            raise ValueError('Checker failed to reject a wrong expected amount')
        invalid_api = copy.deepcopy(doc)
        invalid_api['components']['schemas']['Broken'] = {'$ref': '#/components/schemas/DOES_NOT_EXIST'}
        try:
            check_api(invalid_api)
        except KeyError:
            pass
        else:
            raise ValueError('Checker failed to reject a broken reference')
        print('Negative checks: invalid money expectation and broken reference rejected.')
    print('PASS: basic document links, local API references, operation IDs and synthetic expectations.')
    print('NOT TESTED: application behavior, live providers, full OpenAPI conformance, GitHub CI or deployment.')


if __name__ == '__main__':
    main()
