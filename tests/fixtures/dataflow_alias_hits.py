# Fixed-syntax fixture: dangerous sinks reached through aliases.
# Every call below must be reported with its full data-flow path.

import subprocess


def direct_alias():
    sp = subprocess.Popen
    sp("ls", shell=True)


def nested_attribute_alias():
    import subprocess as s

    popen = s.Popen
    popen("ls", shell=True)


def keyword_value_alias():
    flag = True
    subprocess.Popen("ls", shell=flag)


def module_constant_alias():
    import ssl
    import urllib3

    cert = ssl.CERT_NONE
    urllib3.PoolManager(cert_reqs=cert)
