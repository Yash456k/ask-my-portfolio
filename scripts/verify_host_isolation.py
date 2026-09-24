#!/usr/bin/env python3
"""Read-only production hardening assertions; no credentials printed."""
import json
import subprocess
import urllib.request


def run(*args):
    return subprocess.check_output(args,text=True)


def main():
    containers=json.loads(run('sudo','-n','docker','inspect','rag-playground-api','rag-playground-db','rag-playground-proxy'))
    for c in containers:
        h=c['HostConfig']
        assert c['State']['Running']
        assert h['ReadonlyRootfs'] and not h['Privileged']
        assert 'ALL' in h['CapDrop'] and not h.get('CapAdd')
        assert c['Config']['User'] not in ('','0','root')
        assert not any(m['Destination'].startswith('/home/yash/.hermes') or m['Destination']=='/var/run/docker.sock' for m in c['Mounts'])
    api=containers[0];env=dict(e.split('=',1) for e in api['Config']['Env'])
    assert env['DATABASE_BOOTSTRAP_SCHEMA']=='false'
    assert 'POSTGRES_PASSWORD' not in env and 'POSTGRES_USER' not in env
    assert env['TRUSTED_PROXY_CIDRS']=='172.18.0.4/32'
    assert all(not m['RW'] for m in api['Mounts'] if m['Destination'] in ['/models','/activity','/model-artifacts'])
    assert set(containers[1]['NetworkSettings']['Networks'])=={'rag-playground-db-private'}
    assert 'rag-playground-db-private' not in containers[2]['NetworkSettings']['Networks']
    print('PASS: all containers nonroot, readonly rootfs, zero capabilities; DB network and credential separation')
    for c in containers:
        for bindings in (c['HostConfig'].get('PortBindings') or {}).values():
            assert all(b['HostIp']=='127.0.0.1' for b in (bindings or []))
    for key in ['is-active','is-enabled']:
        assert run('sudo','-n','systemctl',key,'cloudflared-portfolio.service').strip() in ('active','enabled')
    assert run('sudo','-n','systemctl','show','cloudflared-portfolio.service','-p','Restart','--value').strip()=='always'
    firewall=run('sudo','-n','ufw','status')
    assert '80/tcp' not in firewall and '443/tcp' not in firewall
    check="import socket; s=socket.socket(); s.settimeout(1); assert s.connect_ex(('172.18.0.1',18081))!=0; s.close()"
    run('sudo','-n','docker','exec','rag-playground-api','python','-c',check)
    # Same-bridge TCP is possible, but only host-gateway requests may use the tunnel route.
    check="import http.client; c=http.client.HTTPConnection('172.18.0.4',8081,timeout=3); c.request('GET','/v1/config',headers={'Host':'api.yash456k.com','CF-Connecting-IP':'203.0.113.77'}); assert c.getresponse().status==404; c.close()"
    run('sudo','-n','docker','exec','rag-playground-api','python','-c',check)
    print('PASS: all published ports loopback-only; public firewall closed; tunnel enabled/restarting; container requests to the tunnel route are denied')

    probe='''import socket,os,psycopg,json
for host,port in [('172.18.0.1',22),('178.104.56.243',22),('100.79.43.0',443),('100.79.43.0',9120),('172.18.0.1',18814),('172.30.251.1',22),('169.254.169.254',80)]:
 s=socket.socket();s.settimeout(1)
 try:assert s.connect_ex((host,port))!=0,(host,port)
 finally:s.close()
print('PASS: public API cannot connect to host SSH, private HTTPS, dashboard, browser control or metadata listener')
c=psycopg.connect(os.environ['DATABASE_URL'],autocommit=True)
r=c.execute('SELECT current_user,rolsuper,rolcreaterole,rolcreatedb FROM pg_roles WHERE rolname=current_user').fetchone()
assert r==('rag_runtime',False,False,False),r
assert c.execute('SELECT count(*) FROM chunks').fetchone()[0]>0
for q in ['CREATE TABLE public.boundary_should_fail(id int)',"SELECT pg_read_file('/etc/passwd')",'UPDATE chunks SET title=title WHERE false']:
 try:c.execute(q)
 except psycopg.errors.InsufficientPrivilege:pass
 else:raise AssertionError('Excessive database privileges')
for path in ['/app/boundary_should_fail','/models/boundary_should_fail','/activity/boundary_should_fail']:
 try:open(path,'w')
 except OSError:pass
 else:raise AssertionError('Writable protected filesystem')
print('PASS: live runtime role works, forbidden SQL/filesystem writes fail')
for host in ['api.groq.com','openrouter.ai']:
 s=socket.create_connection((host,443),timeout=10);s.close()
print('PASS: required public HTTPS provider connections still work')
'''
    print(run('sudo','-n','docker','exec','rag-playground-api','python','-c',probe).strip())
    for target,port in [('172.18.0.1','22'),('100.79.43.0','443'),('172.30.251.2','5432')]:
        r=subprocess.run(['sudo','-n','docker','exec','rag-playground-proxy','nc','-z','-w','1',target,port],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        assert r.returncode!=0,(target,port)
    print('PASS: public proxy cannot connect to host/private HTTPS/database')
    assert run('sudo','-n','systemctl','is-active','rag-isolation.service').strip()=='active'
    assert run('sudo','-n','systemctl','is-enabled','rag-isolation.service').strip()=='enabled'
    for path in ['/v1/health','/v1/config','/v1/activity']:
        with urllib.request.urlopen(urllib.request.Request('https://api.yash456k.com'+path, headers={'User-Agent': 'portfolio-isolation-verifier/1.0'}),timeout=20) as r:
            assert r.status==200
            data=json.load(r)
            if path.endswith('health'):assert data['status']=='ok'
    with urllib.request.urlopen('https://www.yash456k.com',timeout=20) as r:assert r.status==200
    print('PASS: persistent firewall enabled; public website, health, config and activity endpoints return 200')


if __name__=='__main__':main()
