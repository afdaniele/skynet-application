import sys

from setuptools import setup


def get_version(filename):
    import ast
    version = None
    with open(filename) as f:
        for line in f:
            if line.startswith('__version__'):
                version = ast.parse(line).body[0].value.s
                break
        else:
            raise ValueError('No version found in %r.' % filename)
    if version is None:
        raise ValueError(filename)
    return version


if sys.version_info < (3, 8):
    msg = 'skynet works with Python 3.8 and later.\nDetected %s.' % str(sys.version)
    sys.exit(msg)

lib_version = get_version(filename='skynet/application/__init__.py')

setup(
    name='skynet-application',
    packages=[
        "skynet.application"
    ],
    version=lib_version,
    description='Skynet - Node',
    author='Andrea F. Daniele',
    author_email='afdaniele@ttic.edu',
    url='https://github.com/afdaniele/skynet',
    zip_safe=False,
    include_package_data=True,
    keywords=['skynet'],
    install_requires=[
        "requests~=2.27.1",
        "termcolor~=1.1.0",
        "urllib3~=1.26.8",
        "pyzmq~=22.3.0",
        "cbor2~=5.4.2.post1",
    ],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
    ],
)
