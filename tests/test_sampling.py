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
