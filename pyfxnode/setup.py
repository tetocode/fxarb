from setuptools import setup, find_packages

PACKAGE = 'pyfxnode'

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
                       'Programming Language :: Python :: 3.6.1',),
          platforms='any',
          license='MIT',
          package=find_packages(exclude=('tests', 'docs')),
          install_requires=[
              'docopt',
              'h5py',
              'keras',
              'lxml',
              'mitmproxy', 'msgpack-python',
              'numpy',
              'pillow', 'pyautogui', 'python-dateutil', 'pytz', 'pyyaml',
              'socketpool',
              'tensorflow',
          ],
          extras_require={
              'posix': ['ewmh'],
          },
          )
