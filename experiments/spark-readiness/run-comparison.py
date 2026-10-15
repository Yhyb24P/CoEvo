import argparse,hashlib,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from coevo.complete_work import run
from coevo.rsi import Server
from coevo.runtime import write_json
parser=argparse.ArgumentParser(description='Run an explicitly prepared Spark/Qwen complete Office comparison.')
parser.add_argument('--out',required=True)
base=Path(parser.parse_args().out).resolve();root=ROOT
p=base/'comparison.json';m=json.loads(p.read_text())
if m['status']!='prepared':raise ValueError('Comparison already started; preserve previous evidence')
for arm in m['arms']:
 if hashlib.sha256((base/arm/'agent_request.json').read_bytes()).hexdigest()!=m['models'][arm]['request_sha256']:raise ValueError('Prepared request changed')
m.update(status='starting',started_at=time.time());write_json(p,m)
server=telemetry=None;results={}
try:
 with (base/'gpu-samples.csv').open('w') as gpu:
  telemetry=subprocess.Popen(['nvidia-smi','--query-gpu=timestamp,memory.used,utilization.gpu','--format=csv,noheader,nounits','-l','5'],stdout=gpu,stderr=subprocess.STDOUT)
 for arm in m['arms']:
  current=base/arm;m.update(status='starting-server',current_arm=arm);write_json(p,m)
  start=time.monotonic();server=Server(m['models'][arm]['config_path'],current/'server.log');loading=time.monotonic()-start
  m.update(status='running-task');write_json(p,m)
  result=run(current);results[arm]={'execution':result,'server_ready_seconds':loading}
  server.stop();server=None
  try:
   text=subprocess.check_output([str(root/'.cache/pilotdeck-office-env/bin/python'),str(root/'experiments/olympic-office/check.py'),'--workspace',str(current/'workspace')],text=True,timeout=120)
   verdict=json.loads(text);write_json(current/'file-verdict.json',verdict);results[arm]['file_checks_passed']=verdict['file_checks_passed']
  except Exception as e:results[arm]['file_check_error']=repr(e)
  write_json(base/'results.json',results)
  print(json.dumps({'arm':arm,'load_seconds':loading,'seconds':result['wall_seconds'],'calls':result['tool_calls'],'completion':result['completion'],'file_checks_passed':results[arm].get('file_checks_passed')}),flush=True)
 m.update(status='completed',ended_at=time.time());write_json(p,m)
except BaseException as e:
 m.update(status='failed',error=repr(e),ended_at=time.time());write_json(p,m);raise
finally:
 if server:server.stop()
 if telemetry:
  telemetry.terminate()
  try:telemetry.wait(timeout=5)
  except subprocess.TimeoutExpired:telemetry.kill();telemetry.wait()
