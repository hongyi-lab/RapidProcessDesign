"""Local BWB review API. One evaluator backs analysis, search and trace inspection."""
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
import json
import sys

from engine import analyze, geometry, model_metadata
from configuration import DEFAULTS, BOUNDS, ModelConfig, SolverConfig, config_schema
from model_adapter import model_catalog, predict_mit, MIT_EXAMPLE, MIT_INPUT_SCHEMA
from optimization import optimize, OPTIMIZATION_DEFAULTS
from uq_evaluate import evaluate as evaluate_uq

ANALYSES=OrderedDict()
LOCK=Lock()


def remember(result):
    with LOCK:
        ANALYSES[result['analysis_id']]=result
        while len(ANALYSES)>250:
            ANALYSES.popitem(last=False)
    return result


def unpack(data):
    if not isinstance(data,dict):
        raise ValueError('Request must be an object')
    if 'inputs' not in data:
        return data,None,None
    if set(data)-{'inputs','model_config','solver_config','search'}:
        raise ValueError('Unknown analysis request field')
    return data['inputs'],data.get('model_config'),data.get('solver_config')


class Handler(BaseHTTPRequestHandler):
    def send_json(self,value,code=200):
        blob=json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf-8')
        self.send_response(code)
        if self.headers.get('Origin') in ('http://localhost:3981','http://127.0.0.1:3981'):
            self.send_header('Access-Control-Allow-Origin',self.headers['Origin'])
            self.send_header('Vary','Origin')
        self.send_header('Access-Control-Allow-Headers','Content-Type')
        self.send_header('Access-Control-Allow-Methods','GET,POST,OPTIONS')
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(blob)))
        self.end_headers()
        try: self.wfile.write(blob)
        except (BrokenPipeError,ConnectionResetError): pass

    def do_OPTIONS(self):
        self.send_json({})

    def do_GET(self):
        if self.path=='/health':
            self.send_json({'service':'bwb-flow-demo','version':'review-v2','status':'ready'})
        elif self.path=='/defaults':
            schema=config_schema()
            self.send_json({'inputs':DEFAULTS,'bounds':BOUNDS,'schema':schema,
                            'model_config':ModelConfig().snapshot(),'solver_config':SolverConfig().snapshot(),
                            'modules':schema['modules'],'optimization_defaults':OPTIMIZATION_DEFAULTS})
        elif self.path=='/models':
            self.send_json({'models':[model_metadata(geometry(DEFAULTS)),*model_catalog()],
                            'mit_example':MIT_EXAMPLE,'mit_input_schema':MIT_INPUT_SCHEMA})
        elif self.path=='/uq/status':
            self.send_json(evaluate_uq())
        elif self.path.startswith('/analyses/'):
            identifier=self.path.removeprefix('/analyses/')
            with LOCK: result=ANALYSES.get(identifier)
            self.send_json(result if result else {'error':'analysis_not_in_current_session'},200 if result else 404)
        else:
            self.send_json({'error':'not_found'},404)

    def do_POST(self):
        if self.path not in ('/analyze','/optimize','/coefficients','/uq/evaluate'):
            return self.send_json({'error':'not_found'},404)
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<2_000_000:
                return self.send_json({'error':'invalid_length'},400)
            data=json.loads(self.rfile.read(length))
            if self.path=='/coefficients':
                result=predict_mit(data)
            elif self.path=='/uq/evaluate':
                if not isinstance(data,dict) or set(data)-{'manifest','reference','predictions'}:
                    raise ValueError('Invalid offline evaluation request')
                result=evaluate_uq(**data)
            else:
                inputs,config,numerics=unpack(data)
                if self.path=='/analyze':
                    if 'search' in data:
                        raise ValueError('search settings are only accepted by /optimize')
                    result=remember(analyze(inputs,model_config=config,solver_config=numerics))
                else:
                    result=optimize(inputs,model_config=config,solver_config=numerics,search=data.get('search'),
                                    on_evaluation=lambda record,analysis:remember(analysis))
            self.send_json(result)
        except (ValueError,TypeError) as exc:
            self.send_json({'error':str(exc)},400)
        except Exception as exc:
            print(type(exc).__name__,str(exc),file=sys.stderr,flush=True)
            self.send_json({'error':'calculation_error','type':type(exc).__name__},500)


if __name__=='__main__':
    print('BWB review v2 API: http://127.0.0.1:8842',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8842),Handler).serve_forever()
