#!/usr/bin/env python

from distutils.core import setup
from babel.messages import frontend as babel

setup(name='Clashogram',
      version='1.0',
      description='Clash of Clans war moniting for telegram channels.',
      author='Mehdi Sadeghi',
      author_email='mehdi@mehdix.org',
      url='https://github.com/mehdisadeghi/clashogram',
      py_modules=['clashogram'],
      scripts=['clashogram.py'],
      license='MIT',
      platforms='any',
      cmdclass={'compile_catalog': babel.compile_catalog,
                'extract_messages': babel.extract_messages,
                'init_catalog': babel.init_catalog,
                'update_catalog': babel.update_catalog},
      classifiers=['Development Status :: 4 - Beta',
                   'Environment :: Console',
                   'Intended Audience :: End Users/Desktop',
                   'License :: OSI Approved :: MIT License',
                   'Natural Language :: Persian',
                   'Natural Language :: English',
                   'Topic :: Games/Entertainment'
                   'Programming Language :: Python :: 3',
                   'Programming Language :: Python :: 3.1',
                   'Programming Language :: Python :: 3.2',
                   'Programming Language :: Python :: 3.3',
                   'Programming Language :: Python :: 3.4',
                   'Programming Language :: Python :: 3.5',
                   'Programming Language :: Python :: 3.6']
     )
