"""Run from a daily systemd timer; images are never included in DB backups."""
import argparse
import json
import logging
from cloud.link_evidence import Evidence


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',default='/srv/ops-console/link-evidence')
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    store=Evidence(args.root)
    store.cleanup()
    print(json.dumps(store.backup()))


if __name__=='__main__':main()
