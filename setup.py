from setuptools import setup


setup(name='Clashogram',
      version='0.3.0',
      description='Clash of Clans war moniting for telegram channels.',
      long_description=open('README.rst', encoding='utf-8').read(),
      author='Mehdi Sadeghi',
      author_email='mehdi@mehdix.org',
      url='https://github.com/mehdisadeghi/clashogram',
      py_modules=['clashogram'],
      scripts=['clashogram.py'],
      entry_points={
        'console_scripts': ['clashogram=clashogram:main']
      },
      license='MIT',
      platforms='any',
      install_requires=['babel',
                        'requests',
                        'jdatetime',
                        'pytz',
                        'python-dateutil',
                        'click'],
      keywords=['games', 'telegram', 'coc', 'notification', 'clash of clans'],
      classifiers=['Development Status :: 4 - Beta',
                   'Environment :: Console',
                   'Intended Audience :: End Users/Desktop',
                   'License :: OSI Approved :: MIT License',
                   'Natural Language :: Persian',
                   'Natural Language :: English',
                   'Programming Language :: Python :: 3.5',
                   'Programming Language :: Python :: 3.6'])
