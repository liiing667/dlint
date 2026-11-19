# Fixed-syntax fixture: values that cannot be resolved statically must keep
# an explicit unknown/dynamic state and must NOT produce findings.

import subprocess


def indirect_call():
    def get_popen_factory():
        raise NotImplementedError

    factory = get_popen_factory()
    factory("ls", shell=True)


def dynamic_keyword(options):
    subprocess.Popen("ls", **options)


def parameter_value(flag):
    subprocess.Popen("ls", shell=flag)


def subscript_value(config):
    subprocess.Popen("ls", shell=config["shell"])
