"""Activate a reviewed git-archive bundle as root; keep live data outside releases."""
import argparse
import json
import os
import pwd
import re
import shutil
import sqlite3
import subprocess
import tarfile
import time
from pathlib import Path


def run(*args):
    subprocess.run(args,check=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('archive',type=Path)
    p.add_argument('--commit',required=True)
    args=p.parse_args()
    if os.geteuid()!=0: p.error('run with sudo')
    if not re.fullmatch('[a-f0-9]{40}',args.commit): p.error('require a full git commit')
    base=Path('/opt/telescope-db')
    release=base/'releases'/args.commit
    release.parent.mkdir(parents=True,exist_ok=True)
    if release.exists(): raise RuntimeError('Release already exists; never overwrite a release')
    release.mkdir(mode=0o755)
    with tarfile.open(args.archive) as archive:
        for member in archive.getmembers():
            target=(release/member.name).resolve()
            if not target.is_relative_to(release.resolve()) or member.issym() or member.islnk():
                raise RuntimeError('Unsafe archive member')
        archive.extractall(release)
    for f in release.rglob('*'): f.chmod(0o755 if f.is_dir() else 0o644)
    try: account=pwd.getpwnam('telescope-db')
    except KeyError:
        run('useradd','--system','--home-dir','/var/lib/telescope-db','--no-create-home','--shell','/usr/sbin/nologin','telescope-db')
        account=pwd.getpwnam('telescope-db')
    data=Path('/var/lib/telescope-db');data.mkdir(mode=0o700,exist_ok=True)
    os.chown(data,account.pw_uid,account.pw_gid);data.chmod(0o700)
    python=base/'venv/bin/python'
    if not python.is_file(): raise RuntimeError('Create /opt/telescope-db/venv and install requirements first')
    os.chdir(release)
    # The full suite uses isolated synthetic databases, never live submissions.
    run(str(python),'-m','unittest','discover','-s',str(release/'tests'),'-v')
    current=base/'current'
    previous=current.resolve() if current.is_symlink() else None
    backup=Path('/var/backups/telescope-db')/time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
    backup.mkdir(mode=0o700,parents=True)
    caddy=Path('/etc/caddy/Caddyfile')
    if 'import /etc/caddy/telescope-db.caddy' not in caddy.read_text(encoding='utf-8').splitlines():
        raise RuntimeError('Install and validate the shared gateway route through vps-management first')
    active=False
    try:
        if previous:
            run('systemctl','stop','telescope-db')
            if (data/'catalog.db').is_file():
                source=sqlite3.connect(data/'catalog.db');dest=sqlite3.connect(backup/'catalog.db')
                try: source.backup(dest)
                finally: source.close();dest.close()
            if (data/'images').is_dir(): shutil.copytree(data/'images',backup/'images')
            if (data/'request-secret').is_file(): shutil.copy2(data/'request-secret',backup/'request-secret')
        link=base/'next';link.symlink_to(release,target_is_directory=True);link.replace(current)
        shutil.copy2(release/'deployment/telescope-db.service','/etc/systemd/system/telescope-db.service')
        run('systemctl','daemon-reload')
        run('systemctl','enable','--now','telescope-db')
        active=True
        run('curl','--fail','--retry','10','--retry-connrefused','--retry-delay','1','-H','Host: wyj.cangming.fyi','http://127.0.0.1:8092/api/health')
    except Exception:
        if previous:
            restore=base/'restore';restore.symlink_to(previous,target_is_directory=True);restore.replace(current)
            shutil.copy2(previous/'deployment/telescope-db.service','/etc/systemd/system/telescope-db.service')
            run('systemctl','daemon-reload');run('systemctl','restart','telescope-db')
        elif active: run('systemctl','stop','telescope-db')
        raise
    receipt={'commit':args.commit,'release':str(release),'previous':str(previous) if previous else None,'data':str(data),'backup':str(backup),'local_health':'passed','public_dns_tls':'verify separately'}
    (backup/'release.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt))


if __name__=='__main__': main()
