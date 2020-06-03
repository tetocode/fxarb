from setuptools import setup

if __name__ == '__main__':
    setup(name='timeutil',
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
                       'Intended Audience :: System Administrators',
                       'License :: OSI Approved :: MIT License',
                       'Operating System :: OS Independent',
                       'Programming Language :: Python :: 3',),
          platforms='any',
          license='MIT',
          packages=['timeutil'],
          package_dir={'timeutil': '.'},
          install_requires=('pytz', 'python-dateutil'), )
