# Fixed-syntax fixture: legal, clean code that must never be reported.

import subprocess


def safe_popen():
    subprocess.Popen("ls")


def safe_shell_false():
    subprocess.Popen("ls", shell=False)


def safe_verify():
    import requests

    requests.get("https://example.com", verify=True)


def safe_cert_required():
    import ssl
    import urllib3

    urllib3.PoolManager(cert_reqs=ssl.CERT_REQUIRED)
