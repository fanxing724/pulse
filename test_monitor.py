import importlib
import ipaddress
import os
import socket
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import json


class TargetSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        import hashlib
        salt='00'*16
        (root/'config.json').write_text(json.dumps({'password_salt':salt,'password_hash':hashlib.pbkdf2_hmac('sha256',b'admin',bytes.fromhex(salt),200000).hex(),'must_change_password':True}))
        os.environ['PULSE_CONFIG'] = str(root/'config.json')
        os.environ['PULSE_STATE'] = str(root/'state')
        cls.app = importlib.import_module('server')
        cls.app.initialize()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def addresses(self, *ips):
        return [(socket.AF_INET6 if ':' in ip else socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,443)) for ip in ips]

    def test_rejects_private_and_mixed_dns(self):
        for ips in [('127.0.0.1',),('169.254.169.254',),('10.0.0.1',),('::1',),('::ffff:127.0.0.1',),('1.1.1.1','192.168.1.1')]:
            with self.subTest(ips=ips), patch.object(socket,'getaddrinfo',return_value=self.addresses(*ips)):
                with self.assertRaises(ValueError):self.app.validated_url('https://example.com')

    def test_rejects_credentials_ports_and_bad_protocols(self):
        for url in ['file:///etc/passwd','http://user:password@example.com','https://example.com:8443','https://example.com/\nabc']:
            with self.subTest(url=url),self.assertRaises(ValueError):self.app.validated_url(url)

    def test_pins_validated_address(self):
        addresses=self.addresses('1.1.1.1')
        with patch.object(socket,'getaddrinfo',return_value=addresses):
            p,host,result=self.app.validated_url('https://example.com/path')
        self.assertEqual(host,'example.com');self.assertEqual(result,addresses)

    def test_password_verification_and_persistence(self):
        a=self.app
        original=a.credentials()
        self.assertTrue(a.password_matches('admin',original))
        self.assertFalse(a.password_matches('wrong',original))
        self.assertTrue(original['must_change'])
        # Re-initialization must not overwrite the current password with the seed.
        with a.connection() as c:c.execute('UPDATE admin_credentials SET must_change=0 WHERE id=1')
        a.initialize()
        self.assertFalse(a.credentials()['must_change'])
        with a.connection() as c:c.execute('UPDATE admin_credentials SET must_change=1 WHERE id=1')

    def test_redirect_cannot_reach_private_network(self):
        from unittest.mock import MagicMock
        response=MagicMock();response.status=302;response.getheader.return_value='http://127.0.0.1/'
        conn=MagicMock();conn.getresponse.return_value=response
        with patch.object(socket,'getaddrinfo',side_effect=[self.addresses('1.1.1.1'),self.addresses('127.0.0.1')]),patch.object(socket,'socket'),patch.object(self.app.http.client,'HTTPConnection',return_value=conn):
            with self.assertRaises(ValueError):self.app.request_target('http://example.com/')
        self.assertEqual(conn.request.call_count,1)

    def test_real_aggregates_and_cascade_delete(self):
        import time
        a=self.app
        with a.connection() as c:
            c.execute("INSERT INTO sites(id,name,url,interval,category) VALUES('test','test','https://example.com',5,'test')")
            for status in ['online','error']:
                c.execute("INSERT INTO checks(site_id,checked_at,response,code,status,error) VALUES('test',?,100,200,?,'')",(time.time(),status))
        state=a.snapshot()
        self.assertEqual(state['sites'][0]['uptime'],50)
        self.assertEqual(len(state['history']),2)
        self.assertEqual(state['trend'][0]['uptime'],50)
        with a.connection() as c:c.execute("DELETE FROM sites WHERE id='test'")
        a.CACHE['expires']=0
        self.assertEqual(a.snapshot()['history'],[])


if __name__=='__main__':unittest.main()
