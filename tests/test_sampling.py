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
