import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from agent.backup_crypto import CryptoError,create_recipient,encrypt,decrypt
from agent.backup_policy import PolicyError,Rule,inventory

class RealJunctionTests(unittest.TestCase):
    def test_directory_junction_cannot_expand_whitelist(self):
        with TemporaryDirectory() as folder,TemporaryDirectory() as outside:
            root=Path(folder); (Path(outside)/'state.json').write_text('{}')
            link=root/'linked'
            if os.name=='nt':
                import subprocess
                completed=subprocess.run(['cmd','/c','mklink','/J',str(link),outside],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
                self.assertEqual(0,completed.returncode)
            else: link.symlink_to(outside,target_is_directory=True)
            try:
                with self.assertRaises(PolicyError): inventory({'OPS':root},[Rule('OPS','linked/*.json')])
            finally:
                if os.name=='nt': link.rmdir()
                else: link.unlink()

class ExistingOpenSSLCryptoTests(unittest.TestCase):
    def test_real_authenticated_roundtrip_wrong_password_and_tamper_no_plaintext(self):
        executable=Path(os.environ.get('OPS_BACKUP_TEST_OPENSSL',r'C:\Program Files\Git\usr\bin\openssl.exe'))
        self.assertTrue(executable.is_file(),'Existing OpenSSL required; do not install into Dashboard venv')
        with TemporaryDirectory() as folder:
            root=Path(folder); source=root/'state.zip'
            source.write_bytes(b'\x00inert synthetic archive contents\xff'*100)
            password='synthetic-test-passphrase-not-a-live-credential'
            certificate,key=create_recipient(executable,root/'recovery',password)
            encrypted=root/'state.cms'; encrypt(executable,source,encrypted,certificate)
            self.assertNotIn(source.read_bytes()[:30],encrypted.read_bytes())
            restored=root/'restored.zip'; decrypt(executable,encrypted,restored,certificate,key,password)
            self.assertEqual(source.read_bytes(),restored.read_bytes())
            failed=root/'failed.zip'
            with self.assertRaises(CryptoError): decrypt(executable,encrypted,failed,certificate,key,'wrong-password')
            self.assertFalse(failed.exists())
            damaged=bytearray(encrypted.read_bytes()); damaged[-12]^=1
            corrupt=root/'corrupt.cms'; corrupt.write_bytes(damaged)
            with self.assertRaises(CryptoError): decrypt(executable,corrupt,failed,certificate,key,password)
            self.assertFalse(failed.exists())
            with self.assertRaises(CryptoError): encrypt(executable,source,encrypted,certificate)
            with self.assertRaises(FileExistsError): create_recipient(executable,root/'recovery',password)
