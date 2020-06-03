from setuptools import setup, find_packages

PACKAGE = 'pyfx'

if __name__ == '__main__':
    setup(name=PACKAGE,
          version='0.0.1',
          author='tetocode',
          author_email='',
          maintainer='',
          maintainer_email='',
          url='',
          description='',
          long_description='',
          download_url='',
          classifiers=('Intended Audience :: Developers',
                       'License :: OSI Approved :: MIT License',
                       'Operating System :: OS Independent',
                       'Programming Language :: Python :: 3',),
          platforms='any',
          license='MIT',
          packages=[PACKAGE],
          package_dir={PACKAGE: PACKAGE},
          #package=find_packages(exclude=('tests', 'docs')),# {PACKAGE: '.'},
          install_requires=['gevent', 'gsocketpool', 'mprpc', 'pytz', 'python-dateutil'])
