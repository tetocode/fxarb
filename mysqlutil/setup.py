# -*- coding: utf-8 -*-
from __future__ import division, print_function, absolute_import, unicode_literals

from setuptools import setup

if __name__ == '__main__':
    setup(name='mysqlutil',
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
          packages=['mysqlutil'],
          package_dir={'mysqlutil': '.'},
          install_requires=('pymysql',), )
