"""Short-lived hidden backup packer; return only an opaque result location."""
import argparse
import json
from pathlib import Path
from agent.backup_snapshot import create_package
from agent.backup_crypto import CryptoError
from agent.backup_policy import PolicyError
from contracts.state_files import read_json

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--state',required=True)
    args=parser.parse_args();state=Path(args.state).absolute()
    try:
        settings=read_json(state/'backup-settings.json')
        package,summary=create_package(settings['roots'],state/'backup-work/outgoing',state/'backup-work/scratch',settings['openssl'],settings['recipientCertificate'])
    except (OSError,ValueError,KeyError,TypeError,CryptoError,PolicyError):
        raise SystemExit('Metadata backup packing failed; no private details logged') from None
    print(json.dumps({'directory':str(package.absolute()),'packageId':summary['packageId']}))
if __name__=='__main__':main()
