import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from experiment_lab.acp import Client, AuthenticationRequired

class AuthTest(unittest.IsolatedAsyncioTestCase):
    async def test_bare_acp_auth_is_actionable_and_never_retries_or_copies_raw_error(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)
            script=path / "agent.py"
            script.write_text("""import json,sys
for line in sys.stdin:
 r=json.loads(line)
 assert r['method'] in ('initialize','session/new')
 result={'protocolVersion':1,'authMethods':[{'id':'login','name':'Browser login','url':'https://private.invalid/token'}]} if r['method']=='initialize' else None
 print(json.dumps({'jsonrpc':'2.0','id':r['id'],**({'result':result} if result else {'error':{'code':-32000,'message':'DO NOT DISPLAY SECRET'}})}),flush=True)
""")
            events=[]
            client=Client({'command':[sys.executable,str(script)],'cwd':temp},lambda kind,**data:events.append({'kind':kind,**data}))
            try:
                await client.start()
                with self.assertRaises(AuthenticationRequired) as error:
                    await client.open_session()
                self.assertIn('same service account',str(error.exception))
                self.assertNotIn('SECRET',str(error.exception))
                auth=events[0]['authentication']
                self.assertEqual(auth['methods'][0]['name'],'Browser login')
                self.assertNotIn('private.invalid',json.dumps(events))
                self.assertEqual(events[-1]['kind'],'agent_sign_in_required')
            finally: await client.close()
