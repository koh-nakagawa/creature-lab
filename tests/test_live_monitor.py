"""Monitor stages and Mac-only endpoint protection, without any printer I/O."""
from pathlib import Path
import sys,time,unittest,threading,urllib.request,urllib.error,json
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server,workshop

class MonitorTests(unittest.TestCase):
    def test_selection_and_latest_preview_are_reported(self):
        s=workshop.Session('b'*20);s.last_preview_job_id='p';s.client_ip='192.0.2.200';s.last_seen_at=time.time()
        s.choose(0,'body','turtle');s.activity=[{'at':time.time(),'action':'choose','key':'body','value':'turtle'}]
        model={'stl_url':'/actual.stl','config':dict(s.config)}
        with patch.object(server,'WORKSHOPS',{s.id:s}),patch.object(server,'JOBS',{'p':{'status':'done','result':model}}),patch.object(server.studio_handoff,'items',return_value=[]):
            value=server.workshop_monitor()[0]
        self.assertEqual(value['stage'],'selecting');self.assertEqual(value['config']['body'],'turtle')
        self.assertEqual(value['preview_url'],'/actual.stl');self.assertFalse(value['model_ready'])
        self.assertEqual(value['activity'][-1]['value'],'turtle')
    def test_model_ready_and_operator_mark_are_distinct_from_print_start(self):
        s=workshop.Session('c'*20,now=time.time()-400);s.state();s.prepare_job_id='prepared'
        model={'stl_url':'/finished.stl','config':dict(s.config)}
        result={'model':model,'slice':{'id':'slice'}}
        with patch.object(server,'WORKSHOPS',{s.id:s}),patch.object(server,'JOBS',{'prepared':{'status':'done','result':result}}),patch.object(server.studio_handoff,'items',return_value=[{'id':'q','slice_id':'slice','status':'sent_by_operator'}]):
            value=server.workshop_monitor()[0]
        self.assertTrue(value['model_ready']);self.assertEqual(value['stage'],'sent_by_operator');self.assertNotIn('started',value)
    def test_remote_clients_cannot_view_monitor_or_open_mac_app(self):
        http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(http.server_port)
        try:
            with patch.object(server.Handler,'local',return_value=False),patch.object(server.studio_handoff,'open_studio') as open_app:
                for path,data in [('/api/studio/monitor',None),('/api/studio/queue/'+'d'*20+'/open',b'{}')]:
                    request=urllib.request.Request(base+path,data=data,headers={'Content-Type':'application/json'})
                    with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(request)
                    self.assertEqual(caught.exception.code,403)
                open_app.assert_not_called()
        finally:http.shutdown();http.server_close()

if __name__=='__main__':unittest.main(verbosity=2)
