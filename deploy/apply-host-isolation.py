#!/usr/bin/python3
# ruff: noqa: E501, S603 - fixed-argv operator script run as root by rag-isolation.service
"""Atomically replace only the portfolio isolation table."""
import subprocess
from pathlib import Path

NFT='/usr/sbin/nft'
if subprocess.run([NFT,'list','table','inet','rag_isolation'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
    subprocess.run([NFT,'add','table','inet','rag_isolation'],check=True)
rules='delete table inet rag_isolation\n'+Path('/etc/rag-isolation.nft').read_text()
subprocess.run([NFT,'--check','--file','-'],input=rules,text=True,check=True)
subprocess.run([NFT,'--file','-'],input=rules,text=True,check=True)
