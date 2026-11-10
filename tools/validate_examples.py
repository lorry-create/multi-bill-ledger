"""Validate OpenAPI and synthetic request/response snapshots, not a running application."""
from pathlib import Path
import argparse
import copy
import json

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from openapi_spec_validator import validate_spec

ROOT=Path(__file__).resolve().parents[1]

def validator(schema,spec):
    return Draft202012Validator({**schema,'components':spec['components']},format_checker=FormatChecker())

def validate_case(case,spec):
    operation=spec['paths'][case['path_template']][case['method'].lower()]
    if operation['operationId']!=case['operation_id']:raise ValueError('Operation mismatch')
    request=case['request']
    for location in ('path','query'):
        parameters=[p for p in operation.get('parameters',[]) if p['in']==location]
        schema={'type':'object','properties':{p['name']:p['schema'] for p in parameters},'required':[p['name'] for p in parameters if p.get('required')],'additionalProperties':False}
        validator(schema,spec).validate(request.get(location,{}))
    request_content=operation.get('requestBody',{}).get('content',{})
    if request_content:
        media=next(iter(request_content))
        check=validator(request_content[media]['schema'],spec)
        if case.get('request_valid',True):check.validate(request['body'])
        else:
            try:check.validate(request['body'])
            except ValidationError:pass
            else:raise ValueError('Negative request is unexpectedly valid: '+case['case_id'])
    elif 'body' in request:raise ValueError('Unexpected request body')
    response=case['response'];status=str(response['status'])
    declared=operation['responses'][status]
    if response['headers'].get('X-Contract-Version')!=spec['info']['version']:raise ValueError('Response version header mismatch')
    for name,definition in declared.get('headers',{}).items():
        if name not in response['headers']:raise ValueError('Missing documented response header: '+name)
        validator(definition['schema'],spec).validate(response['headers'][name])
    content=declared.get('content',{})
    if content:
        media=next(iter(content))
        if response['headers'].get('Content-Type')!=media:raise ValueError('Media mismatch')
        validator(content[media]['schema'],spec).validate(response['body'])
    elif 'body' in response:raise ValueError('Body supplied for no-content response')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--self-test',action='store_true');args=parser.parse_args()
    spec=json.loads((ROOT/'contracts/openapi.json').read_text(encoding='utf-8'))
    cases=json.loads((ROOT/'contracts/examples.json').read_text(encoding='utf-8'))
    validate_spec(spec)
    if cases['contract_version']!=spec['info']['version'] or cases['synthetic'] is not True:raise ValueError('Example metadata mismatch')
    expected={o['operationId'] for methods in spec['paths'].values() for o in methods.values()}
    actual={c['operation_id'] for c in cases['cases'] if c['case_id'].endswith('_success')}
    if expected!=actual:raise ValueError('Every operation must have a success example')
    ids=[c['case_id'] for c in cases['cases']]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate example case ID')
    for case in cases['cases']:validate_case(case,spec)
    if args.self_test:
        broken=copy.deepcopy(next(c for c in cases['cases'] if c['case_id']=='listTransactions_success'))
        broken['response']['body']['items'][0]['amount_fen']='23.00'
        try:validate_case(broken,spec)
        except ValidationError:pass
        else:raise ValueError('Validator did not reject money type drift')
        broken=copy.deepcopy(next(c for c in cases['cases'] if c['case_id']=='login_success'))
        del broken['response']['body']['csrf_token']
        try:validate_case(broken,spec)
        except ValidationError:pass
        else:raise ValueError('Validator did not reject missing response field')
        print('Negative tests passed: wrong money type and missing CSRF response field rejected.')
    print(f'PASS: OpenAPI standard validation and {len(cases["cases"])} request/response snapshots across {len(expected)} operations.')
    print('NOT TESTED: live HTTP, authentication security, database transactions, OCR/model quality, browser or deployment.')

if __name__=='__main__':main()
