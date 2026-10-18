"""Use existing OpenSSL CMS authenticated encryption, never Python package installs."""
from pathlib import Path
import subprocess

class CryptoError(RuntimeError): pass

def invoke(executable,arguments,secret_input=None):
    # All process output stays private, including OpenSSL failure context.
    try:
        completed=subprocess.run([str(executable),*map(str,arguments)],
            input=secret_input,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except (OSError,subprocess.SubprocessError):
        raise CryptoError('Existing encryption tool unavailable; no package was installed') from None
    if completed.returncode: raise CryptoError('Encryption operation failed; details and credentials were not logged')
    return completed.stdout

def create_recipient(executable,directory,password):
    if not isinstance(password,str) or len(password)<16 or '\n' in password or '\r' in password:
        raise CryptoError('Recovery passphrase needs at least 16 characters, without newlines')
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=False)
    key=directory/'recovery-key.pem'; certificate=directory/'recipient.pem'
    secret=(password+'\n').encode('utf-8')
    try:
        invoke(executable,['genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:3072',
            '-aes-256-cbc','-pass','stdin','-out',key],secret)
        invoke(executable,['req','-new','-x509','-sha256','-days','3650','-key',key,
            '-passin','stdin','-subj','/CN=OpsBackupRecovery','-out',certificate],secret)
    except BaseException:
        # Keep any incomplete key material private; no silent key replacement.
        raise
    return certificate,key

def encrypt(executable,source,destination,certificate):
    destination=Path(destination)
    if destination.exists(): raise CryptoError('Ciphertext destination already exists')
    try:
        invoke(executable,['cms','-encrypt','-binary','-stream','-aes-256-gcm','-in',source,
            '-outform','DER','-out',destination,'-recip',certificate,
            '-keyopt','rsa_padding_mode:oaep','-keyopt','rsa_oaep_md:sha256'])
    except BaseException:
        destination.unlink(missing_ok=True)
        raise

def decrypt(executable,source,destination,certificate,private_key,password):
    destination=Path(destination)
    if destination.exists(): raise CryptoError('Restore destination already exists')
    try:
        invoke(executable,['cms','-decrypt','-binary','-inform','DER','-in',source,
            '-out',destination,'-recip',certificate,'-inkey',private_key,'-passin','stdin'],
            (password+'\n').encode('utf-8'))
    except BaseException:
        # GCM may write provisional plaintext before validating the tag.
        destination.unlink(missing_ok=True)
        raise
