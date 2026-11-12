"""Generate human API docs, browser TypeScript bindings and Postman from the contract."""
from pathlib import Path
import argparse
import json
from urllib.parse import urlencode

ROOT=Path(__file__).resolve().parents[1]

def dumps(value): return json.dumps(value,ensure_ascii=False,indent=2)
def resolve(schema, spec):
    while '$ref' in schema:
        schema=spec['components']['schemas'][schema['$ref'].split('/')[-1]]
    return schema
def schema_name(schema):
    if '$ref' in schema: return schema['$ref'].split('/')[-1]
    if 'const' in schema: return json.dumps(schema['const'],ensure_ascii=False)
    if 'enum' in schema: return ' / '.join(str(x) for x in schema['enum'])
    kind=schema.get('type','object')
    if isinstance(kind,list): return ' / '.join(kind)
    return 'array['+schema_name(schema['items'])+']' if kind=='array' else kind
def field_table(schema, spec):
    schema=resolve(schema,spec)
    if schema.get('type')!='object': return '类型：`'+schema_name(schema)+'`。\n'
    lines=['| 字段 | 类型 | 必填 | 约束和含义 |','| --- | --- | --- | --- |']
    for name,s in schema.get('properties',{}).items():
        limits=[]
        for k in ('minimum','maximum','minLength','maxLength','minItems','maxItems','pattern','default','format'):
            if k in s: limits.append(k+'='+str(s[k]))
        desc=s.get('description','见共享模型定义。')
        lines.append('| `'+name+'` | `'+schema_name(s).replace('|',' / ')+'` | '+('是' if name in schema.get('required',[]) else '否')+' | '+('; '.join(limits)+'。' if limits else '')+desc.replace('|',' / ')+' |')
    return '\n'.join(lines)+'\n'

def ts_type(s):
    if '$ref' in s:
        name=s['$ref'].split('/')[-1]
        return 'ApiErrorResponse' if name=='Error' else name
    if 'const' in s:return json.dumps(s['const'],ensure_ascii=False)
    if 'enum' in s:return ' | '.join(json.dumps(x,ensure_ascii=False) for x in s['enum'])
    t=s.get('type','object')
    if isinstance(t,list):return ' | '.join(ts_type({**s,'type':k}) for k in t)
    if t=='null':return 'null'
    if t=='string':return 'Blob' if s.get('format')=='binary' else 'string'
    if t in ('integer','number'):return 'number'
    if t=='boolean':return 'boolean'
    if t=='array':return 'Array<'+ts_type(s['items'])+'>'
    if t=='object':
        props=s.get('properties',{})
        if not props:return 'Record<string, unknown>' if s.get('additionalProperties') else 'Record<string, never>'
        return '{ '+ '; '.join(json.dumps(k)+('' if k in s.get('required',[]) else '?')+': '+ts_type(v) for k,v in props.items())+' }'
    raise ValueError('Unsupported schema type '+str(t))

def artifacts(spec, examples):
    version=spec['info']['version']
    success={c['operation_id']:c for c in examples['cases'] if c['case_id'].endswith('_success')}
    entries=[(p,m,o) for p,methods in spec['paths'].items() for m,o in methods.items()]
    doc=['# 前后端接口开发手册','',f'契约版本 {version}。本文由 contracts/openapi.json 和 contracts/examples.json 自动生成；修改源契约后重新生成，避免手写两份字段。','',
         '这里的HTTP示例为独立合成快照；不是一段连续的真实数据库记录。multipart文件和二进制内容为占位说明，业务应用尚待实现。','',
         '## 公共调用规则','',
         '- 开发后端 http://127.0.0.1:8000，前端 http://127.0.0.1:5173；Vite代理 /api 和 /health。Compose对外默认8080。浏览器SDK默认同源相对地址；Postman的baseUrl按实际环境调整。',
         '- 登录后浏览器自动保存HttpOnly Cookie bill_session。登录和me的JSON提供csrf_token；除登录外的写请求设置X-CSRF-Token。不要在JavaScript读取Set-Cookie，也不要把Cookie当请求JSON字段。',
         '- 普通请求application/json；文件上传使用FormData，浏览器自动生成multipart boundary，不手动设置Content-Type。文件下载读Blob，204不调用response.json()。',
         '- 所有成功和失败响应带X-Contract-Version。金额使用整数分，日期时间带时区，统一枚举，错误读error.code。具体语义见02。',
         '- 缺省查询参数与显式null不同。JSON可空字段在模型中标null，未提供PATCH字段保持旧值；未知请求字段应拒绝。列表空结果为items:[]，报表空月返回全月0值。','',
         '## 接口总表','', '| 编号 | 方法和路径 | SDK函数 | 页面动作 | 任务 |','| --- | --- | --- | --- | --- |']
    for i,(path,method,op) in enumerate(entries,1):
        doc.append(f'| API{i:02d} | `{method.upper()} {path}` | `{op["operationId"]}` | {op["x-page"]}：{op["x-action"]} | {op["x-task"]} |')
    for i,(path,method,op) in enumerate(entries,1):
        name=op['operationId'];case=success[name];req=case['request'];res=case['response']
        doc+=['',f'## API{i:02d} {op["summary"]}','',f'`{method.upper()} {path}`','',op['description'],'',f'前端导出函数：`{name}`。后端负责人H；智能处理由D模块提供，前端负责人F。对应任务：{op["x-task"]}。','',
              ('认证：无需会话。' if op.get('security')==[] else '认证：本人会话Cookie。'+('写请求必须CSRF。' if method!='get' else '')),'']
        params=op.get('parameters',[])
        if params:
            doc+=['### 路径和查询参数','', '| 参数 | 位置 | 类型 | 必填 | 含义 |','| --- | --- | --- | --- | --- |']
            for p in params:
                doc.append(f'| `{p["name"]}` | {p["in"]} | `{schema_name(p["schema"])}` | '+('是' if p.get('required') else '否')+' | '+p.get('description','')+' |')
            doc+=['']
        body_spec=op.get('requestBody',{}).get('content',{})
        if body_spec:
            media=next(iter(body_spec))
            doc+=['### 请求体','',f'媒体类型：`{media}`。', '',field_table(body_spec[media]['schema'],spec)]
        else:doc+=['请求体：无。','']
        url=path
        for k,v in req.get('path',{}).items():url=url.replace('{'+k+'}',str(v))
        if req.get('query'):url+='?'+urlencode(req['query'])
        doc+=['### 请求示例','', '```http',method.upper()+' '+url+' HTTP/1.1','Host: 127.0.0.1:8000']
        if op.get('security')!=[]:doc+=['Cookie: bill_session=<浏览器自动携带的会话>']
        for k,v in req.get('headers',{}).items():doc+=[k+': '+str(v)]
        doc+=['```','']
        if 'body' in req:doc+=['字段值示例（上传接口表示FormData字段，不是JSON上传）：' if 'multipart/form-data' in body_spec else 'JSON请求正文：','', '```json',dumps(req['body']),'```','']
        doc+=['### 成功响应','',f'HTTP状态：`{res["status"]}`。','', '```http']
        for k,v in res['headers'].items():doc+=[k+': '+str(v)]
        doc+=['```','']
        if 'body' in res:
            if res['headers'].get('Content-Type')=='application/json':doc+=['```json',dumps(res['body']),'```','']
            else:doc+=['```text',str(res['body']),'```','以上仅说明文件载荷，不能据此声称文件已生成。','']
        else:doc+=['响应无正文；SDK返回undefined。','']
        if str(res['status'])!='204':
            media=next(iter(op['responses'][str(res['status'])].get('content',{})),None)
            if media:doc+=['响应模型：`'+schema_name(op['responses'][str(res['status'])]['content'][media]['schema'])+'`。逐字段见文末共享模型。','']
        doc+=['### 失败和前端处理','', '| HTTP | 错误代码或含义 | 前端动作 |','| --- | --- | --- |']
        actions={'401':'回登录或展示登录失败，不循环重试。','403':'刷新会话/CSRF或提示拒绝，不自动重放修改。','404':'提示资源不可用，不泄露别的用户资源。','409':'按error.code区分版本、幂等或状态冲突；重新读取后由用户确认。','413':'提示缩小文件，不原样重试。','415':'提示支持的文件类型。','422':'映射details.fields至对应字段，修正后提交。','429':'按Retry-After或details重试等待，限制次数。','503':'保留用户输入并提示稍后手动重试。'}
        for code,r in op['responses'].items():
            if code.startswith('2'):continue
            codes=op.get('x-error-codes',{}).get(code) or list(r.get('content',{}).get('application/json',{}).get('examples',{})) or [r['description']]
            doc.append('| '+code+' | '+', '.join(codes)+' | '+actions.get(code,'展示错误。')+' |')
        errors=[c for c in examples['cases'] if c['operation_id']==name and not c['case_id'].endswith('_success')]
        for e in errors:
            doc+=['',f'错误示例：HTTP {e["response"]["status"]}','', '```json',dumps(e['response']['body']),'```']
    doc+=['','## 共享数据模型','', '下列定义由接口契约生成。表中的必填表示字段必须出现；允许null时仍可能是必填。日期、金额、版本和规则的跨字段限制还须执行02的业务约定。']
    for name,schema in spec['components']['schemas'].items():
        doc+=['', '### '+name,'',schema.get('description',''),'',field_table(schema,spec)]
    doc+=['','## 维护步骤','','1. 先修改OpenAPI和合成请求响应示例，再运行生成器。','2. 两端用生成类型和调用入口，CI验证示例与生成文件没有漂移。','3. 后端实现后还要执行真实HTTP和业务验收；静态契约通过不保证功能已实现。','']

    ts=['// Generated by tools/generate_contract_artifacts.py; DO NOT EDIT.','// Browser API bindings only; no UI or backend implementation.',f'export const CONTRACT_VERSION = "{version}" as const;','']
    for name,schema in spec['components']['schemas'].items():ts.append('export type '+('ApiErrorResponse' if name=='Error' else name)+' = '+ts_type(schema)+';')
    args={};results={};metadata={}
    for path,method,op in entries:
        name=op['operationId'];parts=[];params=op.get('parameters',[])
        for location in ('path','query'):
            ps=[p for p in params if p['in']==location]
            if ps:
                shape=obj_schema={ 'type':'object','properties':{p['name']:p['schema'] for p in ps},'required':[p['name'] for p in ps if p.get('required')]}
                parts.append(location+('' if any(p.get('required') for p in ps) else '?')+': '+ts_type(shape))
        body=op.get('requestBody',{}).get('content',{})
        media=next(iter(body),None)
        if media:parts.append('body: '+ts_type(body[media]['schema']))
        args[name]='{ '+'; '.join(parts)+' }'
        ok=next(k for k in op['responses'] if k.startswith('2'))
        content=op['responses'][ok].get('content',{})
        result_media=next(iter(content),None)
        results[name]=ts_type(content[result_media]['schema']) if result_media else 'undefined'
        metadata[name]={'path':path,'method':method.upper(),'media':media,'status':int(ok),'binary':result_media not in (None,'application/json'),'csrf':method!='get' and op.get('security')!=[]}
    ts+=['','export type OperationArgs = {']+[json.dumps(k)+': '+v+';' for k,v in args.items()]+['};','export type OperationResults = {']+[json.dumps(k)+': '+v+';' for k,v in results.items()]+['};','type OperationId = keyof OperationArgs;','const OPERATIONS = '+json.dumps(metadata,ensure_ascii=False,indent=2)+' as const;']
    ts+=['''
let baseUrl = "";
export function setApiBaseUrl(value: string): void { baseUrl = value.replace(/\\/$/, ""); }
export class ApiError extends globalThis.Error {
  constructor(public status: number, public payload: ApiErrorResponse) { super(payload.error.message); }
}
type RuntimeArgs = { path?: Record<string,string>; query?: Record<string,unknown>; body?: unknown };
export async function callApi<K extends OperationId>(operation: K, args: OperationArgs[K], csrfToken?: string): Promise<OperationResults[K]> {
  const meta = OPERATIONS[operation];
  const runtime = args as RuntimeArgs;
  let path: string = meta.path;
  for (const [key, value] of Object.entries(runtime.path ?? {})) path = path.replace("{" + key + "}", encodeURIComponent(value));
  if (/\\{[^}]+\\}/.test(path)) throw new globalThis.Error("Missing path parameter");
  const query = new URLSearchParams();
  for (const [key,value] of Object.entries(runtime.query ?? {})) if (value !== undefined && value !== null) query.set(key,String(value));
  const headers: Record<string,string> = {};
  if (meta.csrf) { if (!csrfToken) throw new globalThis.Error("CSRF token required"); headers["X-CSRF-Token"] = csrfToken; }
  let body: BodyInit | undefined;
  if (meta.media === "multipart/form-data") {
    const form = new FormData();
    for (const [key,value] of Object.entries(runtime.body as Record<string,unknown>)) {
      if (value instanceof Blob) form.append(key,value); else form.append(key,String(value));
    }
    body = form;
  } else if (meta.media === "application/json") { headers["Content-Type"]="application/json"; body=JSON.stringify(runtime.body); }
  const url=baseUrl+path+(query.size ? "?"+query.toString() : "");
  const response=await fetch(url,{method:meta.method,headers,body,credentials:"include"});
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as ApiErrorResponse | null;
    throw new ApiError(response.status,payload?.error ? payload : {error:{code:"INVALID_ERROR_RESPONSE",message:"服务器返回了非约定错误",details:{}}});
  }
  if (response.status !== meta.status) throw new ApiError(response.status,{error:{code:"UNEXPECTED_STATUS",message:"成功状态码与契约不符",details:{}}});
  if (response.status===204) return undefined as OperationResults[K];
  if (meta.binary) return await response.blob() as OperationResults[K];
  return await response.json() as OperationResults[K];
}
''']
    for name in args:
        ts.append(f'export function {name}(args: OperationArgs["{name}"], csrfToken?: string): Promise<OperationResults["{name}"]> {{ return callApi("{name}", args, csrfToken); }}')

    collection={'info':{'name':'multi-bill-ledger '+version+' 契约请求示例','schema':'https://schema.getpostman.com/json/collection/v2.1.0/collection.json','description':'独立合成请求模板，不能一键执行所有示例。先登录，上传时选择本机文件，按实际草稿替换确认行和版本。失败批次重试单独运行；不含真实凭据。'},'variable':[{'key':k,'value':v} for k,v in {'baseUrl':'http://127.0.0.1:8000','username':'demo_a','password':'','csrfToken':'','batchId':'','transactionId':'','ruleId':''}.items()],'item':[]}
    for path,method,op in entries:
        name=op['operationId'];case=success[name];req=case['request'];url=path
        if '{id}' in url:url=url.replace('{id}', '{{'+('batchId' if '/imports/' in url else 'ruleId' if '/classification-rules/' in url else 'transactionId')+'}}')
        if req.get('query'):url+='?'+urlencode(req['query'])
        request={'method':method.upper(),'header':[],'url':'{{baseUrl}}'+url,'description':op['description']+'\n请求中的版本、row_id和字段必须按实际返回核对。'}
        for k,v in req.get('headers',{}).items():
            if k=='Content-Type' and v=='multipart/form-data':continue
            request['header'].append({'key':k,'value':'{{csrfToken}}' if k=='X-CSRF-Token' else v})
        if 'body' in req:
            body=req['body']
            if name=='login':body={'username':'{{username}}','password':'{{password}}'}
            if name=='createImport':request['body']={'mode':'formdata','formdata':[{'key':'source','value':'wechat','type':'text'},{'key':'ingestion_method','value':'file','type':'text'},{'key':'file','type':'file','src':[]}]}
            else:request['body']={'mode':'raw','raw':dumps(body),'options':{'raw':{'language':'json'}}}
        scripts=[f'pm.test("成功HTTP状态", () => pm.response.to.have.status({case["response"]["status"]}));']
        if name in ('login','getSession'):scripts+=['if (pm.response.code === 200) pm.collectionVariables.set("csrfToken", pm.response.json().csrf_token);']
        if name=='createImport':scripts+=['if (pm.response.code === 202) pm.collectionVariables.set("batchId", pm.response.json().id);']
        if name=='confirmImport':scripts+=['if (pm.response.code === 200) pm.collectionVariables.set("transactionId", pm.response.json().transaction_ids[0] ?? "");']
        if name=='listRules':scripts+=['if (pm.response.code === 200) pm.collectionVariables.set("ruleId", pm.response.json().items[0]?.id ?? "");']
        collection['item'].append({'name':method.upper()+' '+path+' ['+name+']','request':request,'event':[{'listen':'test','script':{'type':'text/javascript','exec':scripts}}]})
    generated={'docs/11_api_reference.md':'\n'.join(doc)+'\n','contracts/client.generated.ts':'\n'.join(ts)+'\n','contracts/postman_collection.json':dumps(collection)+'\n'}
    if (ROOT/'web/src/api').is_dir():
        generated['web/src/api/client.generated.ts']=generated['contracts/client.generated.ts']
    return generated

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    spec=json.loads((ROOT/'contracts/openapi.json').read_text(encoding='utf-8'))
    examples=json.loads((ROOT/'contracts/examples.json').read_text(encoding='utf-8'))
    for name,content in artifacts(spec,examples).items():
        path=ROOT/name
        if args.check:
            if not path.exists() or path.read_text(encoding='utf-8')!=content:raise SystemExit('Generated artifact drift: '+name)
        else:path.write_text(content,encoding='utf-8')
    print('Generated artifacts match contract.' if args.check else 'Generated API manual, browser TypeScript bindings and Postman requests.')

if __name__=='__main__':main()
