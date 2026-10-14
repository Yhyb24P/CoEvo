"""Transport-only Pi fixture: validates settings sent, not model capability."""
import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from tests.test_project_tools import PI_ENTRY


@unittest.skipUnless(PI_ENTRY.exists(),'Pinned Pi required')
class SamplingTests(unittest.TestCase):
    def test_exhausted_wall_quota_stops_before_actual_http(self):
        captured=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):captured.append(True);self.send_response(500);self.end_headers()
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);(root/'workspace').mkdir()
                request={'workspace':str(root/'workspace'),'run_dir':str(root/'run'),'pi_entry':str(PI_ENTRY.resolve()),
                         'endpoint':f'http://127.0.0.1:{server.server_port}/v1','model':'fixture','context_tokens':4096,
                         'prompts':['No remaining quota.'],'system_prompt':'Fixture.','timeout_ms':0,
                         'max_tool_calls':1,'sandbox_prefix':['unused'],'capture_payload':True}
                p=root/'request.json';p.write_text(json.dumps(request))
                proc=subprocess.run(['node','scripts/pi-project-agent.mjs'],env={**os.environ,'COEVO_REQUEST_FILE':str(p)},capture_output=True,text=True,timeout=25)
                self.assertNotEqual(proc.returncode,0)
                self.assertFalse(captured)
                trace=json.loads((root/'run/transcript.json').read_text())
                self.assertIn('COEVO_WALL_TIMEOUT_STOP',trace['messages'][-1]['errorMessage'])
                self.assertEqual(trace['resource_stop']['reason'],'wall_timeout')
        finally:server.shutdown();server.server_close()

    def test_qwen_thinking_round_trips_provider_reasoning_and_tool_results(self):
        captured=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                captured.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
                if len(captured)==1:
                    chunks=[({'role':'assistant','reasoning':'VISIBLE_PROVIDER_REASONING_FIXTURE'},None),
                            ({'tool_calls':[{'index':0,'id':'thinking-tool','type':'function','function':{'name':'write','arguments':json.dumps({'path':'copy.txt','content':'fixture'})}}]},None),({},'tool_calls')]
                else:chunks=[({'role':'assistant','content':'fixture-done'},None),({},'stop')]
                for delta,stop in chunks:
                    body={'id':'transport-fixture','object':'chat.completion.chunk','created':0,'model':'fixture','choices':[{'index':0,'delta':delta,'finish_reason':stop}]}
                    self.wfile.write(('data: '+json.dumps(body)+'\n\n').encode())
                self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);(root/'workspace').mkdir()
                request={'workspace':str(root/'workspace'),'run_dir':str(root/'run'),'pi_entry':str(PI_ENTRY.resolve()),
                         'endpoint':f'http://127.0.0.1:{server.server_port}/v1','model':'fixture','context_tokens':4096,
                         'enable_thinking':True,'prompts':['Transport fixture.'],'system_prompt':'Fixture.',
                         'timeout_ms':15000,'max_tool_calls':1,'sandbox_prefix':['unused'],
                         'capture_payload':True,'sampling':{'temperature':0.6,'top_p':0.95,'top_k':20,'seed':17}}
                p=root/'request.json';p.write_text(json.dumps(request))
                proc=subprocess.run(['node','scripts/pi-project-agent.mjs'],env={**os.environ,'COEVO_REQUEST_FILE':str(p)},capture_output=True,text=True,timeout=25)
                self.assertEqual(proc.returncode,0,proc.stderr)
                self.assertEqual(len(captured),2)
                self.assertTrue(captured[0]['chat_template_kwargs']['enable_thinking'])
                self.assertNotIn('reasoning_effort',captured[0])
                self.assertEqual(captured[0]['top_k'],20)
                assistant=next(m for m in captured[1]['messages'] if m['role']=='assistant')
                self.assertEqual(assistant['reasoning'],'VISIBLE_PROVIDER_REASONING_FIXTURE')
                self.assertEqual((root/'workspace/copy.txt').read_text(),'fixture')
        finally:server.shutdown();server.server_close()

    def test_payload_preview_stops_before_http_and_is_not_a_model_response(self):
        captured=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                captured.append(True);self.send_response(500);self.end_headers()
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);(root/'workspace').mkdir()
                request={'workspace':str(root/'workspace'),'run_dir':str(root/'run'),'pi_entry':str(PI_ENTRY.resolve()),
                    'endpoint':f'http://127.0.0.1:{server.server_port}/v1','model':'fixture','context_tokens':4096,
                    'prompts':['Preview only.'],'system_prompt':'Transport fixture.', 'timeout_ms':15000,
                    'max_tool_calls':1,'sandbox_prefix':['unused'],'preview_only':True,'sampling':{'temperature':0,'seed':17}}
                p=root/'request.json';p.write_text(json.dumps(request))
                proc=subprocess.run(['node','scripts/pi-project-agent.mjs'],env={**os.environ,'COEVO_REQUEST_FILE':str(p)},capture_output=True,text=True,timeout=25)
                self.assertNotEqual(proc.returncode,0)
                self.assertFalse(captured)
                payload=json.loads((root/'run/payloads.jsonl').read_text().splitlines()[0])
                self.assertEqual(payload['messages'][-1]['content'],[{'type':'text','text':'Preview only.'}])
                trace=json.loads((root/'run/transcript.json').read_text())
                self.assertIn('COEVO_PAYLOAD_PREVIEW_ONLY',trace['messages'][-1]['errorMessage'])
        finally:server.shutdown();server.server_close()

    def test_controlled_sampling_reaches_actual_http_payload(self):
        captured=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                captured.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
                for delta,stop in [({'role':'assistant','content':'ok'},None),({},'stop')]:
                    body={'id':'transport-fixture','object':'chat.completion.chunk','created':0,'model':'fixture','choices':[{'index':0,'delta':delta,'finish_reason':stop}]}
                    self.wfile.write(('data: '+json.dumps(body)+'\n\n').encode())
                self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);(root/'workspace').mkdir()
                request={'workspace':str(root/'workspace'),'run_dir':str(root/'run'),'pi_entry':str(PI_ENTRY.resolve()),
                         'endpoint':f'http://127.0.0.1:{server.server_port}/v1','model':'fixture','context_tokens':4096,
                         'prompts':['Respond briefly.'],'system_prompt':'Transport fixture, not a task result.',
                         'timeout_ms':15000,'max_tool_calls':1,'sandbox_prefix':['unused'],
                         'sampling':{'temperature':0,'seed':17}}
                (root/'request.json').write_text(json.dumps(request))
                result=subprocess.run(['node','scripts/pi-project-agent.mjs'],env={**os.environ,'COEVO_REQUEST_FILE':str(root/'request.json')},capture_output=True,text=True,timeout=25)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(len(captured),1)
                self.assertEqual(captured[0]['temperature'],0)
                self.assertEqual(captured[0]['seed'],17)
        finally:
            server.shutdown();server.server_close()
