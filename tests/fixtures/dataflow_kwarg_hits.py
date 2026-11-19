# Fixed-syntax fixture: dangerous keyword arguments delivered through
# dictionary unpacking and aliased keyword containers.

import subprocess


def unpacked_dict_literal():
    subprocess.Popen("ls", **{"shell": True})


def unpacked_dict_variable():
    options = {"shell": True}
    subprocess.Popen("ls", **options)


def aliased_verify_false():
    import requests

    insecure = False
    requests.get("https://example.com", verify=insecure)
